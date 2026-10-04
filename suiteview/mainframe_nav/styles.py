"""Mainframe Nav palette and UI style helpers."""

from suiteview.ui import tokens

_MAINFRAME_NAV_KEYS = (
    "brand_blue",
    "brand_blue_dark",
    "brand_blue_deep",
    "nav_text",
    "nav_text_dark",
    "panel_bg",
    "panel_header",
    "panel_border",
    "primary",
    "primary_border",
    "primary_hover",
    "viewer_hover",
    "disabled_bg",
    "disabled_text",
    "disabled_border",
    "action_blue",
    "action_blue_border",
    "action_blue_hover",
    "success",
    "success_border",
    "success_hover",
    "danger",
    "danger_border",
    "danger_hover",
    "dark_disabled",
    "dark_disabled_border",
    "dark_disabled_text",
    "breadcrumb_border",
    "focus_blue",
    "tool_grad_top",
    "tool_grad_mid",
    "tool_grad_bottom",
    "tool_grad_hover_mid",
    "tool_grad_hover_bottom",
    "tool_disabled_bg",
    "tool_disabled_text",
    "list_selected",
    "list_hover",
    "table_selected",
    "table_header",
    "table_header_border",
    "muted",
    "dark_text",
    "white",
)
MAINFRAME_NAV_PALETTE = {key: tokens.MAINFRAME_NAV_COLORS[key] for key in _MAINFRAME_NAV_KEYS}
_MAINFRAME_EXTRA_COLORS = {
    key: value
    for key, value in tokens.MAINFRAME_NAV_COLORS.items()
    if key not in MAINFRAME_NAV_PALETTE
}

MAINFRAME_HEADER_COLORS = (
    MAINFRAME_NAV_PALETTE["brand_blue"],
    MAINFRAME_NAV_PALETTE["brand_blue_dark"],
    MAINFRAME_NAV_PALETTE["brand_blue_deep"],
)
MAINFRAME_BORDER_COLOR = tokens.MAINFRAME.border


def c(name: str) -> str:
    """Return a palette color."""
    try:
        return MAINFRAME_NAV_PALETTE[name]
    except KeyError:
        return _MAINFRAME_EXTRA_COLORS[name]


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
            padding: 2px 6px;
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
