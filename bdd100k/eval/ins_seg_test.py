"""Test cases for evaluation scripts."""
import json
import os
import unittest

import numpy as np
from PIL import Image

from ..common.utils import load_bdd100k_config
from .ins_seg import evaluate_ins_seg


class TestBDD100KInsSegEval(unittest.TestCase):
    """Test cases for BDD100K detection evaluation."""

    def test_ins_seg(self) -> None:
        """Check detection evaluation correctness."""
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        gt_base = "{}/testcases/ins_seg/gt".format(cur_dir)
        pred_base = "{}/testcases/ins_seg/pred".format(cur_dir)
        pred_json = "{}/testcases/ins_seg/pred.json".format(cur_dir)
        bdd100k_config = load_bdd100k_config("ins_seg")
        result = evaluate_ins_seg(
            gt_base, pred_base, pred_json, bdd100k_config.config
        )
        overall_reference = {
            "AP": 0.686056105610561,
            "AP_50": 0.8968646864686468,
            "AP_75": 0.6666666666666666,
            "AP_small": 0.686056105610561,
            "AR_max_1": 0.6583333333333333,
            "AR_max_10": 0.7083333333333334,
            "AR_max_100": 0.7083333333333334,
            "AR_small": 0.7083333333333334,
        }
        for key in overall_reference:
            self.assertAlmostEqual(result[key], overall_reference[key])


def create_test_file() -> None:
    """Creat mocking files for the InsSeg test case."""
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    gt_base = "{}/testcases/ins_seg/gt".format(cur_dir)
    dt_base = "{}/testcases/ins_seg/pred".format(cur_dir)
    dt_json = "{}/testcases/ins_seg/pred.json".format(cur_dir)

    if not os.path.isdir(gt_base):
        os.makedirs(gt_base)
        gt_mask = np.zeros((100, 100, 4), dtype=np.uint8)
        gt_mask[:10, :10] = np.array([1, 0, 0, 1], dtype=np.uint8)
        gt_mask[20:40, 10:20] = np.array([2, 0, 0, 2], dtype=np.uint8)
        gt_mask[20:40, 20:30] = np.array([3, 0, 0, 3], dtype=np.uint8)
        gt_mask[40:60, 10:30] = np.array([3, 0, 0, 4], dtype=np.uint8)
        gt_mask[40:60, 30:40] = np.array([3, 0, 0, 5], dtype=np.uint8)
        gt_mask[60:70, 50:60] = np.array([3, 0, 0, 6], dtype=np.uint8)
        Image.fromarray(gt_mask).save(os.path.join(gt_base, "a.png"))

    if not os.path.isdir(dt_base):
        os.makedirs(dt_base)
        dt_mask = np.zeros((100, 100, 4), dtype=np.uint8)
        dt_mask[:10, :10] = np.array([1, 0, 0, 1], dtype=np.uint8)
        dt_mask[20:40, 10:19] = np.array([2, 0, 0, 2], dtype=np.uint8)
        dt_mask[20:40, 20:27] = np.array([3, 0, 0, 4], dtype=np.uint8)
        dt_mask[40:60, 10:22] = np.array([3, 0, 0, 6], dtype=np.uint8)
        dt_mask[40:60, 30:35] = np.array([3, 0, 0, 7], dtype=np.uint8)
        dt_mask[60:70, 50:54] = np.array([3, 0, 0, 8], dtype=np.uint8)
        Image.fromarray(dt_mask).save(os.path.join(dt_base, "a.png"))

    if not os.path.isfile(dt_json):
        scores = [
            [1, 0.4],
            [2, 0.9],
            [3, 0.7],
            [4, 0.8],
            [6, 0.9],
            [7, 0.9],
            [8, 0.9],
            [9, 0.9],
        ]
        dt_pred = [
            {
                "name": "a.png",
                "labels": [
                    {
                        "index": item[0],
                        "score": item[1],
                    }
                    for item in scores
                ],
            }
        ]
        with open(dt_json, "w") as fp:
            json.dump(dt_pred, fp)


if __name__ == "__main__":
    unittest.main()
