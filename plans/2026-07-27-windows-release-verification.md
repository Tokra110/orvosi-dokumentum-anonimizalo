# Windows release verification implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent a Windows release from being published unless the installed application downloads its real models, opens the real GUI, processes vector and scanned PDFs, redacts their contents and filenames, writes output, and survives an upgrade from the previous published installer.

**Architecture:** Add a release-only command to the normal executable so PyInstaller must bundle and execute the same modules used by the GUI. A PowerShell verifier installs the candidate, runs that command on a real Windows runner, installs the previous release, upgrades it, and repeats the check while confirming that models and logs survive. The existing release workflow gains a manual non-publishing candidate mode and uses the same full verifier before tag-triggered publication.

**Tech Stack:** Python 3.13, PySide6, ReportLab, Pillow, Docling Slim, ONNX Runtime, PyInstaller, Inno Setup, PowerShell, GitHub Actions, pytest

---

### Task 1: Add self-contained installed-application verification

**Files:**
- Create: `release_harness.py`
- Modify: `main.py`
- Test: `tests/test_release_harness.py`

- [ ] **Step 1: Write failing tests for fixture generation and output validation**

Create tests that call `create_test_pdfs(tmp_path / "input")` and assert that it returns one Unicode-named vector PDF and one image-only PDF. Add a validation test that creates two redacted Markdown files and confirms that `validate_outputs()` rejects raw values such as `Teszt Elek`, `teszt.elek@example.com`, `+36 30 123 4567`, and `123 456 788`.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
MEDICAL_REDACTOR_MODEL_DIR="$PWD/models" .venv/bin/python -m pytest tests/test_release_harness.py -v
```

Expected: collection or import failure because `release_harness.py` does not exist.

- [ ] **Step 3: Implement the release harness**

Create `release_harness.py` with focused functions:

```python
def create_test_pdfs(input_dir: Path) -> list[Path]:
    """Create a vector medical PDF with a table and an image-only OCR PDF."""

def validate_outputs(output_dir: Path, expected_count: int) -> list[Path]:
    """Require non-empty redacted Markdown, redacted filenames, and preserved table text."""

def download_and_verify_models() -> None:
    """Use the shipped manifest downloader, then hash every installed file."""

def run_release_verification(work_dir: Path) -> int:
    """Download models, process both PDFs, validate output, then smoke-test the GUI."""
```

The vector document must contain a valid TAJ number (`123 456 788`), email, phone, `Teszt Elek`, and a small lab table containing `GGT` and `Na+`. The scanned document must render the same PII into a page image so RapidOCR is required. After `process_pdfs()`, require two Markdown outputs, typed redaction placeholders, no raw fixture PII, redacted filenames, and table content in the vector result.

Create the GUI smoke test with a normal `QApplication`, `MainWindow.show()`, and a `QTimer.singleShot(1500, app.quit)`. Do not set an offscreen Qt platform so the Windows platform plugin is actually loaded.

- [ ] **Step 4: Add the executable command**

In `main.py`, recognize:

```text
--release-verify <working-directory>
```

Import `run_release_verification()` only in this command branch, return a nonzero exit code on any exception, and keep normal GUI startup unchanged.

- [ ] **Step 5: Run focused and source end-to-end tests**

Run:

```bash
MEDICAL_REDACTOR_MODEL_DIR="$PWD/models" .venv/bin/python -m pytest tests/test_release_harness.py tests/test_docling_table_registration.py tests/test_ner_onnx.py -v
```

Expected: all tests pass.

### Task 2: Verify fresh install and real upgrade on Windows

**Files:**
- Create: `scripts/verify_windows_installer.ps1`
- Test: `tests/test_windows_packaging.py`

- [ ] **Step 1: Add failing packaging-contract tests**

Require the PowerShell verifier to:

```text
install the candidate into a fresh temporary directory
run --release-verify against that installed executable
download the latest published Windows setup executable
install the previous release into the normal per-user directory
seed models and logs
install the candidate over it
confirm _internal was replaced
confirm models and logs survived
run --release-verify again after the upgrade
print the diagnostic log when verification fails
```

- [ ] **Step 2: Run the focused packaging tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_windows_packaging.py -v
```

Expected: failure because `scripts/verify_windows_installer.ps1` does not exist and the workflow does not call it.

- [ ] **Step 3: Implement the PowerShell verifier**

Create a parameterized script:

```powershell
param(
  [Parameter(Mandatory = $true)][string]$CandidateInstaller,
  [Parameter(Mandatory = $true)][string]$Repository,
  [Parameter(Mandatory = $true)][string]$WorkRoot
)
```

Use `Start-Process -Wait -PassThru` for every installer and executable. Treat every nonzero exit code as fatal. For the fresh check, install to `$WorkRoot\fresh-install`, set `HF_HOME` to a new empty directory, run `--release-verify`, and require two `.md` files.

For the upgrade check, use the GitHub latest-release API to download the previous `*-setup.exe`, install it normally, create preservation sentinels under `models` and `logs`, create a stale file under `_internal`, install the candidate normally, and assert that the sentinels remain while the stale runtime file is gone. Copy the verified real models from the fresh installation into the default installation before upgrading so the upgrade check covers real model preservation without downloading them twice. Run `--release-verify` again and print `logs\medical-redactor.log` if it fails.

- [ ] **Step 4: Run the focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_windows_packaging.py -v
```

Expected: all packaging-contract tests pass.

### Task 3: Make full Windows verification block publication

**Files:**
- Modify: `.github/workflows/release.yml`
- Test: `tests/test_windows_packaging.py`

- [ ] **Step 1: Add failing workflow tests**

Require:

```yaml
workflow_dispatch:
```

Require the Windows job to run `scripts/verify_windows_installer.ps1`. Require the release job to run only for a `refs/tags/v` ref and only after the full Windows verifier succeeds. Preserve the existing rule that release bundles themselves do not contain model files.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_windows_packaging.py -v
```

Expected: failure because the workflow has no manual candidate mode and does not call the full verifier.

- [ ] **Step 3: Update the workflow**

Add manual dispatch without publishing. On manual runs, skip the Linux and release jobs and build only the Windows candidate with version `9999.0.0-candidate.<run number>` so Inno Setup treats installation over the current published release as a real upgrade. On version tags, retain Linux packaging and publication, but call the same Windows verifier before artifacts are uploaded. Give the release job an explicit tag-only condition.

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_windows_packaging.py tests/test_release_harness.py -v
```

Expected: all tests pass.

### Task 4: Validate locally and on a real Windows candidate runner

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Document the new release rule**

Document that a release candidate must first pass the manual release workflow, including real model download, fresh Docling layout download, vector PDF, OCR PDF, GUI startup, output validation, and previous-version upgrade. State that a tag run repeats the same Windows verification before publication.

- [ ] **Step 2: Run the complete local verification**

Run:

```bash
MEDICAL_REDACTOR_MODEL_DIR="$PWD/models" .venv/bin/python -m pytest -v
MEDICAL_REDACTOR_MODEL_DIR="$PWD/models" ./dist/medical-redactor/medical-redactor --selftest
.venv/bin/python -m pip freeze | grep -Ei '^(torch|torchvision|triton|nvidia)' && exit 1 || true
git diff --check
```

Expected: all runnable tests pass, the frozen self-test passes with NER, no prohibited runtime packages are listed, and `git diff --check` is clean.

- [ ] **Step 3: Build a fresh local frozen bundle**

Run:

```bash
.venv/bin/pyinstaller packaging/medical-redactor.spec --noconfirm
MEDICAL_REDACTOR_MODEL_DIR="$PWD/models" ./dist/medical-redactor/medical-redactor --selftest
```

Expected: build exits successfully and the rebuilt frozen self-test passes.

- [ ] **Step 4: Commit and push the harness without tagging**

Run:

```bash
git add main.py release_harness.py scripts/verify_windows_installer.ps1 \
  .github/workflows/release.yml tests/test_release_harness.py \
  tests/test_windows_packaging.py README.md CLAUDE.md \
  plans/2026-07-27-windows-release-verification.md
git commit -m "ci: verify installed Windows PDF processing"
git push origin main
```

Expected: the commit is on `main` and pushed. Do not create a tag.

- [ ] **Step 5: Dispatch and monitor the non-publishing candidate**

Run:

```bash
gh workflow run release.yml --ref main
gh run watch <run-id> --exit-status
```

Expected: Windows build, fresh install, real model download, empty-cache Docling initialization, vector conversion, OCR conversion, GUI smoke test, and previous-version upgrade all pass. No GitHub Release is created.

### Self-review

- Requirement coverage: The plan covers installed Windows startup, GUI construction, app and Docling model downloads, NER, layout, TableFormer, OCR, Unicode filenames, output content and names, fresh install, previous-version upgrade, preservation, diagnostics, non-publishing candidate execution, and tag publication blocking.
- Placeholder scan: No deferred implementation placeholders remain.
- Type consistency: `run_release_verification(work_dir: Path) -> int` is the single executable entry point used by `main.py`; PowerShell invokes the matching `--release-verify <working-directory>` command in both fresh and upgrade checks.
