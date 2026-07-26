"""TableFormer inference on onnxruntime — no PyTorch.

Python port of TableModel04_rs.predict() (docling-ibm-models): the three
exported ONNX graphs do the tensor math, this module drives the greedy
autoregressive loop and replicates the OTSL structure-error correction and
horizontal-span bbox merging verbatim.
"""

import json
from pathlib import Path

import numpy as np
import onnxruntime as ort

_DIR = Path(__file__).parent


class OrtTableFormer:
    def __init__(self, model_dir: Path = _DIR, max_steps: int = 1024):
        opts = ort.SessionOptions()
        providers = ["CPUExecutionProvider"]
        self._enc = ort.InferenceSession(str(model_dir / "encoder.onnx"), opts, providers=providers)
        self._dec = ort.InferenceSession(str(model_dir / "decoder_step.onnx"), opts, providers=providers)
        self._bbox = ort.InferenceSession(str(model_dir / "bbox_decoder.onnx"), opts, providers=providers)
        self._word_map = json.loads((model_dir / "word_map.json").read_text())
        self._max_steps = max_steps
        cache_shape = self._dec.get_inputs()[2].shape  # [L, cache_len, 1, 512]
        self._n_layers = cache_shape[0]
        self._d_model = cache_shape[3]

    @staticmethod
    def _merge_bboxes(bbox1, bbox2):
        new_w = (bbox2[0] + bbox2[2] / 2) - (bbox1[0] - bbox1[2] / 2)
        new_h = (bbox2[1] + bbox2[3] / 2) - (bbox1[1] - bbox1[3] / 2)
        new_left = bbox1[0] - bbox1[2] / 2
        new_top = min(bbox2[1] - bbox2[3] / 2, bbox1[1] - bbox1[3] / 2)
        return np.array(
            [new_left + new_w / 2, new_top + new_h / 2, new_w, new_h], dtype=bbox1.dtype
        )

    def predict(self, img: np.ndarray):
        """img: float32 [1, 3, 448, 448], preprocessed. Returns (seq, classes, coords)."""
        wm = self._word_map
        enc_out, memory = self._enc.run(None, {"image": img.astype(np.float32)})

        decoded_tags = np.array([[wm["<start>"]]], dtype=np.int64)  # [seq, 1]
        cache = np.zeros((self._n_layers, 0, 1, self._d_model), dtype=np.float32)
        output_tags: list[int] = []
        tag_H_buf: list[np.ndarray] = []

        skip_next_tag = True
        prev_tag_ucel = False
        first_lcel = True
        bboxes_to_merge: dict[int, int] = {}
        cur_bbox_ind = -1
        bbox_ind = 0
        line_num = 0

        while len(output_tags) < self._max_steps:
            logits, last_h, cache = self._dec.run(
                None, {"tags": decoded_tags, "memory": memory, "cache": cache}
            )
            new_tag = int(logits.argmax(axis=1)[0])

            # STRUCTURE ERROR CORRECTION (verbatim from upstream)
            if line_num == 0 and new_tag == wm["xcel"]:
                new_tag = wm["lcel"]
            if prev_tag_ucel and new_tag == wm["lcel"]:
                new_tag = wm["fcel"]

            if new_tag == wm["<end>"]:
                output_tags.append(new_tag)
                decoded_tags = np.concatenate(
                    [decoded_tags, [[new_tag]]], axis=0
                ).astype(np.int64)
                break
            output_tags.append(new_tag)

            if not skip_next_tag:
                if new_tag in (
                    wm["fcel"], wm["ecel"], wm["ched"], wm["rhed"],
                    wm["srow"], wm["nl"], wm["ucel"],
                ):
                    tag_H_buf.append(last_h)
                    if not first_lcel:
                        bboxes_to_merge[cur_bbox_ind] = bbox_ind
                    bbox_ind += 1

            if new_tag != wm["lcel"]:
                first_lcel = True
            else:
                if first_lcel:
                    tag_H_buf.append(last_h)
                    first_lcel = False
                    cur_bbox_ind = bbox_ind
                    bboxes_to_merge[cur_bbox_ind] = -1
                    bbox_ind += 1

            skip_next_tag = new_tag in (wm["nl"], wm["ucel"], wm["xcel"])
            prev_tag_ucel = new_tag == wm["ucel"]

            decoded_tags = np.concatenate(
                [decoded_tags, [[new_tag]]], axis=0
            ).astype(np.int64)

        seq = decoded_tags.squeeze(1).tolist()

        if tag_H_buf:
            tag_H = np.concatenate(tag_H_buf, axis=0)  # [num_cells, 512]
            classes, coords = self._bbox.run(
                None, {"enc_out": enc_out, "tag_H": tag_H}
            )
        else:
            classes = np.empty((0,), dtype=np.float32)
            coords = np.empty((0,), dtype=np.float32)

        # Merge first/last bbox of each horizontal span (verbatim from upstream)
        out_classes, out_coords, skip = [], [], []
        for i in range(len(coords)):
            if i in bboxes_to_merge:
                skip.append(bboxes_to_merge[i])
                out_coords.append(self._merge_bboxes(coords[i], coords[bboxes_to_merge[i]]))
                out_classes.append(classes[i])
            elif i not in skip:
                out_coords.append(coords[i])
                out_classes.append(classes[i])

        classes = np.stack(out_classes) if out_classes else np.empty(0, dtype=np.float32)
        coords = np.stack(out_coords) if out_coords else np.empty(0, dtype=np.float32)
        return seq, classes, coords
