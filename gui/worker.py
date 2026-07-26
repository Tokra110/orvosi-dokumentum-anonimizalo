"""Background thread running the redaction pipeline with Qt signals."""

import logging
import threading

from PySide6.QtCore import QThread, Signal

_LOGGER = logging.getLogger(__name__)


class RedactionWorker(QThread):
    file_event = Signal(str, str, object, str)  # path, stage, counts|None, error
    log_line = Signal(str)
    progress_changed = Signal(int, int)

    def __init__(self, pdf_paths: list[str], output_dir: str | None, parent=None):
        super().__init__(parent)
        self._paths = list(pdf_paths)
        self._output_dir = output_dir
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        from redactor import process_pdfs

        try:
            process_pdfs(
                self._paths,
                self._output_dir,
                stop_event=self._stop_event,
                log=self.log_line.emit,
                progress=self.progress_changed.emit,
                on_file_event=lambda ev: self.file_event.emit(
                    ev.path, ev.stage, ev.counts, ev.error or ""
                ),
            )
        except Exception as e:
            _LOGGER.exception("Redaction worker failed")
            self.log_line.emit(f"FATAL ERROR: {e}")
