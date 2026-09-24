def test_main_window_constructs_offscreen(qapp, tmp_path, monkeypatch):
    # Point at an empty model dir: the window must construct and show the
    # missing-models banner instead of crashing.
    monkeypatch.setenv("MEDICAL_REDACTOR_MODEL_DIR", str(tmp_path))
    from gui import settings

    config_path = tmp_path / "settings.json"
    config_path.write_text('{"language": "en"}')
    monkeypatch.setattr(settings, "CONFIG_PATH", config_path)
    from gui.main_window import MainWindow

    w = MainWindow()
    assert w.windowTitle() == "Medical document anonymizer"
    assert w.queue.rowCount() == 0
    assert w.missing_banner.isVisibleTo(w)
    assert w.model_chip.text() == "Download models"
    assert w.output_btn.text() == "Output: beside originals"


def test_main_module_has_qt_entry_point():
    import main

    assert hasattr(main, "main")
    src = open(main.__file__, encoding="utf-8").read()
    assert "tkinter" not in src
    assert "PySide6" in src or "gui.main_window" in src
