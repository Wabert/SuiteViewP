"""Semantic visual identity tokens for SuiteView."""

from __future__ import annotations

from dataclasses import dataclass

# Core SuiteView brand colors.
BRAND_BLUE = "#1E5BA8"
BRAND_BLUE_LIGHT = "#2A5AAA"
BRAND_BLUE_DARK = "#0D3A7A"
BRAND_BLUE_DEEP = "#082B5C"
GOLD_BORDER = "#D4A017"
GOLD_DARK = "#B8860B"
GOLD_TEXT = "#FFD54F"
GOLD_LIGHT = "#FFF3D0"
GOLD_BUTTON = "#FFC107"

# Shared neutral roles.
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F5F7FA"
SURFACE_PANEL = "#FFF9E6"
SURFACE_WARNING = "#FFF4C2"
TEXT = "#2D3748"
TEXT_MUTED = "#4A5568"
TEXT_DARK = "#1A202C"
BORDER = "#E1E5EB"
BORDER_MUTED = "#A0B8D8"
SELECTION = "#A0C4E8"
INPUT_FOCUS_SURFACE = "#F5F8FF"
DISABLED_SURFACE = "#F0F0F0"
DISABLED_TEXT = "#A0AEC0"
MUTED_CONTROL_SURFACE = "#E4E4E4"
CONTROL_HOVER_SURFACE = "#F8FBFF"
AUDIT_CHECKED_BORDER = "#14407A"
AUDIT_PRESSED_SURFACE = "#C0D8F0"

# Shared component states.
TAB_IDLE_START = "#E0E0E0"
TAB_IDLE_END = "#BDBDBD"
STATUS_OK = "#27AE60"
STATUS_OK_DARK = "#229954"
STATUS_OK_LIGHT = "#2ECC71"
STATUS_WARN = "#B58900"
STATUS_ERROR = "#C62828"
STATUS_ERROR_DARK = "#C0392B"
STATUS_ERROR_LIGHT = "#EC7063"
STATUS_INFO = "#2563EB"
WINDOW_CLOSE_HOVER = "#E81123"

# Common typography and spacing tokens for dense PyQt views.
FONT_FAMILY_UI = "Segoe UI"
FONT_FAMILY_MONO = "'Cascadia Code', 'Consolas', monospace"
FONT_SIZE_COMPACT_PT = 9
FONT_SIZE_BODY_PX = 11
FONT_SIZE_LABEL_PX = 12
FONT_SIZE_SECTION_PX = 13
CONTROL_HEIGHT_COMPACT = 22
ROW_HEIGHT_COMPACT = 16
SPACE_XS = 2
SPACE_SM = 4
SPACE_MD = 8
RADIUS_SM = 3
RADIUS_MD = 4
RADIUS_LG = 8


@dataclass(frozen=True)
class AppPalette:
    """Stable brand palette for one SuiteView application."""

    primary: str
    primary_dark: str
    primary_light: str
    accent: str
    accent_text: str
    header_start: str
    header_mid: str
    header_end: str
    border: str
    body: str
    subtle: str
    surface: str = SURFACE
    surface_alt: str = SURFACE_ALT
    text: str = TEXT
    text_muted: str = TEXT_MUTED
    selection: str = SELECTION
    selection_text: str = TEXT
    scroll: str = BORDER_MUTED


DEFAULT = AppPalette(
    primary=BRAND_BLUE,
    primary_dark=BRAND_BLUE_DARK,
    primary_light=BRAND_BLUE_LIGHT,
    accent=GOLD_BORDER,
    accent_text=GOLD_TEXT,
    header_start=BRAND_BLUE,
    header_mid=BRAND_BLUE_DARK,
    header_end=BRAND_BLUE_DEEP,
    border=GOLD_BORDER,
    body=SURFACE_ALT,
    subtle="#E3ECF7",
    selection=SELECTION,
    selection_text=TEXT_DARK,
)
AUDIT = DEFAULT

POLVIEW = AppPalette(
    primary="#1B5E20",
    primary_dark="#0A3D0A",
    primary_light="#4CAF50",
    accent=GOLD_BORDER,
    accent_text=GOLD_TEXT,
    header_start="#0A3D0A",
    header_mid="#1B5E20",
    header_end="#2E7D32",
    border=GOLD_BORDER,
    body="#C8E6C9",
    subtle="#E8F5E9",
    selection=GOLD_LIGHT,
    selection_text="#0A3D0A",
    scroll="#81C784",
)
POLVIEW_DUPLICATE_HEADER = ("#2E7D32", "#4CAF50", "#66BB6A")

ABR = AppPalette(
    primary="#8B1A2A",
    primary_dark="#5C0A14",
    primary_light="#C96070",
    accent="#4A6FA5",
    accent_text="#B8D0F0",
    header_start="#5C0A14",
    header_mid="#8B1A2A",
    header_end="#A52535",
    border="#4A6FA5",
    body="#EDD8DA",
    subtle="#F9ECED",
    selection="#D8E4F4",
    selection_text="#5C0A14",
    scroll="#C08090",
)
ABR_SLATE_DARK = "#2E4F85"

ILLUSTRATION = AppPalette(
    primary="#5E35A5",
    primary_dark="#2A1458",
    primary_light="#7E57C2",
    accent=GOLD_BORDER,
    accent_text=GOLD_TEXT,
    header_start="#2A1458",
    header_mid="#4B2383",
    header_end="#5E35A5",
    border=GOLD_BORDER,
    body="#EDE7F6",
    subtle="#F6F1FB",
    selection="#F6F1FB",
    selection_text="#2A1458",
    scroll="#B79CDE",
)

RATEMANAGER = AppPalette(
    primary="#1A3A7A",
    primary_dark=BRAND_BLUE_DARK,
    primary_light=BRAND_BLUE_LIGHT,
    accent=GOLD_BORDER,
    accent_text=GOLD_TEXT,
    header_start=BRAND_BLUE,
    header_mid=BRAND_BLUE_DARK,
    header_end=BRAND_BLUE_DEEP,
    border=GOLD_BORDER,
    body="#1E1E2E",
    subtle="#343456",
    surface="#32325A",
    surface_alt="#343456",
    text="#E8E8F0",
    text_muted="#A8A8C4",
    selection="#1A3A7A",
    selection_text=GOLD_TEXT,
    scroll="#55558A",
)

MAINFRAME = AppPalette(
    primary="#4A6FA5",
    primary_dark="#3A5A8A",
    primary_light="#5A7FB5",
    accent=GOLD_BORDER,
    accent_text=GOLD_TEXT,
    header_start=BRAND_BLUE,
    header_mid=BRAND_BLUE_DARK,
    header_end=BRAND_BLUE_DEEP,
    border=GOLD_BORDER,
    body=SURFACE_PANEL,
    subtle="#C0D4F0",
    selection="#B0C8E8",
    selection_text="#0A1E5E",
)


@dataclass(frozen=True)
class ModeColor:
    """Color pair for an Audit build-mode identity."""

    color: str
    tint: str


AUDIT_MODE_CYBERLIFE = ModeColor(BRAND_BLUE, "#E3ECF7")
AUDIT_MODE_VISUAL = ModeColor("#2E7D32", "#E6F3E6")
AUDIT_MODE_MANUAL_SQL = ModeColor("#5A3218", "#F4E9DC")
AUDIT_MODE_FILE_SOURCE = ModeColor(STATUS_WARN, SURFACE_WARNING)
AUDIT_MODE_EXECUTABLE = ModeColor("#374151", "#E5E7EB")
AUDIT_MODE_DEFAULT = ModeColor("#475569", "#E8ECF1")
AUDIT_MODE_DATAFORGE = ModeColor("#C2410C", "#FFEDD5")
AUDIT_MODE_GROUP = ModeColor("#3F3F46", "#ECEAE6")


@dataclass(frozen=True)
class IllustrationStyle:
    """Illustration-only component colors that extend the app palette."""

    issue_header: tuple[str, str, str]
    snapshot_header: tuple[str, str, str]
    issue_primary: str
    issue_dark: str
    issue_light: str
    issue_body: str
    table_rule: str
    disabled_surface: str
    disabled_text: str
    value_gloss: tuple[str, str, str, str, str]
    value_hover: tuple[str, str, str, str, str]
    value_pressed: tuple[str, str]
    value_matured: tuple[str, str, str, str, str]
    value_matured_hover: tuple[str, str, str]
    value_matured_text: str
    value_matured_border: str
    input_border: str
    input_readonly_surface: str
    input_disabled_text: str
    input_small_button_surface: str
    input_small_button_hover: str
    invalid_surface: str
    checkbox_hover_surface: str
    checkbox_disabled_text: str
    checkbox_disabled_border: str
    checkbox_disabled_surface: str
    checkbox_disabled_checked: str
    gold_highlight: str
    gold_shadow: str
    gold_soft_text: str
    menu_hover_text: str


ILLUSTRATION_STYLE = IllustrationStyle(
    issue_header=("#123C56", "#205B78", "#317897"),
    snapshot_header=("#9E7BD8", "#8E67CE", "#7E57C2"),
    issue_primary="#6F9FBE",
    issue_dark="#315F7D",
    issue_light="#A9C9DD",
    issue_body="#EAF4FA",
    table_rule="#D8C8F0",
    disabled_surface="#ECECEC",
    disabled_text="#666666",
    value_gloss=("#B99AF0", "#7E57C2", "#5E35A5", "#4B2383", "#2A1458"),
    value_hover=("#D1BEF7", "#9270D2", "#6E43B8", "#5E35A5", "#3B1B70"),
    value_pressed=("#2A1458", "#5E35A5"),
    value_matured=("#E7DDF7", "#CDBDEC", "#B9A6E0", "#6E5E92", "#C9BBE2"),
    value_matured_hover=("#EFE8FA", "#D9CCF1", "#C7B7E8"),
    value_matured_text="#6E5E92",
    value_matured_border="#C9BBE2",
    input_border="#B79CDE",
    input_readonly_surface="#E8DDF8",
    input_disabled_text="#7A6B91",
    input_small_button_surface="#F3ECFC",
    input_small_button_hover="#E6DAF8",
    invalid_surface="#FDECEA",
    checkbox_hover_surface="#FBF9FE",
    checkbox_disabled_text="#9A8FB0",
    checkbox_disabled_border="#C9B8E4",
    checkbox_disabled_surface="#EEE7F9",
    checkbox_disabled_checked="#B7A6D6",
    gold_highlight="#FFE08A",
    gold_shadow="#9F7610",
    gold_soft_text="#FFF3B0",
    menu_hover_text="#FFD700",
)


MAINFRAME_NAV_COLORS = {
    "brand_blue": BRAND_BLUE,
    "brand_blue_dark": BRAND_BLUE_DARK,
    "brand_blue_deep": BRAND_BLUE_DEEP,
    "nav_text": "#1A3A6E",
    "nav_text_dark": "#0A1E5E",
    "panel_bg": SURFACE_PANEL,
    "panel_header": "#C0D4F0",
    "panel_border": BORDER_MUTED,
    "primary": MAINFRAME.primary,
    "primary_border": MAINFRAME.primary_dark,
    "primary_hover": MAINFRAME.primary_light,
    "viewer_hover": "#3D5A7F",
    "disabled_bg": "#B0C0D8",
    "disabled_text": "#7A8A9E",
    "disabled_border": "#95A5B8",
    "action_blue": "#3498DB",
    "action_blue_border": "#2980B9",
    "action_blue_hover": "#5DADE2",
    "success": STATUS_OK,
    "success_border": STATUS_OK_DARK,
    "success_hover": STATUS_OK_LIGHT,
    "danger": "#E74C3C",
    "danger_border": STATUS_ERROR_DARK,
    "danger_hover": STATUS_ERROR_LIGHT,
    "dark_disabled": "#5D6D7E",
    "dark_disabled_border": "#4A5A6A",
    "dark_disabled_text": "#95A5A6",
    "breadcrumb_border": "#6B8DC9",
    "focus_blue": STATUS_INFO,
    "tool_grad_top": SURFACE,
    "tool_grad_mid": "#F0F5FF",
    "tool_grad_bottom": "#D0E3FF",
    "tool_grad_hover_mid": "#E3EDFF",
    "tool_grad_hover_bottom": "#B8D0F0",
    "tool_disabled_bg": "#E8EEF7",
    "tool_disabled_text": "#95A5C0",
    "list_selected": MAINFRAME.selection,
    "list_hover": "#C8DCF0",
    "table_selected": "#0078D4",
    "table_header": "#F0F0F0",
    "table_header_border": "#D0D0D0",
    "muted": "#7F8C8D",
    "dark_text": "#2C3E50",
    "note_bg": "#F0F8FF",
    "note_border": "#CCE5FF",
    "note_text": "#666",
    "info_bg": "#E8F4F8",
    "search_bg": "#F8F9FA",
    "search_border": "#BDC3C7",
    "results_bg": "#E8F8F5",
    "filter_text": "#34495E",
    "warning_bg": "#FFF3CD",
    "success_bg": "#D4EDDA",
    "error_bg": "#F8D7DA",
    "dialog_border": "#ccc",
    "dialog_hover_bg": "#F0F0F0",
    "dialog_hover_text": "#333",
    "dialog_hover_border": "#999",
    "secondary_text": "#555",
    "dialog_action": "#2C5F8D",
    "dialog_action_hover": "#1E4A6B",
    "white": SURFACE,
}

RATEMANAGER_DISABLED_TEXT = "#555"
RATEMANAGER_DISABLED_BUTTON = "#333"
RATEMANAGER_DISABLED_BUTTON_TEXT = "#666"
RATEMANAGER_DISABLED_BUTTON_BORDER = "#444"
POLVIEW_DISABLED_TAB_BG = "#EEF1F4"
POLVIEW_LOOKUP_FOCUS = "#FFFEF5"
POLVIEW_TOOLTIP_SURFACE = "#FFFDF2"
BOOKMARK_POPUP_PANEL = "#9EC8EE"
BOOKMARK_POPUP_PANEL_BORDER = "#5A9FD8"
BOOKMARK_POPUP_TITLE_BORDER = "#3A7DC8"
