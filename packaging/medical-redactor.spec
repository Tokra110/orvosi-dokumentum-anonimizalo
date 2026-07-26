# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: lean onedir bundle (no model artifacts).

Models are downloaded in-app on first run (gui/models_dialog.py) into the
per-user data dir (paths.py handles sys.frozen). Docling's layout + OCR
models are fetched by docling itself into the Hugging Face cache.

Build:  .venv/bin/pyinstaller packaging/medical-redactor.spec --noconfirm
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ("../models_manifest.json", "."),
    ("../assets", "assets"),
]
# RapidOCR ships its ONNX models + yaml config as package data and imports
# lazily (only when a scanned page needs OCR), so nothing pulls it in
# automatically.
datas += collect_data_files("rapidocr")

hiddenimports = collect_submodules("rapidocr")

a = Analysis(
    ["../main.py"],
    pathex=[".."],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "torch", "torchvision", "FixTk"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="medical-redactor",
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="medical-redactor",
)
