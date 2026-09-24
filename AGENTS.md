# Orvosi dokumentum anonimizáló (medical record redactor)

PySide6 desktop app that turns Hungarian medical PDFs into redacted Markdown: Docling converts, ONNX HuBERT NER and Hungarian regex rules strip patient PII. Torch-free runtime. Own git repo, public on GitHub.

## Commands

```bash
bash setup.sh                                   # Python 3.13 venv, deps, checks models/ and no torch
.venv/bin/python main.py                        # run
.venv/bin/python main.py --selftest             # quick headless check
MEDICAL_REDACTOR_MODEL_DIR="$PWD/models" .venv/bin/python -m pytest -v
xvfb-run -a .venv/bin/python main.py --release-verify /tmp/medical-redactor-release-check   # full release gate
.venv/bin/pyinstaller packaging/medical-redactor.spec --noconfirm && bash packaging/build_rpm.sh 0.1.0
```

## Hard rules

- **Never commit private information. No session log, by policy.** `notes.md` and `plans/` are gitignored; commits use the repo's anonymous git identity.
- Tests, comments and docs use invented names, IDs, dates and addresses only. Never copy text from a real record, not even a short line.
- Push, tag or release only when the maintainer asks. A `v*` tag publishes a GitHub Release.
- Python 3.13 only; 3.14 breaks the ML dependencies.
- Never add torch, full `docling` or full `PySide6` to `requirements.txt`.
- Never enable truncation on the NER tokenizer; never remove the oversized-chunk halving in `_find_ner_pii`.
- Build the Docling converter only through `build_docling_converter()`, and reuse it.
- Every UI string goes through `gui/i18n.py` (HU default, EN).
- New weights go to a new release tag plus manifest; never overwrite assets.
- Keep the full Windows release gate; `--selftest` is not a substitute.

## First gotchas

- Keep the docling-slim format extras; Docling imports every backend at module level.
- `transformers` stays in the runtime: docling-slim imports it undeclared.
- TableFormer preprocessing transposes to (C, W, H) on purpose; cell matching must stay on.
- Desktop entry: never wrap `Exec=` in `bash -c '...'`.

`manual.md` has the pipeline, PII patterns, decisions and all gotchas.
