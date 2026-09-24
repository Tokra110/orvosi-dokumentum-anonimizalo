from pathlib import Path

import pytest


@pytest.fixture
def generated_medical_pdf(tmp_path: Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    pdf_path = tmp_path / "medical-record.pdf"
    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4)
    styles = getSampleStyleSheet()

    story = [
        Paragraph("Magyar orvosi lelet", styles["Title"]),
        Paragraph("Beteg neve: Teszt Elek", styles["Normal"]),
        Paragraph("TAJ szam: 123 456 789", styles["Normal"]),
        Paragraph("Szuletesi datum: 1980. 01. 02.", styles["Normal"]),
        Paragraph("Vizsgalat datuma: 2026. 07. 05.", styles["Normal"]),
        Paragraph("Email: teszt.elek@example.com", styles["Normal"]),
        Paragraph("Telefon: +36 30 123 4567", styles["Normal"]),
        Spacer(1, 12),
    ]

    table = Table(
        [
            ["Vizsgalat", "Eredmeny", "Egyseg", "Referencia"],
            ["GGT", "45", "U/l", "0-55"],
            ["Na+", "141", "mmol/l", "136-146"],
            ["K+", "4.2", "mmol/l", "3.5-5.1"],
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
    story.append(table)
    doc.build(story)
    return pdf_path


class FakeDoc:
    def __init__(self, markdown: str):
        self._markdown = markdown

    def export_to_markdown(self) -> str:
        return self._markdown


class FakeConversion:
    def __init__(self, markdown: str):
        self.document = FakeDoc(markdown)


class FakeConverter:
    def __init__(self, markdown: str):
        self._markdown = markdown

    def convert(self, _pdf_path: str) -> FakeConversion:
        return FakeConversion(self._markdown)


class EmptyNerPipeline:
    def count_tokens(self, text: str) -> int:
        return min(len(text), 32)

    def __call__(self, _text: str) -> list[dict]:
        return []


@pytest.fixture(scope="session")
def qapp():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
