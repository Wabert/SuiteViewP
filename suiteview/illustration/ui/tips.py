"""RERUN Tips — a cheat-sheet of the app's hidden-ish features.

Opened from the header "Tips" button. Lists the right-click menus,
double-clicks, drag/drop targets, keyboard shortcuts and hidden tabs that
are easy to forget. When you add a feature like that to RERUN, add a line
here too so users can find it again.
"""

from dataclasses import dataclass
from html import escape

from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QTextBrowser

from suiteview.ui.widgets.frameless_window import FramelessDialog

from .styles import (
    ILLUSTRATION_BORDER_COLOR,
    ILLUSTRATION_HEADER_COLORS,
    PURPLE_BG,
    PURPLE_DARK,
    PURPLE_LIGHT,
    PURPLE_PRIMARY,
    WHITE,
)


@dataclass(frozen=True)
class Tip:
    """One tip: *where* to go (bold lead-in) and *what* it does."""

    where: str
    what: str


@dataclass(frozen=True)
class TipSection:
    title: str
    tips: tuple[Tip, ...]


RERUN_TIPS: tuple[TipSection, ...] = (
    TipSection("Policy Badges", (
        Tip("Badge strip under the policy number",
            "The same badges as PolView. Hover a badge for its detail; "
            "right-click to copy its text."),
        Tip("Timeline / Notes / Copy",
            "Timeline lists every key policy date. Notes are your private notes "
            "for the policy, shared with PolView. Copy puts a policy summary on "
            "the clipboard for email or tickets."),
    )),
    TipSection("Illustration Inputs", (
        Tip("Transactions by date — Grid Inputs tab",
            "Right-click the Input / Illustration Control tab bar and check "
            "Grid Inputs. It holds dated tables for Scheduled Premiums, "
            "Scheduled Loans, Face Amount, DB Option, Unscheduled Premiums, "
            "Unscheduled Loans, Loan Repayments and Withdrawals. The tab is "
            "hidden by default; showing it is remembered per saved case."),
        Tip("Paste from Excel",
            "Right-click any Grid Inputs table → Paste from Clipboard. Copy a "
            "range in Excel first; the table grows to fit."),
        Tip("Premium history from the policy",
            "Right-click the Unscheduled Premiums table → Populate from policy "
            "transactions. Fills every unreversed PR/PI/PA/PF/PT/PB/PW premium "
            "since issue, with its transaction type."),
        Tip("Grid keyboard navigation",
            "Arrow keys, Enter and Tab move between Grid Inputs cells. Dates "
            "should be monthliversary dates — a warning appears if not."),
        Tip("More rows on the Input tab",
            "Use ＋ to add another premium / face / DB option / withdrawal row "
            "and − to remove one."),
        Tip("Keep / change / drop a rider",
            "Click a rider or benefit button under Riders and Benefits. Choose "
            "Keep, Change or Drop, effective by Year or by Date. The button "
            "turns gold for a change and red for a drop."),
    )),
    TipSection("Values", (
        Tip("Drill into a number",
            "Double-click any Overview ledger cell to open the tab where that "
            "value is calculated, pinned to the same month."),
        Tip("See the months",
            "Expand an annual row in the Overview ledger to see its monthly "
            "rows."),
        Tip("Dump the ledger to Excel",
            "Right-click the Overview ledger → Dump Annual Rows (or Annual + "
            "Monthly Rows) to Excel."),
        Tip("Chart click-through",
            "Click a year on the Chart to jump to that year in the Overview."),
        Tip("Find a value",
            "Type in the Find a value… box above the Values Group list to "
            "filter the calculation tabs and columns."),
        Tip("Simple / Guaranteed",
            "Simple collapses the ledger to the key columns. Current Values | "
            "Guaranteed Values appears after a run that has a guaranteed "
            "projection."),
    )),
    TipSection("List Panel & Cases", (
        Tip("List button (header)",
            "Opens the side panel with Policies, Saved Cases and Imported Cases."),
        Tip("Saved Cases",
            "Right-click a case → Rename, Copy, Export or Delete. Ctrl/Shift-click "
            "to multi-select; the Delete key deletes the selection. Click a "
            "column header to sort; the search box matches case names."),
        Tip("Import by drag & drop",
            "Drop .cases.json files anywhere on the List panel to import them."),
        Tip("Imported Cases",
            "Double-click a case to load it. Right-click → Load, Export or "
            "Remove; the Delete key removes it."),
        Tip("Policies",
            "Right-click a policy → Remove from list."),
        Tip("Compare against a saved case",
            "Drag a Saved Cases row onto a Compare tab scenario picker (A, B "
            "or C)."),
    )),
    TipSection("Options Menu (header)", (
        Tip("Additional Premium Types",
            "Adds Billable to MD, Max Level and Monthly Deduction to the "
            "Premium Type dropdown."),
        Tip("Testing Mode",
            "Shows the Export Summary button and export-folder picker on the "
            "Values Overview."),
        Tip("ABR Quote",
            "Solves the level annual premium that carries the policy to "
            "maturity with a $1,000 surrender value at the Illustrated Rate."),
        Tip("Edit Record",
            "Adds a Valuation Date picker (roll back to an earlier valuation) "
            "and makes the Policy tab editable: click a coverage or benefit to "
            "edit its Amount, double-click fund values to edit them."),
    )),
)


def tips_html(sections: tuple[TipSection, ...] = RERUN_TIPS) -> str:
    """Render *sections* as the dialog's rich-text body."""
    parts = [
        f"<div style='font-size:11px; color:{PURPLE_DARK};'>",
    ]
    for section in sections:
        parts.append(
            f"<p style='margin:10px 0 3px 0; font-size:13px; font-weight:bold;"
            f" color:{PURPLE_PRIMARY};'>{escape(section.title)}</p>"
            "<ul style='margin-top:0; margin-left:-18px;'>"
        )
        for tip in section.tips:
            parts.append(
                f"<li style='margin-bottom:4px;'><b>{escape(tip.where)}</b>"
                f" — {escape(tip.what)}</li>"
            )
        parts.append("</ul>")
    parts.append("</div>")
    return "".join(parts)


class RerunTipsDialog(FramelessDialog):
    """Non-modal Tips cheat-sheet so it can stay open while you work."""

    def __init__(self, parent=None):
        super().__init__(
            "RERUN Tips", parent,
            header_colors=ILLUSTRATION_HEADER_COLORS,
            border_color=ILLUSTRATION_BORDER_COLOR,
            body_color=PURPLE_BG,
        )
        self.setModal(False)
        self.resize(640, 640)

        self.browser = QTextBrowser(self)
        self.browser.setOpenLinks(False)
        self.browser.setStyleSheet(
            f"QTextBrowser {{ background: {WHITE}; border: 1px solid {PURPLE_LIGHT};"
            " border-radius: 4px; padding: 4px 8px; }")
        self.browser.setHtml(tips_html())
        self.body_layout.addWidget(self.browser, 1)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            f"QPushButton {{ background: {PURPLE_PRIMARY}; color: {WHITE};"
            f" border: 1px solid {PURPLE_DARK}; border-radius: 4px;"
            " padding: 4px 16px; font-size: 11px; font-weight: bold; }"
            f"QPushButton:hover {{ background: {PURPLE_LIGHT}; }}")
        close_btn.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_btn)
        self.body_layout.addLayout(row)
