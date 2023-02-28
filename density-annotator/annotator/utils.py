import os
from glob import glob
from pathlib import Path
from typing import List

import cv2
import numpy as np

from annotator.exceptions import LoadImageError, LoadVideoError, PathNotExistError
from annotator.logger import logger


def get_path_list(working_directory: Path, path: str) -> List:
    """
    Takes a file or directory path and creates a list of full paths.

    :param working_directory: current working directory.
        if input path provided full path, set an empty string.
    :param path: input path that file or directory
    :return: full path list
    """
    full_path = working_directory / path
    if os.path.isfile(full_path):
        path_list = [full_path]
    elif os.path.isdir(full_path):
        path_list = [current_path for current_path in glob(f"{full_path}/*")]
    else:
        message = f'path="{full_path}" is not exist.'
        logger.error(message)
        raise PathNotExistError(message)

    return path_list


def get_full_path_list(current_working_dirc: Path, relative_path_list: List):
    """
    Join the current working directory name and relative path to get a list of full paths.

    :param current_working_dirc: current working directory name
    :param relative_path_list: list of relative paths to be converted
    :return: List of converted full path
    """
    full_path_list = [str(current_working_dirc / path) for path in relative_path_list]
    return full_path_list


def get_input_data_type(path: str) -> str:
    """
    Get the extension from the input data path and get the data processing format.
    The target format is images or videos.

    :param path: file path to be annotated
    :return: processing format of annotator
    """
    data_type = "invalid"
    if os.path.isfile(path):
        _, ext = os.path.splitext(path)
        if ext in [".png", ".jpg", ".jpeg"]:
            data_type = "image"
        elif ext in [".mp4", ".mov"]:
            data_type = "video"

    logger.info(f"Input Data Type: {data_type}")

    return data_type


def load_image(path: str) -> np.array:
    """
    Loads image data from the input path and returns image in numpy array format.

    :param path: input image file path
    :return: loaded image
    """
    image = cv2.imread(path)
    if image is None:
        message = f'path="{path}" cannot read image file.'
        logger.error(message)
        raise LoadImageError(message)
    logger.info(f"Loaded Image: {path}")

    return image


def load_video(path: str) -> cv2.VideoCapture:
    """
    Loads video data from the input path and returns video in cv2.VideoCapture format.

    :param path: input video file path
    :return: loaded video
    """
    video = cv2.VideoCapture(path)
    if not (video.isOpened()):
        message = f'path="{path}" cannot read video file.'
        logger.error(message)
        raise LoadVideoError(message)
    logger.info(f"Loaded Video: {path}")

    return video


def save_image(path: str, image: np.array) -> None:
    """
    Save the image data in numpy format in the target path.

    :param path: save path of image
    :param image: target image
    :return: None
    """
    cv2.imwrite(path, image)
    logger.info(f"Saved Image: {path}")


def save_coordinate(path: str, coordinate: np.array) -> None:
    """
    Save the coordinate data (x, y) in numpy format in the target path.

    :param path: save path of coordinate
    :param coordinate: coordinate of annotated points
    :return: None
    """
    np.savetxt(path, coordinate, delimiter=",", fmt="%d")
    logger.info(f"Saved Coordinate: {path}")


def save_density_map(path: str, density_map: np.array) -> None:
    """
    Save the density map data in numpy format in the target path.

    :param path: save path of density map
    :param density_map: annotated density map
    :return: None
    """
    np.save(path, density_map)
    logger.info(f"Save Density Map: {path}")