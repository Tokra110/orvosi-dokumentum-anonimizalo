#!/usr/bin/env python
"""Export the Hungarian HuBERT NER model to ONNX Runtime artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from transformers import AutoConfig, AutoModelForTokenClassification, AutoTokenizer


ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "NYTK/named-entity-recognition-nerkor-hubert-hungarian"
OUT_DIR = ROOT / "models" / "hubert-ner-onnx"


class TokenClassificationWrapper(torch.nn.Module):
    def __init__(self, model: AutoModelForTokenClassification):
        super().__init__()
        self.model = model

    def forward(self, input_ids, attention_mask, token_type_ids):
        return self.model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
        ).logits


def _ort_logits(inputs: dict[str, torch.Tensor]) -> np.ndarray:
    session = ort.InferenceSession(
        str(OUT_DIR / "model.onnx"),
        providers=["CPUExecutionProvider"],
    )
    ort_inputs = {name: tensor.cpu().numpy() for name, tensor in inputs.items()}
    return session.run(None, ort_inputs)[0]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    config = AutoConfig.from_pretrained(MODEL_ID, local_files_only=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, local_files_only=True)
    model = AutoModelForTokenClassification.from_pretrained(MODEL_ID, local_files_only=True)
    model.eval()

    tokenizer.save_pretrained(OUT_DIR)
    config.save_pretrained(OUT_DIR)
    labels = {int(k): v for k, v in config.id2label.items()}
    (OUT_DIR / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")

    sample = "Teszt Elek Budapesten lakik."
    inputs = tokenizer(sample, return_tensors="pt")
    ordered_inputs = (
        inputs["input_ids"],
        inputs["attention_mask"],
        inputs["token_type_ids"],
    )

    with torch.no_grad():
        torch_logits = model(**inputs).logits.cpu().numpy()

    wrapper = TokenClassificationWrapper(model).eval()
    torch.onnx.export(
        wrapper,
        ordered_inputs,
        str(OUT_DIR / "model.onnx"),
        input_names=["input_ids", "attention_mask", "token_type_ids"],
        output_names=["logits"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "sequence"},
            "attention_mask": {0: "batch", 1: "sequence"},
            "token_type_ids": {0: "batch", 1: "sequence"},
            "logits": {0: "batch", 1: "sequence"},
        },
        opset_version=18,
        dynamo=False,
    )

    onnx_logits = _ort_logits(inputs)
    max_diff = float(np.max(np.abs(torch_logits - onnx_logits)))
    print(f"exported {OUT_DIR / 'model.onnx'}")
    print(f"max |torch - onnx logits|: {max_diff:.2e}")
    if max_diff >= 1e-4:
        raise SystemExit(f"ONNX parity failed: {max_diff:.2e}")


if __name__ == "__main__":
    main()
