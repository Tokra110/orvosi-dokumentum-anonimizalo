import logging


def test_diagnostic_log_records_sanitized_traceback(tmp_path, monkeypatch):
    import diagnostics

    log_path = tmp_path / "logs" / "medical-redactor.log"
    monkeypatch.setattr(diagnostics, "get_log_path", lambda: log_path)

    diagnostics.configure_file_logging()
    try:
        raise RuntimeError(
            r"Could not open C:\Users\Dávid\Documents\Takács Dávid lelet.pdf"
        )
    except RuntimeError:
        logging.getLogger("test.diagnostics").exception("PDF backend failed")

    for handler in logging.getLogger().handlers:
        handler.flush()

    text = log_path.read_text(encoding="utf-8")
    assert "Traceback" in text
    assert "PDF backend failed" in text
    assert "Dávid" not in text
    assert "Takács" not in text
    assert "XYZ.pdf" in text


def test_display_log_path_is_copyable_on_frozen_windows(monkeypatch):
    import diagnostics

    monkeypatch.setattr(diagnostics.sys, "platform", "win32")
    monkeypatch.setattr(diagnostics.sys, "frozen", True, raising=False)

    assert diagnostics.display_log_path() == (
        r"%LOCALAPPDATA%\Programs\Medical Redactor\logs\medical-redactor.log"
    )
