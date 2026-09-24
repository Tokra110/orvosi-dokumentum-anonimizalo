from pathlib import Path

import pytest


def test_create_test_pdfs_builds_vector_table_and_image_only_scan(tmp_path):
    import pypdfium2 as pdfium

    from release_harness import create_test_pdfs

    pdfs = create_test_pdfs(tmp_path / "input")

    assert len(pdfs) == 2
    assert all(path.is_file() and path.read_bytes().startswith(b"%PDF") for path in pdfs)
    assert any("Árvíztűrő" in path.name and "Lelet" in path.name for path in pdfs)
    assert any("Árvíztűrő" in path.name and "Scanned" in path.name for path in pdfs)

    vector = next(path for path in pdfs if "Lelet" in path.name)
    scanned = next(path for path in pdfs if "Scanned" in path.name)
    vector_doc = pdfium.PdfDocument(vector)
    scanned_doc = pdfium.PdfDocument(scanned)
    try:
        vector_text = vector_doc[0].get_textpage().get_text_range()
        scanned_text = scanned_doc[0].get_textpage().get_text_range()
    finally:
        vector_doc.close()
        scanned_doc.close()

    assert "Teszt Elek" in vector_text
    assert "GGT" in vector_text
    assert scanned_text.strip() == ""


def _write_valid_outputs(output_dir: Path) -> None:
    output_dir.mkdir()
    (output_dir / "Árvíztűrő - [REDACTED_NAME] - Lelet.md").write_text(
        "Beteg neve: [REDACTED_NAME]\n"
        "TAJ: [REDACTED_TAJ]\n"
        "Email: [REDACTED_EMAIL]\n"
        "Telefon: [REDACTED_PHONE]\n"
        "| Vizsgalat | Eredmeny |\n"
        "| --- | --- |\n"
        "| GGT | 45 |\n"
        "| Na+ | 141 |\n",
        encoding="utf-8",
    )
    (output_dir / "Árvíztűrő - [REDACTED_NAME] - Scanned.md").write_text(
        "Beteg neve: [REDACTED_NAME]\n"
        "Email: [REDACTED_EMAIL]\n"
        "Telefon: [REDACTED_PHONE]\n",
        encoding="utf-8",
    )


def test_validate_outputs_accepts_redacted_vector_and_scanned_results(tmp_path):
    from release_harness import validate_outputs

    output_dir = tmp_path / "output"
    _write_valid_outputs(output_dir)

    outputs = validate_outputs(output_dir, expected_count=2)

    assert len(outputs) == 2


@pytest.mark.parametrize(
    "raw_value",
    [
        "Teszt Elek",
        "teszt.elek@example.com",
        "+36 30 123 4567",
        "123 456 788",
    ],
)
def test_validate_outputs_rejects_raw_pii(tmp_path, raw_value):
    from release_harness import validate_outputs

    output_dir = tmp_path / "output"
    _write_valid_outputs(output_dir)
    scanned = next(output_dir.glob("*Scanned.md"))
    scanned.write_text(scanned.read_text(encoding="utf-8") + raw_value, encoding="utf-8")

    with pytest.raises(AssertionError, match="raw fixture PII"):
        validate_outputs(output_dir, expected_count=2)
