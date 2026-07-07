"""Purple and gold UI styling for the Illustration app."""

PURPLE_DARK = "#2A1458"
PURPLE_RICH = "#4B2383"
PURPLE_PRIMARY = "#5E35A5"
PURPLE_LIGHT = "#7E57C2"
PURPLE_BG = "#EDE7F6"
PURPLE_SUBTLE = "#F6F1FB"
GOLD_PRIMARY = "#D4A017"
GOLD_TEXT = "#FFD54F"
WHITE = "#FFFFFF"
GRAY_DARK = "#2D3748"

ILLUSTRATION_HEADER_COLORS = (PURPLE_DARK, PURPLE_RICH, PURPLE_PRIMARY)
ILLUSTRATION_BORDER_COLOR = GOLD_PRIMARY

TAB_WIDGET_STYLE = f"""
    QTabWidget::pane {{
        border: 1px solid {PURPLE_PRIMARY};
        border-radius: 4px;
        background-color: {PURPLE_BG};
        top: -1px;
    }}
    QTabWidget {{
        background-color: transparent;
    }}
    QTabBar::tab {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #E0E0E0, stop:1 #BDBDBD);
        color: {GRAY_DARK};
        padding: 8px 16px;
        margin-right: 2px;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        font-size: 11px;
        font-weight: 500;
    }}
    QTabBar::tab:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {PURPLE_LIGHT}, stop:1 {PURPLE_PRIMARY});
        color: {WHITE};
    }}
    QTabBar::tab:selected {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {PURPLE_DARK}, stop:1 {PURPLE_RICH});
        color: {GOLD_TEXT};
        font-weight: bold;
        border-bottom: 3px solid {GOLD_PRIMARY};
    }}
"""

GROUP_STYLE = f"""
    QGroupBox {{
        font-weight: bold;
        border: 2px solid {PURPLE_PRIMARY};
        border-radius: 8px;
        margin-top: 14px;
        background-color: {WHITE};
        color: {PURPLE_DARK};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 2px 10px;
        color: {GOLD_TEXT};
        background-color: {PURPLE_PRIMARY};
        border: 1px solid {GOLD_PRIMARY};
        border-radius: 5px;
    }}
"""

FUND_TABLE_STYLE = f"""
    QFrame#outerFrame {{
        background-color: {WHITE};
        border: 1px solid {PURPLE_PRIMARY};
        border-radius: 4px;
    }}
    QTableWidget {{
        background-color: {WHITE};
        border: none;
        gridline-color: transparent;
        font-size: 11px;
        selection-background-color: {PURPLE_SUBTLE};
        selection-color: {PURPLE_DARK};
    }}
    QHeaderView::section {{
        background-color: {PURPLE_SUBTLE};
        color: {PURPLE_DARK};
        padding: 2px 4px;
        border: none;
        border-right: 1px solid #D8C8F0;
        border-bottom: 1px solid {PURPLE_PRIMARY};
        font-size: 10px;
        font-weight: bold;
        height: 18px;
    }}
    QHeaderView::section:last {{
        border-right: none;
    }}
    QTableWidget::item {{
        padding: 0px 4px;
        border: none;
    }}
    QTableWidget::item:selected {{
        background-color: {PURPLE_SUBTLE};
        color: {PURPLE_DARK};
        border: none;
    }}
"""

INPUT_TABLE_STYLE = f"""
    QTableWidget {{
        background-color: {WHITE};
        border: 1px solid {PURPLE_PRIMARY};
        border-radius: 4px;
        gridline-color: #D8C8F0;
        font-size: 11px;
        selection-background-color: {PURPLE_SUBTLE};
        selection-color: {PURPLE_DARK};
    }}
    QHeaderView::section {{
        background-color: {PURPLE_SUBTLE};
        color: {PURPLE_DARK};
        padding: 0px;
        border: none;
        border-right: 1px solid #D8C8F0;
        border-bottom: 1px solid {PURPLE_PRIMARY};
        font-size: 10px;
        font-weight: bold;
        height: 16px;
    }}
    QHeaderView::section:last {{
        border-right: none;
    }}
    QTableWidget::item {{
        padding: 0px;
    }}
"""

VALUE_BUTTON_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #B99AF0, stop:0.18 #7E57C2, stop:0.52 #5E35A5,
            stop:0.54 #4B2383, stop:1 #2A1458);
        color: {GOLD_TEXT};
        border: 2px solid {GOLD_PRIMARY};
        border-top-color: #FFE08A;
        border-left-color: #FFE08A;
        border-radius: 5px;
        font-size: 10px;
        font-weight: bold;
        padding: 3px 12px;
        min-height: 22px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #D1BEF7, stop:0.20 #9270D2, stop:0.55 #6E43B8,
            stop:0.57 #5E35A5, stop:1 #3B1B70);
        border-color: #FFE08A;
        color: #FFF3B0;
    }}
    QPushButton:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #2A1458, stop:1 #5E35A5);
        border-top-color: #9F7610;
        border-left-color: #9F7610;
        border-bottom-color: #FFE08A;
        border-right-color: #FFE08A;
        padding-top: 6px;
        padding-bottom: 4px;
    }}
"""

# A paler, de-emphasized version of VALUE_BUTTON_STYLE for riders/benefits that
# have already matured. Still clickable (the detail dialog opens) — just muted so
# it reads as "no longer in force."
VALUE_BUTTON_MATURED_STYLE = """
    QPushButton {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #E7DDF7, stop:0.5 #CDBDEC, stop:1 #B9A6E0);
        color: #6E5E92;
        border: 2px solid #C9BBE2;
        border-radius: 5px;
        font-size: 10px;
        font-weight: bold;
        font-style: italic;
        padding: 3px 12px;
        min-height: 22px;
    }
    QPushButton:hover {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #EFE8FA, stop:0.5 #D9CCF1, stop:1 #C7B7E8);
        color: #4B2383;
    }
"""

LIST_BUTTON_STYLE = f"""
    QPushButton {{
        background: transparent;
        border: 1px solid {GOLD_PRIMARY};
        border-radius: 3px;
        min-width: 56px; max-width: 56px;
        min-height: 28px; max-height: 28px;
        font-size: 11px; font-weight: bold;
        color: {GOLD_TEXT};
        padding: 0 6px;
    }}
    QPushButton:hover {{
        background-color: rgba(255, 255, 255, 0.15);
    }}
    QPushButton:checked {{
        background-color: rgba(212, 160, 23, 0.30);
    }}
"""

STATUS_BAR_STYLE = f"""
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {PURPLE_DARK}, stop:1 {PURPLE_PRIMARY});
    border-top: 2px solid {GOLD_PRIMARY};
"""

# ── Shared input-field styles (Inputs tab + Allocations panel) ──────────────

INPUT_EDIT_STYLE = (
    "QLineEdit { background: white; color: #2A1458; border: 1px solid #B79CDE;"
    " border-radius: 3px; padding: 1px 4px; min-height: 18px; font-size: 11px; }"
    "QLineEdit:read-only { background: #E8DDF8; color: #4B2383; }"
    "QLineEdit:disabled { background: #E8DDF8; color: #7A6B91; }"
    "QLineEdit[invalid=\"true\"] { border: 1px solid #C62828; background: #FDECEA; }"
)
INPUT_COMBO_STYLE = (
    "QComboBox { background: white; color: #2A1458; border: 1px solid #B79CDE;"
    " border-radius: 3px; padding: 1px 4px; min-height: 18px; font-size: 11px; }"
    "QComboBox:disabled { background: #E8DDF8; color: #7A6B91; }"
    "QComboBox::drop-down { border-left: 1px solid #B79CDE; width: 14px; }"
)
INPUT_SMALL_BTN_STYLE = (
    "QPushButton { background: #F3ECFC; color: #4B2383; border: 1px solid #7E57C2;"
    " border-radius: 9px; min-width: 18px; max-width: 18px; min-height: 18px;"
    " max-height: 18px; font-size: 12px; font-weight: bold; padding: 0; }"
    "QPushButton:hover { background: #E6DAF8; }"
)
INPUT_CAPTION_STYLE = (
    f"color: {PURPLE_DARK}; background: transparent; font-size: 9px; font-weight: bold;"
)
INPUT_CHECKBOX_STYLE = (
    f"QCheckBox {{ color: {PURPLE_DARK}; background: transparent; font-size: 11px;"
    " font-weight: bold; spacing: 6px; }"
    "QCheckBox::indicator { border: 1px solid #5E35A5; width: 12px; height: 12px;"
    " background-color: white; }"
    "QCheckBox::indicator:disabled { background-color: #E8DDF8; }"
    "QCheckBox::indicator:checked { background-color: #5E35A5; }"
)
