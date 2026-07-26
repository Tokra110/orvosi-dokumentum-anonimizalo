from pathlib import Path

import pytest


TABLEFORMER_FILES = {
    "encoder.onnx",
    "encoder.onnx.data",
    "decoder_step.onnx",
    "decoder_step.onnx.data",
    "bbox_decoder.onnx",
    "bbox_decoder.onnx.data",
    "word_map.json",
    "tm_config.json",
}

HUBERT_FILES = {
    "model.onnx",
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
    "labels.json",
}


def _touch_all(directory: Path, names: set[str]) -> None:
    directory.mkdir(parents=True)
    for name in names:
        (directory / name).write_text("x", encoding="utf-8")


def test_model_dir_defaults_to_project_models(monkeypatch):
    monkeypatch.delenv("MEDICAL_REDACTOR_MODEL_DIR", raising=False)

    from medical_redactor_onnx.paths import get_model_dir

    assert get_model_dir().name == "models"
    assert get_model_dir().parent.name == "medical-redactor"


def test_model_dir_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDICAL_REDACTOR_MODEL_DIR", str(tmp_path))

    from medical_redactor_onnx.paths import get_model_dir

    assert get_model_dir() == tmp_path


def test_tableformer_dir_requires_expected_files(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDICAL_REDACTOR_MODEL_DIR", str(tmp_path))
    _touch_all(tmp_path / "tableformer-onnx", TABLEFORMER_FILES - {"tm_config.json"})

    from medical_redactor_onnx.paths import tableformer_dir

    with pytest.raises(FileNotFoundError, match="tm_config.json"):
        tableformer_dir(require=True)

    (tmp_path / "tableformer-onnx" / "tm_config.json").write_text("{}", encoding="utf-8")
    assert tableformer_dir(require=True) == tmp_path / "tableformer-onnx"


def test_hubert_ner_dir_requires_expected_files(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDICAL_REDACTOR_MODEL_DIR", str(tmp_path))
    _touch_all(tmp_path / "hubert-ner-onnx", HUBERT_FILES - {"model.onnx", "labels.json"})

    from medical_redactor_onnx.paths import hubert_ner_dir

    with pytest.raises(FileNotFoundError) as exc:
        hubert_ner_dir(require=True)

    assert "model.onnx" in str(exc.value)
    assert "labels.json" in str(exc.value)

    (tmp_path / "hubert-ner-onnx" / "model.onnx").write_text("x", encoding="utf-8")
    (tmp_path / "hubert-ner-onnx" / "labels.json").write_text("{}", encoding="utf-8")
    assert hubert_ner_dir(require=True) == tmp_path / "hubert-ner-onnx"


def test_frozen_non_windows_app_uses_user_data_dir(tmp_path, monkeypatch):
    import sys

    from medical_redactor_onnx import paths

    monkeypatch.delenv(paths.MODEL_DIR_ENV, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    result = paths.get_model_dir()
    assert result == tmp_path / "medical-redactor" / "models"


def test_frozen_windows_models_live_beside_executable_and_migrate(
    tmp_path, monkeypatch
):
    import sys

    from medical_redactor_onnx import paths

    install_dir = tmp_path / "Programs" / "Medical Redactor"
    executable = install_dir / "medical-redactor.exe"
    legacy_models = tmp_path / "medical-redactor" / "models"
    (legacy_models / "hubert-ner-onnx").mkdir(parents=True)
    (legacy_models / "hubert-ner-onnx" / "model.onnx").write_bytes(b"model")

    monkeypatch.delenv(paths.MODEL_DIR_ENV, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", str(executable))

    result = paths.get_model_dir()

    assert result == install_dir / "models"
    assert (result / "hubert-ner-onnx" / "model.onnx").read_bytes() == b"model"
    assert not legacy_models.exists()


def test_env_override_beats_frozen(tmp_path, monkeypatch):
    import sys

    from medical_redactor_onnx import paths

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv(paths.MODEL_DIR_ENV, str(tmp_path / "override"))
    assert paths.get_model_dir() == (tmp_path / "override").resolve()
