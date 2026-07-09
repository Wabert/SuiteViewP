"""
Shared RateManager palette + stylesheet (standard SuiteView blue & gold).

Used by both the Rate File Converter window and the Rate Workup window so the
two stay visually identical.
"""

BLUE        = "#1A3A7A"
BLUE_LIGHT  = "#2A5AAA"
BLUE_DARK   = "#0D3A7A"
GOLD        = "#D4A017"
GOLD_TEXT   = "#FFD54F"
GOLD_PRIMARY = "#FFC107"

# Inputs/controls sit a few shades lighter than the page so they read as
# interactive against BG_DARK (user feedback: the old #252540 was too close).
BG_DARK     = "#1E1E2E"
BG_MID      = "#343456"
BG_INPUT    = "#32325A"
TEXT        = "#E8E8F0"
TEXT_MID    = "#A8A8C4"
BORDER      = "#55558A"

# Header colours for FramelessWindowBase
HEADER_COLORS = ("#1E5BA8", "#0D3A7A", "#082B5C")
BORDER_COLOR  = "#D4A017"


def body_stylesheet(root_object_name: str = "RateManagerBody") -> str:
    """The shared dark blue/gold stylesheet for RateManager window bodies."""
    return f"""
        #{root_object_name} {{
            background: {BG_DARK};
        }}

        #Subtitle {{
            color: {TEXT_MID};
            font-size: 12px;
            font-style: italic;
        }}

        #SectionLabel {{
            color: {GOLD_TEXT};
            font-weight: bold;
            font-size: 13px;
        }}

        QLineEdit {{
            background: {BG_INPUT};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 4px;
            padding: 5px 8px;
            font-size: 13px;
            selection-background-color: {BLUE};
        }}
        QLineEdit:focus {{
            border-color: {GOLD};
        }}
        QLineEdit:read-only {{
            color: {GOLD_TEXT};
            background: {BG_MID};
        }}

        QComboBox {{
            background: {BG_INPUT};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 4px;
            padding: 3px 8px;
            font-size: 12px;
        }}
        QComboBox:focus {{
            border-color: {GOLD};
        }}
        QComboBox QAbstractItemView {{
            background: {BG_MID};
            color: {TEXT};
            selection-background-color: {BLUE};
        }}

        #SecondaryBtn {{
            background: {BG_MID};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 4px;
            padding: 6px 14px;
            font-size: 13px;
        }}
        #SecondaryBtn:hover {{
            background: {BLUE};
            border-color: {GOLD};
        }}
        #SecondaryBtn:disabled {{
            color: #555;
        }}

        #PrimaryBtn {{
            background: {BLUE};
            color: {GOLD_TEXT};
            border: 2px solid {GOLD};
            border-radius: 4px;
            padding: 8px 28px;
            font-size: 14px;
            font-weight: bold;
        }}
        #PrimaryBtn:hover {{
            background: {BLUE_LIGHT};
        }}
        #PrimaryBtn:disabled {{
            background: #333;
            color: #666;
            border-color: #444;
        }}

        #LogArea {{
            background: {BG_INPUT};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 4px;
            font-family: 'Cascadia Code', 'Consolas', monospace;
            font-size: 12px;
        }}

        #LogToggle {{
            background: transparent;
            color: {TEXT_MID};
            border: none;
            text-align: left;
            padding: 2px 2px;
            font-size: 12px;
            font-weight: bold;
        }}
        #LogToggle:hover {{
            color: {GOLD_TEXT};
        }}
        #LogToggle:checked {{
            color: {GOLD_TEXT};
        }}

        #BenefitTable {{
            background: {BG_INPUT};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 4px;
            font-size: 13px;
            gridline-color: {BORDER};
        }}
        #BenefitTable QHeaderView::section {{
            background: {BG_MID};
            color: {GOLD_TEXT};
            border: none;
            border-right: 1px solid {BORDER};
            border-bottom: 1px solid {BORDER};
            padding: 3px 6px;
            font-size: 12px;
            font-weight: bold;
        }}
        #BenefitTable::item {{
            padding: 2px 4px;
        }}
        #BenefitIndex {{
            background: {BG_DARK};
            color: {TEXT};
            border: 1px solid {GOLD};
            border-radius: 3px;
            padding: 2px 6px;
            font-size: 12px;
            min-width: 78px;
        }}

        QCheckBox#BenefitCheck::indicator {{
            width: 17px;
            height: 17px;
            border: 2px solid {GOLD};
            border-radius: 4px;
            background: {BG_DARK};
        }}
        QCheckBox#BenefitCheck::indicator:hover {{
            border-color: {GOLD_PRIMARY};
            background: {BG_MID};
        }}
        QCheckBox#BenefitCheck::indicator:checked {{
            background: {GOLD_PRIMARY};
            border-color: {GOLD};
            image: none;
        }}

        QProgressBar {{
            background: {BG_INPUT};
            border: 1px solid {BORDER};
            border-radius: 4px;
            text-align: center;
            color: {TEXT};
            font-size: 12px;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {BLUE}, stop:1 {GOLD});
            border-radius: 3px;
        }}

        #FilePreview {{
            color: {TEXT_MID};
            font-size: 11px;
            font-style: italic;
            padding-left: 8px;
        }}

        QTabWidget::pane {{
            border: 1px solid {BORDER};
            border-radius: 4px;
            top: -1px;
            background: {BG_DARK};
        }}
        QTabBar::tab {{
            background: {BG_MID};
            color: {TEXT_MID};
            border: 1px solid {BORDER};
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            padding: 6px 18px;
            margin-right: 2px;
            font-size: 13px;
            font-weight: bold;
        }}
        QTabBar::tab:selected {{
            background: {BLUE};
            color: {GOLD_TEXT};
            border-color: {GOLD};
        }}
        QTabBar::tab:hover:!selected {{
            background: {BLUE_LIGHT};
            color: {TEXT};
        }}
    """
