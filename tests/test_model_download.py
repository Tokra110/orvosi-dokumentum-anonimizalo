"""Tests for the manifest-driven model downloader (no Qt involved)."""

import hashlib
import http.server
import threading

import pytest

from medical_redactor_onnx.download import (
    DownloadCancelled,
    DownloadError,
    FileSpec,
    ModelSpec,
    download_model,
)


@pytest.fixture
def served_dir(tmp_path):
    """Serve tmp_path/source over local HTTP; yield (source_dir, base_url)."""
    source = tmp_path / "source" / "test-model"
    source.mkdir(parents=True)

    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(
        *args, directory=str(tmp_path / "source"), **kwargs
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield source, f"http://127.0.0.1:{server.server_address[1]}/test-model"
    server.shutdown()


def _spec(source, base_url, files):
    file_specs = []
    for name in files:
        data = (source / name).read_bytes()
        file_specs.append(FileSpec(name=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    return ModelSpec(name="test-model", description="test", base_url=base_url, files=tuple(file_specs))


def test_downloads_verifies_and_installs(tmp_path, monkeypatch, served_dir):
    source, base_url = served_dir
    monkeypatch.setenv("MEDICAL_REDACTOR_MODEL_DIR", str(tmp_path / "models"))
    (source / "model.onnx").write_bytes(b"weights" * 1000)
    (source / "labels.json").write_bytes(b'{"0": "O"}')
    spec = _spec(source, base_url, ["model.onnx", "labels.json"])

    events = []
    download_model(spec, progress=lambda done, total: events.append((done, total)))

    target = tmp_path / "models" / "test-model"
    assert (target / "model.onnx").read_bytes() == b"weights" * 1000
    assert (target / "labels.json").exists()
    assert not list(target.glob("*.part"))
    assert events[-1] == (spec.total_bytes, spec.total_bytes)


def test_checksum_mismatch_discards_file(tmp_path, monkeypatch, served_dir):
    source, base_url = served_dir
    monkeypatch.setenv("MEDICAL_REDACTOR_MODEL_DIR", str(tmp_path / "models"))
    (source / "model.onnx").write_bytes(b"corrupted content")
    spec = ModelSpec(
        name="test-model",
        description="test",
        base_url=base_url,
        files=(FileSpec(name="model.onnx", bytes=17, sha256="0" * 64),),
    )

    with pytest.raises(DownloadError, match="Checksum mismatch"):
        download_model(spec)

    target = tmp_path / "models" / "test-model"
    assert not (target / "model.onnx").exists()
    assert not list(target.glob("*.part"))


def test_existing_complete_file_is_skipped(tmp_path, monkeypatch, served_dir):
    source, base_url = served_dir
    model_dir = tmp_path / "models" / "test-model"
    model_dir.mkdir(parents=True)
    monkeypatch.setenv("MEDICAL_REDACTOR_MODEL_DIR", str(tmp_path / "models"))
    (source / "model.onnx").write_bytes(b"payload")
    spec = _spec(source, base_url, ["model.onnx"])
    # Pre-place a file with the right size but different content: it must be
    # left alone (size check only — presence implies a prior verified install).
    (model_dir / "model.onnx").write_bytes(b"locally!"[:7])

    download_model(spec)
    assert (model_dir / "model.onnx").read_bytes() == b"locally"


def test_cancel_leaves_no_partial_file(tmp_path, monkeypatch, served_dir):
    source, base_url = served_dir
    monkeypatch.setenv("MEDICAL_REDACTOR_MODEL_DIR", str(tmp_path / "models"))
    (source / "model.onnx").write_bytes(b"x" * 4_000_000)
    spec = _spec(source, base_url, ["model.onnx"])

    with pytest.raises(DownloadCancelled):
        download_model(spec, should_cancel=lambda: True)

    target = tmp_path / "models" / "test-model"
    assert not (target / "model.onnx").exists()
    assert not list(target.glob("*.part"))


def test_no_base_url_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDICAL_REDACTOR_MODEL_DIR", str(tmp_path / "models"))
    spec = ModelSpec(
        name="test-model",
        description="test",
        base_url=None,
        files=(FileSpec(name="model.onnx", bytes=1, sha256="0" * 64),),
    )
    with pytest.raises(DownloadError, match="No download source"):
        download_model(spec)


def test_manifest_specs_cover_required_files():
    """The shipped manifest must list every runtime-required file with hashes."""
    from medical_redactor_onnx.download import load_model_specs
    from medical_redactor_onnx.paths import (
        HUBERT_NER_REQUIRED_FILES,
        TABLEFORMER_REQUIRED_FILES,
    )

    specs = {s.name: s for s in load_model_specs()}
    for name, required in (
        ("hubert-ner-onnx", HUBERT_NER_REQUIRED_FILES),
        ("tableformer-onnx", TABLEFORMER_REQUIRED_FILES),
    ):
        listed = {f.name for f in specs[name].files}
        assert set(required) <= listed, f"{name} manifest missing {set(required) - listed}"
        for f in specs[name].files:
            assert len(f.sha256) == 64
            assert f.bytes > 0
