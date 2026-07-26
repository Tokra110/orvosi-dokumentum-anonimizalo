"""Release packaging contract for the Windows installer."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pyinstaller_embeds_windows_icon():
    spec = (ROOT / "packaging" / "medical-redactor.spec").read_text()

    assert 'icon="../assets/icon.ico"' in spec
    assert (ROOT / "assets" / "icon.ico").is_file()


def test_pyinstaller_embeds_docling_pdf_resources():
    spec = (ROOT / "packaging" / "medical-redactor.spec").read_text()

    assert 'collect_data_files("docling_parse")' in spec


def test_pyinstaller_embeds_docling_plugin_registration():
    spec = (ROOT / "packaging" / "medical-redactor.spec").read_text()

    assert 'copy_metadata("docling-slim")' in spec
    assert '"docling.models.plugins.defaults"' in spec


def test_inno_installer_has_standard_per_user_behavior():
    installer = (ROOT / "packaging" / "medical-redactor.iss").read_text()

    assert "PrivilegesRequired=lowest" in installer
    assert r"DefaultDirName={localappdata}\Programs\Medical Redactor" in installer
    assert r"UninstallDisplayIcon={app}\medical-redactor.exe" in installer
    assert r'Name: "{group}\{#MyAppName}"' in installer
    assert r'Name: "{autodesktop}\{#MyAppName}"' in installer
    assert "ArchitecturesAllowed=x64compatible" in installer
    assert "ArchitecturesInstallIn64BitMode=x64compatible" in installer
    assert "VersionInfoProductVersion={#MyAppNumericVersion}" in installer


def test_inno_installer_wraps_complete_onedir_bundle():
    installer = (ROOT / "packaging" / "medical-redactor.iss").read_text()

    assert r'Source: "..\dist\medical-redactor\*"' in installer
    assert "Flags: ignoreversion recursesubdirs createallsubdirs" in installer
    assert '#define MyAppExeName "medical-redactor.exe"' in installer
    assert r'Filename: "{app}\{#MyAppExeName}"' in installer


def test_inno_installer_replaces_only_the_immutable_runtime_tree():
    installer = (ROOT / "packaging" / "medical-redactor.iss").read_text()

    assert "[InstallDelete]" in installer
    assert r'Type: filesandordirs; Name: "{app}\_internal"' in installer
    assert r'Type: filesandordirs; Name: "{app}\models"' not in installer
    assert r'Type: filesandordirs; Name: "{app}\logs"' not in installer


def test_inno_uninstaller_offers_to_remove_downloaded_models_by_default():
    installer = (ROOT / "packaging" / "medical-redactor.iss").read_text()

    assert "RemoveDownloadedModelsPrompt" in installer
    assert "MB_YESNOCANCEL" in installer
    assert "IDYES" in installer
    assert r"DelTree(ExpandConstant('{app}\models')" in installer
    assert r"{localappdata}\medical-redactor\models" in installer
    assert r"DelTree(ExpandConstant('{app}\logs')" not in installer


def test_release_workflow_publishes_installer_and_portable_zip():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()

    assert "choco install innosetup --no-progress -y" in workflow
    assert "ISCC.exe" in workflow
    assert "packaging\\medical-redactor.iss" in workflow
    assert "dist/*-setup.exe" in workflow
    assert "dist/*.zip" in workflow


def test_release_workflow_tests_the_installed_windows_application():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()

    assert "Verify installed Windows application" in workflow
    assert "scripts\\verify_windows_installer.ps1" in workflow
    assert "-CandidateInstaller" in workflow


def test_windows_installer_verifier_covers_fresh_install_and_real_upgrade():
    verifier = ROOT / "scripts" / "verify_windows_installer.ps1"

    assert verifier.is_file()
    script = verifier.read_text()
    assert "--release-verify" in script
    assert "fresh-install" in script
    assert "releases/latest" in script
    assert "*-setup.exe" in script
    assert "release-verification.json" in script
    assert r"_internal\stale-runtime-file.txt" in script
    assert "preserve-models.txt" in script
    assert "preserve-logs.txt" in script
    assert "Final candidate uninstaller" in script
    assert "uninstaller left downloaded models behind" in script
    assert "uninstaller unexpectedly removed diagnostic logs" in script
    assert "Copy-Item" in script
    assert "Get-Content" in script


def test_release_workflow_has_non_publishing_full_windows_candidate_gate():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow
    assert "scripts\\verify_windows_installer.ps1" in workflow
    assert "9999.0.0-candidate." in workflow
    assert "startsWith(github.ref, 'refs/tags/v')" in workflow
    assert "needs.windows.result == 'success'" in workflow
    assert "needs.linux.result == 'success'" in workflow


def test_windows_selftest_requires_pdfium_backend():
    entrypoint = (ROOT / "main.py").read_text()

    assert "unexpected Windows PDF backend" in entrypoint
    assert "selftest: Windows PDFium backend OK" in entrypoint
    assert "PictureDescriptionVlmEngineOptions" in entrypoint
    assert "docling plugin registry OK" in entrypoint


def test_release_workflow_does_not_download_models():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()

    assert "models-v1" not in workflow
    assert "MEDICAL_REDACTOR_MODEL_DIR" not in workflow


def test_linux_release_runner_installs_qt_egl_runtime():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()

    assert "sudo apt-get install -y rpm libegl1" in workflow


def test_xdg_platform_theme_is_linux_only():
    entrypoint = (ROOT / "main.py").read_text()

    assert 'if sys.platform.startswith("linux"):' in entrypoint
    assert (
        'if sys.platform.startswith("linux"):\n'
        '    os.environ.setdefault("QT_QPA_PLATFORMTHEME", "xdgdesktopportal")'
    ) in entrypoint
