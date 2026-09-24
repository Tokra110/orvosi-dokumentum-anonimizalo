"""Table model for the PDF queue: one row per file, live status + counts."""

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor

from gui import theme
from gui.i18n import t

COLUMN_COUNT = 7
_COLUMN_KEYS = (
    "col_file", "col_status", "col_names", "col_taj", "col_dates", "col_addr", "col_total",
)

_NAME_LABELS = {"NAME"}
_DATE_LABELS = {"DATE_OF_BIRTH"}
_ADDR_LABELS = {"ADDRESS", "LOCATION"}

_STATUS_KEYS = {
    "queued": "status_queued",
    "converting": "status_converting",
    "redacting": "status_redacting",
    "done": "status_done",
    "failed": "status_failed",
}


@dataclass
class FileRow:
    path: str
    status: str = "queued"
    counts: dict = field(default_factory=dict)
    error: str = ""

    @property
    def zero_names(self) -> bool:
        return self.status == "done" and self._sum(_NAME_LABELS) == 0

    def _sum(self, labels) -> int:
        return sum(v for k, v in self.counts.items() if k in labels)

    def cell(self, col: int) -> str:
        if col == 0:
            return Path(self.path).name
        if col == 1:
            if self.zero_names:
                return t("zero_names")
            key = _STATUS_KEYS.get(self.status)
            return t(key) if key else self.status
        if self.status != "done":
            return "–"
        if col == 2:
            return str(self._sum(_NAME_LABELS))
        if col == 3:
            return str(self.counts.get("TAJ", 0))
        if col == 4:
            return str(self._sum(_DATE_LABELS))
        if col == 5:
            return str(self._sum(_ADDR_LABELS))
        if col == 6:
            return str(sum(self.counts.values()))
        return ""


class QueueModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[FileRow] = []

    # --- queue management ---

    def add_paths(self, paths: list[str]) -> int:
        existing = {r.path for r in self._rows}
        new = []
        for p in paths:
            path = str(Path(p))
            if path.lower().endswith(".pdf") and path not in existing:
                existing.add(path)
                new.append(FileRow(path=path))
        if not new:
            return 0
        first = len(self._rows)
        self.beginInsertRows(QModelIndex(), first, first + len(new) - 1)
        self._rows.extend(new)
        self.endInsertRows()
        return len(new)

    def clear(self):
        self.beginResetModel()
        self._rows = []
        self.endResetModel()

    def remove_rows(self, row_indexes: list[int]):
        for row in sorted(row_indexes, reverse=True):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._rows[row]
            self.endRemoveRows()

    def pending_paths(self) -> list[str]:
        return [r.path for r in self._rows if r.status in ("queued", "failed")]

    def row_count_total(self) -> int:
        return len(self._rows)

    def retranslate(self):
        """Repaint headers and cells after the UI language changed."""
        self.headerDataChanged.emit(Qt.Horizontal, 0, COLUMN_COUNT - 1)
        if self._rows:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self._rows) - 1, COLUMN_COUNT - 1)
            )

    # --- event application ---

    def apply_event(self, path: str, stage: str, counts, error: str):
        for i, row in enumerate(self._rows):
            if row.path == path:
                row.status = stage
                if counts:
                    row.counts = dict(counts)
                row.error = error or ""
                self.dataChanged.emit(
                    self.index(i, 0), self.index(i, COLUMN_COUNT - 1)
                )
                return

    # --- Qt model interface ---

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return COLUMN_COUNT

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return t(_COLUMN_KEYS[section])
        if orientation == Qt.Horizontal and role == Qt.TextAlignmentRole:
            if section >= 2:
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        if role == Qt.DisplayRole:
            return row.cell(index.column())
        if role == Qt.ToolTipRole and row.status == "failed":
            return row.error
        if role == Qt.BackgroundRole and row.zero_names:
            return QBrush(QColor(theme.WARN_BG))
        if role == Qt.ForegroundRole:
            if row.zero_names:
                return QBrush(QColor(theme.WARN_TEXT))
            if row.status == "failed":
                return QBrush(QColor(theme.FAIL_TEXT))
            if row.status == "done" and index.column() == 1:
                return QBrush(QColor(theme.OK_TEXT))
            if row.status == "queued":
                return QBrush(QColor(theme.TEXT_MUTED))
        if role == Qt.TextAlignmentRole and index.column() >= 2:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None
