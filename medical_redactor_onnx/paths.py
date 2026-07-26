from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR_ENV = "MEDICAL_REDACTOR_MODEL_DIR"


def _user_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / "medical-redactor"

TABLEFORMER_REQUIRED_FILES = (
    "encoder.onnx",
    "encoder.onnx.data",
    "decoder_step.onnx",
    "decoder_step.onnx.data",
    "bbox_decoder.onnx",
    "bbox_decoder.onnx.data",
    "word_map.json",
    "tm_config.json",
)

HUBERT_NER_REQUIRED_FILES = (
    "model.onnx",
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
    "labels.json",
)


def get_model_dir() -> Path:
    override = os.environ.get(MODEL_DIR_ENV)
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        # Installed bundle: the app dir is read-only, so downloaded models
        # go to the per-user data dir instead.
        return _user_data_dir() / "models"
    return PROJECT_ROOT / "models"


def _artifact_dir(name: str, required_files: tuple[str, ...], require: bool) -> Path:
    path = get_model_dir() / name
    if require:
        missing = [filename for filename in required_files if not (path / filename).exists()]
        if missing:
            missing_list = ", ".join(missing)
            raise FileNotFoundError(f"Missing {name} artifact(s) in {path}: {missing_list}")
    return path


def tableformer_dir(require: bool = False) -> Path:
    return _artifact_dir("tableformer-onnx", TABLEFORMER_REQUIRED_FILES, require)


def hubert_ner_dir(require: bool = False) -> Path:
    return _artifact_dir("hubert-ner-onnx", HUBERT_NER_REQUIRED_FILES, require)
