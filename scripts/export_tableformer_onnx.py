#!/usr/bin/env python
"""Export TableFormer ONNX artifacts into the runtime model directory."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPIKE_EXPORTER = ROOT / "onnx-tableformer" / "export_onnx.py"
OUT_DIR = ROOT / "models" / "tableformer-onnx"


def _load_spike_exporter():
    spec = importlib.util.spec_from_file_location("tableformer_export_onnx", SPIKE_EXPORTER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load exporter from {SPIKE_EXPORTER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    exporter = _load_spike_exporter()
    exporter.export_tableformer(OUT_DIR, "accurate")


if __name__ == "__main__":
    main()
