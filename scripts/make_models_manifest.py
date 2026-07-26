#!/usr/bin/env python
"""Regenerate models_manifest.json from the local model artifacts.

Hashes every required file under models/ (per medical_redactor_onnx.paths)
and writes name/bytes/sha256 entries so the in-app downloader can verify
what it fetches. Run this after re-exporting ONNX artifacts and before
uploading them to the hosting location.

Existing base_url values are preserved unless --base-url-root is given,
in which case each model's base_url becomes <root>/<model-name>.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from medical_redactor_onnx.paths import (  # noqa: E402
    HUBERT_NER_REQUIRED_FILES,
    TABLEFORMER_REQUIRED_FILES,
    get_model_dir,
)

MANIFEST_PATH = ROOT / "models_manifest.json"

MODELS = (
    ("hubert-ner-onnx", "Hungarian HuBERT NER (ONNX, fp32)", HUBERT_NER_REQUIRED_FILES),
    ("tableformer-onnx", "Docling TableFormer table structure (ONNX)", TABLEFORMER_REQUIRED_FILES),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url-root",
        help="Set each model's base_url to <root>/<model-name> "
        "(directory-style hosting, e.g. https://huggingface.co/<user>/<repo>/resolve/main)",
    )
    parser.add_argument(
        "--base-url",
        help="Set the SAME base_url for every model (flat hosting, e.g. a GitHub "
        "release: https://github.com/<user>/<repo>/releases/download/<tag>). "
        "Requires globally unique filenames across models.",
    )
    args = parser.parse_args()
    if args.base_url and args.base_url_root:
        raise SystemExit("Use either --base-url or --base-url-root, not both.")

    if args.base_url:
        # Flat hosting has one namespace: refuse to build a manifest that
        # would make two models fetch the same asset.
        all_files = [f for _, _, required in MODELS for f in required]
        duplicates = {f for f in all_files if all_files.count(f) > 1}
        if duplicates:
            raise SystemExit(f"Filename collision across models: {sorted(duplicates)}")

    existing_base_urls: dict[str, str | None] = {}
    if MANIFEST_PATH.exists():
        for entry in json.loads(MANIFEST_PATH.read_text())["models"]:
            existing_base_urls[entry["name"]] = entry.get("base_url")

    models = []
    for name, description, required_files in MODELS:
        model_dir = get_model_dir() / name
        files = []
        for filename in required_files:
            path = model_dir / filename
            if not path.exists():
                raise SystemExit(f"Missing artifact: {path} — export the models first.")
            files.append(
                {
                    "name": filename,
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
        if args.base_url:
            base_url = args.base_url.rstrip("/")
        elif args.base_url_root:
            base_url = f"{args.base_url_root.rstrip('/')}/{name}"
        else:
            base_url = existing_base_urls.get(name)
        total_mb = round(sum(f["bytes"] for f in files) / 1_000_000)
        models.append(
            {
                "name": name,
                "description": description,
                "approx_size_mb": total_mb,
                "base_url": base_url,
                "files": files,
            }
        )

    MANIFEST_PATH.write_text(json.dumps({"models": models}, indent=2) + "\n")
    for model in models:
        print(f"{model['name']}: {len(model['files'])} files, ~{model['approx_size_mb']} MB")
    print(f"Wrote {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
