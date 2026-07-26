"""End-to-end verification used by installed release candidates.

This module is imported by the frozen executable only when
``--release-verify`` is requested. It deliberately exercises the same model
downloader, PDF pipeline, output writer, and GUI entry point used by users.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


_RAW_FIXTURE_PII = (
    "Teszt Elek",
    "teszt.elek@example.com",
    "+36 30 123 4567",
    "123 456 788",
)


def create_test_pdfs(input_dir: Path) -> list[Path]:
    """Create one vector table PDF and one image-only OCR PDF."""
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import (
        Image as ReportLabImage,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    input_dir.mkdir(parents=True, exist_ok=False)
    styles = getSampleStyleSheet()

    vector_pdf = input_dir / "Árvíztűrő - Teszt Elek - Lelet.pdf"
    vector_doc = SimpleDocTemplate(str(vector_pdf), pagesize=A4)
    table = Table(
        [
            ["Vizsgalat", "Eredmeny", "Egyseg", "Referencia"],
            ["GGT", "45", "U/l", "0-55"],
            ["Na+", "141", "mmol/l", "136-146"],
        ]
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ]
        )
    )
    vector_doc.build(
        [
            Paragraph("Beteg neve: Teszt Elek", styles["Normal"]),
            Paragraph("TAJ szam: 123 456 788", styles["Normal"]),
            Paragraph("Email: teszt.elek@example.com", styles["Normal"]),
            Paragraph("Telefon: +36 30 123 4567", styles["Normal"]),
            Spacer(1, 12),
            table,
        ]
    )

    scan_image = input_dir / "release-scan.png"
    image = Image.new("RGB", (1654, 2339), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=38)
    lines = (
        "Beteg neve: Teszt Elek",
        "TAJ szam: 123 456 788",
        "Email: teszt.elek@example.com",
        "Telefon: +36 30 123 4567",
    )
    for index, line in enumerate(lines):
        draw.text((120, 180 + index * 80), line, fill="black", font=font)
    image.save(scan_image)

    scanned_pdf = input_dir / "Árvíztűrő - Teszt Elek - Scanned.pdf"
    scanned_doc = SimpleDocTemplate(str(scanned_pdf), pagesize=A4)
    scanned_doc.build([ReportLabImage(str(scan_image), width=430, height=608)])
    scan_image.unlink()

    return [vector_pdf, scanned_pdf]


def validate_outputs(output_dir: Path, expected_count: int) -> list[Path]:
    """Validate successful conversion, redaction, filenames, and table output."""
    outputs = sorted(output_dir.glob("*.md"))
    assert len(outputs) == expected_count, (
        f"expected {expected_count} Markdown outputs, found {len(outputs)}"
    )
    assert all(path.stat().st_size > 0 for path in outputs), "an output file is empty"
    assert all("Teszt Elek" not in path.name for path in outputs), (
        "an output filename still contains fixture PII"
    )

    contents = {
        path: path.read_text(encoding="utf-8")
        for path in outputs
    }
    for path, text in contents.items():
        assert "[REDACTED_" in text, f"{path.name} contains no redaction placeholder"
        for raw_value in _RAW_FIXTURE_PII:
            assert raw_value.lower() not in text.lower(), (
                f"{path.name} contains raw fixture PII: {raw_value}"
            )

    vector_output = next(
        (path for path in outputs if "Lelet" in path.name),
        None,
    )
    assert vector_output is not None, "vector PDF output is missing"
    vector_text = contents[vector_output]
    assert "GGT" in vector_text and "Na+" in vector_text and "|" in vector_text, (
        "vector PDF table content was not preserved"
    )
    return outputs


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download_and_verify_models() -> None:
    """Download through the shipped manifest and verify every installed file."""
    from medical_redactor_onnx.download import download_model, load_model_specs
    from medical_redactor_onnx.paths import get_model_dir

    model_dir = get_model_dir()
    for spec in load_model_specs():
        download_model(spec)
        for file_spec in spec.files:
            path = model_dir / spec.name / file_spec.name
            assert path.is_file(), f"downloaded model file is missing: {path}"
            assert path.stat().st_size == file_spec.bytes, (
                f"downloaded model file has the wrong size: {path}"
            )
            assert _sha256(path) == file_spec.sha256, (
                f"downloaded model file has the wrong SHA-256: {path}"
            )
        print(f"release verification: {spec.name} download and hashes OK")


def _run_gui_smoke() -> None:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow
    from gui.theme import APP_QSS

    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Orvosi dokumentum anonimizáló")
    app.setStyleSheet(APP_QSS)
    window = MainWindow()
    observed_visibility: list[bool] = []

    def finish() -> None:
        observed_visibility.append(window.isVisible())
        window.close()
        app.quit()

    window.show()
    QTimer.singleShot(1500, finish)
    exit_code = app.exec()
    assert exit_code == 0, f"GUI event loop exited with code {exit_code}"
    assert observed_visibility == [True], "main window did not become visible"
    print("release verification: GUI window OK")


def run_release_verification(work_dir: Path) -> int:
    """Run the full installed-application verification."""
    from redactor import process_pdfs

    work_dir = Path(work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=False)
    input_dir = work_dir / "input"
    output_dir = work_dir / "output"

    download_and_verify_models()
    pdfs = create_test_pdfs(input_dir)
    process_pdfs([str(path) for path in pdfs], str(output_dir))
    outputs = validate_outputs(output_dir, expected_count=len(pdfs))
    print(f"release verification: processed {len(outputs)} PDFs successfully")

    _run_gui_smoke()
    marker = work_dir / "release-verification.json"
    marker.write_text(
        json.dumps(
            {
                "status": "passed",
                "inputs": [path.name for path in pdfs],
                "outputs": [path.name for path in outputs],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"release verification: complete marker written to {marker}")
    return 0
