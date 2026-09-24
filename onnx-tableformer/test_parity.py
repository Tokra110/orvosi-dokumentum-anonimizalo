"""Parity test: torch TableFormer vs ONNX Runtime port on a synthetic table.

Renders a realistic table image, feeds the identical preprocessed tensor
through both implementations, and compares tag sequences and bboxes.
"""

import time

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="TableFormer parity test is export-only")
from PIL import Image, ImageDraw

from export_onnx import load_predictor
from ort_tableformer import OrtTableFormer


def make_table_image() -> Image.Image:
    """Draw a 4x5 bordered table with header row, lab-report style."""
    img = Image.new("RGB", (448, 448), "white")
    d = ImageDraw.Draw(img)
    rows, cols = 5, 4
    x0, y0, x1, y1 = 20, 60, 428, 380
    rh, cw = (y1 - y0) / rows, (x1 - x0) / cols
    header = ["Vizsgalat", "Eredmeny", "Egyseg", "Referencia"]
    body = [
        ["GGT", "45", "U/l", "0-55"],
        ["Na+", "141", "mmol/l", "136-146"],
        ["K+", "4.2", "mmol/l", "3.5-5.1"],
        ["CRP", "2.3", "mg/l", "0-5"],
    ]
    for r in range(rows + 1):
        d.line([(x0, y0 + r * rh), (x1, y0 + r * rh)], fill="black", width=2)
    for c in range(cols + 1):
        d.line([(x0 + c * cw, y0), (x0 + c * cw, y1)], fill="black", width=2)
    for c, text in enumerate(header):
        d.text((x0 + c * cw + 8, y0 + 20), text, fill="black")
    for r, row in enumerate(body):
        for c, text in enumerate(row):
            d.text((x0 + c * cw + 8, y0 + (r + 1) * rh + 20), text, fill="black")
    return img


def preprocess(img: Image.Image) -> np.ndarray:
    arr = np.asarray(img, dtype=np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    arr = (arr - mean) / std
    return arr.transpose(2, 0, 1)[None, ...]  # [1, 3, 448, 448]


def main():
    x = preprocess(make_table_image())

    predictor = load_predictor("accurate")
    model = predictor._model
    model.eval()

    with torch.no_grad():
        t0 = time.perf_counter()
        seq_pt, cls_pt, coord_pt = model.predict(torch.from_numpy(x), 1024, 1)
        t_pt = time.perf_counter() - t0

    ort_model = OrtTableFormer()
    t0 = time.perf_counter()
    seq_ort, cls_ort, coord_ort = ort_model.predict(x)
    t_ort = time.perf_counter() - t0

    print(f"torch: {len(seq_pt)} tags, {len(coord_pt)} bboxes, {t_pt:.2f}s")
    print(f"ort:   {len(seq_ort)} tags, {len(coord_ort)} bboxes, {t_ort:.2f}s")

    assert seq_pt == seq_ort, (
        f"tag sequences differ:\n torch: {seq_pt}\n ort:   {seq_ort}"
    )
    print("tag sequences: IDENTICAL")

    cls_pt, coord_pt = cls_pt.numpy(), coord_pt.numpy()
    d_coord = np.abs(coord_pt - coord_ort).max() if len(coord_ort) else 0.0
    d_cls = np.abs(cls_pt - cls_ort).max() if len(cls_ort) else 0.0
    print(f"max |bbox coord diff|: {d_coord:.2e}, max |class logit diff|: {d_cls:.2e}")
    assert d_coord < 1e-3 and d_cls < 1e-3, "numeric outputs diverge"
    print(f"PARITY OK (ort is {t_pt / t_ort:.1f}x vs torch)")


if __name__ == "__main__":
    main()
