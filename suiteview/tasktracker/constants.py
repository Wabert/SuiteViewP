"""
TaskTracker Constants — Colors, fonts, layout values, seed contacts.

Crimson & Slate theme — a rich crimson paired with cool slate greys.
"""

# ════════════════════════════════════════════════════════════════════
#  Color palette  — Crimson & Slate theme
# ════════════════════════════════════════════════════════════════════

class C:
    """Color constants — Crimson & Slate theme.

    Primary: Crimson (#DC143C) — headers, accents, active elements
    Secondary: Slate (#708090) — borders, highlights, accents
    """

    # Primary crimson tones
    BLUE        = "#8B0A25"       # Deep crimson (primary dark)
    BLUE_LIGHT  = "#B01030"       # Lighter crimson (hover)
    BLUE_MID    = "#6B0820"       # Mid crimson
    BLUE_PALE   = "#F5EAED"       # Pale rose / crimson wash background
    BLUE_BG     = "#5A0A1E"       # Dark crimson background
    BLUE_LIST_BG = "#4A0818"      # Darkest crimson for list background

    # Header colours (crimson gradient)
    HEADER_BLUE      = "#DC143C"  # Crimson
    HEADER_BLUE_END  = "#E8405E"  # Lighter crimson end
    HEADER_FLAT      = "#D4506A"  # Lighter rose-crimson for card list bg

    # Stronger border for detail-panel sections
    SECTION_BORDER = "#8B0A25"    # Deep crimson border

    # Secondary: Slate tones (replacing gold)
    GOLD        = "#708090"       # Slate grey (accent)
    GOLD_PALE   = "#ECF0F3"       # Pale slate wash
    GOLD_BORDER = "#8A9BAD"       # Lighter slate border

    BORDER         = "#B8C4CE"    # Cool grey border
    BORDER_ON_DARK = "#8A6070"    # Muted crimson-grey on dark

    TEXT       = "#1a2332"
    TEXT_MID   = "#4a5568"
    TEXT_LIGHT = "#7a8599"

    WHITE = "#ffffff"

    GREEN     = "#1a8a4a"
    GREEN_DOT = "#1a8a4a"

    RED        = "#c53030"
    RED_CARD   = "#f9d4d4"
    RED_BORDER = "#e8a0a0"
    RED_DARK   = "#b91c1c"

    YELLOW_DOT = "#DC143C"        # Crimson dot for activity

    # Derived / compound colours used in card rendering
    GOLD_TRANSLUCENT = "rgba(112,128,144,0.6)"   # Slate translucent
    WHITE_TRANSLUCENT = "rgba(255,255,255,0.25)"
    CLOSED_BG = "rgba(255,255,255,0.6)"
    GREEN_CLOSED_BORDER = "#8ac4a0"


# ════════════════════════════════════════════════════════════════════
#  Fonts
# ════════════════════════════════════════════════════════════════════

FONT_FAMILY = "Segoe UI, Tahoma, sans-serif"
MONO_FAMILY = "Cascadia Code, Consolas, monospace"


# ════════════════════════════════════════════════════════════════════
#  Column widths (pixels)
# ════════════════════════════════════════════════════════════════════

COL_ID_WIDTH       = 80
COL_DATE_WIDTH     = 100
COL_ACTIVITY_WIDTH = 110
# Assignee column is flex (takes remaining space)


# ════════════════════════════════════════════════════════════════════
#  Detail panel constraints
# ════════════════════════════════════════════════════════════════════

DETAIL_MIN_WIDTH = 200
DETAIL_MAX_WIDTH = 700
LIST_WIDTH = 460
DETAIL_DEFAULT_WIDTH = 690   # 1.5 × LIST_WIDTH

RESIZE_HANDLE_WIDTH = 6


# ════════════════════════════════════════════════════════════════════
#  Task status values
# ════════════════════════════════════════════════════════════════════

STATUS_OPEN   = "open"
STATUS_CLOSED = "closed"

TASK_ID_PREFIX = "TSK"


# ════════════════════════════════════════════════════════════════════
#  Seed contacts (Robert's team of 7)
# ════════════════════════════════════════════════════════════════════

SEED_CONTACTS = [
    {"name": "John Martinez",  "email": "john.martinez@company.com"},
    {"name": "Sarah Chen",     "email": "sarah.chen@company.com"},
    {"name": "Mike Thompson",  "email": "mike.thompson@company.com"},
    {"name": "Lisa Patel",     "email": "lisa.patel@company.com"},
    {"name": "David Kim",      "email": "david.kim@company.com"},
    {"name": "Rachel Woods",   "email": "rachel.woods@company.com"},
    {"name": "James Taylor",   "email": "james.taylor@company.com"},
]


# ════════════════════════════════════════════════════════════════════
#  Email scan interval
# ════════════════════════════════════════════════════════════════════

EMAIL_SCAN_INTERVAL_MS = 60_000   # 60 seconds


# ════════════════════════════════════════════════════════════════════
#  Version
# ════════════════════════════════════════════════════════════════════

VERSION = "v1.0"
