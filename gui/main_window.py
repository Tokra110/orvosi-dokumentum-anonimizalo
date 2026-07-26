"""Main window: queue-first UI. Drag PDFs in, watch per-file results."""

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui import i18n, settings
from gui.i18n import t
from gui.models_dialog import ModelsDialog, all_models_ready
from gui.queue_model import QueueModel
from gui.worker import RedactionWorker

_STAGE_ACTIVITY = {
    "converting": "activity_converting",
    "redacting": "activity_redacting",
}


def _card(name: str = "card") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName(name)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(8)
    return frame, layout


def _accent_bar() -> QFrame:
    bar = QFrame()
    bar.setObjectName("accentBar")
    return bar


class CollapsibleSection(QWidget):
    """A toggle strip that smoothly expands/collapses its content."""

    def __init__(
        self,
        title: str,
        hint: str,
        content: QWidget,
        expanded_height: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._expanded_height = expanded_height
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._toggle = QToolButton()
        self._toggle.setObjectName("sectionToggle")
        self._toggle.setText(f"{title}  ·  {hint}")
        self.set_labels = lambda ti, hi: self._toggle.setText(f"{ti}  ·  {hi}")
        self._toggle.setCheckable(True)
        self._toggle.setChecked(False)
        self._toggle.setArrowType(Qt.RightArrow)
        self._toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._toggle.setCursor(Qt.PointingHandCursor)
        self._toggle.toggled.connect(self._on_toggled)

        self._content = content
        self._content.setMinimumHeight(0)
        self._content.setMaximumHeight(0)

        self._anim = QPropertyAnimation(self._content, b"maximumHeight", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._after_anim)

        layout.addWidget(self._toggle)
        layout.addWidget(self._content)

    def _on_toggled(self, checked: bool):
        self._toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        expanded = self._expanded_height or self._content.sizeHint().height()
        self._anim.stop()
        if not checked:
            self._content.setMinimumHeight(0)
        self._anim.setStartValue(min(self._content.height(), expanded) if not checked else 0)
        self._anim.setEndValue(expanded if checked else 0)
        self._anim.start()

    def _after_anim(self):
        if self._toggle.isChecked():
            self._content.setMaximumHeight(self._expanded_height or 16777215)
            if self._expanded_height:
                self._content.setMinimumHeight(self._expanded_height)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("rootWindow")
        self.resize(800, 680)
        self.setAcceptDrops(True)

        self.queue = QueueModel(self)
        self.worker: RedactionWorker | None = None

        cfg = settings.load_config()
        i18n.set_language(cfg.get("language", i18n.get_language()))
        self.setWindowTitle(t("app_title"))
        self._output_mode = cfg.get(
            "output_mode",
            "folder" if (not cfg.get("save_beside", True) and cfg.get("output_dir")) else "beside",
        )
        self._output_dir = cfg.get("output_dir", "")

        self._build_ui()
        self._refresh_model_chip()
        self._refresh_output_button()

    # --- UI construction ---

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        band = QFrame()
        band.setObjectName("headerBand")
        band_layout = QHBoxLayout(band)
        band_layout.setContentsMargins(16, 10, 16, 10)
        band_layout.setSpacing(10)
        icon_label = QLabel()
        icon_path = Path(__file__).resolve().parents[1] / "assets" / "icon.svg"
        icon_label.setPixmap(QIcon(str(icon_path)).pixmap(28, 28))
        band_layout.addWidget(icon_label)
        self.app_title = QLabel(t("app_title"))
        self.app_title.setObjectName("appTitle")
        band_layout.addWidget(self.app_title)
        band_layout.addStretch()
        band_layout.addWidget(self._build_lang_toggle())
        self.model_chip = QPushButton()
        self.model_chip.setFlat(True)
        self.model_chip.setCursor(Qt.PointingHandCursor)
        self.model_chip.setToolTip(t("chip_tooltip"))
        self.model_chip.clicked.connect(self._open_models_dialog)
        band_layout.addWidget(self.model_chip)
        outer.addWidget(band)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(10)
        outer.addWidget(content, stretch=1)

        self.missing_banner = QLabel(t("banner_missing"))
        self.missing_banner.setObjectName("missingBanner")
        self.missing_banner.setWordWrap(True)
        self.missing_banner.setVisible(False)
        root.addWidget(self.missing_banner)

        queue_card = QFrame()
        queue_card.setObjectName("card")
        card_outer = QVBoxLayout(queue_card)
        card_outer.setContentsMargins(0, 0, 0, 0)
        card_outer.setSpacing(0)

        body = QWidget()
        queue_layout = QVBoxLayout(body)
        queue_layout.setContentsMargins(14, 12, 14, 10)
        queue_layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addWidget(_accent_bar())
        self.queue_title = QLabel(t("queue_title"))
        self.queue_title.setObjectName("sectionTitle")
        title_row.addWidget(self.queue_title)
        title_row.addStretch()
        self.count_label = QLabel(t("count_empty"))
        self.count_label.setObjectName("mutedLabel")
        title_row.addWidget(self.count_label)
        queue_layout.addLayout(title_row)

        toolbar = QHBoxLayout()
        self.add_files_btn = QPushButton(t("add_files"))
        self.add_files_btn.clicked.connect(self._add_files)
        self.add_folder_btn = QPushButton(t("add_folder"))
        self.add_folder_btn.setToolTip(t("add_folder_tooltip"))
        self.add_folder_btn.clicked.connect(self._add_folder)
        self.clear_btn = QPushButton(t("clear"))
        self.clear_btn.setToolTip(t("clear_tooltip"))
        self.clear_btn.clicked.connect(self._clear_queue)
        self.drop_hint = QLabel(t("drop_hint"))
        self.drop_hint.setObjectName("mutedLabel")
        toolbar.addWidget(self.add_files_btn)
        toolbar.addWidget(self.add_folder_btn)
        toolbar.addWidget(self.clear_btn)
        toolbar.addStretch()
        toolbar.addWidget(self.drop_hint)
        queue_layout.addLayout(toolbar)

        self.table = QTableView()
        self.table.setModel(self.queue)
        self.table.setToolTip(t("table_tooltip"))
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 7):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        queue_layout.addWidget(self.table, stretch=1)
        card_outer.addWidget(body, stretch=1)

        footer_frame = QFrame()
        footer_frame.setObjectName("cardFooter")
        footer_layout = QVBoxLayout(footer_frame)
        footer_layout.setContentsMargins(14, 10, 14, 8)
        footer_layout.setSpacing(6)

        footer = QHBoxLayout()
        self.start_btn = QPushButton(t("start"))
        self.start_btn.setObjectName("startButton")
        self.start_btn.setToolTip(t("start_tooltip"))
        self.start_btn.clicked.connect(self._start)
        self.stop_btn = QPushButton(t("stop"))
        self.stop_btn.setEnabled(False)
        self.stop_btn.setToolTip(t("stop_tooltip"))
        self.stop_btn.clicked.connect(self._stop)
        self.output_btn = QToolButton()
        self.output_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.output_btn)
        self._output_beside_action = menu.addAction(
            t("output_beside_menu"), self._set_output_beside
        )
        self._output_choose_action = menu.addAction(
            t("output_choose_menu"), self._choose_output_folder
        )
        self.output_btn.setMenu(menu)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("mutedLabel")
        footer.addWidget(self.start_btn)
        footer.addWidget(self.stop_btn)
        footer.addWidget(self.output_btn)
        footer.addWidget(self.progress, stretch=1)
        footer.addWidget(self.progress_label)
        footer_layout.addLayout(footer)

        self.activity_label = QLabel(" ")
        self.activity_label.setObjectName("mutedLabel")
        footer_layout.addWidget(self.activity_label)
        card_outer.addWidget(footer_frame)
        root.addWidget(queue_card, stretch=1)

        root.addWidget(self._build_manual_card())

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_section = CollapsibleSection(
            t("log_title"), t("log_hint"), self.log_view, expanded_height=160,
        )
        root.addWidget(self.log_section)

    def _build_lang_toggle(self) -> QWidget:
        """Segmented HU | EN switch that flips the whole UI language."""
        wrap = QFrame()
        wrap.setObjectName("langToggle")
        row = QHBoxLayout(wrap)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(0)
        self._lang_group = QButtonGroup(self)
        self._lang_group.setExclusive(True)
        for lang in i18n.LANGUAGES:
            btn = QToolButton()
            btn.setObjectName("langOption")
            btn.setText(lang.upper())
            btn.setCheckable(True)
            btn.setChecked(lang == i18n.get_language())
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(t("lang_tooltip"))
            btn.clicked.connect(lambda _=False, code=lang: self._set_language(code))
            self._lang_group.addButton(btn)
            row.addWidget(btn)
        return wrap

    def _build_manual_card(self) -> QWidget:
        card, layout = _card("tintedCard")

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(_accent_bar())
        self.manual_title = QLabel(t("manual_title"))
        self.manual_title.setObjectName("sectionTitle")
        self.manual_title.setToolTip(t("manual_section_tip"))
        self.manual_hint = QLabel(t("manual_hint"))
        self.manual_hint.setObjectName("mutedLabel")
        self.manual_hint.setToolTip(t("manual_section_tip"))
        head.addWidget(self.manual_title)
        head.addWidget(self.manual_hint)
        head.addStretch()
        layout.addLayout(head)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        self.manual_value_label = QLabel(t("manual_value_label"))
        self.manual_value_label.setToolTip(t("manual_value_tip"))
        grid.addWidget(self.manual_value_label, 0, 0)
        self.manual_value = QLineEdit()
        self.manual_value.setPlaceholderText("Kiss Pál")
        self.manual_value.setToolTip(t("manual_value_tip"))
        grid.addWidget(self.manual_value, 0, 1)
        self.manual_type_label = QLabel(t("manual_type_label"))
        self.manual_type_label.setToolTip(t("manual_type_tip"))
        grid.addWidget(self.manual_type_label, 0, 2)
        self.manual_type = QComboBox()
        self.manual_type.addItems(
            ["NAME", "TAJ", "DOB", "ADDRESS", "PHONE", "EMAIL", "LOCATION", "ORG", "CUSTOM"]
        )
        self.manual_type.setToolTip(t("manual_type_tip"))
        grid.addWidget(self.manual_type, 0, 3)

        self.manual_folder_label = QLabel(t("manual_folder_label"))
        self.manual_folder_label.setToolTip(t("manual_folder_tip"))
        grid.addWidget(self.manual_folder_label, 1, 0)
        self.manual_dir = QLineEdit(self._output_dir)
        self.manual_dir.setPlaceholderText(t("manual_folder_placeholder"))
        self.manual_dir.setToolTip(t("manual_folder_tip"))
        grid.addWidget(self.manual_dir, 1, 1)
        self.browse_btn = QPushButton(t("browse"))
        self.browse_btn.clicked.connect(self._browse_manual_dir)
        grid.addWidget(self.browse_btn, 1, 2)
        self.manual_run_btn = QPushButton(t("manual_run"))
        self.manual_run_btn.setToolTip(t("manual_run_tooltip"))
        self.manual_run_btn.clicked.connect(self._manual_redact)
        grid.addWidget(self.manual_run_btn, 1, 3)

        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        return card

    # --- model status chip ---

    def _refresh_model_chip(self):
        ready = all_models_ready()
        self.model_chip.setText(t("chip_ready") if ready else t("chip_missing"))
        self.model_chip.setObjectName("modelChipReady" if ready else "modelChipMissing")
        self.model_chip.style().unpolish(self.model_chip)
        self.model_chip.style().polish(self.model_chip)
        self.missing_banner.setVisible(not ready)

    def _open_models_dialog(self):
        ModelsDialog(self).exec()
        self._refresh_model_chip()

    # --- language ---

    def _set_language(self, lang: str):
        if lang == i18n.get_language():
            return
        i18n.set_language(lang)
        settings.update_config(language=lang)
        self._retranslate()

    def _retranslate(self):
        """Push the current language onto every visible widget."""
        self.setWindowTitle(t("app_title"))
        self.app_title.setText(t("app_title"))
        self.model_chip.setToolTip(t("chip_tooltip"))
        self.missing_banner.setText(t("banner_missing"))

        self.queue_title.setText(t("queue_title"))
        self.add_files_btn.setText(t("add_files"))
        self.add_folder_btn.setText(t("add_folder"))
        self.add_folder_btn.setToolTip(t("add_folder_tooltip"))
        self.clear_btn.setText(t("clear"))
        self.clear_btn.setToolTip(t("clear_tooltip"))
        self.drop_hint.setText(t("drop_hint"))
        self.table.setToolTip(t("table_tooltip"))

        self.start_btn.setText(t("start"))
        self.start_btn.setToolTip(t("start_tooltip"))
        self.stop_btn.setText(t("stop"))
        self.stop_btn.setToolTip(t("stop_tooltip"))
        self._output_beside_action.setText(t("output_beside_menu"))
        self._output_choose_action.setText(t("output_choose_menu"))

        self.manual_title.setText(t("manual_title"))
        self.manual_title.setToolTip(t("manual_section_tip"))
        self.manual_hint.setText(t("manual_hint"))
        self.manual_hint.setToolTip(t("manual_section_tip"))
        self.manual_value_label.setText(t("manual_value_label"))
        self.manual_value_label.setToolTip(t("manual_value_tip"))
        self.manual_value.setToolTip(t("manual_value_tip"))
        self.manual_type_label.setText(t("manual_type_label"))
        self.manual_type_label.setToolTip(t("manual_type_tip"))
        self.manual_type.setToolTip(t("manual_type_tip"))
        self.manual_folder_label.setText(t("manual_folder_label"))
        self.manual_folder_label.setToolTip(t("manual_folder_tip"))
        self.manual_dir.setPlaceholderText(t("manual_folder_placeholder"))
        self.manual_dir.setToolTip(t("manual_folder_tip"))
        self.browse_btn.setText(t("browse"))
        self.manual_run_btn.setText(t("manual_run"))
        self.manual_run_btn.setToolTip(t("manual_run_tooltip"))

        self.log_section.set_labels(t("log_title"), t("log_hint"))

        for btn in self._lang_group.buttons():
            btn.setToolTip(t("lang_tooltip"))

        self.queue.retranslate()
        self._refresh_model_chip()
        self._refresh_count_label()
        self._refresh_output_button()

    # --- queue building ---

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, t("dlg_add_files"), settings.get_last_dir(), t("dlg_pdf_filter")
        )
        if paths:
            settings.remember_dir(str(Path(paths[0]).parent))
            self._enqueue(paths)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, t("dlg_add_folder"), settings.get_last_dir()
        )
        if folder:
            settings.remember_dir(folder)
            self._enqueue(sorted(str(p) for p in Path(folder).glob("*.pdf")))

    def _enqueue(self, paths: list[str]):
        added = self.queue.add_paths(paths)
        self._refresh_count_label()
        if added == 0 and paths:
            self._append_log(t("log_no_new"))

    def _clear_queue(self):
        if self.worker is None:
            self.queue.clear()
            self._refresh_count_label()

    def _refresh_count_label(self):
        n = self.queue.row_count_total()
        self.count_label.setText(t("count_empty") if n == 0 else t("count_files", n=n))

    def _table_menu(self, pos):
        if self.worker is not None:
            return
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        if not rows:
            return
        menu = QMenu(self)
        menu.addAction(t("remove_from_queue"), lambda: self._remove_rows(rows))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _remove_rows(self, rows):
        self.queue.remove_rows(rows)
        self._refresh_count_label()

    # --- drag and drop ---

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths: list[str] = []
        for url in event.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.is_dir():
                paths.extend(sorted(str(f) for f in p.glob("*.pdf")))
            elif p.suffix.lower() == ".pdf":
                paths.append(str(p))
        if paths:
            self._enqueue(paths)
        event.acceptProposedAction()

    # --- output selection ---

    def _set_output_beside(self):
        self._output_mode = "beside"
        settings.update_config(output_mode="beside")
        self._refresh_output_button()

    def _choose_output_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, t("dlg_output_folder"), settings.get_last_dir()
        )
        if folder:
            self._output_mode = "folder"
            self._output_dir = folder
            settings.update_config(output_mode="folder", output_dir=folder)
            settings.remember_dir(folder)
            if not self.manual_dir.text():
                self.manual_dir.setText(folder)
            self._refresh_output_button()

    def _refresh_output_button(self):
        explain = t("output_tooltip")
        if self._output_mode == "folder" and self._output_dir:
            self.output_btn.setText(t("output_folder_btn", name=Path(self._output_dir).name))
            self.output_btn.setToolTip(f"{self._output_dir}\n\n{explain}")
        else:
            self.output_btn.setText(t("output_beside_btn"))
            self.output_btn.setToolTip(explain)

    # --- run control ---

    def _start(self):
        if self.worker is not None:
            return
        if not all_models_ready():
            self._append_log(t("log_models_missing"))
            return
        paths = self.queue.pending_paths()
        if not paths:
            self._append_log(t("log_nothing"))
            return
        if self._output_mode == "folder":
            if not self._output_dir:
                self._choose_output_folder()
                if not self._output_dir:
                    return
            output_dir = self._output_dir
        else:
            output_dir = None

        self.worker = RedactionWorker(paths, output_dir, parent=self)
        self.worker.file_event.connect(self._on_file_event)
        self.worker.log_line.connect(self._append_log)
        self.worker.progress_changed.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.setValue(0)
        self.progress.setMaximum(len(paths))
        self.progress_label.setText(f"0 / {len(paths)}")
        self.log_view.clear()
        self.worker.start()

    def _stop(self):
        if self.worker is not None:
            self.worker.stop()
            self.stop_btn.setEnabled(False)
            self.activity_label.setText(t("activity_stopping"))

    def _on_file_event(self, path: str, stage: str, counts, error: str):
        self.queue.apply_event(path, stage, counts, error)
        key = _STAGE_ACTIVITY.get(stage)
        if key:
            self.activity_label.setText(t(key, name=Path(path).name))

    def _on_progress(self, current: int, total: int):
        self.progress.setMaximum(total)
        self.progress.setValue(current)
        self.progress_label.setText(f"{current} / {total}")

    def _on_finished(self):
        self.worker = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.activity_label.setText(" ")

    # --- log / manual redact ---

    def _append_log(self, msg: str):
        self.log_view.appendPlainText(settings.sanitize_log(msg))

    def _browse_manual_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self, t("dlg_manual_folder"), settings.get_last_dir()
        )
        if folder:
            self.manual_dir.setText(folder)
            settings.remember_dir(folder)

    def _manual_redact(self):
        value = self.manual_value.text().strip()
        folder = self.manual_dir.text().strip()
        label = self.manual_type.currentText()
        if not value:
            self._append_log(t("log_enter_value"))
            return
        if not folder or not Path(folder).is_dir():
            self._append_log(t("log_pick_folder"))
            return
        from redactor import manual_redact_folder

        count, files = manual_redact_folder(folder, value, label)
        self._append_log(t("log_manual_done", count=count, files=files, label=label))
        self.manual_value.clear()
