"""Download model artifacts listed in models_manifest.json.

Qt-free so it can be unit-tested and reused outside the GUI; the models
dialog wraps it in a QThread. Files are streamed to a ".part" file,
sha256-verified, then renamed into place, so an interrupted or corrupted
download never leaves a half-written artifact behind.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .paths import get_model_dir

MANIFEST_PATH = Path(__file__).resolve().parents[1] / "models_manifest.json"

_CHUNK_BYTES = 1 << 20
_TIMEOUT_SECONDS = 30


class DownloadCancelled(Exception):
    """Raised when the caller's should_cancel() hook returns True."""


class DownloadError(Exception):
    """Raised on network failures, missing configuration, or checksum mismatch."""


@dataclass(frozen=True)
class FileSpec:
    name: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class ModelSpec:
    name: str
    description: str
    base_url: str | None
    files: tuple[FileSpec, ...]

    @property
    def total_bytes(self) -> int:
        return sum(f.bytes for f in self.files)


def load_model_specs(manifest_path: Path = MANIFEST_PATH) -> list[ModelSpec]:
    manifest = json.loads(manifest_path.read_text())
    specs = []
    for entry in manifest["models"]:
        specs.append(
            ModelSpec(
                name=entry["name"],
                description=entry["description"],
                base_url=entry.get("base_url"),
                files=tuple(
                    FileSpec(f["name"], f["bytes"], f["sha256"])
                    for f in entry.get("files", ())
                ),
            )
        )
    return specs


def download_model(
    spec: ModelSpec,
    progress: Callable[[int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> None:
    """Download every missing file of one model into the model dir.

    progress(done_bytes, total_bytes) is called after each chunk. Files
    already present with the expected size are skipped, so a partially
    completed model only fetches what is missing.
    """
    if not spec.base_url:
        raise DownloadError(f"No download source configured for '{spec.name}'")
    if not spec.files:
        raise DownloadError(f"Manifest lists no files for '{spec.name}'")

    target_dir = get_model_dir() / spec.name
    target_dir.mkdir(parents=True, exist_ok=True)

    total = spec.total_bytes
    done = 0
    for file in spec.files:
        target = target_dir / file.name
        if target.exists() and target.stat().st_size == file.bytes:
            done += file.bytes
            if progress:
                progress(done, total)
            continue
        done = _download_file(spec.base_url, file, target, done, total, progress, should_cancel)


def _download_file(
    base_url: str,
    file: FileSpec,
    target: Path,
    done: int,
    total: int,
    progress: Callable[[int, int], None] | None,
    should_cancel: Callable[[], bool] | None,
) -> int:
    url = f"{base_url.rstrip('/')}/{file.name}"
    part = target.parent / (target.name + ".part")
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={"User-Agent": "medical-redactor"})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as resp:
            with open(part, "wb") as out:
                while True:
                    if should_cancel and should_cancel():
                        raise DownloadCancelled()
                    chunk = resp.read(_CHUNK_BYTES)
                    if not chunk:
                        break
                    out.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(min(done, total), total)
    except DownloadCancelled:
        part.unlink(missing_ok=True)
        raise
    except OSError as e:
        part.unlink(missing_ok=True)
        raise DownloadError(f"Downloading {url} failed: {e}") from e

    if digest.hexdigest() != file.sha256:
        part.unlink(missing_ok=True)
        raise DownloadError(
            f"Checksum mismatch for {file.name}; the corrupted download was discarded"
        )
    part.replace(target)
    return done
