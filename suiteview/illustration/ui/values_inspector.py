"""Month Inspector — the per-month calculation waterfall.

Select any month anywhere in the Values section (Overview ledger or any detail
grid) and this panel explains it: beginning AV through premium, loads, each
deduction charge, interest, to ending AV — plus the guideline/TAMRA/target
state and protection flags for that month. The vertical statement view is the
debugging companion to the horizontal grids.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .styles import PURPLE_BG

SECTION_FG = QColor("#4B2383")
SUBTOTAL_BG = QColor("#F3ECFC")
ALERT_FG = QColor("#B71C1C")


def _money(value, decimals: int = 2) -> str:
    if value is None:
        return ""
    return f"{value:,.{decimals}f}"


class MonthInspector(QWidget):
    """Field/value statement for one projected month."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.title = QLabel("Month Inspector")
        self.title.setStyleSheet(
            "background-color: #2A1458; color: #FFD54F; border: 1px solid #5E35A5;"
            " border-radius: 4px; font-size: 11px; font-weight: bold; padding: 4px 8px;"
        )
        layout.addWidget(self.title)

        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(10)
        self.tree.setStyleSheet(
            "QTreeWidget { background: white; border: 1px solid #B79CDE; font-size: 11px; }"
            "QTreeWidget::item { height: 16px; padding: 0px; }"
            "QTreeWidget::item:selected { background: #E8DDF8; color: #2A1458; }"
        )
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tree, 1)

        self._bold = QFont()
        self._bold.setBold(True)
        self.clear()

    def clear(self):
        self.tree.clear()
        self.title.setText("Month Inspector — select a row")

    # ── building blocks ───────────────────────────────────────

    def _section(self, label: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([label, ""])
        item.setFont(0, self._bold)
        item.setForeground(0, SECTION_FG)
        self.tree.addTopLevelItem(item)
        item.setExpanded(True)
        return item

    @staticmethod
    def _row(parent: QTreeWidgetItem, label: str, value: str,
             bold: bool = False, alert: bool = False) -> QTreeWidgetItem:
        item = QTreeWidgetItem([label, value])
        item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if bold:
            font = QFont()
            font.setBold(True)
            item.setFont(0, font)
            item.setFont(1, font)
            item.setBackground(0, SUBTOTAL_BG)
            item.setBackground(1, SUBTOTAL_BG)
        if alert:
            item.setForeground(0, ALERT_FG)
            item.setForeground(1, ALERT_FG)
        parent.addChild(item)
        return item

    # ── content ───────────────────────────────────────────────

    def show_month(self, state, prior_state=None):
        """Render the calculation waterfall for ``state``."""
        self.tree.clear()
        when = f"{state.date:%m/%d/%Y}" if state.date else "—"
        self.title.setText(
            f"{when}   ·   Yr {state.policy_year} Mo {state.policy_month}"
            f"   ·   Age {state.attained_age}")

        boy_av = prior_state.av_end_of_month if prior_state is not None else None

        premium = self._section("Premium")
        if boy_av is not None:
            self._row(premium, "BOY Account Value", _money(boy_av))
        if state.guideline_forceout:
            self._row(premium, "Guideline Force Out", f"−{_money(state.guideline_forceout)}", alert=True)
        self._row(premium, "Gross Premium", _money(state.gross_premium))
        if state.premium_capped:
            self._row(premium, "Requested (capped)", _money(state.requested_premium), alert=True)
        if state.prem_under_target or state.prem_over_target:
            self._row(premium, "Under / Over Target",
                      f"{_money(state.prem_under_target)} / {_money(state.prem_over_target)}")
        for label, value in (("Target Load", state.target_load),
                             ("Excess Load", state.excess_load),
                             ("Flat Load", state.flat_load)):
            if value:
                self._row(premium, label, f"−{_money(value)}")
        self._row(premium, "Net Premium", _money(state.net_premium))
        self._row(premium, "AV after Premium (mAV)", _money(state.av_after_premium), bold=True)

        deduction = self._section("Monthly Deduction")
        for key in sorted(state.coi_charges_by_coverage):
            self._row(deduction, f"COI {key.replace('cov', 'Cov ')}",
                      f"−{_money(state.coi_charges_by_coverage[key])}")
        if state.coi_charge_corr:
            self._row(deduction, "COI Corridor", f"−{_money(state.coi_charge_corr)}")
        self._row(deduction, "EPU", f"−{_money(state.epu_charge)}")
        self._row(deduction, "Monthly Fee", f"−{_money(state.mfee_charge)}")
        if state.av_charge:
            self._row(deduction, "AV Charge", f"−{_money(state.av_charge)}")
        for key, value in (state.rider_charge_detail or {}).items():
            self._row(deduction, f"Rider {key}", f"−{_money(value)}")
        for key, value in (state.benefit_charge_detail or {}).items():
            self._row(deduction, f"Benefit {key}", f"−{_money(value)}")
        self._row(deduction, "Total Deduction", f"−{_money(state.total_deduction)}")
        self._row(deduction, "AV after Deduction", _money(state.av_after_deduction), bold=True)

        interest = self._section("Interest")
        self._row(interest, "Days / Eff Annual Rate",
                  f"{state.days_in_month} / {state.effective_annual_rate:.4%}")
        self._row(interest, "Interest Credited", f"+{_money(state.interest_credited)}")
        if state.md_premium:
            self._row(interest, "MD Premium", f"+{_money(state.md_premium)}",
                      alert=state.md_premium_capped)
        if state.gp_exception_prem:
            self._row(interest, "GP Exception Prem", f"+{_money(state.gp_exception_prem)}", alert=True)
        self._row(interest, "EOM Account Value", _money(state.av_end_of_month), bold=True)

        values = self._section("Values")
        self._row(values, "Surrender Charge", f"−{_money(state.surrender_charge)}")
        if state.policy_debt:
            self._row(values, "Policy Debt", f"−{_money(state.policy_debt)}")
        self._row(values, "Surrender Value", _money(state.ending_sv), bold=True)
        self._row(values, "Ending Death Benefit", _money(state.ending_db or state.gross_db, 0), bold=True)

        guideline = self._section("Guideline (7702)")
        self._row(guideline, "GLP / GSP", f"{_money(state.glp)} / {_money(state.gsp)}")
        self._row(guideline, "Accum GLP", _money(state.accumulated_glp))
        self._row(guideline, "Guideline Limit", _money(state.guideline_limit))
        prem_wd = state.premiums_to_date - state.withdrawals_to_date
        self._row(guideline, "Prem − WD", _money(prem_wd))
        room = state.guideline_limit - prem_wd
        self._row(guideline, "GP Room", _money(room), alert=room < 0)

        tamra = self._section("TAMRA (7702A)")
        self._row(tamra, "7-Pay Level", _money(state.tamra_7pay_level))
        year_text = str(state.tamra_year) if state.tamra_year < 900 else "—"
        self._row(tamra, "TAMRA Year", year_text)
        self._row(tamra, "Amount in 7-Pay", _money(state.amount_in_7pay))

        targets = self._section("Targets")
        self._row(targets, "Monthly MTP", _money(state.monthly_mtp))
        self._row(targets, "Accum MTP", _money(state.accumulated_mtp))
        self._row(targets, "CTP", _money(state.ctp))
        self._row(targets, "Accum MTP less Prem", _money(state.accum_mtp_less_prem))

        status = self._section("Status")
        flags = []
        if state.snet_active:
            flags.append("SNET")
        if state.shadow_protection:
            flags.append("Shadow")
        if state.exception_prem_mode:
            flags.append("ExcPrem")
        if state.positive_sv:
            flags.append("PositiveSV")
        self._row(status, "Protection", " ".join(flags) or "—")
        self._row(status, "Lapsed", "YES" if state.lapsed else "no", alert=state.lapsed)
