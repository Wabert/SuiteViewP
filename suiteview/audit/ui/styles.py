"""
Audit Tool Styles — Blue & Silver Theme
==========================================
Blue header/footer (#1E5BA8 gradient) with Silver (#C0C0C0) text accents.

Provides header colors for FramelessWindowBase, panel/tab stylesheets,
and widget-level style helpers.
"""

from __future__ import annotations

# ── Header gradient for FramelessWindowBase ─────────────────────────────
# Blue gradient header with silver text
AUDIT_HEADER_COLORS = ("#1E5BA8", "#164A8A", "#0F3A6E")
AUDIT_BORDER_COLOR = "#C0C0C0"      # Silver text/border on blue header

# ── Silver & Blue palette ───────────────────────────────────────────────
SILVER_LIGHT = "#E8E8E8"
SILVER_MID = "#C0C0C0"
SILVER_DARK = "#808080"
BLUE_PRIMARY = "#1E5BA8"
BLUE_LIGHT = "#4A90D9"
BLUE_DARK = "#14407A"
WHITE = "#FFFFFF"
TEXT_DARK = "#1A1A1A"
TEXT_LIGHT = "#FFFFFF"
ERROR_RED = "#CC3333"
SUCCESS_GREEN = "#2E7D32"
PANEL_BG = "#F5F5F5"
GROUP_BG = "#ECECEC"

# ── Blue-themed group box CSS (replaces green/gold) ──────────────
STYLED_FORM_GROUP_CSS = f"""
QGroupBox {{
    font-size: 11px;
    font-weight: bold;
    color: {BLUE_DARK};
    border: 2px solid {BLUE_PRIMARY};
    border-radius: 8px;
    margin-top: 18px;
    margin-bottom: 0px;
    padding: 0px;
    padding-top: 12px;
    background-color: #ffffff;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 3px 10px;
    background-color: {BLUE_PRIMARY};
    color: {SILVER_MID};
    border-radius: 4px;
    left: 10px;
    top: 2px;
}}
QGroupBox QLabel {{
    font-size: 10px;
    color: #2D3748;
    border: none;
    background: transparent;
}}
"""

# ── Blue/silver group box (used by StyledFormGroup) ───────────────────
STYLED_FORM_GROUP_BLUE_CSS = f"""
QGroupBox {{
    font-size: 11px;
    font-weight: bold;
    color: {BLUE_DARK};
    border: 2px solid {BLUE_PRIMARY};
    border-radius: 8px;
    margin-top: 18px;
    padding: 8px 8px 8px 8px;
    background-color: #ffffff;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 3px 10px;
    background-color: {BLUE_PRIMARY};
    color: {SILVER_MID};
    border-radius: 4px;
    left: 10px;
    top: 2px;
}}
"""


def audit_window_stylesheet() -> str:
    """Main window stylesheet for the Audit tool."""
    return f"""
    QMainWindow, QWidget#CentralWidget {{
        background-color: {PANEL_BG};
    }}
    
    /* Toolbar area */
    QFrame#ToolbarFrame {{
        background-color: {SILVER_LIGHT};
        border-bottom: 2px solid {BLUE_PRIMARY};
        padding: 4px;
    }}
    
    /* Tab bar */
    QTabWidget::pane {{
        border: 1px solid {SILVER_MID};
        background-color: {WHITE};
    }}
    QTabBar::tab {{
        background-color: {SILVER_LIGHT};
        color: {TEXT_DARK};
        padding: 6px 16px;
        margin-right: 2px;
        border: 1px solid {SILVER_MID};
        border-bottom: none;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        font-size: 11px;
    }}
    QTabBar::tab:selected {{
        background-color: {WHITE};
        color: {BLUE_PRIMARY};
        font-weight: bold;
        border-bottom: 2px solid {BLUE_PRIMARY};
    }}
    QTabBar::tab:hover:!selected {{
        background-color: {SILVER_MID};
    }}
    
    /* Buttons */
    QPushButton {{
        background-color: {BLUE_PRIMARY};
        color: {TEXT_LIGHT};
        border: none;
        border-radius: 4px;
        padding: 6px 16px;
        font-size: 11px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: {BLUE_LIGHT};
    }}
    QPushButton:pressed {{
        background-color: {BLUE_DARK};
    }}
    QPushButton:disabled {{
        background-color: {SILVER_MID};
        color: {SILVER_DARK};
    }}
    QPushButton#SecondaryButton {{
        background-color: {SILVER_LIGHT};
        color: {TEXT_DARK};
        border: 1px solid {SILVER_MID};
    }}
    QPushButton#SecondaryButton:hover {{
        background-color: {SILVER_MID};
    }}
    
    /* ComboBox */
    QComboBox {{
        background-color: {WHITE};
        color: {TEXT_DARK};
        border: 1px solid {SILVER_MID};
        border-radius: 3px;
        padding: 3px 6px;
        font-size: 11px;
        min-height: 22px;
    }}
    QComboBox:focus {{
        border: 1px solid {BLUE_PRIMARY};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    
    /* LineEdit */
    QLineEdit {{
        background-color: {WHITE};
        color: {TEXT_DARK};
        border: 1px solid {SILVER_MID};
        border-radius: 3px;
        padding: 3px 6px;
        font-size: 11px;
        min-height: 22px;
    }}
    QLineEdit:focus {{
        border: 1px solid {BLUE_PRIMARY};
    }}
    
    /* CheckBox */
    QCheckBox {{
        color: {TEXT_DARK};
        font-size: 11px;
        spacing: 4px;
    }}
    QCheckBox::indicator {{
        width: 14px;
        height: 14px;
        border: 1px solid {SILVER_MID};
        border-radius: 2px;
        background-color: {WHITE};
    }}
    QCheckBox::indicator:checked {{
        background-color: {BLUE_PRIMARY};
        border: 1px solid {BLUE_PRIMARY};
    }}
    
    /* ListWidget (multi-select listboxes) — tight packing */
    QListWidget {{
        background-color: transparent;
        color: {TEXT_DARK};
        border: none;
        outline: none;
        font-size: 11px;
        padding: 0px;
        margin: 0px;
    }}
    QListWidget::item {{
        padding: 0px 4px;
        margin: 0px;
        min-height: 14px;
        max-height: 16px;
        border: none;
        color: {TEXT_DARK};
    }}
    QListWidget::item:selected {{
        background-color: rgba(0, 0, 0, 30);
        color: {TEXT_DARK};
        font-weight: bold;
        padding: 0px 4px;
        margin: 0px;
    }}
    QListWidget::item:hover {{
        background-color: rgba(0, 0, 0, 15);
        padding: 0px 4px;
        margin: 0px;
    }}
    
    /* GroupBox (Blue theme) */
    QGroupBox {{
        background-color: #ffffff;
        border: 2px solid {BLUE_PRIMARY};
        border-radius: 8px;
        margin-top: 18px;
        margin-bottom: 0px;
        padding: 0px;
        padding-top: 12px;
        font-size: 11px;
        font-weight: bold;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 3px 10px;
        background-color: {BLUE_PRIMARY};
        color: {SILVER_MID};
        border-radius: 4px;
        left: 10px;
        top: 2px;
    }}
    
    /* ScrollArea */
    QScrollArea {{
        border: none;
        background-color: transparent;
    }}
    QScrollBar:vertical {{
        border: none;
        background-color: {SILVER_LIGHT};
        width: 10px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {SILVER_MID};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {SILVER_DARK};
    }}
    
    /* Label */
    QLabel {{
        color: {TEXT_DARK};
        font-size: 11px;
    }}
    QLabel#SectionLabel {{
        color: {BLUE_PRIMARY};
        font-size: 12px;
        font-weight: bold;
    }}
    QLabel#StatusLabel {{
        color: {SILVER_MID};
        font-size: 10px;
    }}
    
    /* Footer / Status bar */
    QFrame#StatusBarFrame {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {BLUE_DARK}, stop:0.5 {BLUE_PRIMARY}, stop:1 {BLUE_DARK});
        border-bottom-left-radius: 4px;
        border-bottom-right-radius: 4px;
    }}
    QFrame#StatusBarFrame QLabel {{
        color: {SILVER_MID};
        font-size: 10px;
        background: transparent;
    }}
    
    /* Splitter */
    QSplitter::handle {{
        background-color: {SILVER_MID};
    }}
    QSplitter::handle:horizontal {{
        width: 3px;
    }}
    """


def results_panel_stylesheet() -> str:
    """Stylesheet for the results panel with summary bar."""
    return f"""
    QFrame#ResultsFrame {{
        background-color: {WHITE};
        border: 1px solid {SILVER_MID};
    }}
    
    QFrame#SummaryBar {{
        background-color: {SILVER_LIGHT};
        border-bottom: 1px solid {SILVER_MID};
        padding: 4px 8px;
    }}
    
    QLabel#FilterChip {{
        background-color: {BLUE_PRIMARY};
        color: {TEXT_LIGHT};
        border-radius: 10px;
        padding: 2px 8px;
        font-size: 10px;
    }}
    
    QLabel#TimingLabel {{
        color: {SILVER_DARK};
        font-size: 10px;
        font-style: italic;
    }}
    
    QTextEdit#SqlPreview {{
        background-color: #F8F8F8;
        color: {TEXT_DARK};
        border: 1px solid {SILVER_MID};
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: 10px;
    }}
    """


def criteria_panel_stylesheet() -> str:
    """Stylesheet for the criteria input panel."""
    return f"""
    QFrame#CriteriaPanel {{
        background-color: {PANEL_BG};
    }}
    
    QFrame#SectionHeader {{
        background-color: {SILVER_LIGHT};
        border: 1px solid {SILVER_MID};
        border-radius: 4px;
        padding: 4px 8px;
    }}
    
    QLabel#SectionTitle {{
        color: {BLUE_PRIMARY};
        font-size: 11px;
        font-weight: bold;
    }}
    """
