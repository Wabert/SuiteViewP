"""Configuration, styles and small helpers for the Policy Support tab."""

from __future__ import annotations

import calendar
import json
import os
from datetime import date
from typing import List

from suiteview.core.profile_paths import profile_path
from suiteview.core.json_store import write_json
from suiteview.core.support_files import (
    abr_support_directory,
    onedrive_directory,
    policy_support_directory,
    process_control_directory,
)
from ..styles import (
    GRAY_DARK,
    GRAY_LIGHT,
    GRAY_MID,
    GOLD_DARK,
    GOLD_LIGHT,
    GOLD_PRIMARY,
    GOLD_TEXT,
    GREEN_DARK,
    GREEN_PRIMARY,
    GREEN_SUBTLE,
    WHITE,
)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _get_process_control_dir() -> str:
    return process_control_directory()


def _get_onedrive_dir() -> str:
    return onedrive_directory()


def _get_abr_root_dir() -> str:
    return os.path.dirname(abr_support_directory())


def _get_policy_support_dir() -> str:
    return policy_support_directory()

def _get_policy_library_dir() -> str:
    return os.path.join(_get_policy_support_dir(), "POLICY_LIBRARY")

def _get_abr_dir() -> str:
    return abr_support_directory()


# ---------------------------------------------------------------------------
# Pinned tool folders shown on the Available Tools home screen
# Each entry: (display_label, relative_path_from_onedrive_root)
# ---------------------------------------------------------------------------

TOOL_FOLDERS = [
    ("Tools\\Illustration\\RERUN",
    r"Life Product - Process_Control\Tools\Illustration\RERUN"),
    ("Tools\\Illustration\\Product Models\\TERM",
    r"Life Product - Process_Control\Tools\Illustration\Product Models\TERM"),
    ("Task\\Policy Support\\Term Premiums Illustrations\\TERM TEMPLATE",
    r"Life Product - Process_Control\Task\Policy Support\Term Premiums Illustrations\TERM TEMPLATE"),
    ("Task\\Policy Support\\Guideline and TAMRA\\Guideline Adjust for Exception Prems",
    r"Life Product - Process_Control\Task\Policy Support\Guideline and TAMRA\Guideline Adjust for Exception Prems"),
    ("Task\\Policy Support\\Mistatement",
    r"Life Product - Process_Control\Task\Policy Support\Mistatement"),
    ("Task\\Policy Support\\Interpolated_Terminal_Reserve",
    r"Life Product - Process_Control\Task\Policy Support\Interpolated_Terminal_Reserve"),
    ("Task\\Policy Support",
    r"Life Product - Process_Control\Task\Policy Support"),
    ("Tools\\Whole Life Nonforfeiture Calc",
    r"Life Product - Process_Control\Tools\Whole Life Nonforfeiture Calc"),
    ("Cyberlife Reference Files",
    r"Life Product - Data\Cyberlife Reference Files"),
    ("Task\\Accelerated Death Benefit (ABR11 & ABR14)",
    r"Life Product - Accelerated_Benefits\Accelerated Death Benefit (ABR11 & ABR14)"),
]


# ---------------------------------------------------------------------------
# Default task categories
# ---------------------------------------------------------------------------

DEFAULT_TASK_CATEGORIES = [
    "Annual_Statement",
    "Annuity_Rider",
    "Cash_Value_Quote",
    "Decrease",
    "GLP_Exception",
    "Illustration",
    "Increase",
    "Interpolated_Terminal_Reserve",
    "Mistatement",
    "Nonforfeiture",
    "Product_Contract_and_Specs",
    "Reinstatement",
    "Time_Driven_Error",
]


# ---------------------------------------------------------------------------
# User task storage
# ---------------------------------------------------------------------------

def _get_user_tasks_path() -> str:
    return str(profile_path("policy_support_tasks.json"))

def _load_user_tasks() -> List[str]:
    path = _get_user_tasks_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return sorted(data) if isinstance(data, list) else []
    except Exception:
        return []

def _save_user_tasks(tasks: List[str]):
    path = _get_user_tasks_path()
    write_json(path, sorted(set(tasks)), ensure_ascii=True)


def _safe_anniversary(issue_date: date, year: int) -> date:
    try:
        return issue_date.replace(year=year)
    except ValueError:
        return issue_date.replace(year=year, day=28)


def _add_months(base: date, months: int) -> date:
    month_index = base.month - 1 + months
    year = base.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


GLP_HELP_TEXT = """GLP Exception Quote - what this screen does

This screen answers a practical question for a Universal Life / Guideline Premium policy: to keep the policy in force through a target date, will the policy have to pay guideline exception premiums, and if so, how much room must be created in the Accum GLP so CyberLife will accept them?

How the solve works

1. Minimum premium to the target date. When you click Calculate, the tool solves for the smallest level premium (paid on the policy's current mode) that keeps the policy in force through the target date, with exception premiums allowed in the forecast. The solve stops at the target date - it is not a solve to maturity, because premium the policy would need years later has no bearing on whether the Accum GLP must be opened up now.

If opening account value is negative, first fund the shortfall through the next modal payment with a one-time lump sum, then solve the ongoing premium above it. The first forecast payment combines the lump sum and any premium due that month; the lump sum is not repeated. Loads, guideline/TAMRA caps and exception rules still apply. Ordinary funding is solved as close to zero as cent-rounded premiums and the engine's positive-value lapse boundary permit; exact zero is available when protected by the exception rules.

2. The answer lands in one of three places. The minimum may be $0, meaning the account value alone carries the policy to the target date. It may be a positive premium that fits inside the remaining guideline room, which the policy can simply pay. Or the room may run out before the policy can be funded, at which point the forecast starts paying guideline exception premiums.

3. Only the third case needs an adjustment. If an exception premium fires before the target date, the policy will have to pay exception premiums to get there and the Accum GLP must be raised. If none fires, no exception premiums are needed for this target and the Accum GLP should be left alone.

Ordinary funding must leave positive surrender value (account value less surrender charges and debt), not just a positive account value. An exception premium funds the engine's zero-value exception boundary. The forecast stops before the target date: no premium, monthly deduction, or anniversary change on that date is included.

Solving for the minimum is what makes this test fair - a larger premium can collide with the guideline for reasons the policy never actually has to incur.

Why the Accum GLP has to be adjusted

Once a policy enters the exception premium period it stays there. It can no longer build cash value, and it may only take in enough premium to cover its monthly deductions. For CyberLife to accept those exception premiums, the guideline has to be opened up: the GLP is set to 0 and the Accum GLP is raised just enough to admit the exception premiums needed through the target date.

The adjustment is sized with:

    Accum GLP Adjustment = max(0, Premiums-to-Date - AccumWDs - AccumGLP)

All three forecasts start from the same valuation-date snapshot as RERUN. Opening AV is already after that month's deduction; no later premium receipts are added to this earlier balance. Interest uses monthly compounding, matching RERUN with Exact Days Interest unchecked. The opening deduction is displayed for reference, not deducted again.

Premiums-to-Date is the valuation-date premium accumulator plus all ordinary and exception premiums in the independently solved GLP=0 forecast before the target date. Loan repayments are not premiums. AccumWDs are valuation-date accumulated withdrawals, which create room. AccumGLP is the starting Accum GLP. Only if the original scenario requires exception premiums should the GLP be set to 0 and the Accum GLP raised to the New Accum GLP shown.

Note that the New Accum GLP only covers the policy up to (but not including) the target date. Because the policy remains in the exception premium period, the Accum GLP will need to be recalculated and adjusted again each year going forward.

The forecast tables

The tables use the RERUN Values Overview columns in the same order. AV and SV are before interest; EAV and ESV are ending values. GLP, GSP, TotalGP and SubjectPayments show the guideline position. Prem excludes Exception Prem, and Withdrawals excludes ForceOuts. Contributions includes loan repayments plus ordinary and exception premiums; Distributions includes withdrawals, forceouts and new loans. Status retains RERUN's exception, MEC and lapse indicators. An explicit zero-premium schedule overrides normal billing, but engine exception premiums may still be required and are shown separately.

All three forecast tabs are always available. Min Prem To Target keeps the current GLP. Min Prem To Target (GLP=0) independently solves the same policy with starting GLP set to zero, retaining current accumulated guideline premiums, guideline caps, forceouts and exception premiums. Min Prem to Target (no forceout) independently solves GLP=0 with only forceout distributions suppressed: premium acceptance caps, TEFRA/TAMRA, targets and exception premiums are unchanged. It is a comparison only, not the basis for the adjustment. All three exclude deductions on the target date. If the original scenario needs exceptions, the regular GLP=0 scenario's total premium outlay (Prem + Exception Prem, not loan repayments) sizes the AccumGLP adjustment; otherwise do not adjust. Columns and amounts match the RERUN Values Overview monthly ledger."""


_GLP_PREMIUM_MODE_LABELS = {"M": "monthly", "Q": "quarterly", "S": "semi-annual", "A": "annual"}


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

_CONTEXT_MENU_STYLE = f"""
    QMenu {{
        background-color: #F0F0F0;
        border: 1px solid {GRAY_DARK};
        padding: 2px;
        font-size: 11px;
    }}
    QMenu::item {{ padding: 3px 20px 3px 8px; color: #1a1a1a; }}
    QMenu::item:selected {{ background-color: {GOLD_LIGHT}; color: {GREEN_DARK}; }}
    QMenu::item:disabled {{ color: #999999; }}
    QMenu::separator {{ height: 1px; background: {GRAY_MID}; margin: 2px 4px; }}
"""

_LIST_STYLE = f"""
    QListWidget {{
        font-size: 11px;
        border: none;
        background-color: {WHITE};
        outline: none;
        padding: 0px;
        margin: 0px;
    }}
    QListWidget::item {{
        padding: 0px 4px;
        margin: 0px;
        border: none;
        min-height: 0px;
    }}
    QListWidget::item:hover   {{ background-color: {GREEN_SUBTLE}; }}
    QListWidget::item:selected {{ background-color: {GOLD_LIGHT}; color: {GREEN_DARK}; font-weight: bold; }}
"""

_ACTION_BTN_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {GOLD_TEXT}, stop:1 {GOLD_PRIMARY});
        color: {GREEN_DARK};
        border: 1px solid {GOLD_DARK};
        border-radius: 3px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: bold;
        min-height: 18px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {GOLD_PRIMARY}, stop:1 {GOLD_DARK});
        color: {WHITE};
    }}
    QPushButton:pressed {{ background-color: {GOLD_DARK}; }}
    QPushButton:disabled {{
        background: {GRAY_MID}; color: {GRAY_DARK}; border-color: {GRAY_MID};
    }}
"""

_FILTER_INPUT_STYLE = f"""
    QLineEdit {{
        background: {WHITE};
        color: {GRAY_DARK};
        border: 1px solid {GRAY_MID};
        border-radius: 3px;
        padding: 3px 6px;
        font-size: 11px;
        min-height: 18px;
    }}
    QLineEdit:focus {{ border-color: {GREEN_PRIMARY}; }}
"""

_MODE_BTN_ACTIVE_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {GREEN_PRIMARY}, stop:1 {GREEN_DARK});
        color: {WHITE};
        border: 2px solid {GREEN_DARK};
        border-radius: 4px;
        padding: 4px 6px;
        font-size: 11px;
        font-weight: bold;
        min-height: 22px;
    }}
"""

_MODE_BTN_INACTIVE_STYLE = f"""
    QPushButton {{
        background: {GRAY_LIGHT};
        color: {GRAY_DARK};
        border: 1px solid {GRAY_MID};
        border-radius: 4px;
        padding: 4px 6px;
        font-size: 11px;
        font-weight: bold;
        min-height: 22px;
    }}
    QPushButton:hover {{
        background: {GREEN_SUBTLE};
        color: {GREEN_DARK};
        border-color: {GREEN_PRIMARY};
    }}
    QPushButton:disabled {{
        background: {GRAY_LIGHT};
        color: {GRAY_MID};
        border-color: {GRAY_MID};
    }}
"""

_NAV_PANEL_STYLE = f"""
    QWidget#PolicySupportNavPanel {{
        background-color: {GREEN_SUBTLE};
        border: 2px solid {GREEN_PRIMARY};
        border-radius: 8px;
    }}
"""

_RESULT_VALUE_STYLE = f"""
    font-size: 11px;
    color: {GREEN_DARK};
    font-weight: normal;
    background: transparent;
    border: none;
"""

_RESULT_LABEL_STYLE = f"""
    font-size: 11px;
    color: {GRAY_DARK};
    background: transparent;
    border: none;
"""

_NAV_BTN_STYLE = f"""
    QPushButton {{
        background: {GREEN_SUBTLE};
        color: {GREEN_DARK};
        border: 1px solid {GREEN_PRIMARY};
        border-radius: 3px;
        padding: 1px 5px;
        font-size: 11px;
        font-weight: bold;
        min-height: 16px;
        max-height: 18px;
    }}
    QPushButton:hover {{ background: {GREEN_PRIMARY}; color: {WHITE}; }}
    QPushButton:disabled {{ background: {GRAY_LIGHT}; color: {GRAY_MID}; border-color: {GRAY_MID}; }}
"""

_PATH_BAR_STYLE = f"""
    font-size: 10px;
    color: {GREEN_DARK};
    background: {GREEN_SUBTLE};
    border: 1px solid {GREEN_PRIMARY};
    border-radius: 3px;
    padding: 1px 4px;
"""

_STATUS_STYLE = f"""
    font-size: 10px; color: {GRAY_DARK};
    background: transparent; border: none; padding: 2px 4px;
"""

_PATH_LABEL_STYLE = f"""
    font-size: 10px; color: {GREEN_DARK};
    background: {GREEN_SUBTLE};
    border: 1px solid {GREEN_PRIMARY};
    border-radius: 3px; padding: 3px 6px;
"""

_GLP_FORECAST_TABS_STYLE = f"""
    QTabWidget::pane {{
        border: 1px solid {GREEN_PRIMARY};
        border-radius: 3px;
        top: -1px;
        background: {WHITE};
    }}
    QTabBar::tab {{
        background: {GREEN_SUBTLE};
        color: {GREEN_DARK};
        font-size: 11px;
        font-weight: bold;
        padding: 4px 14px;
        border: 1px solid {GREEN_PRIMARY};
        border-bottom: none;
        border-top-left-radius: 3px;
        border-top-right-radius: 3px;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        background: {GREEN_PRIMARY};
        color: {WHITE};
    }}
    QTabBar::tab:!selected {{
        margin-top: 2px;
    }}
"""

# ── ABR (Crimson) theme overrides ──────────────────────────────────────────
# These mirror the green/gold styles above but use ABR crimson/slate colours.

_CRIMSON_DARK    = "#5C0A14"
_CRIMSON_PRIMARY = "#8B1A2A"
_CRIMSON_RICH    = "#A52535"
_CRIMSON_LIGHT   = "#C96070"
_CRIMSON_SUBTLE  = "#F9ECED"
_SLATE_PRIMARY   = "#4A6FA5"
_SLATE_TEXT      = "#B8D0F0"
_SLATE_DARK      = "#2E4F85"

_ABR_FRAME_STYLE = f"""
    QGroupBox {{
        font-size: 11px;
        font-weight: bold;
        color: {_CRIMSON_DARK};
        border: 2px solid {_CRIMSON_PRIMARY};
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
        background-color: {_CRIMSON_PRIMARY};
        color: {_SLATE_TEXT};
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

_ABR_LIST_STYLE = f"""
    QListWidget {{
        font-size: 11px;
        border: none;
        background-color: {WHITE};
        outline: none;
        padding: 0px;
        margin: 0px;
    }}
    QListWidget::item {{
        padding: 0px 4px;
        margin: 0px;
        border: none;
        min-height: 0px;
    }}
    QListWidget::item:hover   {{ background-color: {_CRIMSON_SUBTLE}; }}
    QListWidget::item:selected {{ background-color: {_SLATE_PRIMARY}; color: {WHITE}; font-weight: bold; }}
"""

_ABR_NAV_BTN_STYLE = f"""
    QPushButton {{
        background: {_CRIMSON_SUBTLE};
        color: {_CRIMSON_DARK};
        border: 1px solid {_CRIMSON_PRIMARY};
        border-radius: 3px;
        padding: 1px 5px;
        font-size: 11px;
        font-weight: bold;
        min-height: 16px;
        max-height: 18px;
    }}
    QPushButton:hover {{ background: {_CRIMSON_PRIMARY}; color: {WHITE}; }}
    QPushButton:disabled {{ background: {GRAY_LIGHT}; color: {GRAY_MID}; border-color: {GRAY_MID}; }}
"""

_ABR_PATH_BAR_STYLE = f"""
    font-size: 10px;
    color: {_CRIMSON_DARK};
    background: {_CRIMSON_SUBTLE};
    border: 1px solid {_CRIMSON_PRIMARY};
    border-radius: 3px;
    padding: 1px 4px;
"""

_ABR_PATH_LABEL_STYLE = f"""
    font-size: 10px; color: {_CRIMSON_DARK};
    background: {_CRIMSON_SUBTLE};
    border: 1px solid {_CRIMSON_PRIMARY};
    border-radius: 3px; padding: 3px 6px;
"""

_ABR_ACTION_BTN_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {_SLATE_TEXT}, stop:1 {_SLATE_PRIMARY});
        color: {WHITE};
        border: 1px solid {_SLATE_DARK};
        border-radius: 3px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: bold;
        min-height: 18px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {_SLATE_PRIMARY}, stop:1 {_SLATE_DARK});
        color: {WHITE};
    }}
    QPushButton:pressed {{ background-color: {_SLATE_DARK}; }}
    QPushButton:disabled {{
        background: {GRAY_MID}; color: {GRAY_DARK}; border-color: {GRAY_MID};
    }}
"""

_MODE_BTN_ABR_ACTIVE_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {_CRIMSON_RICH}, stop:1 {_CRIMSON_PRIMARY});
        color: {WHITE};
        border: 2px solid {_CRIMSON_DARK};
        border-radius: 4px;
        padding: 4px 6px;
        font-size: 11px;
        font-weight: bold;
        min-height: 22px;
    }}
"""

# Mime type tokens used for drag-and-drop
_MIME_CATEGORY = "application/x-suiteview-category"
_MIME_TOOL_FILE = "application/x-suiteview-toolfile"
