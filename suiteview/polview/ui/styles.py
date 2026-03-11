"""
Green & Gold color scheme and stylesheet definitions for PolView.

Variable names retain BLUE_ prefix for backward compatibility with
widgets.py, tree_panel.py, tabs/ etc. that import them.  The actual
colour values are all rich casino-poker-table greens.

All color constants and QSS stylesheet strings are defined here so that
every widget module can import them from a single source.
"""

# =============================================================================
# GREEN & GOLD COLOR SCHEME -- Rich casino poker-table green
# =============================================================================

# Primary Greens -- deep, rich felt green
# (Variable names keep BLUE_ prefix so downstream files need zero changes)
BLUE_RICH          = "#1B5E20"       # Rich deep green (main)
BLUE_GRADIENT_TOP  = "#0A3D0A"       # Darkest green for gradient top
BLUE_GRADIENT_BOT  = "#2E7D32"       # Lighter green for gradient bottom
BLUE_PRIMARY       = "#1B5E20"       # Main green
BLUE_LIGHT         = "#4CAF50"       # Lighter green for highlights
BLUE_SCROLL        = "#81C784"       # Light green for scrollbar handles
BLUE_DARK          = "#0A3D0A"       # Dark green for headers
BLUE_SUBTLE        = "#E8F5E9"       # Very light green for backgrounds
BLUE_BG            = "#C8E6C9"       # Light green for main background

# Semantic aliases (use these in NEW code)
GREEN_RICH          = BLUE_RICH
GREEN_GRADIENT_TOP  = BLUE_GRADIENT_TOP
GREEN_GRADIENT_BOT  = BLUE_GRADIENT_BOT
GREEN_PRIMARY       = BLUE_PRIMARY
GREEN_LIGHT         = BLUE_LIGHT
GREEN_SCROLL        = BLUE_SCROLL
GREEN_DARK          = BLUE_DARK
GREEN_SUBTLE        = BLUE_SUBTLE
GREEN_BG            = BLUE_BG

# Gold/Yellow -- warm golden accents (matching SuiteView family)
GOLD_PRIMARY = "#D4A017"
GOLD_LIGHT   = "#FFF3D0"
GOLD_DARK    = "#B8860B"
GOLD_TEXT    = "#FFD54F"

# Neutral Colors
WHITE      = "#FFFFFF"
GRAY_LIGHT = "#F5F7FA"
GRAY_MID   = "#E1E5EB"
GRAY_TEXT  = "#4A5568"
GRAY_DARK  = "#2D3748"

# FramelessWindowBase theme colours
POLVIEW_HEADER_COLORS = (GREEN_GRADIENT_TOP, GREEN_RICH, GREEN_GRADIENT_BOT)
POLVIEW_BORDER_COLOR  = GOLD_PRIMARY

# =============================================================================
# STYLESHEET DEFINITIONS
# =============================================================================

MAIN_WINDOW_STYLE = f"""
    QMainWindow {{
        background-color: {BLUE_BG};
    }}

    QStatusBar {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {BLUE_GRADIENT_TOP}, stop:1 {BLUE_GRADIENT_BOT});
        color: {GOLD_TEXT};
        font-size: 11px;
        font-weight: bold;
        padding: 4px;
        border-top: 2px solid {GOLD_PRIMARY};
    }}
"""

# Header bar style (gradient green with gold accents)
HEADER_BAR_STYLE = f"""
    QWidget#headerBar {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {BLUE_GRADIENT_TOP}, stop:0.5 {BLUE_RICH}, stop:1 {BLUE_GRADIENT_BOT});
        border-bottom: 2px solid {GOLD_PRIMARY};
        min-height: 30px;
    }}
    QLabel {{
        color: {GOLD_TEXT};
        font-size: 11px;
        font-weight: bold;
        background: transparent;
    }}
    QPushButton {{
        background: transparent;
        color: {GOLD_TEXT};
        border: 1px solid {GOLD_PRIMARY};
        border-radius: 4px;
        padding: 4px 12px;
        font-size: 11px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: {GOLD_PRIMARY};
        color: {BLUE_DARK};
    }}
    QPushButton:checked {{
        background-color: {GOLD_PRIMARY};
        color: {BLUE_DARK};
    }}
"""

SPLITTER_STYLE = f"""
    QSplitter::handle {{
        background-color: {BLUE_PRIMARY};
        width: 3px;
    }}
    QSplitter::handle:hover {{
        background-color: {GOLD_PRIMARY};
    }}
"""

TREE_WIDGET_STYLE = f"""
    QTreeWidget {{
        background-color: {WHITE};
        border: 2px solid {BLUE_PRIMARY};
        border-radius: 4px;
        font-size: 11px;
        outline: none;
    }}
    QTreeWidget::item {{
        padding: 1px 4px;
        border-bottom: 1px solid {GRAY_MID};
    }}
    QTreeWidget::item:hover {{
        background-color: {BLUE_SUBTLE};
    }}
    QTreeWidget::item:selected {{
        background-color: {GOLD_LIGHT};
        color: {BLUE_DARK};
    }}
    QTreeWidget::branch {{
        background-color: transparent;
    }}
    QHeaderView::section {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {BLUE_GRADIENT_TOP}, stop:1 {BLUE_RICH});
        color: {GOLD_TEXT};
        font-weight: bold;
        font-size: 11px;
        padding: 6px;
        border: none;
    }}
    QScrollBar:vertical {{
        background-color: {BLUE_SUBTLE};
        width: 14px;
        margin: 0px;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background-color: {BLUE_SCROLL};
        min-height: 30px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {BLUE_LIGHT};
    }}
    QScrollBar::add-line:vertical {{
        height: 0px;
        border: none;
        background: none;
    }}
    QScrollBar::sub-line:vertical {{
        height: 0px;
        border: none;
        background: none;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}
    QScrollBar:horizontal {{
        background-color: {BLUE_SUBTLE};
        height: 14px;
        margin: 0px;
        border: none;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {BLUE_SCROLL};
        min-width: 30px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {BLUE_LIGHT};
    }}
    QScrollBar::add-line:horizontal {{
        width: 0px;
        border: none;
        background: none;
    }}
    QScrollBar::sub-line:horizontal {{
        width: 0px;
        border: none;
        background: none;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: none;
    }}
"""

TAB_WIDGET_STYLE = f"""
    QTabWidget::pane {{
        border: 1px solid {BLUE_PRIMARY};
        border-radius: 4px;
        background-color: {WHITE};
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
            stop:0 {BLUE_LIGHT}, stop:1 {BLUE_PRIMARY});
        color: {WHITE};
    }}
    QTabBar::tab:selected {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {BLUE_GRADIENT_TOP}, stop:1 {BLUE_RICH});
        color: {GOLD_TEXT};
        font-weight: bold;
        border-bottom: 3px solid {GOLD_PRIMARY};
    }}
"""

COMPACT_TABLE_STYLE = f"""
    QTableWidget {{
        font-size: 11px;
        border: none;
        background-color: {WHITE};
        gridline-color: transparent;
        selection-background-color: {WHITE};
        selection-color: {BLUE_DARK};
    }}
    QTableWidget::item {{
        padding: 0px 4px;
        border: none;
    }}
    QTableWidget::item:selected {{
        background-color: {WHITE};
        color: {BLUE_DARK};
        border: none;
    }}
    QTableWidget::item:alternate {{
        background-color: {WHITE};
    }}
    QHeaderView::section {{
        padding: 2px 4px;
        font-size: 11px;
        font-weight: normal;
        background-color: {BLUE_SUBTLE};
        color: {BLUE_DARK};
        border: none;
        border-right: 1px solid {GRAY_MID};
        border-bottom: 1px solid {BLUE_PRIMARY};
    }}
    QHeaderView::section:first {{
        border-top-left-radius: 3px;
    }}
    QTableCornerButton::section {{
        background-color: {BLUE_SUBTLE};
        border: none;
    }}
    QScrollBar:horizontal {{
        background-color: {BLUE_SUBTLE};
        height: 14px;
        margin: 0px;
        border: none;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {BLUE_SCROLL};
        min-width: 30px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {BLUE_LIGHT};
    }}
    QScrollBar::add-line:horizontal {{
        width: 0px;
        border: none;
        background: none;
    }}
    QScrollBar::sub-line:horizontal {{
        width: 0px;
        border: none;
        background: none;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: none;
    }}
    QScrollBar:vertical {{
        background-color: {BLUE_SUBTLE};
        width: 14px;
        margin: 0px;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background-color: {BLUE_SCROLL};
        min-height: 30px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {BLUE_LIGHT};
    }}
    QScrollBar::add-line:vertical {{
        height: 0px;
        border: none;
        background: none;
    }}
    QScrollBar::sub-line:vertical {{
        height: 0px;
        border: none;
        background: none;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}
"""

LOOKUP_BAR_STYLE = f"""
    QWidget#lookupBar {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {BLUE_GRADIENT_TOP}, stop:0.5 {BLUE_RICH}, stop:1 {BLUE_GRADIENT_BOT});
        border-bottom: 4px solid {GOLD_PRIMARY};
        min-height: 50px;
    }}
    QLabel {{
        color: {BLUE_DARK};
        font-size: 9px;
        font-weight: bold;
        background: transparent;
        padding: 0px;
        margin: 0px;
    }}
    QLineEdit {{
        background-color: {WHITE};
        border: 1px solid {GOLD_PRIMARY};
        border-radius: 2px;
        padding: 2px 4px;
        font-size: 10px;
        color: {GRAY_DARK};
        margin: 0px;
    }}
    QLineEdit:focus {{
        border-color: {GOLD_TEXT};
        background-color: #FFFEF5;
    }}
    QComboBox {{
        background-color: {WHITE};
        border: 1px solid {GOLD_PRIMARY};
        border-radius: 2px;
        padding: 2px 4px;
        font-size: 10px;
        color: {GRAY_DARK};
        margin: 0px;
    }}
    QComboBox:hover {{
        border-color: {GOLD_TEXT};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 16px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {WHITE};
        border: 1px solid {BLUE_PRIMARY};
        selection-background-color: {BLUE_PRIMARY};
        selection-color: {WHITE};
    }}
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {GOLD_TEXT}, stop:1 {GOLD_PRIMARY});
        color: {BLUE_DARK};
        border: 1px solid {GOLD_DARK};
        border-radius: 3px;
        padding: 4px 12px;
        font-size: 10px;
        font-weight: bold;
        margin: 0px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {GOLD_PRIMARY}, stop:1 {GOLD_DARK});
        color: {WHITE};
    }}
    QPushButton:pressed {{
        background-color: {GOLD_DARK};
    }}
"""

POLICY_DISPLAY_STYLE = f"""
    QLabel#policyDisplay {{
        background: transparent;
        color: {BLUE_DARK};
        font-size: 32px;
        font-weight: bold;
        padding: 0px;
        border: none;
    }}
"""

POLICY_INFO_FRAME_STYLE = f"""
    QGroupBox {{
        font-size: 11px;
        font-weight: bold;
        color: {BLUE_DARK};
        border: 2px solid {BLUE_PRIMARY};
        border-radius: 8px;
        margin-top: 3px;
        margin-bottom: 0px;
        padding: 0px;
        background-color: {WHITE};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 1px 10px;
        background-color: {BLUE_PRIMARY};
        color: {GOLD_TEXT};
        border-radius: 4px;
        left: 10px;
    }}
    QGroupBox QLabel {{
        font-size: 10px;
        color: {GRAY_DARK};
        border: none;
        background: transparent;
    }}
"""

SCROLL_AREA_STYLE = f"""
    QScrollArea {{
        border: none;
        background-color: transparent;
    }}
    QScrollBar:vertical {{
        background-color: {GRAY_LIGHT};
        width: 12px;
        border-radius: 6px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {BLUE_LIGHT};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {BLUE_PRIMARY};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background-color: {GRAY_LIGHT};
        height: 12px;
        border-radius: 6px;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {BLUE_LIGHT};
        border-radius: 5px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {BLUE_PRIMARY};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
"""

# Context menu styling - used throughout the app (tight/compact)
CONTEXT_MENU_STYLE = f"""
    QMenu {{
        background-color: {WHITE};
        border: 1px solid {BLUE_PRIMARY};
        border-radius: 2px;
        padding: 0px;
        margin: 0px;
        min-width: 25px;
    }}
    QMenu::item {{
        padding: 2px 8px;
        margin: 0px;
        color: {GRAY_DARK};
        background-color: transparent;
    }}
    QMenu::item:selected {{
        background-color: {BLUE_LIGHT};
        color: {WHITE};
    }}
    QMenu::separator {{
        height: 1px;
        background-color: {GRAY_MID};
        margin: 1px 4px;
    }}
"""
