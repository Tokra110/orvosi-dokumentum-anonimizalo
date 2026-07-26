"""Clinical theme with real tonal zones: dark teal header band, white hero
card on a gray-green canvas, tinted wells for secondary sections, dark log."""

BG = "#C2CCC7"
SURFACE = "#FFFFFF"
WELL = "#E2E9E6"
BORDER = "#B7C1BD"
BORDER_SOFT = "#C2CCC7"
TEXT = "#16211E"
TEXT_MUTED = "#5F6B68"
ACCENT = "#0F6E56"
ACCENT_HOVER = "#0C5A47"
ACCENT_SOFT = "#DFF2EC"
HEADER_BG = "#14453A"
HEADER_TEXT = "#F2F7F5"
LOG_BG = "#222A27"
LOG_TEXT = "#A8BCB4"
WARN_BG = "#FAEEDA"
WARN_TEXT = "#854F0B"
OK_TEXT = "#3B6D11"
OK_BG = "#EAF3DE"
FAIL_TEXT = "#A32D2D"

APP_QSS = f"""
QWidget {{
    font-size: 10pt;
    color: {TEXT};
}}
QWidget#rootWindow, QDialog {{ background: {BG}; }}
QFrame#headerBand {{
    background: {HEADER_BG};
    border: none;
}}
QFrame#headerBand QLabel {{
    color: {HEADER_TEXT};
    background: transparent;
}}
QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#tintedCard {{
    background: {WELL};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#cardFooter {{
    background: {WELL};
    border: none;
    border-top: 1px solid {BORDER};
    border-bottom-left-radius: 9px;
    border-bottom-right-radius: 9px;
}}
QFrame#accentBar {{
    background: {ACCENT};
    border: none;
    border-radius: 2px;
    min-width: 4px; max-width: 4px;
    min-height: 15px; max-height: 15px;
}}
QLabel {{ background: transparent; }}
QLabel#appTitle {{ font-size: 14pt; font-weight: 600; }}
QLabel#sectionTitle {{ font-weight: 600; }}
QLabel#mutedLabel {{ color: {TEXT_MUTED}; }}
QToolTip {{
    background: {SURFACE}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 9px;
}}
QLabel#modelChipReady {{
    background: {OK_BG}; color: {OK_TEXT};
    border-radius: 10px; padding: 3px 12px;
}}
QLabel#modelChipMissing {{
    background: {WARN_BG}; color: {WARN_TEXT};
    border-radius: 10px; padding: 3px 12px;
}}
QLabel#missingBanner {{
    background: {WARN_BG}; color: {WARN_TEXT};
    border: 1px solid {WARN_TEXT}; border-radius: 8px; padding: 8px 12px;
}}
QPushButton {{
    background: {SURFACE}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 6px 14px;
}}
QPushButton:hover {{ background: {WELL}; border-color: {TEXT_MUTED}; }}
QPushButton:pressed {{ background: {BG}; }}
QPushButton:disabled {{ color: {TEXT_MUTED}; background: {WELL}; border-color: {BORDER_SOFT}; }}
QPushButton#startButton {{
    background: {ACCENT}; color: {ACCENT_SOFT}; border: none;
    font-weight: 600; padding: 7px 22px;
}}
QPushButton#startButton:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#startButton:disabled {{ background: {BG}; color: {TEXT_MUTED}; }}
QPushButton#modelChipReady {{
    background: {OK_BG}; color: {OK_TEXT};
    border: none; border-radius: 12px; padding: 5px 16px; font-weight: 600;
}}
QPushButton#modelChipMissing {{
    background: {WARN_BG}; color: {WARN_TEXT};
    border: none; border-radius: 12px; padding: 5px 16px; font-weight: 600;
}}
QToolButton {{
    background: {SURFACE}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 6px 12px;
}}
QToolButton:hover {{ background: {WELL}; border-color: {TEXT_MUTED}; }}
QToolButton#sectionToggle {{
    background: transparent; border: none; border-radius: 6px;
    color: {TEXT_MUTED}; font-weight: 600; padding: 6px 8px;
}}
QToolButton#sectionToggle:hover {{ background: {WELL}; color: {TEXT}; }}
QFrame#langToggle {{
    background: rgba(255, 255, 255, 0.10);
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 8px;
}}
QToolButton#langOption {{
    background: transparent; border: none; border-radius: 6px;
    color: {HEADER_TEXT}; font-weight: 600; padding: 3px 12px; min-width: 22px;
}}
QToolButton#langOption:hover {{ background: rgba(255, 255, 255, 0.14); }}
QToolButton#langOption:checked {{ background: {ACCENT_SOFT}; color: {HEADER_BG}; }}
QTableView {{
    background: {SURFACE}; border: 1px solid {BORDER_SOFT};
    border-radius: 6px; gridline-color: {BORDER_SOFT};
    alternate-background-color: #EFF4F2;
    selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT};
    outline: none;
}}
QTableView::item {{ padding: 2px 6px; }}
QHeaderView::section {{
    background: {WELL}; color: {TEXT}; font-weight: 600;
    border: none; border-bottom: 1px solid {BORDER}; padding: 7px 8px;
}}
QProgressBar {{
    background: {SURFACE}; border: 1px solid {BORDER};
    border-radius: 4px; color: transparent;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QLineEdit, QComboBox {{
    background: {SURFACE}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 5px 8px;
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE}; border: 1px solid {BORDER};
    selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT};
}}
QPlainTextEdit {{
    background: {LOG_BG}; border: 1px solid {HEADER_BG};
    border-radius: 8px; color: {LOG_TEXT};
    font-family: monospace; font-size: 9pt; padding: 6px;
}}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; }}
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 4px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {TEXT_MUTED}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""
