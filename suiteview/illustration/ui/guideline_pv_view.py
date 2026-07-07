"""Guideline PV Detail — an inline Values-tab group.

Shows the Guideline Level Premium as a survival-weighted, month-by-month present
value: a row per policy month (q'x, p'x, tp'x, vᵗ, v^(t+1), death benefit, each
benefit/rider charge, EPU, MFEE, Charges, PVDB, PV Charges, PV Annuity) plus the
roll-up that divides the components into the GLP — written out with the actual
values so it visibly adds up. The followable alternative to the commutation
drill-down (no lx/dx/Nx/Dx/Cx/Mx).

Fed from a policy change's ``guideline_recalc["monthly_pv"]`` (built by
``illustration.core.guideline_pv``); this view only renders it. Greyed with an
italic note when the projection has no guideline re-solve.
"""
from __future__ import annotations

import logging

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from suiteview.ui.widgets.filter_table_view import FilterTableView

from .styles import GOLD_TEXT, PURPLE_BG, PURPLE_DARK, PURPLE_PRIMARY

logger = logging.getLogger(__name__)


class GuidelinePvDetailView(QWidget):
    """Inline group: the GLP as a month-by-month present value."""

    def __init__(self, parent=None, *, search_visible: bool = True):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        self._detail: dict | None = None
        self._grid_df: pd.DataFrame | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.header = QLabel("", self)
        self.header.setWordWrap(True)
        self.header.setStyleSheet(
            f"background-color: {PURPLE_DARK}; color: {GOLD_TEXT};"
            f" border: 1px solid {PURPLE_PRIMARY}; border-radius: 4px;"
            " font-size: 12px; font-weight: bold; padding: 5px 9px;")
        layout.addWidget(self.header)

        self.empty_note = QLabel("", self)
        self.empty_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_note.setStyleSheet(
            "color: #6A5A8A; background: transparent; font-size: 12px; font-style: italic;")
        layout.addWidget(self.empty_note)

        # ── Body: monthly grid + worked-out equation ──
        self.body = QWidget(self)
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(4)

        self.grid = FilterTableView(self.body)
        self.grid.set_search_visible(search_visible)
        self.grid.apply_ledger_style()
        self.grid.set_sort_enabled(False)
        body_layout.addWidget(self.grid, 1)

        # ── Worked-out equation (symbolic, then with the actual values) ──
        self.equation = QLabel("", self.body)
        self.equation.setWordWrap(True)
        self.equation.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.equation.setFont(QFont("Consolas", 10))
        self.equation.setStyleSheet(
            f"color: {PURPLE_DARK}; background: #F6F1FB;"
            f" border: 1px solid {PURPLE_PRIMARY}; border-radius: 4px; padding: 6px 9px;")
        body_layout.addWidget(self.equation)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.export_btn = QPushButton("Dump to Excel", self.body)
        self.export_btn.setStyleSheet(
            f"QPushButton {{ background: {PURPLE_PRIMARY}; color: white; border: none;"
            " border-radius: 4px; padding: 3px 14px; font-size: 11px; font-weight: bold; }"
            f" QPushButton:hover {{ background: {PURPLE_DARK}; }}")
        self.export_btn.clicked.connect(self._on_export)
        footer.addWidget(self.export_btn)
        body_layout.addLayout(footer)

        layout.addWidget(self.body, 1)
        self.clear()

    # ── Public API ──
    def clear(self):
        self.show_detail(None)

    def show_detail(self, detail: dict | None):
        rows = (detail or {}).get("glp_rows") or []
        if not rows:
            # Hide the body and leave the inner grids as-is (resetting them to an
            # empty frame triggers a stale-header repaint in FilterTableView —
            # the Recalc group hides rather than clears for the same reason).
            self._detail = None
            self._grid_df = None
            label = (detail or {}).get("premium_label") or "GLP"
            self.header.setText(f"Guideline PV Detail ({label})")
            self.empty_note.setText(
                "No guideline re-solve in this projection — nothing to break down.")
            self.empty_note.setVisible(True)
            self.body.setVisible(False)
            return

        self._detail = detail
        self.empty_note.setVisible(False)
        self.body.setVisible(True)
        rollup = detail.get("glp_rollup") or {}

        self.header.setText(self._header_text(detail, rollup))

        df = pd.DataFrame([{k: v for k, v in r.items() if k != "_endowment"} for r in rows])
        self._grid_df = df
        self.grid.set_dataframe(df, limit_rows=False)
        if self.grid.model is not None:
            self.grid.model._left_align_columns = {0, 1}
        self.grid.autofit_columns_to_data()

        self.equation.setText(self._equation_text(rollup, detail.get("premium_label") or "GLP"))

    # ── Rendering helpers ──
    def _header_text(self, detail: dict, rollup: dict) -> str:
        label = detail.get("premium_label") or "GLP"
        sa = detail.get("specified_amount")
        rate = detail.get("glp_rate")
        dbo = str(detail.get("db_option") or "A").upper()
        prem = rollup.get("premium")
        bits = []
        if prem is not None:
            bits.append(f"{label} = {prem:,.2f}")
        if sa is not None:
            bits.append(f"SA {sa:,.0f}")
        if detail.get("attained_age"):
            bits.append(f"attained age {detail['attained_age']}")
        if rate is not None:
            bits.append(f"basis {rate:.2%}")
        bits.append(f"DBO {dbo}")
        line = "   ·   ".join(bits)
        note = "Σ PVDB includes the maturity endowment (survive to maturity → receive SA)"
        if dbo == "B":
            note += "   ·   DBO B: increasing-DB approximation (exact for level DB)"
        return f"{line}\n{note}"

    @staticmethod
    def _equation_text(rollup: dict, label: str = "GLP") -> str:
        db = rollup.get("PV death benefit") or 0.0
        endow = rollup.get("PV maturity endowment") or 0.0
        chg = rollup.get("PV Charges") or 0.0
        load_d = rollup.get("load $ term") or 0.0
        gross = rollup.get("PV Annuity (gross)") or 0.0
        load_pct = rollup.get("load %") or 0.0
        num = rollup.get("numerator") or 0.0
        den = rollup.get("denominator") or 0.0
        glp = rollup.get("premium") or 0.0

        av0 = rollup.get("starting AV offset") or 0.0

        load_piece = f" + {load_d:,.2f}" if abs(load_d) >= 0.005 else ""
        load_sym = "  +  Load $" if load_piece else ""
        av_piece = f" − {av0:,.2f}" if abs(av0) >= 0.005 else ""
        av_sym = "  −  Starting AV" if av_piece else ""
        return (
            f"{label} = (Σ PV Death Benefit + Σ PV Endowment + Σ PV Charges"
            f"{load_sym}{av_sym})  ÷  ((1 − load%) × Σ PV Annuity)\n"
            f"    = ({db:,.2f} + {endow:,.2f} + {chg:,.2f}{load_piece}{av_piece})"
            f"  ÷  ((1 − {load_pct:.3%}) × {gross:,.6f})\n"
            f"    = {num:,.2f}  ÷  {den:,.6f}\n"
            f"    = {glp:,.2f}"
        )

    def _on_export(self):
        from PyQt6.QtWidgets import QMessageBox

        df = self._grid_df
        if df is None or df.empty:
            return
        try:
            from suiteview.core.excel_export import ExcelExportError, dump_to_new_workbook

            label = (self._detail or {}).get("premium_label") or "GLP"
            headers = list(df.columns)
            data = [tuple(rec) for rec in df.itertuples(index=False, name=None)]
            text_cols = [i for i, c in enumerate(headers) if c in ("Policy Month", "Age")]
            dump_to_new_workbook(
                headers, data, sheet_name=f"Guideline PV ({label})", text_col_indexes=text_cols)
        except ExcelExportError as e:
            QMessageBox.warning(self, "Export Error", f"Could not export to Excel:\n{e}")
        except Exception as e:  # pragma: no cover - UI guard
            logger.error("Guideline PV export failed: %s", e, exc_info=True)
            QMessageBox.warning(self, "Export Error", f"Could not export to Excel:\n{e}")
