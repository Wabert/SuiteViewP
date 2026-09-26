"""Mainframe Nav palette and UI style helpers."""

MAINFRAME_NAV_PALETTE = {
    "brand_blue": "#1E5BA8",
    "brand_blue_dark": "#0D3A7A",
    "brand_blue_deep": "#082B5C",
    "nav_text": "#1A3A6E",
    "nav_text_dark": "#0A1E5E",
    "panel_bg": "#FFF9E6",
    "panel_header": "#C0D4F0",
    "panel_border": "#A0B8D8",
    "primary": "#4A6FA5",
    "primary_border": "#3A5A8A",
    "primary_hover": "#5A7FB5",
    "viewer_hover": "#3D5A7F",
    "disabled_bg": "#B0C0D8",
    "disabled_text": "#7A8A9E",
    "disabled_border": "#95A5B8",
    "action_blue": "#3498db",
    "action_blue_border": "#2980b9",
    "action_blue_hover": "#5dade2",
    "success": "#27ae60",
    "success_border": "#229954",
    "success_hover": "#2ecc71",
    "danger": "#e74c3c",
    "danger_border": "#c0392b",
    "danger_hover": "#ec7063",
    "dark_disabled": "#5d6d7e",
    "dark_disabled_border": "#4a5a6a",
    "dark_disabled_text": "#95a5a6",
    "breadcrumb_border": "#6B8DC9",
    "focus_blue": "#2563EB",
    "tool_grad_top": "#FFFFFF",
    "tool_grad_mid": "#F0F5FF",
    "tool_grad_bottom": "#D0E3FF",
    "tool_grad_hover_mid": "#E3EDFF",
    "tool_grad_hover_bottom": "#B8D0F0",
    "tool_disabled_bg": "#E8EEF7",
    "tool_disabled_text": "#95A5C0",
    "list_selected": "#B0C8E8",
    "list_hover": "#C8DCF0",
    "table_selected": "#0078d4",
    "table_header": "#f0f0f0",
    "table_header_border": "#d0d0d0",
    "muted": "#7f8c8d",
    "dark_text": "#2c3e50",
    "white": "#FFFFFF",
}

MAINFRAME_HEADER_COLORS = (
    MAINFRAME_NAV_PALETTE["brand_blue"],
    MAINFRAME_NAV_PALETTE["brand_blue_dark"],
    MAINFRAME_NAV_PALETTE["brand_blue_deep"],
)
MAINFRAME_BORDER_COLOR = "#D4A017"


def c(name: str) -> str:
    """Return a palette color."""
    return MAINFRAME_NAV_PALETTE[name]


def push_button_style(kind: str = "primary", *, dark_disabled: bool = False, font_size: str | None = None) -> str:
    """Shared rounded button stylesheet preserving the Mainframe Nav visuals."""
    variants = {
        "primary": ("primary", "primary_border", "primary_hover", "primary_border"),
        "search": ("action_blue", "action_blue_border", "action_blue_hover", "action_blue_border"),
        "success": ("success", "success_border", "success_hover", "success_border"),
        "danger": ("danger", "danger_border", "danger_hover", "danger_border"),
        "neutral": ("muted", "muted", "dark_disabled", "dark_disabled"),
    }
    bg, border, hover, pressed = variants[kind]
    disabled_bg = "dark_disabled" if dark_disabled else "disabled_bg"
    disabled_border = "dark_disabled_border" if dark_disabled else "disabled_border"
    disabled_text = "dark_disabled_text" if dark_disabled else "disabled_text"
    font_line = f"font-size: {font_size};" if font_size else ""
    border_width = "2px" if kind in {"success", "danger"} else "1px"
    return f"""
        QPushButton {{
            background-color: {c(bg)};
            color: white;
            border: {border_width} solid {c(border)};
            padding: 6px;
            font-weight: bold;
            border-radius: 4px;
            {font_line}
        }}
        QPushButton:hover {{
            background-color: {c(hover)};
            border-color: {c(border)};
        }}
        QPushButton:pressed {{
            background-color: {c(pressed)};
        }}
        QPushButton:disabled {{
            background-color: {c(disabled_bg)};
            color: {c(disabled_text)};
            border: 1px solid {c(disabled_border)};
        }}
    """


def tool_button_style() -> str:
    """Shared breadcrumb navigation button stylesheet."""
    return f"""
        QToolButton {{
            border: 1px solid {c("primary")};
            border-bottom: 2px solid {c("primary_border")};
            border-radius: 4px;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                        stop:0 {c("tool_grad_top")},
                                        stop:0.45 {c("tool_grad_mid")},
                                        stop:1 {c("tool_grad_bottom")});
            color: {c("nav_text_dark")};
            font-weight: 600;
            font-size: 12px;
            padding: 2px 8px;
        }}
        QToolButton:hover:enabled {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                        stop:0 {c("tool_grad_top")},
                                        stop:0.35 {c("tool_grad_hover_mid")},
                                        stop:1 {c("tool_grad_hover_bottom")});
            border-color: {c("focus_blue")};
        }}
        QToolButton:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                        stop:0 {c("tool_grad_hover_bottom")},
                                        stop:1 {c("tool_grad_hover_mid")});
            border: 1px solid {c("primary_border")};
            border-top: 2px solid {c("primary_border")};
        }}
        QToolButton:disabled {{
            color: {c("tool_disabled_text")};
            background: {c("tool_disabled_bg")};
            border: 1px solid {c("disabled_bg")};
        }}
    """


def connections_list_style() -> str:
    return f"""
        QListWidget {{
            border: none;
            background-color: transparent;
            outline: none;
        }}
        QListWidget::item {{
            padding: 8px;
            border: none;
            background-color: transparent;
            color: {c("nav_text")};
        }}
        QListWidget::item:selected {{
            background-color: {c("list_selected")};
            color: {c("nav_text_dark")};
            font-weight: bold;
        }}
        QListWidget::item:hover {{
            background-color: {c("list_hover")};
            color: {c("nav_text_dark")};
            font-weight: bold;
        }}
    """


def breadcrumb_style() -> str:
    return f"""
        QWidget {{
            background-color: {c("panel_bg")};
            border: 2px solid {c("breadcrumb_border")};
            border-radius: 3px;
            padding: 1px;
        }}
        QWidget:hover {{
            border-color: {c("focus_blue")};
        }}
    """


def path_input_style() -> str:
    return f"""
        QLineEdit {{
            background-color: {c("panel_bg")};
            border: none;
            padding: 2px 6px;
            font-size: 11pt;
            color: {c("focus_blue")};
        }}
        QLineEdit:focus {{
            border: 1px solid {c("focus_blue")};
        }}
    """


def search_input_style() -> str:
    return f"""
        QLineEdit {{
            padding: 3px 8px;
            border: 1px solid {c("panel_border")};
            border-radius: 3px;
            background: white;
            color: {c("nav_text")};
            font-size: 10pt;
        }}
        QLineEdit:focus {{
            border: 1px solid {c("focus_blue")};
        }}
    """


def members_table_style(widget_name: str = "QTableWidget") -> str:
    return f"""
        {widget_name} {{
            border: none;
            background-color: white;
            outline: none;
        }}
        {widget_name}::item {{
            padding: 0px;
            margin: 0px;
            border: none;
            outline: none;
        }}
        {widget_name}::item:selected {{
            background-color: {c("table_selected")};
            color: white;
            border: none;
            outline: none;
        }}
        {widget_name}::item:focus {{
            border: none;
            outline: none;
            background-color: {c("table_selected")};
            color: white;
        }}
        QHeaderView::section {{
            background-color: {c("table_header")};
            padding: 4px;
            border: none;
            border-bottom: 1px solid {c("table_header_border")};
            font-weight: normal;
            font-size: 11px;
        }}
    """


def viewer_button_style() -> str:
    """Button style used by dataset preview dialogs."""
    return f"""
        QPushButton {{
            background-color: {c("primary")};
            color: white;
            border: none;
            padding: 6px 12px;
            font-size: 10pt;
        }}
        QPushButton:hover {{
            background-color: {c("viewer_hover")};
        }}
    """
