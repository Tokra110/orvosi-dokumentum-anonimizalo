# Orvosi dokumentum anonimizáló manual

How the redactor works and why. The brief is `AGENTS.md`. There is no session log by policy: never commit private information to this repo.

## Repository

- Public GitHub repo `Tokra110/orvosi-dokumentum-anonimizalo`. The app downloads its models from this repo's releases, so it must stay public or the downloader breaks.
- Commits use the anonymous identity in the repo's local git config (`Medical Redactor contributors`). Keep it, so no personal name enters the public history.
- Push, tag or publish a model release only when the maintainer asks. Pushing a `v*` tag runs `release.yml`, which publishes a GitHub Release.

## Architecture

| Path | What it does |
|---|---|
| `main.py` | Thin Qt entry point. Also `--selftest` and `--release-verify <dir>`. |
| `redactor.py` | The public pipeline API: conversion, NER, regex rules, redaction. |
| `gui/` | PySide6 UI: queue main window, queue model, `RedactionWorker` thread, models dialog, `settings.py`, `i18n.py`, theme. |
| `medical_redactor_onnx/` | Torch-free ONNX adapters for TableFormer and HuBERT NER, Docling registration and shims, model downloader (`download.py`), model paths (`paths.py`), `vendor/`. |
| `diagnostics.py` | Rotating log file, cleaned by `sanitize_log`. |
| `release_harness.py` | The installed release gate that `--release-verify` runs. |
| `models_manifest.json` | Name, size and sha256 per model file, plus each model's `base_url`. |
| `models/` | Local model files, gitignored. |
| `scripts/` | `export_*_onnx.py` (torch, export venv only), `make_models_manifest.py`, `verify_windows_installer.ps1`. |
| `onnx-tableformer/` | Exporter source that `scripts/export_tableformer_onnx.py` loads. |
| `packaging/` | PyInstaller spec, RPM spec and build script, Inno Setup script, system `.desktop` file. |
| `.github/workflows/release.yml` | Windows candidate on a manual run; full release on a `v*` tag. |
| `requirements*.txt` | Runtime (torch-free), build (adds PyInstaller), export (pulls torch). |

`main.py` stays thin, `gui/` holds all UI and `redactor.py` stays the public API.

## Pipeline

Per file, in `process_file_detailed`:

1. **Convert** the PDF to Markdown with Docling Slim, which keeps tables. Layout runs on Docling's ONNX engine, tables on our ONNX TableFormer, OCR on RapidOCR's ONNX backend (`english` model, enough for Latin text). A note spanning a full table row appears once, not once per cell.
2. **NER** (`_find_ner_pii`): ONNX HuBERT finds PER, LOC and ORG in 800-character chunks with a 200-character overlap. A second pass, shifted by half a stride, repairs entities cut at chunk edges. Its hits count only within 100 characters of a first-pass boundary; elsewhere they are mostly noise and ate lab analyte names like "Nátrium". Hits under `_NER_MIN_SCORE` (0.7, tuned on the corpus; read the comment before changing it) are dropped.
3. **Regex** (`_find_regex_pii`): the Hungarian patterns below.
4. **Noise filter** (`_drop_isolated_midword_spans`): adjacent NER fragments are judged together. A fragment inside one word with no regex support is dropped, so clinical terms like `Par|ath|ormon` survive. Fragmented names stay redacted, including known Hungarian case suffixes.
5. **Merge** (`_merge_spans`): overlapping spans join. The span that starts first (then the longer one) keeps its label; on an exact tie NER wins because its spans come first.
6. **ID sweep** (`_find_ids_near_names`): bare 5-6 digit stamp IDs within 60 characters of a name are redacted, because doctor stamps sit around the name. Then the spans merge again.
7. **Redact**: spans become typed placeholders such as `[REDACTED_NAME]` and `[REDACTED_TAJ]`.
8. **File names**: `redact_filename()` removes names from output file names too.

## Hungarian PII patterns

- **TAJ number:** `\d{3}[-\s]?\d{3}[-\s]?\d{3}` with checksum validation (weights 3,7,3,7,3,7,3,7; mod 10).
- **Institution codes stay:** 9-digit codes after `NNGYK:` or `NEAK:` often pass the TAJ checksum but identify the lab, not the patient. `_INSTITUTION_CODE_LABEL_RE` suppresses the TAJ match there.
- **Names by field label:** 30+ Hungarian labels (beteg neve, anyja neve, születési neve ...) with accent-flexible matching (`[eé]`, `[aá]`, `[uü]`). The value can be title case or all caps and can sit on the next line (`_FIELD_SEP` includes `\n`).
- **Name shape:** `_HU_NAME_PART` is a capitalised Hungarian word, including the married suffix "né". `_HU_FULL_NAME` is 2 to 5 parts joined by spaces, hyphens, dashes or dots.
- **Other name anchors:** "Dr." before or after a name (`_DR_PREFIX_NAME_RE`, `_DR_SUFFIX_NAME_RE`; no newlines inside, so the next sentence's first word is safe), a clinician title after a name ("<name> Optometrista"), and a name before "részére".
- **Doctor stamp IDs** (`DOCTOR_ID`): "EESZT: A12345", a bracketed ID after a name, and a bare letter plus 5 digits after a name. The stamp ID is public, so it would identify the redacted doctor.
- **Company IDs** (`COMPANY_ID`): cégjegyzékszám `##-##-######` and adószám `########-#-##`, no label needed.
- **Record IDs** (`RECORD_ID`): labelled naplószám, sorszám, munkaszám and védettségi igazolvány szám values, plus the EESZT composite `<institution>-<year>-<serial>`. At merge the composite beats a false TAJ hit on its 9-digit start, because it is longer.
- **Phones:** +36 and 06 prefixes, bare mobiles (`NN/NNN-NNNN`), bracketed landlines (`(06) NN-NNN-NNN`) and institutional slash forms with extensions (`NN/NNN - NNN/NNN`).
- **Addresses:** street type words (utca, út, tér, körút ...) and postal code plus town.
- **Emails**, and **birth dates** (see below).

## Design decisions

- **Only birth dates go:** `_DATE_NUMERIC_RE` and `_DATE_TEXT_RE` redact a date only when `_is_birth_date` finds a birth keyword in the 80 characters before it. Examination dates stay on purpose.
- **All names go, doctors included.**
- **Logs are safe to share:** `sanitize_log()` in `gui/settings.py` removes file paths and PDF/MD file names. `diagnostics.py` applies it to the log file as well.
- **Manual redact:** a card in the main window takes a value, builds its variants (reordered, hyphenated, joined, parts) and replaces them in every output `.md`.
- **Queue UI:** files or a folder go into a queue; Start runs `process_pdfs` on a `RedactionWorker` QThread. Rows with zero names turn amber for manual review.
- **Output location:** a footer menu picks "beside originals" (each `.md` next to its PDF) or a chosen folder.
- **UI language (HU default, EN):** strings live in `gui/i18n.py`, read through `t(key, **fmt)`; no Qt `.ts`/`tr()`. The header toggle calls `MainWindow._retranslate()`, which re-pushes every string without rebuilding the window. New UI text needs a key in both languages and, for a widget that stays on screen, a line in `_retranslate()`.
- **Model downloader:** the header model chip opens `ModelsDialog`. `medical_redactor_onnx/download.py` streams each missing file to `.part`, checks its sha256 against `models_manifest.json` and renames it into place. Both models share one `base_url` on the `models-v1` release, so file names must be unique (the manifest script enforces this).
- **New weights, new tag:** re-exported weights go to a new release tag (`models-v2`, ...) with a regenerated manifest. Never overwrite old assets: shipped app versions pin their manifest.
- **Torch-free runtime:** the runtime installs `docling-slim` and `onnxruntime` only. Export scripts use a separate venv that may pull torch.
- **Docling shims:** `install_docling_torch_free_shims()` turns off torch-based chart extraction, replaces the device resolver with CPU and adds small reading-order and list-item shims, so `docling-ibm-models` is never imported.
- **Windows PDF backend:** on Windows the converter uses PDFium and passes the PDF as a stream, because docling-parse fails there on Unicode paths and on a missing glyph map.
- **Lean releases:** bundles ship without models (about 700 MB instead of 1.4 GB). The app downloads them on first run; Docling fetches its own layout and OCR models into the Hugging Face cache.

## Model locations

- `MEDICAL_REDACTOR_MODEL_DIR` overrides everything.
- Development: `models/tableformer-onnx/` and `models/hubert-ner-onnx/` in the repo. `models/` is gitignored except `.gitkeep`.
- Frozen Windows app: `models/` beside the executable, because the installer puts the app in the writable per-user `%LOCALAPPDATA%\Programs\Medical Redactor`. The first run moves models from the old `%LOCALAPPDATA%\medical-redactor\models`.
- Frozen Linux app: `~/.local/share/medical-redactor/models`, because the RPM install folder is read-only.

## Releases

- **Full Windows release gate** (`release.yml`): a manual run builds and checks a Windows candidate without publishing. A `v*` tag runs the same gate plus Linux packaging before it publishes. The installed candidate downloads and hashes the real models, starts with an empty Docling cache, redacts a Unicode-named table PDF and an image-only OCR PDF, checks content and file names and opens the real window. Then it upgrades over the previous installer and checks again. **Do not replace this gate with `--selftest`.**
- `--selftest` is the quick headless check: imports, PDF backend, converter and, when models are present, NER.
- **Windows uninstall** asks whether to remove the downloaded models. Yes is the default, also for a silent uninstall; `/KEEPMODELS` keeps them. Yes removes both `{app}\models` and the old `%LOCALAPPDATA%\medical-redactor\models`. Diagnostic logs stay.

## Gotchas

- **Python 3.13 only.** 3.14 breaks the ML dependencies. `setup.sh` creates the venv with `python3.13 -m venv .venv`.
- **Never install full `docling`, torch, `onnx` or `onnxscript` for the runtime.** They belong in `requirements-export.txt` only; full Docling pulls torch back in.
- **Keep the docling-slim format extras** (`format-html`, `format-latex`, `format-markdown`, `format-office`). Docling's `document_converter.py` imports every format backend at module level, so without them `DocumentConverter` fails to import. `scipy` is also a real docling-slim dependency.
- **`transformers` stays in the runtime requirements.** NER loads `tokenizer.json` directly through `tokenizers.Tokenizer`, but docling-slim's ONNX layout engine imports `transformers.AutoImageProcessor` without declaring it.
- **Qt: PySide6-Essentials only** (QtCore, QtGui, QtWidgets). Never bring back full `PySide6`; the Addons half is about 400 MB.
- **Never enable truncation on the NER tokenizer.** Dropped tail tokens mean missed PII. Chunking handles length instead.
- **Keep the oversized-chunk halving.** 800-character chunks fit the 512-token limit for prose but not for dense Markdown tables, where lab values take about one token per digit or symbol. `_find_ner_pii` checks `count_tokens(chunk)` and halves oversized chunks before inference.
- **Build the Docling converter only through `build_docling_converter()`,** then reuse it across files. It registers the ONNX TableFormer and installs the torch-free shims before imports settle.
- **TableFormer is ours to maintain** until Docling ships an official torch-free table model. Validate on real lab tables before upgrading Docling.
- **TableFormer bbox clamp is a deliberate upstream deviation.** `multi_table_predict` clamps table boxes to the page and skips degenerate ones, because a slightly out-of-page box makes `cv2.resize` abort the whole page. Keep it when re-syncing with upstream.
- **TableFormer preprocessing is load-bearing.** `_prepare_image` must transpose to (channels, width, height), the orientation upstream trained on; (C, H, W) merges rows. Keep `do_cell_matching=True`: cell matching snaps predicted cells to the PDF text, and without it lab reports lose most of their table content.
- **Vendored modules:** `medical_redactor_onnx/vendor/` holds four files from docling-ibm-models 3.13.2 with only the import paths changed. Re-sync them when you regenerate the ONNX files against a newer upstream.
- **HuBERT ONNX is fp32,** not quantized, so the NER model is still hundreds of MB. Per-table ONNX CPU inference can be slower than torch CPU.
- **GPU VRAM:** the development machine's GPU also drives the display. Check free VRAM before starting any persistent GPU server (llama-server, vLLM); starving the compositor gives a black screen that needs a hard reboot.

## Validation

```bash
MEDICAL_REDACTOR_MODEL_DIR="$PWD/models" .venv/bin/python -m pytest -v
.venv/bin/python -m pip freeze | grep -Ei 'torch|triton|nvidia' || true   # must print nothing
du -sh .venv models

# optional private corpus check
MEDICAL_REDACTOR_MODEL_DIR="$PWD/models" \
MEDICAL_REDACTOR_TEST_PDF_DIR="/path/to/private/test/pdfs" \
.venv/bin/python -m pytest tests/test_real_docs_optional.py -v

# frozen bundle check (after a PyInstaller build)
MEDICAL_REDACTOR_MODEL_DIR="$PWD/models" ./dist/medical-redactor/medical-redactor --selftest
```

## Config

User settings are in `~/.config/medical-redactor/settings.json`: `output_mode`, `output_dir`, `last_dir` and `language` (`"hu"` default or `"en"`). Every file and folder dialog starts at `last_dir` and updates it. Writes are read-modify-write through `update_config`, so keys do not overwrite each other. An old `save_beside` key is still read once to derive `output_mode`.

## Desktop entry

The dev install is `~/.local/share/applications/medical-redactor.desktop`, pinned to KDE favorites. `Exec=` calls `.venv/bin/python main.py` with absolute paths and `Path=` sets the working directory; no `activate` is needed. **Never wrap the command in `bash -c '...'`:** the Desktop Entry spec only supports double quotes, so a single-quoted argument splits at spaces and the launch fails.

The RPM ships its own entry (`packaging/medical-redactor.desktop`, installed to `/usr/share/applications/`) that runs `/usr/bin/medical-redactor`.
