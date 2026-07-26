import sys

import numpy as np
from PIL import Image, ImageDraw


def _make_table_image() -> np.ndarray:
    img = Image.new("RGB", (448, 448), "white")
    draw = ImageDraw.Draw(img)
    rows, cols = 5, 4
    x0, y0, x1, y1 = 20, 60, 428, 380
    row_h, col_w = (y1 - y0) / rows, (x1 - x0) / cols
    for r in range(rows + 1):
        draw.line([(x0, y0 + r * row_h), (x1, y0 + r * row_h)], fill="black", width=2)
    for c in range(cols + 1):
        draw.line([(x0 + c * col_w, y0), (x0 + c * col_w, y1)], fill="black", width=2)
    return np.asarray(img)


def test_register_onnx_tableformer_replaces_docling_default():
    from docling.datamodel.pipeline_options import TableStructureOptions
    from docling.models.factories import get_table_structure_factory

    from medical_redactor_onnx.docling_table_model import OnnxTableStructureModel
    from medical_redactor_onnx.register_docling import register_onnx_tableformer

    register_onnx_tableformer()

    factory = get_table_structure_factory()
    assert factory.classes[TableStructureOptions] is OnnxTableStructureModel
    assert not any(name.startswith("docling_ibm_models") for name in sys.modules)


def test_ort_tableformer_predictor_returns_docling_payload_shape():
    from medical_redactor_onnx.paths import tableformer_dir
    from medical_redactor_onnx.tableformer_predictor import OrtTFPredictor

    predictor = OrtTFPredictor(tableformer_dir(require=True))
    result = predictor.multi_table_predict(
        {
            "width": 448,
            "height": 448,
            "image": _make_table_image(),
            "tokens": [],
        },
        [[0, 0, 448, 448]],
        do_matching=False,
    )

    assert len(result) == 1
    table = result[0]
    assert set(table) == {"tf_responses", "predict_details"}
    assert table["predict_details"]["num_rows"] > 0
    assert table["predict_details"]["num_cols"] > 0
    assert table["predict_details"]["prediction"]["rs_seq"]
    assert table["tf_responses"]
    assert {"bbox", "row_span", "col_span", "start_row_offset_idx", "start_col_offset_idx"} <= set(
        table["tf_responses"][0]
    )


def test_ort_tableformer_clamps_bbox_sticking_past_page_edge():
    # Layout can emit a bbox with a slightly negative top; the unclamped
    # upstream slice would produce an empty crop and abort the page.
    from medical_redactor_onnx.paths import tableformer_dir
    from medical_redactor_onnx.tableformer_predictor import OrtTFPredictor

    predictor = OrtTFPredictor(tableformer_dir(require=True))
    result = predictor.multi_table_predict(
        {
            "width": 448,
            "height": 448,
            "image": _make_table_image(),
            "tokens": [],
        },
        [[2, -6, 448, 448]],
        do_matching=False,
    )

    assert len(result) == 1
    assert result[0]["tf_responses"]


def test_ort_tableformer_skips_fully_degenerate_bbox():
    from medical_redactor_onnx.paths import tableformer_dir
    from medical_redactor_onnx.tableformer_predictor import OrtTFPredictor

    predictor = OrtTFPredictor(tableformer_dir(require=True))
    result = predictor.multi_table_predict(
        {
            "width": 448,
            "height": 448,
            "image": _make_table_image(),
            "tokens": [],
        },
        [[0, -20, 448, -4]],
        do_matching=False,
    )

    assert len(result) == 1
    assert result[0]["tf_responses"] == []
    assert result[0]["predict_details"] == {}


def test_redactor_build_docling_converter_registers_table_model():
    from docling.datamodel.pipeline_options import TableStructureOptions
    from docling.models.factories import get_table_structure_factory

    from medical_redactor_onnx.docling_table_model import OnnxTableStructureModel
    from redactor import build_docling_converter

    build_docling_converter()

    assert get_table_structure_factory().classes[TableStructureOptions] is OnnxTableStructureModel


def test_redactor_build_docling_converter_uses_onnx_layout_options():
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import LayoutObjectDetectionOptions, RapidOcrOptions
    from redactor import build_docling_converter

    converter = build_docling_converter()
    options = converter.format_to_options[InputFormat.PDF].pipeline_options

    assert isinstance(options.layout_options, LayoutObjectDetectionOptions)
    assert isinstance(options.ocr_options, RapidOcrOptions)
    assert options.ocr_options.backend == "onnxruntime"


def test_windows_converter_uses_pdfium_backend(monkeypatch):
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.base_models import InputFormat

    import redactor

    monkeypatch.setattr(redactor, "_is_windows", lambda: True)
    converter = redactor.build_docling_converter()

    assert (
        converter.format_to_options[InputFormat.PDF].backend
        is PyPdfiumDocumentBackend
    )


def test_onnx_docling_converter_extracts_markdown_table(generated_medical_pdf):
    from redactor import build_docling_converter, convert_pdf

    markdown = convert_pdf(str(generated_medical_pdf), build_docling_converter())

    assert "GGT" in markdown
    assert "Na+" in markdown
    assert "|" in markdown


def test_windows_stream_path_converts_unicode_pdf(
    generated_medical_pdf, tmp_path, monkeypatch
):
    import shutil

    import redactor

    unicode_pdf = tmp_path / "Takács-Tolnai Dávid lelet.pdf"
    shutil.copyfile(generated_medical_pdf, unicode_pdf)
    monkeypatch.setattr(redactor, "_is_windows", lambda: True)

    markdown = redactor.convert_pdf(
        str(unicode_pdf), redactor.build_docling_converter()
    )

    assert "GGT" in markdown
    assert "Na+" in markdown
    assert "|" in markdown
