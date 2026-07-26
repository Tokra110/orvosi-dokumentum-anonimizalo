import os
import sys
from pathlib import Path

# Route file dialogs through the XDG desktop portal so the desktop's own
# file picker (Dolphin on KDE, Nautilus on GNOME, ...) is used instead of
# Qt's built-in dialog. PySide6 bundles its own Qt, so distro theme plugins
# like plasma-integration can't load into it; the portal is the
# desktop-agnostic path. Qt falls back to its own dialog if no portal runs.
os.environ.setdefault("QT_QPA_PLATFORMTHEME", "xdgdesktopportal")

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow
from gui.theme import APP_QSS

ICON_PATH = Path(__file__).resolve().parent / "assets" / "icon.svg"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Orvosi dokumentum anonimizáló")
    app.setDesktopFileName("medical-redactor")
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    app.setStyleSheet(APP_QSS)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


def selftest() -> int:
    """Headless check that a frozen bundle has everything wired: heavy
    imports resolve, the Docling converter builds, and (if model artifacts
    are installed) the ONNX NER pipeline runs. No GUI, no display needed."""
    from medical_redactor_onnx import paths
    from redactor import build_docling_converter

    build_docling_converter()
    print("selftest: docling converter OK")
    try:
        model_dir = paths.hubert_ner_dir(require=True)
    except FileNotFoundError:
        print(f"selftest: NER models not installed at {paths.get_model_dir()} "
              "(expected for a lean bundle) — skipping NER check")
        return 0
    from medical_redactor_onnx.ner_onnx import OnnxNerPipeline

    entities = OnnxNerPipeline(model_dir)("Kovács Béláné Budapesten él.")
    print(f"selftest: NER OK ({len(entities)} entities)")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    main()
