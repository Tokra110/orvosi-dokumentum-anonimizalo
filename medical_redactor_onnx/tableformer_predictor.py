"""Torch-free port of docling-ibm-models' `TFPredictor`.

Faithful reimplementation of the upstream predictor around the ONNX
TableFormer runtime: identical image preprocessing (including upstream's
(C, W, H) transpose the model was trained with), identical bbox/tag sync
correction, and the full `CellMatcher` + `MatchingPostProcessor` stage
(vendored, pure numpy) that snaps predicted cells onto PDF text tokens.
Deviating from upstream here degrades table quality — see notes.md 2026-07-05.
"""

from __future__ import annotations

import json
from itertools import groupby
from pathlib import Path

import cv2
import numpy as np

from medical_redactor_onnx.tableformer_runtime import OrtTableFormer
from medical_redactor_onnx.vendor.matching_post_processor import MatchingPostProcessor
from medical_redactor_onnx.vendor.otsl import otsl_to_html
from medical_redactor_onnx.vendor.tf_cell_matcher import CellMatcher


def _otsl_sqr_chk(rs_list: list[str]) -> bool:
    # tf_predictor.py's local otsl_sqr_chk (not the otsl-module one)
    rs_list_split = [
        list(group) for k, group in groupby(rs_list, lambda x: x == "nl") if not k
    ]
    is_square = True
    if len(rs_list_split) > 0:
        init_tag_len = len(rs_list_split[0]) + 1
        for ln in rs_list_split:
            ln.append("nl")
            if len(ln) != init_tag_len:
                is_square = False
    return is_square


def _box_cxcywh_to_xyxy(coords: np.ndarray) -> list[list[float]]:
    out = np.empty_like(coords)
    out[:, 0] = coords[:, 0] - coords[:, 2] / 2
    out[:, 1] = coords[:, 1] - coords[:, 3] / 2
    out[:, 2] = coords[:, 0] + coords[:, 2] / 2
    out[:, 3] = coords[:, 1] + coords[:, 3] / 2
    return out.tolist()


class OrtTFPredictor:
    """Drop-in for the `TFPredictor` surface Docling's table stage uses."""

    def __init__(self, model_dir: Path):
        self.model_dir = Path(model_dir)
        self.config = json.loads((self.model_dir / "tm_config.json").read_text())
        self.model = OrtTableFormer(self.model_dir, self.config["predict"]["max_steps"])
        self._rev_word_map = {v: k for k, v in self.model.word_map.items()}
        self._cell_matcher = CellMatcher(self.config)
        self._post_processor = MatchingPostProcessor(self.config)
        self.enable_post_process = True

    # --- image preprocessing (upstream TFPredictor._prepare_image) ---

    def _prepare_image(self, mat_image: np.ndarray) -> np.ndarray:
        mean = np.asarray(
            self.config["dataset"]["image_normalization"]["mean"], dtype=np.float32
        )
        std = np.asarray(
            self.config["dataset"]["image_normalization"]["std"], dtype=np.float32
        )
        size = int(self.config["dataset"]["resized_image"])
        img = (mat_image.astype(np.float32) - 255.0 * mean) / std
        img = cv2.resize(img, dsize=(size, size), interpolation=cv2.INTER_LINEAR)
        # upstream feeds (channels, width, height) — the model is trained on it
        img = img.transpose(2, 1, 0)
        return (img / 255.0)[None, ...].astype(np.float32)

    @staticmethod
    def resize_img(image: np.ndarray, width=None, height=None):
        h, w = image.shape[:2]
        sf = 1.0
        if width is None and height is None:
            return image, sf
        if width is None:
            sf = height / float(h)
            dim = (int(w * sf), height)
        else:
            sf = width / float(w)
            dim = (width, int(h * sf))
        return cv2.resize(image, dim, interpolation=cv2.INTER_AREA), sf

    # --- tag/bbox sync (upstream _check_bbox_sync and helpers) ---

    def _get_html_tags(self, seq: list[int]) -> list[str]:
        return [self._rev_word_map[ind] for ind in seq[1:-1]]

    @staticmethod
    def _deletebbox(listofbboxes, index):
        return [bbox for i, bbox in enumerate(listofbboxes) if i not in index]

    def _remove_bbox_span_desync(self, prediction):
        index_to_delete_from = 0
        indexes_to_delete = []
        for html_elem in prediction["html_seq"]:
            if html_elem == "<td>":
                index_to_delete_from += 1
            if html_elem == ">":
                index_to_delete_from += 1
                indexes_to_delete.append(index_to_delete_from)
        return self._deletebbox(prediction["bboxes"], indexes_to_delete)

    def _check_bbox_sync(self, prediction):
        count_bbox = len(prediction["bboxes"])
        count_td = 0
        for html_elem in prediction["html_seq"]:
            if html_elem == "<td>" or html_elem == ">":
                count_td += 1
            if html_elem in ["fcel", "ecel", "ched", "rhed", "srow"]:
                count_td += 1
        if count_bbox != count_td:
            return False, self._remove_bbox_span_desync(prediction)
        return True, prediction["bboxes"]

    # --- model invocation shared by predict / predict_dummy ---

    def _run_model(self, table_image: np.ndarray) -> dict:
        image_batch = self._prepare_image(table_image)
        prediction: dict = {}
        pred_tag_seq, class_logits, coords = self.model.predict(image_batch)
        if self.config["predict"]["bbox"]:
            prediction["bboxes"] = _box_cxcywh_to_xyxy(coords) if len(coords) else []
            prediction["classes"] = (
                class_logits.argmax(axis=1).tolist() if len(class_logits) else []
            )
        else:
            prediction["bboxes"] = []
            prediction["classes"] = []
        prediction["tag_seq"] = pred_tag_seq
        prediction["rs_seq"] = self._get_html_tags(pred_tag_seq)
        prediction["html_seq"] = otsl_to_html(prediction["rs_seq"], False)
        _otsl_sqr_chk(prediction["rs_seq"])
        sync, corrected_bboxes = self._check_bbox_sync(prediction)
        if not sync:
            prediction["bboxes"] = corrected_bboxes
        return prediction

    # --- upstream predict(): full cell-matching path ---

    def predict(
        self,
        iocr_page,
        table_bbox,
        table_image,
        scale_factor,
        eval_res_preds=None,
        correct_overlapping_cells=False,
    ):
        del eval_res_preds
        prediction = self._run_model(table_image)

        matching_details = {
            "table_cells": [],
            "matches": {},
            "pdf_cells": [],
            "prediction_bboxes_page": [],
        }
        scaled_table_bbox = [coord / scale_factor for coord in table_bbox]

        if len(prediction["bboxes"]) > 0:
            matching_details = self._cell_matcher.match_cells(
                iocr_page, scaled_table_bbox, prediction
            )
            if len(iocr_page["tokens"]) > 0 and self.enable_post_process:
                matching_details = self._post_processor.process(
                    matching_details, correct_overlapping_cells
                )

        docling_output = self._generate_tf_response(
            matching_details["table_cells"], matching_details["matches"]
        )
        docling_output.sort(key=lambda item: item["cell_id"])
        matching_details["docling_responses"] = docling_output
        tf_output = self._merge_tf_output(docling_output, matching_details["pdf_cells"])
        # docling reads rs_seq via predict_details["prediction"]
        matching_details.setdefault("prediction", prediction)
        return tf_output, matching_details

    # --- upstream predict_dummy(): structure-only fallback ---

    def predict_dummy(self, iocr_page, table_bbox, table_image, scale_factor, eval_res_preds=None):
        del eval_res_preds
        prediction = self._run_model(table_image)

        tf_output = []
        matching_details = {
            "table_cells": [],
            "matches": {},
            "pdf_cells": [],
            "prediction_bboxes_page": [],
        }
        scaled_table_bbox = [coord / scale_factor for coord in table_bbox]

        if len(prediction["bboxes"]) > 0:
            matching_details = self._cell_matcher.match_cells_dummy(
                iocr_page, scaled_table_bbox, prediction
            )
            docling_output = self._generate_tf_response_dummy(
                matching_details["table_cells"]
            )
            docling_output.sort(key=lambda item: item["cell_id"])
            matching_details["docling_responses"] = docling_output
            tf_output = docling_output
        matching_details.setdefault("prediction", prediction)
        return tf_output, matching_details

    # --- upstream response builders (dict logic, ported verbatim) ---

    @staticmethod
    def _generate_tf_response_dummy(table_cells):
        tf_cell_list = []
        for table_cell in table_cells:
            colspan_val = table_cell.get("colspan_val", 1)
            rowspan_val = table_cell.get("rowspan_val", 1)
            row_id = table_cell["row_id"]
            column_id = table_cell["column_id"]
            bbox = table_cell["bbox"]
            tf_cell_list.append(
                {
                    "cell_id": table_cell["cell_id"],
                    "bbox": {
                        "b": bbox[3],
                        "l": bbox[0],
                        "r": bbox[2],
                        "t": bbox[1],
                        "token": "",
                    },
                    "row_span": rowspan_val,
                    "col_span": colspan_val,
                    "start_row_offset_idx": row_id,
                    "end_row_offset_idx": row_id + rowspan_val,
                    "start_col_offset_idx": column_id,
                    "end_col_offset_idx": column_id + colspan_val,
                    "indentation_level": 0,
                    "text_cell_bboxes": [],
                    "column_header": table_cell["label"] == "ched",
                    "row_header": table_cell["label"] == "rhed",
                    "row_section": table_cell["label"] == "srow",
                }
            )
        return tf_cell_list

    @staticmethod
    def _generate_tf_response(table_cells, matches):
        tf_cell_list = []
        for pdf_cell_id, pdf_cell_matches in matches.items():
            tf_cell = {
                "bbox": {},
                "row_span": 1,
                "col_span": 1,
                "start_row_offset_idx": -1,
                "end_row_offset_idx": -1,
                "start_col_offset_idx": -1,
                "end_col_offset_idx": -1,
                "indentation_level": 0,
                "text_cell_bboxes": [{}],
                "column_header": False,
                "row_header": False,
                "row_section": False,
            }
            tf_cell["cell_id"] = int(pdf_cell_id)

            row_ids = set()
            column_ids = set()
            labels = set()

            for match in pdf_cell_matches:
                tm = match["table_cell_id"]
                tcl = [tc for tc in table_cells if tc["cell_id"] == tm]
                if len(tcl) > 0:
                    table_cell = tcl[0]
                    row_ids.add(table_cell["row_id"])
                    column_ids.add(table_cell["column_id"])
                    labels.add(table_cell["label"])

                    if table_cell["label"] is not None:
                        if table_cell["label"] in ["ched"]:
                            tf_cell["column_header"] = True
                        if table_cell["label"] in ["rhed"]:
                            tf_cell["row_header"] = True
                        if table_cell["label"] in ["srow"]:
                            tf_cell["row_section"] = True

                    tf_cell["start_col_offset_idx"] = table_cell["column_id"]
                    tf_cell["end_col_offset_idx"] = table_cell["column_id"] + 1
                    tf_cell["start_row_offset_idx"] = table_cell["row_id"]
                    tf_cell["end_row_offset_idx"] = table_cell["row_id"] + 1

                    if "colspan_val" in table_cell:
                        tf_cell["col_span"] = table_cell["colspan_val"]
                        tf_cell["start_col_offset_idx"] = table_cell["column_id"]
                        tf_cell["end_col_offset_idx"] = (
                            table_cell["column_id"] + tf_cell["col_span"]
                        )
                    if "rowspan_val" in table_cell:
                        tf_cell["row_span"] = table_cell["rowspan_val"]
                        tf_cell["start_row_offset_idx"] = table_cell["row_id"]
                        tf_cell["end_row_offset_idx"] = (
                            table_cell["row_id"] + tf_cell["row_span"]
                        )
                    if "bbox" in table_cell:
                        table_match_bbox = table_cell["bbox"]
                        tf_cell["bbox"] = {
                            "b": table_match_bbox[3],
                            "l": table_match_bbox[0],
                            "r": table_match_bbox[2],
                            "t": table_match_bbox[1],
                        }

            tf_cell["row_ids"] = list(row_ids)
            tf_cell["column_ids"] = list(column_ids)
            tf_cell["label"] = "None"
            l_labels = list(labels)
            if len(l_labels) > 0:
                tf_cell["label"] = l_labels[0]
            tf_cell_list.append(tf_cell)
        return tf_cell_list

    @staticmethod
    def _merge_tf_output(docling_output, pdf_cells):
        tf_output = []
        tf_cells_map = {}

        for docling_item in docling_output:
            r_idx = str(docling_item["start_row_offset_idx"])
            c_idx = str(docling_item["start_col_offset_idx"])
            cell_key = c_idx + "_" + r_idx
            if cell_key in tf_cells_map:
                for pdf_cell in pdf_cells:
                    if pdf_cell["id"] == docling_item["cell_id"]:
                        tf_cells_map[cell_key]["text_cell_bboxes"].append(
                            {
                                "b": pdf_cell["bbox"][3],
                                "l": pdf_cell["bbox"][0],
                                "r": pdf_cell["bbox"][2],
                                "t": pdf_cell["bbox"][1],
                                "token": pdf_cell["text"],
                            }
                        )
            else:
                tf_cells_map[cell_key] = {
                    "bbox": docling_item["bbox"],
                    "row_span": docling_item["row_span"],
                    "col_span": docling_item["col_span"],
                    "start_row_offset_idx": docling_item["start_row_offset_idx"],
                    "end_row_offset_idx": docling_item["end_row_offset_idx"],
                    "start_col_offset_idx": docling_item["start_col_offset_idx"],
                    "end_col_offset_idx": docling_item["end_col_offset_idx"],
                    "indentation_level": docling_item["indentation_level"],
                    "text_cell_bboxes": [],
                    "column_header": docling_item["column_header"],
                    "row_header": docling_item["row_header"],
                    "row_section": docling_item["row_section"],
                }
                for pdf_cell in pdf_cells:
                    if pdf_cell["id"] == docling_item["cell_id"]:
                        tf_cells_map[cell_key]["text_cell_bboxes"].append(
                            {
                                "b": pdf_cell["bbox"][3],
                                "l": pdf_cell["bbox"][0],
                                "r": pdf_cell["bbox"][2],
                                "t": pdf_cell["bbox"][1],
                                "token": pdf_cell["text"],
                            }
                        )

        for k in tf_cells_map:
            tf_output.append(tf_cells_map[k])
        return tf_output

    # --- upstream multi_table_predict ---

    def multi_table_predict(
        self,
        iocr_page,
        table_bboxes,
        do_matching=True,
        correct_overlapping_cells=False,
        sort_row_col_indexes=True,
    ):
        multi_tf_output = []
        page_image = iocr_page["image"]

        page_image_resized, scale_factor = self.resize_img(page_image, height=1024)

        img_height, img_width = page_image_resized.shape[:2]

        for table_bbox in table_bboxes:
            table_bbox[0] = table_bbox[0] * scale_factor
            table_bbox[1] = table_bbox[1] * scale_factor
            table_bbox[2] = table_bbox[2] * scale_factor
            table_bbox[3] = table_bbox[3] * scale_factor

            # Deviation from upstream: the layout model can emit a bbox that
            # sticks slightly past the page edge (e.g. a negative top). The
            # upstream slice turns that into an empty crop and cv2.resize
            # aborts the whole page, so clamp to the page bounds first.
            table_bbox[0] = min(max(table_bbox[0], 0.0), float(img_width))
            table_bbox[1] = min(max(table_bbox[1], 0.0), float(img_height))
            table_bbox[2] = min(max(table_bbox[2], 0.0), float(img_width))
            table_bbox[3] = min(max(table_bbox[3], 0.0), float(img_height))

            table_image = page_image_resized[
                round(table_bbox[1]) : round(table_bbox[3]),
                round(table_bbox[0]) : round(table_bbox[2]),
            ]

            if table_image.size == 0:
                # Fully degenerate bbox: emit an empty table instead of
                # failing the conversion.
                multi_tf_output.append({"tf_responses": [], "predict_details": {}})
                continue

            if do_matching:
                tf_responses, predict_details = self.predict(
                    iocr_page,
                    table_bbox,
                    table_image,
                    scale_factor,
                    None,
                    correct_overlapping_cells,
                )
            else:
                tf_responses, predict_details = self.predict_dummy(
                    iocr_page, table_bbox, table_image, scale_factor, None
                )

            if sort_row_col_indexes:
                indexing_start_cols = []
                indexing_start_rows = []
                for tf_response_cell in tf_responses:
                    if tf_response_cell["start_col_offset_idx"] not in indexing_start_cols:
                        indexing_start_cols.append(tf_response_cell["start_col_offset_idx"])
                    if tf_response_cell["start_row_offset_idx"] not in indexing_start_rows:
                        indexing_start_rows.append(tf_response_cell["start_row_offset_idx"])
                indexing_start_cols.sort()
                indexing_start_rows.sort()

                max_end_col_idx = 0
                max_end_row_idx = 0
                for tf_response_cell in tf_responses:
                    tf_response_cell["start_col_offset_idx"] = indexing_start_cols.index(
                        tf_response_cell["start_col_offset_idx"]
                    )
                    tf_response_cell["end_col_offset_idx"] = (
                        tf_response_cell["start_col_offset_idx"]
                        + tf_response_cell["col_span"]
                    )
                    max_end_col_idx = max(
                        max_end_col_idx, tf_response_cell["end_col_offset_idx"]
                    )
                    tf_response_cell["start_row_offset_idx"] = indexing_start_rows.index(
                        tf_response_cell["start_row_offset_idx"]
                    )
                    tf_response_cell["end_row_offset_idx"] = (
                        tf_response_cell["start_row_offset_idx"]
                        + tf_response_cell["row_span"]
                    )
                    max_end_row_idx = max(
                        max_end_row_idx, tf_response_cell["end_row_offset_idx"]
                    )
                predict_details["num_cols"] = max_end_col_idx
                predict_details["num_rows"] = max_end_row_idx
            else:
                otsl_seq = predict_details["prediction"]["rs_seq"]
                predict_details["num_cols"] = otsl_seq.index("nl")
                predict_details["num_rows"] = otsl_seq.count("nl")

            multi_tf_output.append(
                {"tf_responses": tf_responses, "predict_details": predict_details}
            )
            table_bbox[0] = table_bbox[0] / scale_factor
            table_bbox[1] = table_bbox[1] / scale_factor
            table_bbox[2] = table_bbox[2] / scale_factor
            table_bbox[3] = table_bbox[3] / scale_factor

        return multi_tf_output
