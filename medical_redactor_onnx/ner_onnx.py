from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


class OnnxNerPipeline:
    """Small HuggingFace-pipeline-compatible ONNX token classifier."""

    def __init__(self, model_dir: Path):
        self.model_dir = Path(model_dir)
        # tokenizers.Tokenizer reads the same tokenizer.json AutoTokenizer
        # wrapped (post-processor adds [CLS]/[SEP] identically) without the
        # 112 MB transformers dependency.
        self.tokenizer = Tokenizer.from_file(str(self.model_dir / "tokenizer.json"))
        raw_labels = json.loads((self.model_dir / "labels.json").read_text(encoding="utf-8"))
        self.id2label = {int(k): v for k, v in raw_labels.items()}
        self.session = ort.InferenceSession(
            str(self.model_dir / "model.onnx"),
            providers=["CPUExecutionProvider"],
        )

    @staticmethod
    def _softmax(logits: np.ndarray) -> np.ndarray:
        shifted = logits - logits.max(axis=-1, keepdims=True)
        exp = np.exp(shifted)
        return exp / exp.sum(axis=-1, keepdims=True)

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text).ids)

    def _run(self, text: str) -> tuple[list[tuple[int, int]], np.ndarray, np.ndarray]:
        encoding = self.tokenizer.encode(text)
        offsets = list(encoding.offsets)
        inputs = {
            "input_ids": np.array([encoding.ids], dtype=np.int64),
            "attention_mask": np.array([encoding.attention_mask], dtype=np.int64),
            "token_type_ids": np.array([encoding.type_ids], dtype=np.int64),
        }

        logits = self.session.run(None, inputs)[0][0]
        probabilities = self._softmax(logits)
        label_ids = probabilities.argmax(axis=-1)
        scores = probabilities.max(axis=-1)
        return offsets, label_ids, scores

    def __call__(self, text: str) -> list[dict]:
        offsets, label_ids, scores = self._run(text)
        entities: list[dict] = []
        current: dict | None = None
        current_scores: list[float] = []

        for (start, end), label_id, score in zip(offsets, label_ids, scores, strict=False):
            if start == end:
                continue
            label = self.id2label[int(label_id)]
            if label == "O":
                if current is not None:
                    current["score"] = float(np.mean(current_scores))
                    current["word"] = text[current["start"] : current["end"]]
                    entities.append(current)
                    current = None
                    current_scores = []
                continue

            prefix, entity_group = label.split("-", 1)
            if (
                current is not None
                and current["entity_group"] == entity_group
                and prefix == "I"
                and start <= current["end"] + 1
            ):
                current["end"] = end
                current_scores.append(float(score))
                continue

            if current is not None:
                current["score"] = float(np.mean(current_scores))
                current["word"] = text[current["start"] : current["end"]]
                entities.append(current)

            current = {
                "entity_group": entity_group,
                "start": start,
                "end": end,
            }
            current_scores = [float(score)]

        if current is not None:
            current["score"] = float(np.mean(current_scores))
            current["word"] = text[current["start"] : current["end"]]
            entities.append(current)

        return entities

