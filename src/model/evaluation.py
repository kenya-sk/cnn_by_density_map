#! /usr/bin/env python
#coding: utf-8

import numpy as np
import pandas as pd
import csv
from scipy import optimize

from cnn_util import get_masked_index, pretty_print


def get_ground_truth(ground_truth_path, mask_path=None):
    """
    plots the coordinates of answer label on the black image(all value 0) and
    creates a correct image for accuracy evaluation.

    input:
        ground_truth_path: coordinates of the estimated target (.csv)
        mask_path: enter path only when using mask image

    output:
        array showing the positon of target
    """

    ground_truth_arr = np.array(pd.read_csv(ground_truth_path))
    if mask_path is None:
        return ground_truth_arr
    else:
        valid_h, valid_w = get_masked_index(mask_path)
        valid_ground_truth_lst = []

        for i in range(ground_truth_arr.shape[0]):
            index_w = np.where(valid_w == ground_truth_arr[i][0])
            index_h = np.where(valid_h == ground_truth_arr[i][1])
            intersect = np.intersect1d(index_w, index_h)
            if len(intersect) == 1:
                valid_ground_truth_lst.append([valid_w[intersect[0]], valid_h[intersect[0]]])
            else:
                pass
        return np.array(valid_ground_truth_lst)


def evaluate(est_centroid_arr, ground_truth_arr, dist_treshold):
    """
    the distance between the estimation and groundtruth is less than distThreshold --> True

    input:
        est_centroid_arr: coordinates of the estimated target (.npy). array shape == original image shape
        ground_truth_arr: coordinates of the answer label (.csv)
        dist_treshold: it is set maximum value of kernel width

    output:
        accuracy per frame
    """

    # make distance matrix
    est_centroid_num = len(est_centroid_arr)
    ground_truth_num = len(ground_truth_arr)
    n = max(est_centroid_num, ground_truth_num)
    dist_matrix = np.zeros((n,n))
    for i in range(len(est_centroid_arr)):
        for j in range(len(ground_truth_arr)):
            dist_cord = est_centroid_arr[i] - ground_truth_arr[j]
            dist_matrix[i][j] = np.linalg.norm(dist_cord)

    # calculate by hangarian algorithm
    row, col = optimize.linear_sum_assignment(dist_matrix)
    indexes = []
    for i in range(n):
        indexes.append([row[i], col[i]])
    valid_index_length = min(len(est_centroid_arr), len(ground_truth_arr))
    valid_lst = [i for i in range(valid_index_length)]
    if len(est_centroid_arr) >= len(ground_truth_arr):
        match_indexes = list(filter((lambda index : index[1] in valid_lst), indexes))
    else:
        match_indexes = list(filter((lambda index : index[0] in valid_lst), indexes))

    true_positive = 0
    if est_centroid_num > ground_truth_num:
        false_positive = est_centroid_num - ground_truth_num
        false_negative = 0
    else:
        false_positive = 0
        false_negative = ground_truth_num - est_centroid_num
        
    for i in range(len(match_indexes)):
        pred_index = match_indexes[i][0]
        truth_index = match_indexes[i][1]
        if dist_matrix[pred_index][truth_index] <= dist_treshold:
            true_positive += 1
        else:
            false_positive += 1
            false_negative += 1
            
    accuracy = true_positive / n
    precision = true_positive / (true_positive+false_positive)
    recall = true_positive / (true_positive+false_negative)
    f_value = (2*recall*precision)/(recall+precision)
    
    print("******************************************")
    pretty_print(true_positive, false_positive, false_negative)
    print("\nAccuracy: {}".format(accuracy))
    print("Precision: {}".format(precision))
    print("Recall: {}".format(recall))
    print("F measure: {}".format(f_value))
    print("******************************************\n")

    return accuracy, precision, recall, f_value, true_positive, false_positive, false_negative


if __name__ == "__main__":
    # pred_centroid_dirc = "/data/sakka/estimation/model_201804151507/eval/"
    # ground_truth_dirc = "/data/sakka/cord/eval_image/"
    # mask_path = "/data/sakka/image/mask.png"
    # out_accuracy_dirc = "/data/sakka/estimation/test_image/model_201806142123/accuracy/"

    pred_centroid_dirc = "/Users/sakka/cnn_by_density_map/data/pred/eval_image/eval/"
    ground_truth_dirc = "/Users/sakka/cnn_by_density_map/data/cord/eval/"
    mask_path = "/Users/sakka/cnn_by_density_map/image/mask.png"
    out_accuracy_dirc = "/Users/sakka/cnn_by_density_map/data/acc/"

    band_width = 25
    skip_lst = [15]
    true_positive = 0
    false_positive = 0
    false_negative = 0
    for skip in skip_lst:
        accuracy_lst = []
        precision_lst = []
        recall_lst = []
        f_value_lst = []
        for file_num in range(1, 85):
            print("/Users/sakka/cnn_by_density_map/data/pred/eval_image/eval/{}.png".format(file_num))
            centroid_arr = np.loadtxt(pred_centroid_dirc+"{}.csv".format(file_num), delimiter=",")
            if centroid_arr.shape[0] == 0:
                print("Not found point of centroid\nAccuracy is 0.0")
                accuracy_lst.append(0.0)
                precision_lst.append(0.0)
                recall_lst.append(0.0)
                f_value_lst.append(0.0)
            else:
                ground_truth_arr = get_ground_truth(ground_truth_dirc + "{0}.csv".format(file_num), mask_path)
                accuracy, precision, recall, f_value, tp, fp, fn = evaluate(centroid_arr, ground_truth_arr, band_width)
                true_positive += tp
                false_positive += fp
                false_negative += fn
                accuracy_lst.append(accuracy)
                precision_lst.append(precision)
                recall_lst.append(recall)
                f_value_lst.append(f_value)

        print("\n**************************************************************")
        pretty_print(true_positive, false_positive, false_negative)
        print("\nToal Accuracy (data size {0}, sikp size {1}): {2}".format(len(accuracy_lst), skip, sum(accuracy_lst)/len(accuracy_lst)))
        print("Toal Precision (data size {0}, sikp size {1}): {2}".format(len(precision_lst), skip, sum(precision_lst)/len(precision_lst)))
        print("Toal Recall (data size {0}, sikp size {1}): {2}".format(len(recall_lst), skip, sum(recall_lst)/len(recall_lst)))
        print("Toal F measure (data size {0}, sikp size {1}): {2}".format(len(f_value_lst), skip, sum(f_value_lst)/len(f_value_lst)))
        print("****************************************************************")

        with open(out_accuracy_dirc + "{}/accuracy.csv".format(skip), "w") as f:
            writer = csv.writer(f)
            writer.writerow(accuracy_lst)
        print("SAVE: accuracy data")