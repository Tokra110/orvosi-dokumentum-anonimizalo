def test_all_missing_in_empty_model_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDICAL_REDACTOR_MODEL_DIR", str(tmp_path))
    from gui.models_dialog import all_models_ready, model_statuses

    statuses = model_statuses()
    assert [s.name for s in statuses] == ["hubert-ner-onnx", "tableformer-onnx"]
    assert all(not s.ready and s.missing for s in statuses)
    assert not all_models_ready()


def test_ready_when_required_files_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDICAL_REDACTOR_MODEL_DIR", str(tmp_path))
    from medical_redactor_onnx.paths import (
        HUBERT_NER_REQUIRED_FILES,
        TABLEFORMER_REQUIRED_FILES,
    )

    for name, files in (
        ("hubert-ner-onnx", HUBERT_NER_REQUIRED_FILES),
        ("tableformer-onnx", TABLEFORMER_REQUIRED_FILES),
    ):
        d = tmp_path / name
        d.mkdir()
        for f in files:
            (d / f).touch()

    from gui.models_dialog import all_models_ready, model_statuses

    assert all(s.ready for s in model_statuses())
    assert all_models_ready()
