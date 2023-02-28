import copy
import time
from typing import List

import hydra
import numpy as np
import pandas as pd
from detector.clustering import apply_clustering_to_density_map
from detector.constants import (
    CONFIG_DIR,
    DATA_DIR,
    GPU_DEVICE_ID,
    GPU_MEMORY_RATE,
    SEARCH_PARAMETER_CONFIG_NAME,
)
from detector.evaluate import eval_detection, eval_metrics, get_ground_truth
from detector.logger import logger
from detector.model import DensityModel, load_model
from detector.predict import predict_density_map
from detector.process_dataset import (
    apply_masking_on_image,
    get_masked_index,
    load_image,
    load_mask_image,
)
from omegaconf import DictConfig, OmegaConf
from tensorflow.compat.v1 import InteractiveSession
from tqdm import tqdm


class ParameterStore:
    def __init__(self, cols_order: List[str]) -> None:
        """Initialize ParameterStore class

        Args:
            cols_order (List[str]): define columns name and order to save
        """
        self.cols_order = cols_order
        self.result_dictlist = {key: [] for key in cols_order}
        (
            self.calculation_time_list,
            self.accuracy_list,
            self.precision_list,
            self.recall_list,
            self.f_measure_list,
        ) = ([], [], [], [], [])

    def init_per_image_metrics(self) -> None:
        """Initialize lists that store temporarily metrics value"""
        (
            self.calculation_time_list,
            self.accuracy_list,
            self.precision_list,
            self.recall_list,
            self.f_measure_list,
        ) = ([], [], [], [], [])

    def update_per_image_metrics(
        self,
        calculation_time: float,
        accuracy: float,
        precision: float,
        recall: float,
        f_measure: float,
    ) -> None:
        """Update lists that store temporarily metrics values

        Args:
            calculation_time (float): culculation time per image
            accuracy (float): accuracy per image
            precision (float): precision per image
            recall (float): recall per image
            f_measure (float): f-measure per image
        """
        self.calculation_time_list.append(calculation_time)
        self.accuracy_list.append(accuracy)
        self.precision_list.append(precision)
        self.recall_list.append(recall)
        self.f_measure_list.append(f_measure)

    def update_summury_metrics(
        self,
        key: str,
        summury_method: str,
        metrics_list: List[float],
        percentile_num: int,
    ) -> None:
        """Receive a list of metrics and summarize by mean or percentile.

        Args:
            key (str): dictionary key name
            summury_method (str): summry method name (mean of percentile)
            metrics_list (List[float]): summurized metrics list
            percentile_num (int): percentile number (ex: q1 -> 25)
        """
        if key not in self.result_dictlist.keys():
            return

        if summury_method == "mean":
            self.result_dictlist[key].append(np.mean(metrics_list))
        elif summury_method == "percentile":
            self.result_dictlist[key].append(
                np.percentile(metrics_list, percentile_num)
            )
        else:
            logger.info(f"Invalid summury method: {summury_method}")

    def store_percentile_results(self) -> None:
        """Calculate percentiles based on a list of each metric."""
        # calculate mean of metrics values
        # time metrics is only calculate mean value
        self.result_dictlist["calculation_time_per_image_mean"].append(
            np.mean(self.calculation_time_list)
        )
        self.update_summury_metrics("accuracy_mean", "mean", self.accuracy_list, None)
        self.update_summury_metrics("precision_mean", "mean", self.precision_list, None)
        self.update_summury_metrics("recall_mean", "mean", self.recall_list, None)
        self.update_summury_metrics("f_measure_mean", "mean", self.f_measure_list, None)

        # other metrics calculate 0%, 25%, 50%, 75%, 100% percentile
        str2num = {"min": 0, "q1": 25, "med": 50, "q3": 75, "max": 100}
        for percentile in str2num.keys():
            self.update_summury_metrics(
                f"accuracy_{percentile}",
                "percentile",
                self.accuracy_list,
                str2num[percentile],
            )
            self.update_summury_metrics(
                f"precision_{percentile}",
                "percentile",
                self.precision_list,
                str2num[percentile],
            )
            self.update_summury_metrics(
                f"recall_{percentile}",
                "percentile",
                self.recall_list,
                str2num[percentile],
            )
            self.update_summury_metrics(
                f"f_measure_{percentile}",
                "percentile",
                self.f_measure_list,
                str2num[percentile],
            )

    def save_results(self, save_path: str) -> None:
        """Save search result in "save_path".

        Args:
            save_path (str): save path of CSV file
        """
        results_df = pd.DataFrame(self.result_dictlist)[self.cols_order]
        results_df.to_csv(save_path, index=False)
        logger.info(f'Searched Result Saved in "{save_path}".')


def search(
    search_param: str,
    dataset_path_df: pd.DataFrame,
    patterns: List[float],
    mask_image: np.array,
    model: DensityModel,
    tf_session: InteractiveSession,
    cfg: DictConfig,
) -> None:
    """Validate multiple combinations of parameters and evaluate accuracy, precision, recall, f-measure.

    Args:
        search_param (str): search parameter name
        dataset_path_df (pd.DataFrame): DataFrame containing paths for input, label, and predicted density map
        patterns (List[float]): serach parameter patterns list
        mask_image (np.array): mask image
        model (DensityModel): trained density model
        tf_session (InteractiveSession): tensorflow session
        cfg (DictConfig): config about analysis image region
    """
    params_store = ParameterStore(cfg["cols_order"])
    for param in tqdm(patterns, desc=f"search {search_param} patterns"):
        # store parameter value
        params_store.result_dictlist["parameter"].append(param)
        params_store.result_dictlist["sample_number"].append(len(dataset_path_df))
        # initialized per image metrics
        params_store.init_per_image_metrics()
        for i in range(len(dataset_path_df)):
            # set timer
            start_time = time.time()

            if search_param == "threshold":
                # load predicted density map
                predicted_density_map = np.load(dataset_path_df["predicted"][i])
                # clustering by target threshold
                predicted_centroid_array = apply_clustering_to_density_map(
                    predicted_density_map, cfg["band_width"], param
                )
            elif search_param == "prediction_grid":
                # create current parameter config
                param_cfg = copy.deepcopy(cfg)
                param_cfg["skip_pixel_interval"] = param
                # Predicts a density map with the specified grid size
                image = load_image(dataset_path_df["input"][i], is_rgb=True)
                if mask_image is not None:
                    image = apply_masking_on_image(image, mask_image)
                predicted_density_map = predict_density_map(
                    model, tf_session, image, param_cfg
                )
                predicted_centroid_array = apply_clustering_to_density_map(
                    predicted_density_map,
                    param_cfg["band_width"],
                    param_cfg["fixed_cluster_thresh"],
                )
            else:
                logger.info(f"{param} is not defined.")
                return

            # load groud truth label
            ground_truth_array = get_ground_truth(
                dataset_path_df["label"][i], mask_image, cfg
            )

            # evaluate current frame
            true_pos, false_pos, false_neg, sample_number = eval_detection(
                predicted_centroid_array, ground_truth_array, cfg["detection_threshold"]
            )
            (
                accuracy_per_image,
                precision_per_image,
                recall_per_image,
                f_measure_per_image,
            ) = eval_metrics(true_pos, false_pos, false_neg, sample_number)

            # upadate metrics
            calculation_time = time.time() - start_time
            params_store.update_per_image_metrics(
                calculation_time,
                accuracy_per_image,
                precision_per_image,
                recall_per_image,
                f_measure_per_image,
            )

        # store current paramter percentile results
        params_store.store_percentile_results()

    # save search result
    save_path = (
        f"{str(DATA_DIR)}/{cfg['save_directory']}/search_result_{search_param}.csv"
    )
    params_store.save_results(save_path)


def search_parameter(
    dataset_path_df: pd.DataFrame,
    mask_image: np.array,
    model: DensityModel,
    tf_session: InteractiveSession,
    cfg: DictConfig,
):
    """Search for parameters that maximize accuracy. The search essentially uses a validation data set.
    The parameters that can be explored are "clustering threshold" and "prediction grid".

    Args:
        dataset_path_df (pd.DataFrame): DataFrame containing paths for input, label, and predicted density map
        mask_image (np.array): mask image
        model (DensityModel): trained density model
        tf_session (InteractiveSession): tensorflow session
        cfg (DictConfig): config about analysis image region
    """
    for param, patterns in cfg["search_params"].items():
        assert (
            type(patterns) == list
        ), "The search patterns are expected to be passed in a List type."
        logger.info(f"Search Parameter: {param}")
        logger.info(f"Search Patterns: {patterns}")

        search(param, dataset_path_df, patterns, mask_image, model, tf_session, cfg)
        logger.info(f"Completed: {param}")


@hydra.main(
    config_path=str(CONFIG_DIR),
    config_name=SEARCH_PARAMETER_CONFIG_NAME,
    version_base="1.1",
)
def main(cfg: DictConfig) -> None:
    cfg = OmegaConf.to_container(cfg)
    logger.info(f"Loaded config: {cfg}")

    # load input, label and predicted path list
    dataset_path_df = (
        pd.read_csv(cfg["dataset_path"])
        .sample(frac=cfg["sample_rate"])
        .reset_index(drop=True)
    )

    # load mask image
    if cfg["mask_path"] is not None:
        mask_image = load_mask_image(cfg["mask_path"])
        index_h, index_w = get_masked_index(mask_image, cfg)
        cfg["index_h"] = index_h
        cfg["index_w"] = index_w
    else:
        mask_image = None

    # load trained model
    if "prediction_grid" in cfg["search_params"].keys():
        model, tf_session = load_model(
            str(DATA_DIR / cfg["trained_model_directory"]),
            GPU_DEVICE_ID,
            GPU_MEMORY_RATE,
        )
    else:
        model, tf_session = None, None

    # search best parameter
    search_parameter(dataset_path_df, mask_image, model, tf_session, cfg)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(e)