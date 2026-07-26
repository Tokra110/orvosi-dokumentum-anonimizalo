import os
import re
from pathlib import Path

import pytest


PDF_DIR_ENV = "MEDICAL_REDACTOR_TEST_PDF_DIR"
PDF_LIMIT_ENV = "MEDICAL_REDACTOR_TEST_PDF_LIMIT"

_TAJ_RE = re.compile(r"\b(\d{3})[-\s]?(\d{3})[-\s]?(\d{3})\b")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:\+36|06)[-\s.]?(?:1|[2-9]\d)[-\s.]?\d{3}[-\s.]?\d{2,4}")


def _validate_taj(d1: str, d2: str, d3: str) -> bool:
    digits = [int(c) for c in d1 + d2 + d3]
    weights = [3, 7, 3, 7, 3, 7, 3, 7]
    total = sum(digits[i] * weights[i] for i in range(8))
    return total % 10 == digits[8]


def _unredacted_taj_values(text: str) -> list[str]:
    values = []
    for match in _TAJ_RE.finditer(text):
        if _validate_taj(match.group(1), match.group(2), match.group(3)):
            values.append(match.group())
    return values


@pytest.mark.skipif(
    not os.environ.get(PDF_DIR_ENV),
    reason=f"set {PDF_DIR_ENV} to run private PDF corpus validation",
)
def test_private_pdf_corpus_processes_and_redacts(tmp_path):
    from redactor import process_pdfs

    pdf_dir = Path(os.environ[PDF_DIR_ENV]).expanduser()
    assert pdf_dir.is_dir(), f"{PDF_DIR_ENV} does not point to a directory: {pdf_dir}"

    limit = int(os.environ.get(PDF_LIMIT_ENV, "5"))
    pdfs = sorted(pdf_dir.glob("*.pdf"))[:limit]
    if not pdfs:
        pytest.skip(f"No PDFs found in {pdf_dir}")

    output_dir = tmp_path / "redacted"
    process_pdfs([str(pdf) for pdf in pdfs], str(output_dir))

    markdown_files = sorted(output_dir.glob("*.md"))
    assert len(markdown_files) >= len(pdfs)

    for markdown_file in markdown_files:
        text = markdown_file.read_text(encoding="utf-8")
        assert text.strip(), f"{markdown_file.name} is empty"
        assert not _unredacted_taj_values(text), markdown_file.name
        assert not _EMAIL_RE.search(text), markdown_file.name
        assert not _PHONE_RE.search(text), markdown_file.name
