# Orvosi dokumentum anonimizáló (medical record redactor)

PySide6 desktop app that converts Hungarian medical PDF records to redacted markdown. Removes patient PII (names, TAJ numbers, addresses, phones, emails, dates of birth) using a two-layer pipeline: HuBERT NER model + Hungarian-specific regex patterns.

## Commands

```bash
# setup (runtime is torch-free; uses Python 3.13 because deps need <3.14)
# setup.sh requires local ONNX artifacts under models/ and verifies that the
# runtime venv contains no torch, torchvision, triton, or nvidia-* packages.
cd ~/dev/general-home/projects/medical-redactor
bash setup.sh

# run
.venv/bin/python main.py

# headless sanity check (heavy imports + converter build + NER if models present)
.venv/bin/python main.py --selftest

# regenerate models_manifest.json (per-file bytes+sha256) after re-exporting models;
# provide a release URL only when model hosting is explicitly restored
.venv/bin/python scripts/make_models_manifest.py \
  --base-url <release-base-url>

# release build (lean bundle, no models; see packaging/)
.venv/bin/pip install -r requirements-build.txt
.venv/bin/pyinstaller packaging/medical-redactor.spec --noconfirm
./dist/medical-redactor/medical-redactor --selftest
bash packaging/build_rpm.sh 0.1.0

# export-only tooling (needs a separate venv from requirements-export.txt; pulls torch)
python scripts/export_tableformer_onnx.py
python scripts/export_hubert_onnx.py
```

## Repository lifecycle

- Repository name: `orvosi-dokumentum-anonimizalo`.
- The GitHub remote was intentionally deleted on 2026-07-26. Do not create a remote, push commits, or publish model releases unless the user explicitly asks.
- When the user explicitly requests a new remote, recreate it with the repository name above and then configure a new model-release URL.

## Architecture

```
main.py                  -- thin Qt entry point (QApplication + icon + QSS) and --selftest
gui/                     -- PySide6 UI package
  main_window.py         --   queue-based main window: add files/folder, start/stop,
                         --   output-mode menu, model-status chip, manual redact card, log,
                         --   HU/EN language toggle + _retranslate()
  models_dialog.py       --   model status + in-app downloader dialog (QThread worker)
  queue_model.py         --   table model for the per-file processing queue
  worker.py              --   RedactionWorker QThread wrapping process_pdfs with signals
  settings.py            --   settings.json persistence + log sanitization (no Qt imports)
  i18n.py                --   HU (default) / EN string registry + t(); no Qt imports
  theme.py               --   QSS theme
redactor.py              -- orchestration: Docling conversion, ONNX NER loading, regex PII detection, redaction
medical_redactor_onnx/   -- torch-free ONNX adapters for Docling TableFormer and HuBERT NER
  download.py            --   Qt-free manifest-driven model downloader (sha256 + atomic .part install)
  paths.py               --   model dir resolution (env override > frozen Windows app dir / other user-data dir > repo models/)
models_manifest.json     -- per-file {name, bytes, sha256} + per-model base_url for the downloader
models/                  -- gitignored local model artifacts
onnx-tableformer/        -- spike-era exporter source (loaded by scripts/export_tableformer_onnx.py)
scripts/                 -- export_*.py (torch, export venv only) + make_models_manifest.py
packaging/               -- PyInstaller spec, rpm spec + build script, system .desktop file
.github/workflows/       -- release.yml: Linux tar.gz+rpm, Windows zip on v* tags
setup.sh                 -- creates .venv, installs runtime deps, verifies artifacts + dependency hygiene
requirements.txt         -- torch-free runtime deps
requirements-export.txt  -- export-time deps that may pull torch
requirements-build.txt   -- runtime deps + PyInstaller for release builds
```

`main.py` stays a thin entry point, `gui/` holds all UI, and `redactor.py`
stays the public pipeline API. The ONNX bridge code lives in focused modules
because Docling registration, TableFormer inference, and token-classification
grouping are too large for the old two-file rule.

## Pipeline (redactor.py)

Per-file processing order:
1. **Docling Slim** converts PDF to markdown (preserves tables)
   - Layout is forced through Docling's ONNX Runtime layout engine.
   - Table structure uses the app-local ONNX TableFormer adapter registered before `DocumentConverter()` is built.
   - OCR uses RapidOCR's ONNX Runtime backend (`english` model; lightweight Latin OCR).
2. **NER** runs first (`_find_ner_pii`): ONNX HuBERT detects PER, LOC, ORG in 800-char chunks with 200-char overlap. A second pass shifted by half a stride heals entities cut or context-starved at pass-1 chunk boundaries; pass-2 hits are only accepted within 100 chars of a pass-1 boundary (interior pass-2-only hits are mostly noise — observed eating lab analyte names like "Nátrium"). Entities below `_NER_MIN_SCORE` (0.7, corpus-calibrated — see the comment on the constant before changing) are discarded. NER is ~25% of per-file time; conversion dominates.
3. **Regex** runs second (`_find_regex_pii`): TAJ (with checksum), phones, emails, birth dates (context-sensitive), addresses, names near field labels (title-case AND all-caps), Dr.-prefixed/suffixed names, clinician-title-suffixed names ("X Y Optometrista"), "részére"-anchored names, doctor stamp IDs (EESZT), company IDs (cégjegyzékszám, adószám), record IDs (naplószám, sorszám, munkaszám, védettségi igazolvány szám)
4. **Noise filter**: `_drop_isolated_midword_spans` removes NER spans ≤4 chars that cut into a word with no supporting span within 2 chars (kills "Mo|unjaro"-style drug/analyte eating; longer mid-word fragments are real names and must stay — dropping them leaked on the corpus)
5. **Merge** spans (NER takes priority on overlap since it runs first)
6. **Name-adjacent ID sweep**: `_find_ids_near_names` redacts bare 5-6 digit stamp IDs within 60 chars of any NAME span (doctor stamps float before/after/below the name in the wild), then a final merge
7. **Redact** replaces spans with typed placeholders like `[REDACTED_NAME]`, `[REDACTED_TAJ]`
8. **Filename redaction**: output filenames also have names stripped via `redact_filename()`

## Key design decisions

- **NER before regex**: NER spans take priority in `_merge_spans` because they appear first in the list
- **Birth dates only**: `_DATE_NUMERIC_RE` and `_DATE_TEXT_RE` only redact dates near birth keywords (`_is_birth_date` checks 80 chars before the match). Examination dates are preserved intentionally.
- **No doctor name filtering**: all names are redacted, including doctors, per user request
- **Log sanitization**: `sanitize_log()` in gui/settings.py strips all file paths and PDF/MD filenames from log output so logs are safe to share
- **Manual redact**: post-processing card in the main window that generates all permutations of an entered value (reordered, hyphenated, concatenated, subparts) and replaces them across all output .md files
- **Queue-based UI**: "Add PDF files" / "Add folder" (QFileDialog) fill a queue table; Start runs `process_pdfs(paths, ...)` on a `RedactionWorker` QThread with per-file stage events (rows flag zero-name results amber for manual review). `process_folder()` is a thin wrapper that globs a folder and calls `process_pdfs`.
- **Output mode menu**: a footer QToolButton menu toggles "Beside originals" (`output_dir=None`, each `.md` written next to its source PDF) vs "Choose folder…". Persisted as `output_mode`/`output_dir` in settings.json (legacy `save_beside` still read for migration).
- **Dialogs remember last location**: all pickers start at `last_dir` from settings.json, updated on every successful pick. Config writes are read-modify-write (`update_config`) so keys don't clobber each other.
- **UI language (HU default / EN)**: all user-facing strings live in `gui/i18n.py` as an `{key: {"hu", "en"}}` registry read through `t(key, **fmt)`; there is no Qt `.ts`/`tr()` machinery. A segmented HU/EN toggle in the header (`_build_lang_toggle`) flips `i18n._lang`, persists `language` to settings.json, and calls `MainWindow._retranslate()`, which re-pushes every string onto the live widgets — no window rebuild. `QueueModel.retranslate()` repaints headers/cells; `ModelsDialog` is rebuilt each open so it just reads the current language. When adding UI text, add a key to `i18n.py` (both languages) and a matching line in `_retranslate()` if the widget persists; never hardcode a display string in `gui/`.
- **In-app model downloader**: the header model-status chip opens `ModelsDialog`; missing models download on a QThread via `medical_redactor_onnx/download.py` — streamed to `.part`, sha256-verified against `models_manifest.json`, atomically renamed, size-matched existing files skipped. Models are hosted as flat assets on the GitHub `models-v1` release (both models share one `base_url`; filenames are globally unique — the manifest script enforces this). Re-exported weights go to a NEW tag (`models-v2`, ...) + manifest regen, never overwrite old assets in place: shipped app versions pin old manifests. While the repo is private, asset URLs need auth, so the in-app download only works publicly.
- **Torch-free runtime split**: runtime installs `docling-slim` + `onnxruntime` only. Export scripts are separate and may use torch to regenerate ONNX artifacts.
- **Local model artifacts**: generated files live under `models/tableformer-onnx/` and `models/hubert-ner-onnx/`; `models/` is gitignored except `.gitkeep`. Frozen Windows bundles keep models beside the executable because the installer uses the writable per-user `%LOCALAPPDATA%\Programs\Medical Redactor` location. The first run migrates models from the older `%LOCALAPPDATA%\medical-redactor\models` location. Frozen Linux bundles continue using `~/.local/share/medical-redactor/models` because RPM installation directories are read-only.
- **Lean release strategy**: release artifacts ship without models (~700 MB onedir vs ~1.4 GB); users fetch models via the in-app downloader on first run. Docling fetches its own layout/OCR models into the HF cache.
- **Docling shims**: `install_docling_torch_free_shims()` disables optional torch-backed chart extraction, replaces Docling's torch-based device resolver with CPU, and supplies minimal reading-order/list-item shims so `docling-ibm-models` is not imported at runtime.

## Hungarian PII patterns

- **TAJ szam**: `\d{3}[-\s]?\d{3}[-\s]?\d{3}` with checksum validation (weights [3,7,3,7,3,7,3,7], mod 10)
- **Names**: matched by 30+ Hungarian field label keywords (beteg neve, anyja neve, szuletesi neve, etc.) with accent-flexible regex (`[eé]`, `[aá]`, `[uü]`). Supports names across line breaks, hyphens, dots.
- **Addresses**: street type suffixes (utca, ut, ter, korut, etc.) + postal code patterns
- **Phones**: +36/06 prefix patterns, plus bare mobile forms like `30/482-7035` (slash-separated, no prefix)
- **Name parts regex**: `_HU_NAME_PART` matches capitalized Hungarian words including married suffix "ne". `_HU_FULL_NAME` matches 2-5 parts separated by spaces, hyphens, en/em dashes, or dots.
- **Dr. names**: `_DR_PREFIX_NAME_RE` / `_DR_SUFFIX_NAME_RE` catch "Dr. Fekete Éva", "Dr.Homonai", "Fekete Éva Dr." as a deterministic backstop for NER. Separators deliberately exclude newlines so the pattern can't swallow the first word of the next sentence.
- **Doctor stamp IDs** (`DOCTOR_ID`): "EESZT: O43048", parenthesized IDs after a name ("(azonosító: 220756)", "(36563)"), and bare letter+5-digit stamps after a name ("Fekete Éva  O43048 adjunktus"). Doctor names are redacted, so the publicly searchable stamp ID must go too or the doctor is re-identifiable.
- **Company IDs** (`COMPANY_ID`): cégjegyzékszám `##-##-######`, adószám `########-#-##` (bare formats, no label needed).
- **Record IDs** (`RECORD_ID`): label-anchored naplószám/naplósorszám values plus the composite EESZT form `<institution>-<year>-<serial>`. The composite also outranks a false TAJ hit on its 9-digit prefix at merge (longer span wins).
- **Institution codes stay**: 9-digit codes after `NNGYK:`/`NEAK:` labels routinely pass the TAJ checksum but identify the lab, not the patient — `_INSTITUTION_CODE_LABEL_RE` suppresses the TAJ match there.

## Gotchas

- **Python 3.14 breaks everything**: huspacy, MinerU, and many ML libs need `<3.14`. The venv MUST use Python 3.13: `python3.13 -m venv .venv`
- **Do not install top-level `docling` for runtime**: use `docling-slim[...]` from `requirements.txt`. Top-level/full Docling pulls the torch/docling-ibm stack back in.
- **Export deps are separate**: `requirements-export.txt` is allowed to install torch, full `docling`, `onnx`, and `onnxscript`; never add those to runtime requirements.
- **NER uses the tokenizers lib, but transformers is still a runtime dep (2026-07-12)**: `OnnxNerPipeline` loads `tokenizer.json` directly via `tokenizers.Tokenizer` (verified bit-identical entities incl. scores vs the old AutoTokenizer path). However `transformers` cannot leave requirements.txt: docling-slim's ONNX layout engine imports `transformers.AutoImageProcessor` at conversion time without declaring the dependency. Hostage until upstream drops it.
- **NER truncation bug**: never enable truncation on the NER tokenizer — silently dropping tail tokens means missed PII. The chunking handles length limits instead.
- **512-token chunk overflow**: the 800-char NER chunks are token-based-limit safe for prose but NOT for dense markdown tables (lab values tokenize ~1 token per digit/symbol). `_find_ner_pii` therefore checks `count_tokens(chunk)` and recursively halves oversized chunks before ONNX inference. Don't remove that check.
- **GPU VRAM**: the RTX 3090 also drives the Wayland display (kwin_wayland). Never launch persistent GPU server processes (llama-server, vLLM) without checking free VRAM first. Starving the compositor causes a black screen requiring hard reboot.
- **Docling converter**: build it through `build_docling_converter()` only, then reuse it across files. It registers ONNX TableFormer and installs torch-free Docling shims before imports settle.
- **TableFormer ONNX maintenance**: this app owns the ONNX TableFormer adapter until Docling ships an official torch-free table-structure model. Validate on real lab tables before upgrading Docling.
- **TableFormer bbox clamp is a deliberate upstream deviation**: `multi_table_predict` clamps table bboxes to page bounds before cropping and skips fully degenerate boxes. The layout model can emit slightly out-of-page coords (negative top observed on a scanned invoice); upstream's unclamped slice yields an empty crop and cv2.resize aborts the whole page. Keep the guard when re-syncing with upstream.
- **TableFormer preprocessing is load-bearing**: `_prepare_image` must transpose to **(channels, width, height)** — upstream trains on that orientation; feeding standard (C,H,W) mangles row structure into merged cells. Same for cell matching: `CellMatcher`+`MatchingPostProcessor` (vendored in `medical_redactor_onnx/vendor/`, pure numpy) snap predicted cells to PDF text tokens; without them table quality collapses (~70% content loss on real lab reports). Keep `do_cell_matching=True`.
- **Vendored upstream modules**: `medical_redactor_onnx/vendor/` holds `tf_cell_matcher.py`, `matching_post_processor.py`, `otsl.py`, `settings.py` copied from docling-ibm-models 3.13.2 (import paths rewritten, no other edits). Re-sync when regenerating ONNX artifacts against a newer upstream.
- **HuBERT ONNX is fp32**: quantization is not done yet. Runtime size is lower than torch, but the NER artifact is still hundreds of MB.
- **ONNX CPU tradeoff**: ONNX avoids multi-GB torch/CUDA wheels, but per-table CPU inference can be slower than torch CPU before optimization.
- **Runtime deps slimmed 2026-07-12**: `pymupdf4llm` removed (unused since Docling became the only converter; dragged in 113 MB of pymupdf) and full `PySide6` replaced by `PySide6-Essentials` — the GUI uses only QtCore/QtGui/QtWidgets, and the Addons half is ~400 MB (WebEngine etc.). Never import Qt modules outside Essentials and never reintroduce full `PySide6`.
- **docling-slim format extras are NOT optional**: `format-html,format-latex,format-markdown,format-office` look PDF-irrelevant, but docling's `document_converter.py` unconditionally imports every format backend at module level (bs4, marko, python-pptx, ...). Trimming them breaks `DocumentConverter` import entirely. "Slim" means torch-free, not backend-free. `scipy` is likewise a real docling-slim dependency (declared under an extras marker `pip show` doesn't attribute).
- **`_FIELD_SEP` includes `\n`**: name field labels and their values can be on separate lines in the markdown output, so the separator pattern matches across line breaks.

## Validation

```bash
MEDICAL_REDACTOR_MODEL_DIR="$PWD/models" .venv/bin/python -m pytest -v
.venv/bin/python -m pip freeze | grep -Ei 'torch|triton|nvidia' || true
du -sh .venv models

# optional private corpus check
MEDICAL_REDACTOR_MODEL_DIR="$PWD/models" \
MEDICAL_REDACTOR_TEST_PDF_DIR="/path/to/private/test/pdfs" \
.venv/bin/python -m pytest tests/test_real_docs_optional.py -v

# frozen bundle check (after a PyInstaller build)
MEDICAL_REDACTOR_MODEL_DIR="$PWD/models" ./dist/medical-redactor/medical-redactor --selftest
```

## Config

User settings stored at `~/.config/medical-redactor/settings.json` (`output_mode`, `output_dir`, `last_dir`, `language`; legacy `save_beside` is still read once to derive `output_mode` for old configs). The output-mode menu writes its state immediately on change; `last_dir` is updated automatically by every file/folder dialog; `language` (`"hu"` default, `"en"`) is written by the header HU/EN toggle. Loaded on startup by `MainWindow.__init__`.

## Desktop entry

Dev install: `~/.local/share/applications/medical-redactor.desktop`, pinned to KDE favorites. `Exec=` calls the venv interpreter directly (`.venv/bin/python main.py` — no `activate` needed) and `Path=` sets the working directory. Do not wrap the command in `bash -c '...'`: the Desktop Entry spec only supports double-quote quoting, so a single-quoted argument gets split at spaces and the launch breaks.

The rpm ships its own system-wide entry (`packaging/medical-redactor.desktop` → `/usr/share/applications/`) pointing at `/usr/bin/medical-redactor`.
