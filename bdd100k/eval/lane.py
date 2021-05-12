"""Evaluation code for BDD100K lane marking.

************************************
Byte structure for lane marking:
+---+---+---+---+---+---+---+---+
| - | - | d | s | b | c | c | c |
+---+---+---+---+---+---+---+---+

d: direction
s: style
b: background
c: category

More details: bdd100k.label.label.py
************************************


Code adapted from:
https://github.com/fperazzi/davis/blob/master/python/lib/davis/measures/f_boundary.py

Source License

BSD 3-Clause License

Copyright (c) 2017,
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.s
############################################################################

Based on:
----------------------------------------------------------------------------
A Benchmark Dataset and Evaluation Methodology for Video Object Segmentation
Copyright (c) 2016 Federico Perazzi
Licensed under the BSD License [see LICENSE for details]
Written by Federico Perazzi
----------------------------------------------------------------------------
"""
from functools import partial
from multiprocessing import Pool
from typing import Callable, Dict, List

import cv2  # type: ignore
import numpy as np
from PIL import Image
from skimage.morphology import disk, skeletonize  # type: ignore
from tabulate import tabulate
from tqdm import tqdm

from ..common.utils import list_files
from ..label.label import lane_categories, lane_directions, lane_styles

AVG = "avg"
TOTAL = "total"


def get_lane_class(
    byte: np.ndarray, value: int, offset: int, width: int
) -> np.ndarray:
    """Extract the lane class given offset, width and value."""
    return (((byte >> offset) & ((1 << width) - 1)) == value).astype(np.bool)


def lane_class_func(
    offset: int, width: int
) -> Callable[[np.ndarray, int], np.ndarray]:
    """Get the function for extracting the specific lane class."""
    return partial(get_lane_class, offset=offset, width=width)


get_foreground = partial(get_lane_class, value=0, offset=3, width=1)
sub_task_funcs = dict(
    direction=lane_class_func(5, 1),
    style=lane_class_func(4, 1),
    category=lane_class_func(0, 3),
)
sub_task_cats: Dict[str, List[str]] = dict(
    direction=[label.name for label in lane_directions],
    style=[label.name for label in lane_styles],
    category=[label.name for label in lane_categories],
)


def eval_lane_per_cat(
    gt_mask: np.ndarray, pd_mask: np.ndarray, bound_ths: List[int]
) -> List[float]:
    """Compute mean,recall and decay from per-threshold evaluation."""
    gt_mask = skeletonize(gt_mask).astype(np.uint8)
    pd_mask = skeletonize(pd_mask).astype(np.uint8)

    # Area of the intersection
    n_gt = np.sum(gt_mask)
    n_pd = np.sum(pd_mask)

    if n_gt == 0 and n_pd == 0:
        return [1.0 for _ in bound_ths]
    if n_gt == 0 or n_pd == 0:
        return [0.0 for _ in bound_ths]

    f_scores: List[float] = []
    for bound_th in bound_ths:
        kernel = disk(bound_th)
        gt_dil = cv2.dilate(gt_mask, kernel)
        pd_dil = cv2.dilate(pd_mask, kernel)

        # Get the intersection
        gt_match = gt_mask * pd_dil
        pd_match = pd_mask * gt_dil

        precision = np.sum(pd_match) / float(n_pd)
        recall = np.sum(gt_match) / float(n_gt)

        if precision + recall == 0:
            f_score = 0.0
        else:
            f_score = 2.0 * precision * recall / (precision + recall)
        f_scores.append(f_score)

    return f_scores


def eval_lane_per_frame(
    gt_file: str, pred_file: str, bound_ths: List[int]
) -> Dict[str, np.ndarray]:
    """Compute mean,recall and decay from per-frame evaluation."""
    task2arr: Dict[str, np.ndarray] = dict()  # str -> 2d array, [cat, thres]
    gt_byte = np.asarray(Image.open(gt_file))
    pred_byte = np.asarray(Image.open(pred_file))

    for task_name, class_func in sub_task_funcs.items():
        task_scores: List[List[float]] = []
        for value in range(len(sub_task_cats[task_name])):
            gt_mask = class_func(gt_byte, value)
            pd_mask = class_func(pred_byte, value)
            cat_scores = eval_lane_per_cat(gt_mask, pd_mask, bound_ths)
            task_scores.append(cat_scores)
        task2arr[task_name] = np.array(task_scores)

    return task2arr


def merge_results(
    task2arr_list: List[Dict[str, np.ndarray]]
) -> Dict[str, np.ndarray]:
    """Merge F-score results from all images."""
    task2arr: Dict[str, np.ndarray] = {
        task_name: np.stack(
            [task2arr_img[task_name] for task2arr_img in task2arr_list]
        ).mean(axis=0)
        for task_name in sub_task_cats
    }

    for task_name, arr2d in task2arr.items():
        arr2d *= 100
        arr_mean = arr2d.mean(axis=0, keepdims=True)
        task2arr[task_name] = np.concatenate([arr_mean, arr2d], axis=0)

    avg_arr = np.stack([arr2d[-1] for arr2d in task2arr.values()])
    task2arr[TOTAL] = avg_arr.mean(axis=0, keepdims=True)

    return task2arr


def create_table(
    task2arr: Dict[str, np.ndarray],
    all_task_cats: Dict[str, List[str]],
    bound_ths: List[int],
) -> None:
    """Render the evaluation results."""
    table = []
    headers = ["task", "class"] + [str(th) for th in bound_ths]
    for task_name in sorted(sub_task_cats.keys()) + [TOTAL]:
        arr2d = task2arr[task_name]
        task_list, cat_list, num_strs = [], [], []
        for i, cat_name in enumerate(all_task_cats[task_name]):
            task_name_temp = task_name if i == arr2d.shape[0] // 2 else " "
            task_list.append("{}".format(task_name_temp))
            cat_list.append(cat_name.replace(" ", "_"))
        task_str = "\n".join(task_list)
        cat_str = "\n".join(cat_list)

        for j in range(len(bound_ths)):
            num_list = []
            for i in range(len(all_task_cats[task_name])):
                num_list.append("{:.1f}".format(arr2d[i, j]))
            num_str = "\n".join(num_list)
            num_strs.append(num_str)

        table.append([task_str, cat_str] + num_strs)

    print(tabulate(table, headers, tablefmt="grid", stralign="center"))


def render_results(
    task2arr: Dict[str, np.ndarray],
    all_task_cats: Dict[str, List[str]],
    bound_ths: List[int],
) -> Dict[str, float]:
    """Render the evaluation results."""
    f_score_dict: Dict[str, float] = dict()
    for task_name, arr2d in task2arr.items():
        for cat_name, arr1d in zip(all_task_cats[task_name], arr2d):
            for bound_th, f_score in zip(bound_ths, arr1d):
                f_score_dict[
                    "{}_{}_{}".format(
                        bound_th, task_name, cat_name.replace(" ", "_")
                    )
                ] = f_score
    f_score_dict["average"] = task2arr[TOTAL].mean()
    return f_score_dict


def evaluate_lane_marking(
    gt_dir: str, pred_dir: str, bound_ths: List[int], nproc: int = 4
) -> Dict[str, float]:
    """Evaluate F-score for lane marking from input folders."""
    bound_ths = sorted(set(bound_ths))
    for bound_th in bound_ths:
        assert bound_th >= 0

    gt_files = list_files(gt_dir, ".png", with_prefix=True)
    pred_files = list_files(pred_dir, ".png", with_prefix=True)

    with Pool(nproc) as pool:
        task2arr_list = pool.starmap(
            partial(eval_lane_per_frame, bound_ths=bound_ths),
            tqdm(zip(gt_files, pred_files), total=len(gt_files)),
            chunksize=10,
        )
    task2arr = merge_results(task2arr_list)

    all_task_cats = sub_task_cats.copy()
    for cats in all_task_cats.values():
        cats.append(AVG)
    all_task_cats.update({TOTAL: [AVG]})

    create_table(task2arr, all_task_cats, bound_ths)
    f_score_dict = render_results(task2arr, all_task_cats, bound_ths)
    return f_score_dict
