"""
ABR Quote — Reusable premium breakdown dialog.

Displays a per-coverage premium calculation breakdown in a modal dialog.
Used by both the Policy Info panel (full-face premium) and the Assessment
panel (partial / min-face premium).

The breakdown dict must have the following shape::

    {
        "policy_number": str,
        "policy_year": int,
        "face_amount": float | None,       # optional — shown in title if present
        "coverages": [
            {
                "plancode": str,
                "issue_age": int,
                "sex": str,
                "rate_class": str,
                "rate": float,
                "table_rating": int,
                "rating_factor": float,     # 1.0 + table_rating * 0.25
                "flat_extra": float,
                "units": float,             # face / 1000
                "benefits": [
                    {
                        "label": str,       # e.g. "PW (Ben 30)"
                        "rate": float | None,
                        "factor": float,
                    },
                    ...
                ],
                "premium": float,
            },
            ...
        ],
        "policy_fee": float,
        "modal_label": str,           # e.g. "PAC Monthly"
        "modal_factor": float,
        "calc_modal": float,
    }
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QWidget,
)

from .abr_styles import (
    CRIMSON_DARK, CRIMSON_SUBTLE,
    GRAY_DARK,
    BUTTON_PRIMARY_STYLE,
)


def show_premium_breakdown_dialog(
    breakdown: dict,
    parent: QWidget | None = None,
    title: str | None = None,
) -> None:
    """Show a modal dialog with per-coverage premium breakdown.

    Args:
        breakdown: dict in the standard ``coverages`` shape (see module docstring).
        parent: parent widget for the dialog.
        title: optional window title override.
    """
    bd = breakdown
    if not bd:
        return

    dlg = QDialog(parent)
    dlg.setWindowTitle(title or "Premium Calculation Breakdown")
    dlg.setMinimumWidth(380)
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(8)

    # ── Title label ──────────────────────────────────────────────────────
    face_amt = bd.get("face_amount")
    if face_amt is not None:
        title_text = (
            f"Premium Breakdown - Min Face ${face_amt:,.0f}"
            f"  (Policy Year {bd['policy_year']})"
        )
    else:
        title_text = f"Premium Breakdown - Policy Year {bd['policy_year']}"

    title_lbl = QLabel(title_text)
    title_lbl.setStyleSheet(
        f"font-size: 14px; font-weight: bold; color: {CRIMSON_DARK};"
        f" padding-bottom: 4px;"
    )
    layout.addWidget(title_lbl)

    # ── Grid helpers ─────────────────────────────────────────────────────
    grid = QGridLayout()
    grid.setHorizontalSpacing(16)
    grid.setVerticalSpacing(3)
    row = 0

    LBL_STYLE = f"font-size: 11px; color: {GRAY_DARK};"
    VAL_STYLE = f"font-size: 11px; color: {GRAY_DARK}; font-weight: bold;"
    HDR_STYLE = f"font-size: 11px; color: {CRIMSON_DARK}; font-weight: bold;"
    INDENT_STYLE = f"font-size: 11px; color: {GRAY_DARK}; padding-left: 16px;"
    PREM_STYLE = f"font-size: 12px; color: {CRIMSON_DARK}; font-weight: bold;"

    def add_header(text):
        nonlocal row
        lbl = QLabel(text)
        lbl.setStyleSheet(HDR_STYLE + " padding-top: 8px;")
        grid.addWidget(lbl, row, 0, 1, 2)
        row += 1

    def add_line(label_text, value_text, indent=False):
        nonlocal row
        lbl = QLabel(label_text)
        lbl.setStyleSheet(INDENT_STYLE if indent else LBL_STYLE)
        grid.addWidget(lbl, row, 0, Qt.AlignmentFlag.AlignLeft)
        val = QLabel(str(value_text))
        val.setStyleSheet(VAL_STYLE)
        val.setAlignment(Qt.AlignmentFlag.AlignRight)
        grid.addWidget(val, row, 1)
        row += 1

    def add_premium_line(label_text, value_text, indent=False):
        nonlocal row
        lbl = QLabel(label_text)
        lbl.setStyleSheet(INDENT_STYLE if indent else LBL_STYLE)
        grid.addWidget(lbl, row, 0, Qt.AlignmentFlag.AlignLeft)
        val = QLabel(str(value_text))
        val.setStyleSheet(PREM_STYLE)
        val.setAlignment(Qt.AlignmentFlag.AlignRight)
        grid.addWidget(val, row, 1)
        row += 1

    def add_spacer():
        nonlocal row
        spacer = QLabel("")
        spacer.setFixedHeight(6)
        grid.addWidget(spacer, row, 0)
        row += 1

    def add_divider():
        nonlocal row
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"color: {CRIMSON_SUBTLE};")
        grid.addWidget(div, row, 0, 1, 2)
        row += 1

    # ── Policy number ────────────────────────────────────────────────────
    add_line("Policy Number", bd.get("policy_number", ""))

    # ── Per-coverage breakdown ───────────────────────────────────────────
    for cov_idx, cov in enumerate(bd.get("coverages", [])):
        add_spacer()
        add_header(f"Coverage {cov_idx + 1}")
        add_line("Plan", cov["plancode"], indent=True)
        add_line(
            "Issue age/Sex/Class",
            f"{cov['issue_age']} / {cov['sex']} / {cov['rate_class']}",
            indent=True,
        )
        cov_rate = cov.get("rate", 0)
        add_line(
            "Rate",
            f"{cov_rate:.4f}" if cov_rate else "—",
            indent=True,
        )
        add_line("Table Rating", str(cov["table_rating"]), indent=True)
        add_line(
            "Rating Factor",
            f"{cov['rating_factor']:.3f}",
            indent=True,
        )
        flat = cov.get("flat_extra", 0)
        add_line(
            "Flat Extra",
            f"{flat:.2f}" if flat > 0 else "0",
            indent=True,
        )
        add_line("Units", f"{cov['units']:.3f}", indent=True)

        # Benefits on this coverage (PW, etc.)
        for ben in cov.get("benefits", []):
            add_spacer()
            lbl = ben.get("label", "BEN")
            ben_rate = ben.get("rate")
            add_line(
                f"{lbl} Rate",
                f"{ben_rate:.4f}" if ben_rate is not None else "—",
                indent=True,
            )
            ben_factor = ben.get("factor", 1.0)
            add_line(
                f"{lbl} Factor",
                f"{ben_factor:.2f}" if ben_factor != 1.0 else "1",
                indent=True,
            )

        add_spacer()
        add_premium_line(
            "Premium", f"{cov['premium']:,.4f}", indent=True
        )

    # ── Policy Fee / Premium Mode / Modal / Calculated ───────────────────
    add_spacer()
    add_divider()
    add_line("Policy Fee", f"{bd['policy_fee']:,.3f}")
    add_line("Premium Mode", bd.get("modal_label", ""))
    add_line("Modal Factor", f"{bd['modal_factor']:.4f}")
    add_premium_line("Calculated Modal Premium", f"{bd['calc_modal']:,.2f}")

    layout.addLayout(grid)
    layout.addStretch()

    # Close button
    close_btn = QPushButton("Close")
    close_btn.setStyleSheet(BUTTON_PRIMARY_STYLE)
    close_btn.clicked.connect(dlg.accept)
    btn_row = QHBoxLayout()
    btn_row.addStretch()
    btn_row.addWidget(close_btn)
    layout.addLayout(btn_row)

    dlg.exec()
