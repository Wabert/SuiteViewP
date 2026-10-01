"""Purple and gold UI styling for the Illustration app."""

from suiteview.ui import tokens

_ILLUSTRATION_STYLE = tokens.ILLUSTRATION_STYLE

PURPLE_DARK = tokens.ILLUSTRATION.primary_dark
PURPLE_RICH = tokens.ILLUSTRATION.header_mid
PURPLE_PRIMARY = tokens.ILLUSTRATION.primary
PURPLE_LIGHT = tokens.ILLUSTRATION.primary_light
PURPLE_BG = tokens.ILLUSTRATION.body
PURPLE_SUBTLE = tokens.ILLUSTRATION.subtle
ISSUE_BLUE_DARK = _ILLUSTRATION_STYLE.issue_dark
ISSUE_BLUE_PRIMARY = _ILLUSTRATION_STYLE.issue_primary
ISSUE_BLUE_LIGHT = _ILLUSTRATION_STYLE.issue_light
ISSUE_BLUE_BG = _ILLUSTRATION_STYLE.issue_body
GOLD_PRIMARY = tokens.GOLD_BORDER
GOLD_TEXT = tokens.GOLD_TEXT
WHITE = tokens.SURFACE
GRAY_DARK = tokens.TEXT
_TAB_IDLE_START = tokens.TAB_IDLE_START
_TAB_IDLE_END = tokens.TAB_IDLE_END
_VALUE_GLOSS = _ILLUSTRATION_STYLE.value_gloss
_VALUE_HOVER = _ILLUSTRATION_STYLE.value_hover
_VALUE_PRESSED = _ILLUSTRATION_STYLE.value_pressed
_VALUE_MATURED = _ILLUSTRATION_STYLE.value_matured
_VALUE_MATURED_HOVER = _ILLUSTRATION_STYLE.value_matured_hover

ILLUSTRATION_HEADER_COLORS = (PURPLE_DARK, PURPLE_RICH, PURPLE_PRIMARY)
ILLUSTRATION_ISSUE_HEADER_COLORS = _ILLUSTRATION_STYLE.issue_header
# Visibly lighter gradient the title bar wears while a saved case (frozen
# policy snapshot) is loaded — same hue family, instantly reads as
# "different mode", white title text stays legible on every stop.
ILLUSTRATION_SNAPSHOT_HEADER_COLORS = _ILLUSTRATION_STYLE.snapshot_header
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
            stop:0 {_TAB_IDLE_START}, stop:1 {_TAB_IDLE_END});
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

ISSUE_TAB_WIDGET_STYLE = (
    TAB_WIDGET_STYLE
    .replace(PURPLE_DARK, ISSUE_BLUE_DARK)
    .replace(PURPLE_RICH, ISSUE_BLUE_PRIMARY)
    .replace(PURPLE_PRIMARY, ISSUE_BLUE_PRIMARY)
    .replace(PURPLE_LIGHT, ISSUE_BLUE_LIGHT)
    .replace(PURPLE_BG, ISSUE_BLUE_BG)
)

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

# GROUP_STYLE for the Input-tab request sections: a disabled section drops its
# white body to the window's light-purple background so a locked Input screen
# (ABR Quote mode) reads as one flat purple surface instead of white cards.
INPUT_SECTION_GROUP_STYLE = GROUP_STYLE + f"""
    QGroupBox:disabled {{
        background-color: {PURPLE_BG};
    }}
"""

ISSUE_GROUP_STYLE = (
    GROUP_STYLE.replace(PURPLE_DARK, ISSUE_BLUE_DARK)
    .replace(PURPLE_PRIMARY, ISSUE_BLUE_DARK)
    + (
        f"\nQGroupBox:disabled {{ background-color: {_ILLUSTRATION_STYLE.disabled_surface};"
        f" color: {_ILLUSTRATION_STYLE.disabled_text}; }}"
    )
)


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
        border-right: 1px solid {_ILLUSTRATION_STYLE.table_rule};
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
        gridline-color: {_ILLUSTRATION_STYLE.table_rule};
        font-size: 11px;
        selection-background-color: {PURPLE_SUBTLE};
        selection-color: {PURPLE_DARK};
    }}
    QHeaderView::section {{
        background-color: {PURPLE_SUBTLE};
        color: {PURPLE_DARK};
        padding: 0px;
        border: none;
        border-right: 1px solid {_ILLUSTRATION_STYLE.table_rule};
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
            stop:0 {_VALUE_GLOSS[0]}, stop:0.18 {_VALUE_GLOSS[1]}, stop:0.52 {_VALUE_GLOSS[2]},
            stop:0.54 {_VALUE_GLOSS[3]}, stop:1 {_VALUE_GLOSS[4]});
        color: {GOLD_TEXT};
        border: 2px solid {GOLD_PRIMARY};
        border-top-color: {_ILLUSTRATION_STYLE.gold_highlight};
        border-left-color: {_ILLUSTRATION_STYLE.gold_highlight};
        border-radius: 5px;
        font-size: 10px;
        font-weight: bold;
        padding: 3px 12px;
        min-height: 22px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {_VALUE_HOVER[0]}, stop:0.20 {_VALUE_HOVER[1]}, stop:0.55 {_VALUE_HOVER[2]},
            stop:0.57 {_VALUE_HOVER[3]}, stop:1 {_VALUE_HOVER[4]});
        border-color: {_ILLUSTRATION_STYLE.gold_highlight};
        color: {_ILLUSTRATION_STYLE.gold_soft_text};
    }}
    QPushButton:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {_VALUE_PRESSED[0]}, stop:1 {_VALUE_PRESSED[1]});
        border-top-color: {_ILLUSTRATION_STYLE.gold_shadow};
        border-left-color: {_ILLUSTRATION_STYLE.gold_shadow};
        border-bottom-color: {_ILLUSTRATION_STYLE.gold_highlight};
        border-right-color: {_ILLUSTRATION_STYLE.gold_highlight};
        padding-top: 6px;
        padding-bottom: 4px;
    }}
"""

# A paler, de-emphasized version of VALUE_BUTTON_STYLE for riders/benefits that
# have already matured. Still clickable (the detail dialog opens) — just muted so
# it reads as "no longer in force."
VALUE_BUTTON_MATURED_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {_VALUE_MATURED[0]}, stop:0.5 {_VALUE_MATURED[1]}, stop:1 {_VALUE_MATURED[2]});
        color: {_ILLUSTRATION_STYLE.value_matured_text};
        border: 2px solid {_ILLUSTRATION_STYLE.value_matured_border};
        border-radius: 5px;
        font-size: 10px;
        font-weight: bold;
        font-style: italic;
        padding: 3px 12px;
        min-height: 22px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {_VALUE_MATURED_HOVER[0]}, stop:0.5 {_VALUE_MATURED_HOVER[1]}, stop:1 {_VALUE_MATURED_HOVER[2]});
        color: {PURPLE_RICH};
    }}
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
        color: {_ILLUSTRATION_STYLE.gold_soft_text};
    }}
"""

# "Options"-style header menu button — plain clickable text (no box/border),
# matching the SuiteView taskbar's "Tools" menu button. Gold text that brightens
# on hover; the drop-down arrow indicator is hidden so it reads as bare text.
HEADER_MENU_BUTTON_STYLE = f"""
    QPushButton {{
        background: transparent;
        border: none;
        padding: 4px 12px;
        color: {GOLD_PRIMARY};
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        color: {_ILLUSTRATION_STYLE.menu_hover_text};
    }}
    QPushButton::menu-indicator {{
        image: none;
    }}
"""

# Left-edge ☰ header menu button (before the title) — the same bare gold text
# as the "Options" menu, sized up so the glyph reads as an icon.
HEADER_HAMBURGER_BUTTON_STYLE = HEADER_MENU_BUTTON_STYLE + """
    QPushButton {
        padding: 0px 6px 2px 0px;
        font-size: 18px;
        font-weight: bold;
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
    f"QLineEdit {{ background: white; color: {PURPLE_DARK};"
    f" border: 1px solid {_ILLUSTRATION_STYLE.input_border};"
    " border-radius: 3px; padding: 1px 4px; min-height: 18px; font-size: 11px; }"
    f"QLineEdit:read-only {{ background: {_ILLUSTRATION_STYLE.input_readonly_surface};"
    f" color: {PURPLE_RICH}; }}"
    f"QLineEdit:disabled {{ background: {_ILLUSTRATION_STYLE.input_readonly_surface};"
    f" color: {_ILLUSTRATION_STYLE.input_disabled_text}; }}"
    f"QLineEdit[invalid=\"true\"] {{ border: 1px solid {tokens.STATUS_ERROR};"
    f" background: {_ILLUSTRATION_STYLE.invalid_surface}; }}"
)
INPUT_COMBO_STYLE = (
    f"QComboBox {{ background: white; color: {PURPLE_DARK};"
    f" border: 1px solid {_ILLUSTRATION_STYLE.input_border};"
    " border-radius: 3px; padding: 1px 4px; min-height: 18px; font-size: 11px; }"
    f"QComboBox:disabled {{ background: {_ILLUSTRATION_STYLE.input_readonly_surface};"
    f" color: {_ILLUSTRATION_STYLE.input_disabled_text}; }}"
    f"QComboBox::drop-down {{ border-left: 1px solid {_ILLUSTRATION_STYLE.input_border};"
    " width: 14px; }"
)
INPUT_SMALL_BTN_STYLE = (
    f"QPushButton {{ background: {_ILLUSTRATION_STYLE.input_small_button_surface};"
    f" color: {PURPLE_RICH}; border: 1px solid {PURPLE_LIGHT};"
    " border-radius: 9px; min-width: 18px; max-width: 18px; min-height: 18px;"
    " max-height: 18px; font-size: 12px; font-weight: bold; padding: 0; }"
    f"QPushButton:hover {{ background: {_ILLUSTRATION_STYLE.input_small_button_hover}; }}"
)
INPUT_CAPTION_STYLE = (
    f"color: {PURPLE_DARK}; background: transparent; font-size: 9px; font-weight: bold;"
)
# Reuse the shared checkmark PNG asset (white tick, drawn once to disk) — same
# glyph, different indicator border color per module.
from suiteview.ui.checkmark_icon import CHECKMARK_PATH, ensure_checkmark  # noqa: E402

_CHECKMARK_ICON_PATH = str(CHECKMARK_PATH).replace("\\", "/")

# The canonical purple checkbox look — originated on the Illustration Control
# tab's "Run Controls" group (see IllustrationInputsTab._make_control_checkbox)
# and now the single style every checkbox in the Illustration sub-app should
# use. Bordered box, hover highlight, filled purple + white checkmark when
# checked, muted/greyed when disabled.
INPUT_CHECKBOX_STYLE = (
    f"QCheckBox {{ color: {PURPLE_DARK}; background: transparent; font-size: 11px;"
    " font-weight: bold; spacing: 6px; }"
    f"QCheckBox::indicator {{ border: 1px solid {PURPLE_PRIMARY}; width: 12px; height: 12px;"
    " background-color: white; }"
    f"QCheckBox::indicator:hover {{ border: 1px solid {PURPLE_RICH};"
    f" background-color: {_ILLUSTRATION_STYLE.checkbox_hover_surface}; }}"
    "QCheckBox::indicator:checked {"
    f"  background-color: {PURPLE_PRIMARY}; border: 1px solid {PURPLE_RICH};"
    f"  image: url({_CHECKMARK_ICON_PATH});"
    "}"
    f"QCheckBox:disabled {{ color: {_ILLUSTRATION_STYLE.checkbox_disabled_text}; }}"
    f"QCheckBox::indicator:disabled {{ border: 1px solid {_ILLUSTRATION_STYLE.checkbox_disabled_border};"
    f" background-color: {_ILLUSTRATION_STYLE.checkbox_disabled_surface}; }}"
    "QCheckBox::indicator:checked:disabled {"
    f"  background-color: {_ILLUSTRATION_STYLE.checkbox_disabled_checked};"
    f" border: 1px solid {_ILLUSTRATION_STYLE.checkbox_disabled_border};"
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
    ensure_checkmark()
    checkbox.setStyleSheet(INPUT_CHECKBOX_STYLE)
    return checkbox
INPUT_RADIO_STYLE = (
    f"QRadioButton {{ color: {PURPLE_DARK}; background: transparent; font-size: 11px;"
    " font-weight: bold; spacing: 6px; }"
    f"QRadioButton::indicator {{ border: 1px solid {PURPLE_PRIMARY}; border-radius: 6px;"
    " width: 12px; height: 12px; background-color: white; }"
    f"QRadioButton::indicator:hover {{ border: 1px solid {PURPLE_RICH};"
    f" background-color: {_ILLUSTRATION_STYLE.checkbox_hover_surface}; }}"
    f"QRadioButton::indicator:checked {{ background-color: {PURPLE_PRIMARY};"
    f" border: 1px solid {PURPLE_RICH}; }}"
    f"QRadioButton:disabled {{ color: {_ILLUSTRATION_STYLE.checkbox_disabled_text}; }}"
    f"QRadioButton::indicator:disabled {{ border: 1px solid {_ILLUSTRATION_STYLE.checkbox_disabled_border};"
    f" background-color: {_ILLUSTRATION_STYLE.checkbox_disabled_surface}; }}"
    f"QRadioButton::indicator:checked:disabled {{"
    f" background-color: {_ILLUSTRATION_STYLE.checkbox_disabled_checked};"
    f" border: 1px solid {_ILLUSTRATION_STYLE.checkbox_disabled_border}; }}"
)
