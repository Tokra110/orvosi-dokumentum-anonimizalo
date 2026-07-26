import redactor
from redactor import FileEvent, process_pdfs


MARKDOWN = """
Beteg neve: Teszt Elek
TAJ szam: 123 456 789
"""


def _run(tmp_path, monkeypatch, converter):
    from conftest import EmptyNerPipeline

    pdf = tmp_path / "lelet.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    out_dir = tmp_path / "out"

    monkeypatch.setattr(redactor, "build_docling_converter", lambda: converter)
    monkeypatch.setattr(redactor, "load_ner_model", lambda: EmptyNerPipeline())

    events: list[FileEvent] = []
    process_pdfs([str(pdf)], str(out_dir), on_file_event=events.append)
    return pdf, events


def test_process_pdfs_emits_stage_events_with_counts(tmp_path, monkeypatch):
    from conftest import FakeConverter

    pdf, events = _run(tmp_path, monkeypatch, FakeConverter(MARKDOWN))

    assert [e.stage for e in events] == ["converting", "redacting", "done"]
    assert all(e.path == str(pdf) for e in events)

    done = events[-1]
    assert done.counts["NAME"] >= 1
    assert done.counts["TAJ"] == 1
    assert done.output_name and done.output_name.endswith(".md")
    assert done.error is None


def test_process_pdfs_emits_failed_event_on_error(tmp_path, monkeypatch):
    class BrokenConverter:
        def convert(self, path):
            raise RuntimeError("boom")

    pdf, events = _run(tmp_path, monkeypatch, BrokenConverter())

    assert [e.stage for e in events] == ["converting", "failed"]
    assert "boom" in events[-1].error


def test_process_file_return_type_unchanged(tmp_path):
    from conftest import EmptyNerPipeline, FakeConverter

    pdf = tmp_path / "lelet.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    result = redactor.process_file(str(pdf), EmptyNerPipeline(), FakeConverter(MARKDOWN))
    assert isinstance(result, str)


def test_windows_conversion_uses_stream_for_unicode_pdf_path(tmp_path, monkeypatch):
    pdf = tmp_path / "Takács-Tolnai Dávid lelet.pdf"
    pdf_bytes = b"%PDF-1.4\nunicode-path-regression"
    pdf.write_bytes(pdf_bytes)

    class CapturingConverter:
        source = None

        def convert(self, source):
            self.source = source
            return FakeConversion(MARKDOWN)

    from conftest import FakeConversion

    converter = CapturingConverter()
    monkeypatch.setattr(redactor, "_is_windows", lambda: True)

    redactor.convert_pdf(str(pdf), converter)

    assert converter.source.name == pdf.name
    assert converter.source.stream.read() == pdf_bytes
