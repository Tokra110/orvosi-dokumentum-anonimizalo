"""Model artifact status + download dialog.

Each model row shows Installed / Download / an in-flight progress bar.
Downloads run on a QThread wrapping medical_redactor_onnx.download, which
streams to a .part file and sha256-verifies before install, so a failed or
cancelled download never leaves a broken artifact. One download at a time.
"""

from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from gui.i18n import t
from medical_redactor_onnx.download import (
    DownloadCancelled,
    DownloadError,
    ModelSpec,
    download_model,
    load_model_specs,
)
from medical_redactor_onnx.paths import (
    HUBERT_NER_REQUIRED_FILES,
    TABLEFORMER_REQUIRED_FILES,
    get_model_dir,
)

_REQUIRED_FILES = {
    "hubert-ner-onnx": HUBERT_NER_REQUIRED_FILES,
    "tableformer-onnx": TABLEFORMER_REQUIRED_FILES,
}


@dataclass
class ModelStatus:
    spec: ModelSpec
    missing: list[str]

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def description(self) -> str:
        return self.spec.description

    @property
    def approx_size_mb(self) -> int:
        return round(self.spec.total_bytes / 1_000_000)

    @property
    def ready(self) -> bool:
        return not self.missing


def model_statuses() -> list[ModelStatus]:
    statuses = []
    for spec in load_model_specs():
        model_dir = get_model_dir() / spec.name
        required = _REQUIRED_FILES.get(spec.name, ())
        missing = [f for f in required if not (model_dir / f).exists()]
        statuses.append(ModelStatus(spec=spec, missing=missing))
    return statuses


def all_models_ready() -> bool:
    return all(s.ready for s in model_statuses())


class _DownloadWorker(QThread):
    progress = Signal(int, int)  # done_bytes, total_bytes
    succeeded = Signal()
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, spec: ModelSpec, parent=None):
        super().__init__(parent)
        self._spec = spec
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            download_model(
                self._spec,
                progress=self.progress.emit,
                should_cancel=lambda: self._cancel,
            )
        except DownloadCancelled:
            self.cancelled.emit()
        except DownloadError as e:
            self.failed.emit(str(e))
        else:
            self.succeeded.emit()


class _ModelRow:
    """Widgets for one model in the dialog grid."""

    def __init__(self, status: ModelStatus, grid: QGridLayout, row: int):
        self.status = status
        self.name_label = QLabel(status.description)
        self.size_label = QLabel(f"~{status.approx_size_mb} MB")
        self.size_label.setObjectName("mutedLabel")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, max(status.approx_size_mb, 1))
        self.progress_bar.setFormat("%v / %m MB")
        self.progress_bar.hide()
        self.installed_chip = QLabel(t("installed"))
        self.installed_chip.setObjectName("modelChipReady")
        self.button = QPushButton(t("download"))

        grid.addWidget(self.name_label, row, 0)
        grid.addWidget(self.size_label, row, 1)
        grid.addWidget(self.progress_bar, row, 2)
        grid.addWidget(self.installed_chip, row, 3)
        grid.addWidget(self.button, row, 3)
        self.show_idle()

    def show_idle(self):
        self.progress_bar.hide()
        self.installed_chip.setVisible(self.status.ready)
        self.button.setVisible(not self.status.ready)
        self.button.setText(t("download"))

    def show_downloading(self):
        self.installed_chip.hide()
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.button.setText(t("cancel"))
        self.button.show()


class ModelsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("models_title"))
        self.setMinimumWidth(520)
        self._worker: _DownloadWorker | None = None
        self._active_row: _ModelRow | None = None

        layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setColumnStretch(2, 1)
        self._rows = []
        for i, status in enumerate(model_statuses()):
            row = _ModelRow(status, grid, i)
            row.button.clicked.connect(lambda _=False, r=row: self._on_button(r))
            self._rows.append(row)
        layout.addLayout(grid)

        hint = QLabel(t("model_folder", dir=get_model_dir()))
        hint.setObjectName("mutedLabel")
        layout.addWidget(hint)

        close = QPushButton(t("close"))
        close.clicked.connect(self.accept)
        layout.addWidget(close)

    # --- download control ---

    def _on_button(self, row: _ModelRow):
        if row is self._active_row:
            self._worker.cancel()
            row.button.setEnabled(False)  # until the worker acknowledges
            return
        self._start_download(row)

    def _start_download(self, row: _ModelRow):
        if not row.status.spec.base_url:
            QMessageBox.information(
                self,
                t("dl_not_configured_title"),
                t(
                    "dl_not_configured_body",
                    name=row.status.name,
                    dir=get_model_dir() / row.status.name,
                ),
            )
            return
        self._active_row = row
        row.show_downloading()
        for other in self._rows:
            if other is not row:
                other.button.setEnabled(False)

        self._worker = _DownloadWorker(row.status.spec, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, done_bytes: int, total_bytes: int):
        if self._active_row:
            self._active_row.progress_bar.setMaximum(max(total_bytes // 1_000_000, 1))
            self._active_row.progress_bar.setValue(done_bytes // 1_000_000)

    def _on_succeeded(self):
        self._finish_download()

    def _on_cancelled(self):
        self._finish_download()

    def _on_failed(self, error: str):
        self._finish_download()
        QMessageBox.warning(self, t("dl_failed_title"), error)

    def _finish_download(self):
        self._active_row = None
        self._worker = None
        statuses = {s.name: s for s in model_statuses()}
        for row in self._rows:
            row.status = statuses[row.status.name]
            row.button.setEnabled(True)
            row.show_idle()

    def done(self, result):
        # Covers both the Close button (accept) and the titlebar X (reject).
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(5000)
        super().done(result)
