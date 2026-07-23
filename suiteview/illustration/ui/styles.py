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
# Visibly lighter gradient the title bar wears while a saved case (frozen
# policy snapshot) is loaded — same hue family, instantly reads as
# "different mode", white title text stays legible on every stop.
ILLUSTRATION_SNAPSHOT_HEADER_COLORS = ("#9E7BD8", "#8E67CE", "#7E57C2")
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

# Checkable panel-toggle buttons that live IN the window header (title bar),
# matching its gradient visual language — compact, gold-bordered, translucent.
HEADER_PANEL_BUTTON_STYLE = f"""
    QPushButton {{
        background: rgba(0, 0, 0, 60);
        border: 1px solid {GOLD_PRIMARY};
        border-radius: 4px;
        min-height: 24px; max-height: 24px;
        font-size: 11px; font-weight: bold;
        color: {GOLD_TEXT};
        padding: 0 12px;
    }}
    QPushButton:hover {{
        background-color: rgba(255, 255, 255, 0.15);
    }}
    QPushButton:checked {{
        background-color: rgba(212, 160, 23, 0.35);
        color: #FFF3B0;
    }}
"""

# "Options"-style header menu button — plain clickable text (no box/border),
# matching the SuiteView taskbar's "Tools" menu button. Gold text that brightens
# on hover; the drop-down arrow indicator is hidden so it reads as bare text.
HEADER_MENU_BUTTON_STYLE = """
    QPushButton {
        background: transparent;
        border: none;
        padding: 4px 12px;
        color: #D4A017;
        font-size: 12px;
        font-weight: 600;
    }
    QPushButton:hover {
        color: #FFD700;
    }
    QPushButton::menu-indicator {
        image: none;
    }
"""

# Drop-down menu for the header "Options" button — same shape as the taskbar's
# "Tools" menu, recolored to the Illustration purple theme.
HEADER_MENU_STYLE = f"""
    QMenu {{
        background-color: {PURPLE_PRIMARY};
        border: 1px solid {GOLD_PRIMARY};
        border-radius: 4px;
        padding: 4px;
    }}
    QMenu::item {{
        background-color: transparent;
        color: white;
        padding: 6px 20px;
        font-size: 11px;
    }}
    QMenu::item:selected {{
        background-color: {PURPLE_LIGHT};
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
# Reuse the shared checkmark PNG asset (white tick, drawn once to disk) that
# the Audit tabs' checkbox factory already generates — same glyph, different
# indicator border color per module.
from suiteview.audit.tabs._styles import _CHECKMARK_PATH, _ensure_checkmark  # noqa: E402

_CHECKMARK_ICON_PATH = _CHECKMARK_PATH.replace("\\", "/")

# The canonical purple checkbox look — originated on the Illustration Control
# tab's "Run Controls" group (see IllustrationInputsTab._make_control_checkbox)
# and now the single style every checkbox in the Illustration sub-app should
# use. Bordered box, hover highlight, filled purple + white checkmark when
# checked, muted/greyed when disabled.
INPUT_CHECKBOX_STYLE = (
    f"QCheckBox {{ color: {PURPLE_DARK}; background: transparent; font-size: 11px;"
    " font-weight: bold; spacing: 6px; }"
    "QCheckBox::indicator { border: 1px solid #5E35A5; width: 12px; height: 12px;"
    " background-color: white; }"
    "QCheckBox::indicator:hover { border: 1px solid #4B2383; background-color: #FBF9FE; }"
    "QCheckBox::indicator:checked {"
    "  background-color: #5E35A5; border: 1px solid #4B2383;"
    f"  image: url({_CHECKMARK_ICON_PATH});"
    "}"
    "QCheckBox:disabled { color: #9A8FB0; }"
    "QCheckBox::indicator:disabled { border: 1px solid #C9B8E4; background-color: #EEE7F9; }"
    "QCheckBox::indicator:checked:disabled {"
    "  background-color: #B7A6D6; border: 1px solid #C9B8E4;"
    f"  image: url({_CHECKMARK_ICON_PATH});"
    "}"
)


def apply_input_checkbox_style(checkbox):
    """Apply the shared purple Run-Controls checkbox look to *checkbox*.

    Ensures the shared checkmark PNG asset exists on disk (lazily generated,
    requires a live QApplication) before assigning INPUT_CHECKBOX_STYLE, so
    every Illustration checkbox — not just Run Controls — renders the same
    bordered box / hover / filled-purple-with-white-tick states.
    """
    _ensure_checkmark()
    checkbox.setStyleSheet(INPUT_CHECKBOX_STYLE)
    return checkbox
INPUT_RADIO_STYLE = (
    f"QRadioButton {{ color: {PURPLE_DARK}; background: transparent; font-size: 11px;"
    " font-weight: bold; spacing: 6px; }"
    "QRadioButton::indicator { border: 1px solid #5E35A5; border-radius: 6px;"
    " width: 12px; height: 12px; background-color: white; }"
    "QRadioButton::indicator:hover { border: 1px solid #4B2383; background-color: #FBF9FE; }"
    "QRadioButton::indicator:checked { background-color: #5E35A5; border: 1px solid #4B2383; }"
    "QRadioButton:disabled { color: #9A8FB0; }"
    "QRadioButton::indicator:disabled { border: 1px solid #C9B8E4; background-color: #EEE7F9; }"
    "QRadioButton::indicator:checked:disabled { background-color: #B7A6D6;"
    " border: 1px solid #C9B8E4; }"
)
