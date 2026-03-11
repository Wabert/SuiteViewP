"""
ABR Quote — "Crimson Slate" theme constants and QSS stylesheets.

Theme: Deep crimson/burgundy headers with slate-blue accents.
"""

# =============================================================================
# CRIMSON SLATE COLOR SCHEME — Deep crimson with slate-blue accents
# =============================================================================

# Primary Crimsons — deep burgundy/crimson
CRIMSON_DARK      = "#5C0A14"       # Darkest crimson (gradient start)
CRIMSON_PRIMARY   = "#8B1A2A"       # Main crimson
CRIMSON_RICH      = "#A52535"       # Rich crimson (gradient end)
CRIMSON_LIGHT     = "#C96070"       # Light crimson-rose for hover states
CRIMSON_SUBTLE    = "#F9ECED"       # Very light blush for backgrounds
CRIMSON_BG        = "#EDD8DA"       # Light blush for main background
CRIMSON_SCROLL    = "#C08090"       # Scrollbar handles

# Slate-Blue accents (replacing gold accents for a cooler contrast)
SLATE_PRIMARY   = "#4A6FA5"       # Slate-blue accent / border
SLATE_LIGHT     = "#D8E4F4"       # Light slate-blue for selections
SLATE_DARK      = "#2E4F85"       # Dark slate-blue for pressed states
SLATE_TEXT      = "#B8D0F0"       # Slate-blue text on dark backgrounds

# Neutral Colors
WHITE          = "#FFFFFF"
GRAY_LIGHT     = "#F5F7FA"
GRAY_MID       = "#E1E5EB"
GRAY_TEXT      = "#4A5568"
GRAY_DARK      = "#2D3748"

# FramelessWindowBase theme colours
ABR_HEADER_COLORS = (CRIMSON_DARK, CRIMSON_PRIMARY, CRIMSON_RICH)
ABR_BORDER_COLOR  = SLATE_PRIMARY

# =============================================================================
# STYLESHEET DEFINITIONS
# =============================================================================

BODY_STYLE = f"""
    QWidget#abrBody {{
        background-color: {CRIMSON_BG};
    }}
"""

STEP_BAR_STYLE = f"""
    QWidget#stepBar {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CRIMSON_DARK}, stop:1 {CRIMSON_PRIMARY});
        border-bottom: 3px solid {SLATE_PRIMARY};
        min-height: 40px;
    }}
"""

GROUP_BOX_STYLE = f"""
    QGroupBox {{
        font-size: 12px;
        font-weight: bold;
        color: {CRIMSON_DARK};
        border: 2px solid {SLATE_PRIMARY};
        border-radius: 8px;
        margin-top: 8px;
        padding: 12px 8px 8px 8px;
        background-color: {WHITE};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 2px 12px;
        background-color: {CRIMSON_PRIMARY};
        color: {SLATE_TEXT};
        border-radius: 4px;
        left: 12px;
    }}
"""

DATEEDIT_STYLE = f"""
    QDateEdit {{
        background-color: {WHITE};
        border: 1px solid {CRIMSON_PRIMARY};
        border-radius: 4px;
        padding: 4px 8px;
        font-size: 12px;
        color: {GRAY_DARK};
    }}
    QDateEdit:focus {{
        border: 2px solid {SLATE_PRIMARY};
        background-color: #F5F8FF;
    }}
    QDateEdit::drop-down {{
        border: none;
        width: 20px;
    }}
"""

INPUT_STYLE = f"""
    QLineEdit {{
        background-color: {WHITE};
        border: 1px solid {CRIMSON_PRIMARY};
        border-radius: 4px;
        padding: 4px 8px;
        font-size: 12px;
        color: {GRAY_DARK};
    }}
    QLineEdit:focus {{
        border: 2px solid {SLATE_PRIMARY};
        background-color: #F5F8FF;
    }}
    QLineEdit:disabled {{
        background-color: {GRAY_LIGHT};
        color: {GRAY_TEXT};
    }}
"""

COMBOBOX_STYLE = f"""
    QComboBox {{
        background-color: {WHITE};
        border: 1px solid {CRIMSON_PRIMARY};
        border-radius: 4px;
        padding: 4px 8px;
        font-size: 12px;
        color: {GRAY_DARK};
        min-width: 100px;
    }}
    QComboBox:hover {{
        border-color: {SLATE_PRIMARY};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {WHITE};
        border: 1px solid {CRIMSON_PRIMARY};
        selection-background-color: {CRIMSON_PRIMARY};
        selection-color: {WHITE};
    }}
"""

BUTTON_PRIMARY_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CRIMSON_RICH}, stop:1 {CRIMSON_PRIMARY});
        color: {WHITE};
        border: 1px solid {CRIMSON_DARK};
        border-radius: 6px;
        padding: 8px 20px;
        font-size: 12px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CRIMSON_PRIMARY}, stop:1 {CRIMSON_DARK});
    }}
    QPushButton:pressed {{
        background-color: {CRIMSON_DARK};
    }}
    QPushButton:disabled {{
        background-color: {GRAY_MID};
        color: {GRAY_TEXT};
        border-color: {GRAY_MID};
    }}
"""

BUTTON_SLATE_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {SLATE_TEXT}, stop:1 {SLATE_PRIMARY});
        color: {WHITE};
        border: 1px solid {SLATE_DARK};
        border-radius: 6px;
        padding: 8px 20px;
        font-size: 12px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {SLATE_PRIMARY}, stop:1 {SLATE_DARK});
        color: {WHITE};
    }}
    QPushButton:pressed {{
        background-color: {SLATE_DARK};
    }}
    QPushButton:disabled {{
        background-color: {GRAY_MID};
        color: {GRAY_TEXT};
        border-color: {GRAY_MID};
    }}
"""

BUTTON_NAV_STYLE = f"""
    QPushButton {{
        background: transparent;
        color: {CRIMSON_PRIMARY};
        border: 1px solid {CRIMSON_PRIMARY};
        border-radius: 6px;
        padding: 8px 20px;
        font-size: 12px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: {CRIMSON_SUBTLE};
        border-color: {CRIMSON_DARK};
    }}
    QPushButton:disabled {{
        color: {GRAY_MID};
        border-color: {GRAY_MID};
    }}
"""

RESULTS_TABLE_STYLE = f"""
    QTableWidget {{
        font-size: 12px;
        border: 2px solid {CRIMSON_PRIMARY};
        border-radius: 4px;
        background-color: {WHITE};
        gridline-color: {GRAY_MID};
        selection-background-color: {SLATE_LIGHT};
        selection-color: {CRIMSON_DARK};
    }}
    QTableWidget::item {{
        padding: 4px 8px;
    }}
    QHeaderView::section {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CRIMSON_DARK}, stop:1 {CRIMSON_PRIMARY});
        color: {SLATE_TEXT};
        font-weight: bold;
        font-size: 11px;
        padding: 6px;
        border: none;
    }}
"""

SCROLL_AREA_STYLE = f"""
    QScrollArea {{
        border: none;
        background-color: transparent;
    }}
    QScrollBar:vertical {{
        background-color: {CRIMSON_SUBTLE};
        width: 12px;
        border-radius: 6px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {CRIMSON_SCROLL};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {CRIMSON_LIGHT};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background-color: {CRIMSON_SUBTLE};
        height: 12px;
        border-radius: 6px;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {CRIMSON_SCROLL};
        border-radius: 5px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {CRIMSON_LIGHT};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
"""

STATUS_BAR_STYLE = f"""
    QLabel#statusBar {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CRIMSON_DARK}, stop:1 {CRIMSON_PRIMARY});
        color: {SLATE_TEXT};
        font-size: 11px;
        font-weight: bold;
        padding: 4px 8px;
        border-top: 2px solid {SLATE_PRIMARY};
    }}
"""

LABEL_HEADER_STYLE = f"""
    QLabel {{
        color: {CRIMSON_DARK};
        font-size: 13px;
        font-weight: bold;
        background: transparent;
    }}
"""

LABEL_VALUE_STYLE = f"""
    QLabel {{
        color: {GRAY_DARK};
        font-size: 12px;
        background: transparent;
    }}
"""

LABEL_MONEY_STYLE = f"""
    QLabel {{
        color: {CRIMSON_DARK};
        font-size: 14px;
        font-weight: bold;
        background: transparent;
    }}
"""

LABEL_MONEY_LARGE_STYLE = f"""
    QLabel {{
        color: {CRIMSON_DARK};
        font-size: 20px;
        font-weight: bold;
        background: transparent;
    }}
"""

DIVIDER_STYLE = f"""
    QFrame {{
        background-color: {SLATE_PRIMARY};
        max-height: 2px;
        min-height: 2px;
    }}
"""

# ── Premium table (StyledInfoTableGroup override) ─────────────────────────────
# Applied directly to the widget after creation to override the PolView blue theme.
PREMIUM_TABLE_STYLE = f"""
    QGroupBox {{
        border: 2px solid {SLATE_PRIMARY};
        border-radius: 6px;
        margin-top: 10px;
        background-color: {WHITE};
        font-weight: bold;
        font-size: 12px;
        color: {CRIMSON_DARK};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px;
        padding: 0 4px;
        color: {SLATE_TEXT};
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {CRIMSON_DARK}, stop:1 {CRIMSON_PRIMARY});
        border-radius: 3px;
    }}
    QTableWidget {{
        background-color: {WHITE};
        alternate-background-color: {CRIMSON_SUBTLE};
        border: 1px solid {SLATE_PRIMARY};
        border-radius: 4px;
        gridline-color: {GRAY_MID};
        selection-background-color: {SLATE_LIGHT};
        selection-color: {CRIMSON_DARK};
        font-size: 11px;
    }}
    QTableWidget::item {{
        padding: 3px 8px;
    }}
    QHeaderView::section {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CRIMSON_DARK}, stop:1 {CRIMSON_PRIMARY});
        color: {SLATE_TEXT};
        font-weight: bold;
        font-size: 11px;
        padding: 5px;
        border: none;
    }}
    QScrollBar:vertical {{
        background-color: {CRIMSON_SUBTLE};
        width: 10px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {CRIMSON_SCROLL};
        border-radius: 4px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {CRIMSON_LIGHT};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
"""

# Applied directly to the inner FixedHeaderTableWidget._data_table to
# override the hardcoded PolView green header colours.
PREMIUM_INNER_TABLE_STYLE = f"""
    QTableWidget {{
        background-color: {WHITE};
        border: none;
        gridline-color: transparent;
        font-size: 11px;
        selection-background-color: {SLATE_LIGHT};
        selection-color: {CRIMSON_DARK};
    }}
    QTableWidget::item {{
        padding: 0px 4px;
        border: none;
    }}
    QTableWidget::item:selected {{
        background-color: {SLATE_LIGHT};
        color: {CRIMSON_DARK};
        border: none;
    }}
    QHeaderView::section {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CRIMSON_DARK}, stop:1 {CRIMSON_PRIMARY});
        color: {SLATE_TEXT};
        padding: 2px 4px;
        border: none;
        border-right: 1px solid {SLATE_PRIMARY};
        border-bottom: 1px solid {CRIMSON_DARK};
        font-size: 10px;
        font-weight: bold;
        height: 18px;
    }}
    QHeaderView::section:last {{
        border-right: none;
    }}
    QScrollBar:vertical {{
        background-color: {CRIMSON_SUBTLE};
        width: 14px;
        margin: 0px;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background-color: {CRIMSON_SCROLL};
        min-height: 30px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {CRIMSON_LIGHT};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}
"""

# Override the green border on FixedHeaderTableWidget._outer_frame.
PREMIUM_INNER_FRAME_STYLE = f"""
    QFrame#outerFrame {{
        background-color: {WHITE};
        border: 1px solid {SLATE_PRIMARY};
        border-radius: 4px;
    }}
"""
