"""
Account Values tab.

Advanced products (UL/IUL/VUL/ISWL) show Policy Info, Fund Values,
Monthliversary and Fund History sections. Traditional products show a simple
cash-value page with only the rows that apply to the policy.
"""

import logging
from decimal import Decimal

from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QLabel, QStackedLayout,
)

from ..formatting import format_currency, format_date
from ..widgets import StyledInfoTableGroup
from . import adv_prod_tooltips as tips
from ...services.policy_prefetch import (
    AccountValueCalculations,
    InterimAccountValueUnavailable,
    SurrenderValuesUnavailable,
    TraditionalCashValues,
)
from ...services.fixed_account_rate import FixedAccountRate, FixedRateUnavailable

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation

logger = logging.getLogger(__name__)

# Left column width: fits all ten Monthliversary columns with seven-digit
# values and a vertical scrollbar, so no horizontal scrollbar by default.
LEFT_COLUMN_WIDTH = 668
FUND_BOX_SPACING = 4
FUND_BOX_WIDTH = (LEFT_COLUMN_WIDTH - 2 * FUND_BOX_SPACING) // 3
MV_COLUMNS = ["Eff Date", "Y", "M", "Interest", "AccountValue", "COIChrg",
              "OtherChrg", "Expenses", "NAR", "MD"]
MV_MONTH_COLUMN = MV_COLUMNS.index("M")
MV_MD_COLUMN = MV_COLUMNS.index("MD")
TRAD_PANEL_WIDTH = 300
GCV_COLUMNS = ["Cov", "Basis", "Dur", "Mo", "BOY Rate", "EOY Rate", "Units", "Value"]
_NOTICE_STYLE = "background: #F0F0F0; color: #555555; font-style: italic; padding: 4px;"
# ETI/RPU: the account value bought the nonforfeiture benefit, so these
# AV-derived Policy Info rows and the fund/monthliversary groups are inactive.
_INACTIVE_AV_FIELDS = (
    "unimpaired_av", "impaired_av", "surrender_charge", "surrender_value",
    "guaranteed_cv", "ccv", "interim_av_quote",
)
_INACTIVE_COLOR = "#A0A0A0"
_INACTIVE_GROUP_STYLE = f"""
    QGroupBox {{ border-color: #C8C8C8; color: {_INACTIVE_COLOR}; }}
    QGroupBox::title {{ background-color: #B4B4B4; color: #F4F4F4; }}
"""
_INACTIVE_TABLE_STYLE = f"""
    QTableWidget {{ background-color: #F4F4F4; color: {_INACTIVE_COLOR}; }}
    QHeaderView::section {{ background-color: #E8E8E8; color: {_INACTIVE_COLOR}; }}
"""
_INACTIVE_FRAME_STYLE = "QFrame#outerFrame { background-color: #F4F4F4; border-color: #C8C8C8; }"


def _format_percent_rate(rate) -> str:
    """Percent-form DB2 rate (``4.000``) as a display percent (``4.00%``)."""
    return f"{float(rate) / 100:.2%}"


class AdvProdValuesTab(QWidget):
    """Account Values: advanced fund values, or a traditional cash-value summary."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        self._pages = QStackedLayout(self)
        self.advanced_page = QWidget()
        self._setup_advanced_page(self.advanced_page)
        self._pages.addWidget(self.advanced_page)
        self.traditional_page = QWidget()
        self._setup_traditional_page(self.traditional_page)
        self._pages.addWidget(self.traditional_page)

    def _setup_advanced_page(self, page):
        main_layout = QHBoxLayout(page)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # === LEFT COLUMN ===
        left_column = QVBoxLayout()
        left_column.setSpacing(4)

        self.policy_info = StyledInfoTableGroup("Policy Info", columns=2, show_table=False)
        self.policy_info.setFixedSize(LEFT_COLUMN_WIDTH, 208)
        self._setup_policy_info_fields()
        left_column.addWidget(self.policy_info)

        self.surrender_notice = QLabel()
        self.surrender_notice.setWordWrap(True)
        self.surrender_notice.setFixedWidth(LEFT_COLUMN_WIDTH)
        self.surrender_notice.setStyleSheet(_NOTICE_STYLE)
        self.surrender_notice.hide()
        left_column.addWidget(self.surrender_notice)

        fund_values_row = QHBoxLayout()
        fund_values_row.setSpacing(FUND_BOX_SPACING)

        self.unimpaired_values = StyledInfoTableGroup("Unimpaired Fund Values", show_info=False)
        self.unimpaired_values.setup_table(["FundID", "Amount"])
        self.unimpaired_values.setFixedSize(FUND_BOX_WIDTH, 156)
        fund_values_row.addWidget(self.unimpaired_values)

        self.impaired_values = StyledInfoTableGroup("Impaired Fund Values", show_info=False)
        self.impaired_values.setup_table(["FundID", "Amount"])
        self.impaired_values.setFixedSize(FUND_BOX_WIDTH, 156)
        fund_values_row.addWidget(self.impaired_values)

        self.allocation_percent = StyledInfoTableGroup("Allocation Percent", show_info=False)
        self.allocation_percent.setup_table(["FundID", "Percent"])
        self.allocation_percent.setFixedSize(FUND_BOX_WIDTH, 156)
        fund_values_row.addWidget(self.allocation_percent)

        left_column.addLayout(fund_values_row)

        self.mv_values = StyledInfoTableGroup("Monthliversary Values", show_info=False)
        self.mv_values.setup_table(MV_COLUMNS)
        self.mv_values.setFixedWidth(LEFT_COLUMN_WIDTH)
        self.mv_values.setMinimumHeight(120)
        self.mv_values.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        left_column.addWidget(self.mv_values, 1)

        main_layout.addLayout(left_column)

        # === RIGHT COLUMN ===
        self.fund_history = StyledInfoTableGroup("Fund Value History", show_info=False, filterable=True)
        self.fund_history.setup_table(["FundID", "Phase", "MVDate", "StartDate", "BucketValue"])
        self.fund_history.setFixedWidth(360)
        self.fund_history.setMinimumHeight(200)
        self.fund_history.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(self.fund_history)

        self._account_value_groups = (
            self.unimpaired_values, self.impaired_values, self.allocation_percent,
            self.mv_values, self.fund_history,
        )
        self._group_styles = {
            group: (group.styleSheet(), group.table._data_table.styleSheet(),
                    group.table._outer_frame.styleSheet())
            for group in self._account_value_groups
        }

    def _setup_traditional_page(self, page):
        layout = QHBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        left = QVBoxLayout()
        left.setSpacing(4)
        self.cash_values = StyledInfoTableGroup("Cash Values", columns=1, show_table=False)
        self.cash_values.setFixedWidth(TRAD_PANEL_WIDTH)
        # Height follows the rows that apply to the loaded policy.
        self.cash_values.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        for label, attr, italic in (
            ("Valuation Date", "valuation_date", False),
            ("Guaranteed Cash Value", "guaranteed_cv", True),
            ("Nonforfeiture", "nonforfeiture", False),
            ("Div on Deposit", "div_deposits", False),
            ("Deposit Interest", "deposit_interest", False),
            ("PUA Face Amount", "pua_face", False),
            ("Policy Debt", "policy_debt", False),
        ):
            self.cash_values.add_field(label, attr, 150, 110)
            if italic:
                self.cash_values._fields[attr].setStyleSheet(
                    self.cash_values._val_style + " font-style: italic;")
                self.cash_values._labels[attr].setStyleSheet(
                    self.cash_values._lbl_style + " font-style: italic;")
        left.addWidget(self.cash_values)

        self.cash_value_notice = QLabel()
        self.cash_value_notice.setWordWrap(True)
        self.cash_value_notice.setFixedWidth(TRAD_PANEL_WIDTH)
        self.cash_value_notice.setStyleSheet(_NOTICE_STYLE)
        self.cash_value_notice.hide()
        left.addWidget(self.cash_value_notice)
        left.addStretch(1)
        layout.addLayout(left)

        right = QVBoxLayout()
        self.coverage_cash_values = StyledInfoTableGroup(
            "Guaranteed Cash Value by Coverage", show_info=False)
        self.coverage_cash_values.setup_table(GCV_COLUMNS)
        self.coverage_cash_values.table.align_headers_left(["Basis"])
        self.coverage_cash_values.setFixedWidth(480)
        right.addWidget(self.coverage_cash_values)
        right.addStretch(1)
        layout.addLayout(right)
        layout.addStretch(1)

    def _setup_policy_info_fields(self):
        section = "AdvProdValues"

        def place(row, col, label, attr, lwidth=85, vwidth=65, italic=False):
            self.policy_info._current_row = row
            self.policy_info._current_col = col
            self.policy_info.add_field(label, attr, lwidth, vwidth, section, attr)
            if italic:
                self.policy_info._fields[attr].setStyleSheet(
                    self.policy_info._val_style + " font-style: italic;")
                self.policy_info._labels[attr].setStyleSheet(
                    self.policy_info._lbl_style + " font-style: italic;")

        # Left column (AV / calculated / rate fields)
        place(0, 0, "Total AV", "total_av", lwidth=100)
        place(1, 0, "Unimpaired AV", "unimpaired_av", lwidth=100)
        place(2, 0, "Impaired AV", "impaired_av", lwidth=100)
        place(3, 0, "Surrender Charge", "surrender_charge", lwidth=100, italic=True)
        place(4, 0, "Surrender Value", "surrender_value", lwidth=100, italic=True)
        place(5, 0, "Guaranteed CV", "guaranteed_cv", lwidth=100, italic=True)
        place(6, 0, "CCV", "ccv", lwidth=100)
        place(7, 0, "Guar Int Rate", "guar_int_rate", lwidth=100)
        place(8, 0, "DB Discount Rate", "db_discount_rate", lwidth=100)
        place(9, 0, "Grace Rule Code", "grace_rule_code", lwidth=100)

        # Right column (short-pay / other) — wider labels so long names
        # like "SP Prem Cease Age" are not clipped
        place(0, 1, "Short Pay Prem", "short_pay_prem", lwidth=115)
        place(1, 1, "Short Pay Mode", "short_pay_mode", lwidth=115)
        place(2, 1, "Short Pay Dur", "short_pay_dur", lwidth=115)
        place(3, 1, "SP Billing Cease", "sp_billing_cease_date", lwidth=115)
        place(4, 1, "SP Prem Cease Age", "sp_prem_cease_age", lwidth=115)
        place(5, 1, "DB Dial-To Age", "db_dial_to_age", lwidth=115)
        place(6, 1, "Corridor Rate", "corridor_rate", lwidth=115)
        # Sized for the dated label so loading a quote never shifts the layout.
        place(7, 1, "Interim AV Quote (00/00/0000)", "interim_av_quote",
              lwidth=115, italic=True)
        place(8, 1, "Fixed Crediting Rate", "fixed_crediting_rate", lwidth=115, italic=True)
        place(9, 1, "Fixed Rate ex Bonus", "fixed_rate_ex_bonus", lwidth=115, italic=True)
        self._set_interim_label(None)
        self._field_styles = {
            attr: (self.policy_info._labels[attr].styleSheet(), field.styleSheet())
            for attr, field in self.policy_info._fields.items()
        }
        total_av_label = self.policy_info._labels["total_av"]
        bold = QFont(total_av_label.font())
        bold.setPixelSize(11)
        bold.setBold(True)
        # Room for the ETI/RPU relabel so it never shifts the layout.
        total_av_label.setFixedWidth(max(
            total_av_label.minimumWidth(),
            QFontMetrics(bold).horizontalAdvance("NSP Cash Value:") + 6))

    def _set_interim_label(self, quote_date):
        """Label the Interim AV Quote with the date it is quoted as of."""
        suffix = f" ({quote_date:%m/%d/%Y})" if quote_date is not None else ""
        self.policy_info._labels["interim_av_quote"].setText(f"Interim AV Quote{suffix}:")

    # ── PolicyInformation path ───────────────────────────────────────────

    def load_data_from_policy(
        self, policy: 'PolicyInformation',
        payload: AccountValueCalculations | TraditionalCashValues,
    ):
        if isinstance(payload, TraditionalCashValues):
            self._pages.setCurrentWidget(self.traditional_page)
            self._load_traditional(payload)
            return
        self._pages.setCurrentWidget(self.advanced_page)
        calculations = payload
        # Clear old data first so stale values never remain when switching policies
        self.policy_info.clear_info()
        self.mv_values.load_table_data([])
        self.fund_history.load_table_data([])
        self.unimpaired_values.load_table_data([])
        self.impaired_values.load_table_data([])
        self.allocation_percent.load_table_data([])
        self.surrender_notice.clear()
        self.surrender_notice.hide()
        for field in self.policy_info._fields.values():
            field.setToolTip("")
        self._set_interim_label(None)
        self._set_account_values_active(True)

        try:
            self._load_policy_info_from_policy(policy)
            surrender_values = calculations.surrender
            if isinstance(surrender_values, SurrenderValuesUnavailable):
                for field in ("surrender_charge", "surrender_value"):
                    self.policy_info.set_value(field, "N/A")
                    self.policy_info._fields[field].setToolTip(surrender_values.reason)
                self.surrender_notice.setText(surrender_values.reason)
                self.surrender_notice.show()
            else:
                self._set_calculated(
                    "surrender_charge", format_currency(surrender_values.surrender_charge),
                    tips.surrender_charge_tip(surrender_values))
                self._set_calculated(
                    "surrender_value", format_currency(surrender_values.surrender_value),
                    tips.surrender_value_tip(surrender_values))
            self._load_interim_quote(calculations.interim)
            self._load_fixed_rate(calculations.fixed_rate)
            self._load_monthliversary_from_policy(policy)
            self._load_fund_history_from_policy(policy)
            self._load_fund_summary_from_policy(policy)
            self._load_premium_allocation_from_policy(policy)
            gcv = calculations.guaranteed or {
                "value": None, "details": [], "reason": "Not calculated"}
            if calculations.nonforfeiture_status:
                self._load_nonforfeiture(policy, calculations.nonforfeiture_status, gcv)
            else:
                self._load_guaranteed_cash_value(gcv)
        except Exception:
            logger.exception("AdvProdValuesTab failed to load policy data")
            raise

    # ── Traditional cash values ──────────────────────────────────────────

    def _load_traditional(self, values: TraditionalCashValues):
        """Show only the cash-value rows that apply to this traditional policy."""
        panel = self.cash_values
        panel.clear_info()
        for field in panel._fields.values():
            field.setToolTip("")
        gcv = values.guaranteed
        details = gcv.get("details", [])
        notices = []
        shown = []

        def show(attr, text, tip=""):
            panel.set_value(attr, text)
            panel._fields[attr].setToolTip(tip)
            shown.append(attr)

        if values.has_stored_rates:
            show("valuation_date", format_date(gcv.get("as_of")) or "N/A",
                 "Last processed monthliversary; the guaranteed cash value is "
                 "interpolated to this date.")
            amount = gcv.get("value")
            nsp = any(d["basis"] == "NSP" for d in details)
            show("guaranteed_cv",
                 "N/A" if amount is None else format_currency(amount) + (" (NSP)" if nsp else ""),
                 tips.guaranteed_cash_value_tip(gcv))
            if amount is None:
                notices.append(f"Guaranteed cash value not calculated: {gcv.get('reason')}.")
            nonforfeiture = sorted({d["nonforfeiture"] for d in details if d["nonforfeiture"]})
            if nonforfeiture:
                show("nonforfeiture", " / ".join(nonforfeiture),
                     "Premium-pay status puts the policy on extended term (ETI) or "
                     "reduced paid-up (RPU); its value uses the stored NSP rates.")
        if values.dividend_deposits:
            show("div_deposits", format_currency(values.dividend_deposits),
                 "Current dividends on deposit (LH_PTP_ON_DEP.PTP_DEP_AMT).")
        if values.deposit_interest:
            show("deposit_interest", format_currency(values.deposit_interest),
                 "Interest on current deposits not yet added to them "
                 "(LH_PTP_ON_DEP.DEP_ITS_AMT).")
        if values.pua_face:
            show("pua_face", format_currency(values.pua_face),
                 "Face amount of current paid-up additions (LH_PAID_UP_ADD.PUA_AMT).")
            notices.append("Paid-up additions cash value is not calculated; "
                           "the PUA face amount is shown.")
        if values.policy_debt:
            show("policy_debt", format_currency(values.policy_debt),
                 "Loan principal plus accrued interest (see the Loans tab).")

        for attr in panel._fields:
            panel.set_field_visible(attr, attr in shown)
        self.cash_value_notice.setText("\n".join(notices))
        self.cash_value_notice.setVisible(bool(notices))

        rows = [
            [
                str(d.get("cov_pha_nbr") or d["cov_index"]),
                d["basis"] + (f" ({d['nonforfeiture']})" if d["nonforfeiture"] else ""),
                str(d["duration"]),
                str(d["months"]),
                f"{d['boy_rate']:,.2f}",
                f"{d['eoy_rate']:,.2f}",
                f"{d['units']:,}",
                format_currency(d["value"]),
            ]
            for d in details
        ]
        self.coverage_cash_values.load_table_data(rows)
        self.coverage_cash_values.setVisible(bool(rows))
        if rows:
            self.coverage_cash_values.setFixedHeight(
                self.coverage_cash_values.table.fitted_height(min_rows=1, max_rows=10) + 24)

    # ── Nonforfeiture (ETI/RPU) advanced policies ────────────────────────

    def _set_account_values_active(self, active: bool, reason: str = ""):
        """Grey out (or restore) the account-value rows and fund/monthliversary groups."""
        info = self.policy_info
        info._labels["total_av"].setText("Total AV:")
        for attr in ("total_av",) + _INACTIVE_AV_FIELDS:
            label_style, value_style = self._field_styles[attr]
            grey = "" if active or attr == "total_av" else f" color: {_INACTIVE_COLOR};"
            info._labels[attr].setStyleSheet(label_style + grey)
            info._fields[attr].setStyleSheet(value_style + grey)
        for group in self._account_value_groups:
            group_style, table_style, frame_style = self._group_styles[group]
            if active:
                group.setStyleSheet(group_style)
                group.table._data_table.setStyleSheet(table_style)
                group.table._outer_frame.setStyleSheet(frame_style)
            else:
                group.setStyleSheet(group_style + _INACTIVE_GROUP_STYLE)
                group.table._data_table.setStyleSheet(table_style + _INACTIVE_TABLE_STYLE)
                group.table._outer_frame.setStyleSheet(frame_style + _INACTIVE_FRAME_STYLE)
            group.setToolTip(reason)

    def _load_guaranteed_cash_value(self, gcv):
        """Guaranteed CV interpolated from the stored 02-segment rates, else N/A."""
        amount = gcv.get("value")
        text = "N/A"
        if amount is not None:
            nsp = any(d["basis"] == "NSP" for d in gcv.get("details", []))
            text = format_currency(amount) + (" (NSP)" if nsp else "")
        self._set_calculated("guaranteed_cv", text, tips.guaranteed_cash_value_tip(gcv))

    def _load_nonforfeiture(self, policy, status, gcv):
        """Show the NSP cash value in place of Total AV; mark AV values inactive."""
        info = self.policy_info
        valuation = format_date(policy.values.valuation_date) or "unknown date"
        stored_av = info.get_value("total_av") or "N/A"
        amount = gcv.get("value")
        inactive = (
            f"Inactive: the policy is on {status}. Its account value (last valued "
            f"{valuation}) was applied to purchase the nonforfeiture benefit; these "
            "values are historical."
        )
        self._set_account_values_active(False, inactive)

        info._labels["total_av"].setText("NSP Cash Value:")
        self._set_calculated(
            "total_av", "N/A" if amount is None else format_currency(amount),
            tips.guaranteed_cash_value_tip(gcv)
            + f"\nStored Total AV {stored_av} (valued {valuation}) was applied to "
              f"purchase {status}; it is not the current value.")
        self._set_calculated(
            "guaranteed_cv", "N/A",
            f"On {status} the guaranteed value is the NSP Cash Value above.")

        notice = (
            f"Policy is on {status} (premium pay status "
            f"{policy.status.premium_pay_status_code}): its account value was applied "
            "to purchase the nonforfeiture benefit. NSP Cash Value is interpolated "
            f"from the 02-segment NSP rates as of {format_date(gcv.get('as_of')) or 'N/A'}. "
            f"Account and fund values (last valued {valuation}) are historical and "
            "shown greyed out."
        )
        if amount is None:
            notice += f" NSP Cash Value not calculated: {gcv.get('reason')}."
        self.surrender_notice.setText(notice)
        self.surrender_notice.show()

    def _set_calculated(self, attr, text, tip):
        """Show a calculated value with a hover tip explaining its working."""
        self.policy_info.set_value(attr, text)
        self.policy_info._fields[attr].setToolTip(tip)

    def _load_interim_quote(self, interim):
        """Show the Interim AV Quote with its roll-forward in the tooltip."""
        field = self.policy_info._fields["interim_av_quote"]
        if isinstance(interim, InterimAccountValueUnavailable):
            self.policy_info.set_value("interim_av_quote", "N/A")
            field.setToolTip(interim.reason)
            return
        self._set_interim_label(interim.quote_date)
        self._set_calculated(
            "interim_av_quote", format_currency(interim.account_value),
            tips.interim_av_tip(interim))

    def _load_fixed_rate(self, fixed):
        """Fixed-fund crediting rate with and without the duration bonus; N/A otherwise."""
        if isinstance(fixed, FixedAccountRate):
            tip = tips.fixed_rate_tip(fixed)
            self._set_calculated("fixed_crediting_rate", f"{fixed.credited_rate:.2%}", tip)
            self._set_calculated("fixed_rate_ex_bonus", f"{fixed.declared_rate:.2%}", tip)
            return
        reason = (fixed.reason if isinstance(fixed, FixedRateUnavailable)
                  else "Fixed-account rate was not calculated.")
        for attr in ("fixed_crediting_rate", "fixed_rate_ex_bonus"):
            self._set_calculated(attr, "N/A", reason)

    def _load_policy_info_from_policy(self, policy):
        mvav = policy.values.mv_av(0)
        if mvav:
            self.policy_info.set_value("total_av", format_currency(mvav))

        current = self._is_current_row
        unimpaired_rows = [
            row for row in policy.fetch_table("LH_POL_FND_VAL_TOT") if current(row)]
        unimpaired_total = self._sum_numeric_rows(unimpaired_rows, "CSV_AMT")
        self._set_calculated(
            "unimpaired_av", format_currency(unimpaired_total),
            tips.sum_tip(
                "Unimpaired AV = sum of the current fund buckets",
                "(LH_POL_FND_VAL_TOT.CSV_AMT where MVRY_DT = 12/31/9999)",
                self._bucket_parts(unimpaired_rows, "CSV_AMT"), unimpaired_total,
                empty="No current fund buckets"))

        impaired_rows = [
            row for row in policy.fetch_table("LH_FND_VAL_LOAN")
            if current(row) and str(row.get("FND_ID_CD", "")).strip() != "LZ"
        ]
        impaired_total = self._sum_numeric_rows(impaired_rows, "LN_PRI_AMT")
        self._set_calculated(
            "impaired_av", format_currency(impaired_total),
            tips.sum_tip(
                "Impaired AV = loan principal held as collateral in the funds",
                "(LH_FND_VAL_LOAN.LN_PRI_AMT, current rows, fund LZ excluded)",
                self._bucket_parts(impaired_rows, "LN_PRI_AMT"), impaired_total,
                empty="No current loan collateral rows"))

        if policy.targets.gav:
            self.policy_info.set_value("gav", format_currency(policy.targets.gav))

        ccv_rows = [
            row for row in policy.fetch_table("LH_COV_TARGET")
            if str(row.get("TAR_TYP_CD", "")).strip() == "XP"
        ]
        ccv_total = self._sum_numeric_rows(ccv_rows, "TAR_PRM_AMT")
        if ccv_total != 0:
            self._set_calculated(
                "ccv", format_currency(ccv_total),
                tips.sum_tip(
                    "CCV = sum of the coverages' XP (CCV) targets",
                    "(LH_COV_TARGET.TAR_PRM_AMT where TAR_TYP_CD = 'XP')",
                    (
                        (f"Cov {str(row.get('COV_PHA_NBR', '')).strip() or '?'}",
                         float(row.get("TAR_PRM_AMT") or 0))
                        for row in ccv_rows
                    ),
                    ccv_total))

        self._load_interest_rates(policy)

        if policy.product.grace_rule_code:
            self.policy_info.set_value("grace_rule_code", policy.product.grace_rule_code)

        if policy.product.corridor_percent is not None:
            try:
                self.policy_info.set_value("corridor_rate", f"{float(policy.product.corridor_percent) / 100:.2%}")
            except Exception:
                self.policy_info.set_value("corridor_rate", str(policy.product.corridor_percent))

        if policy.billing.short_pay_premium:
            self.policy_info.set_value("short_pay_prem", format_currency(policy.billing.short_pay_premium))
        if policy.billing.short_pay_duration:
            self.policy_info.set_value("short_pay_dur", str(policy.billing.short_pay_duration))
            if policy.billing.short_pay_mode:
                self.policy_info.set_value("short_pay_mode", policy.billing.short_pay_mode)
            if policy.billing.sp_billing_cease_date:
                self.policy_info.set_value("sp_billing_cease_date", str(policy.billing.sp_billing_cease_date))
            if policy.billing.short_pay_premium and policy.billing.sp_prem_cease_age:
                self._set_calculated(
                    "sp_prem_cease_age", str(policy.billing.sp_prem_cease_age),
                    tips.sp_prem_cease_age_tip(
                        policy.billing.short_pay_duration, policy.coverages.cov_issue_age(1),
                        policy.billing.sp_prem_cease_age))
        if policy.targets.db_dial_to_age:
            self.policy_info.set_value("db_dial_to_age", str(policy.targets.db_dial_to_age))

    def _load_interest_rates(self, policy):
        """Fixed-fund guaranteed crediting rate and the NAR death-benefit discount rate.

        They usually match, but the fund rate (LH_COV_FXD_FND_CTL) can differ
        from the policy guaranteed rate (LH_NON_TRD_POL) used to discount the DB.
        """
        rates = policy.product.fund_guaranteed_interest_rates
        nonzero = sorted({r.rate for r in rates if r.rate})
        shown = nonzero or sorted({r.rate for r in rates if r.rate is not None})
        if shown:
            self._set_calculated(
                "guar_int_rate", " / ".join(_format_percent_rate(rate) for rate in shown),
                tips.fund_guaranteed_rate_tip(rates))

        discount_rate = policy.product.guaranteed_interest_rate
        if discount_rate:
            self._set_calculated(
                "db_discount_rate", _format_percent_rate(discount_rate),
                tips.db_discount_rate_tip(discount_rate))

    @staticmethod
    def _is_current_row(row) -> bool:
        """Fund rows dated 12/31/9999 hold the current values."""
        return "9999" in str(row.get("MVRY_DT", ""))

    @staticmethod
    def _bucket_parts(rows, amount_field: str):
        """``(label, amount)`` per fund row, labelled by fund/phase/start when present."""
        parts = []
        for row in rows:
            label = str(row.get("FND_ID_CD", "")).strip() or "?"
            phase = str(row.get("FND_VAL_PHA_NBR", "") or "").strip()
            if phase:
                label += f" ph {phase}"
            start = format_date(row.get("ITS_PER_STR_DT"))
            if start:
                label += f" (start {start})"
            parts.append((label, float(row.get(amount_field) or 0)))
        return parts

    @staticmethod
    def _sum_numeric_rows(rows, amount_field: str) -> float:
        total = 0.0
        for row in rows:
            amount = row.get(amount_field, 0)
            if amount:
                try:
                    total += float(amount)
                except Exception:
                    pass
        return total

    def _load_monthliversary_from_policy(self, policy):
        mv_rows = policy.fetch_table("LH_POL_MVRY_VAL")

        coverages = getattr(policy, "coverages", policy)
        issue_date = coverages.cov_issue_date(1)
        issue_month = issue_date.month if issue_date else 1
        mv_rows = sorted(mv_rows, key=lambda x: str(x.get("MVRY_DT", "")), reverse=True)

        table_rows = []
        row_tips = []
        for data in mv_rows:
            eff_date = format_date(data.get("MVRY_DT"))
            pol_year = str(data.get("POL_DUR_NBR", "")).strip()

            mv_date = data.get("MVRY_DT")
            month_tip = ""
            if mv_date:
                from datetime import datetime
                if isinstance(mv_date, str):
                    try:
                        mv_date_obj = datetime.strptime(mv_date[:10], "%Y-%m-%d")
                        val_month = mv_date_obj.month
                    except Exception:
                        val_month = 1
                else:
                    val_month = mv_date.month
                mth = abs(issue_month - val_month)
                if issue_month > val_month:
                    mth = 12 - mth
                pol_month = str(mth + 1)
                month_tip = tips.policy_month_tip(issue_month, val_month, mth + 1)
            else:
                pol_month = str(data.get("POL_MTH_NBR", "")).strip()

            monthly_deduction = sum(
                (Decimal(str(data.get(field) or 0)) for field in
                 ("CINS_AMT", "OTH_PRM_AMT", "EXP_CRG_AMT")),
                Decimal("0"),
            )
            table_rows.append([
                eff_date, pol_year, pol_month,
                format_currency(data.get("TOT_CRE_ITS_AMT")),
                format_currency(data.get("CSV_AMT")),
                format_currency(data.get("CINS_AMT")),
                format_currency(data.get("OTH_PRM_AMT")),
                format_currency(data.get("EXP_CRG_AMT")),
                format_currency(data.get("NAR_AMT")),
                format_currency(monthly_deduction),
            ])
            row_tips.append((month_tip, tips.monthly_deduction_tip(
                data.get("CINS_AMT"), data.get("OTH_PRM_AMT"), data.get("EXP_CRG_AMT"),
                monthly_deduction)))

        self.mv_values.load_table_data(table_rows)
        for row, (month_tip, md_tip) in enumerate(row_tips):
            self.mv_values.table.item(row, MV_MONTH_COLUMN).setToolTip(month_tip)
            self.mv_values.table.item(row, MV_MD_COLUMN).setToolTip(md_tip)

    def _load_fund_history_from_policy(self, policy):
        fund_rows = policy.fetch_table("LH_POL_FND_VAL_TOT")

        table_rows = []
        for data in fund_rows:
            fund_id = str(data.get("FND_ID_CD", "")).strip()
            phase = str(data.get("FND_VAL_PHA_NBR", "")).strip()
            mv_date = format_date(data.get("MVRY_DT"))
            start_date = format_date(data.get("ITS_PER_STR_DT"))
            csv_amt = data.get("CSV_AMT")
            if csv_amt is None or csv_amt == "" or (isinstance(csv_amt, (int, float)) and csv_amt == 0):
                bucket_value = "0.00"
            else:
                bucket_value = format_currency(csv_amt)
            table_rows.append([fund_id, phase, mv_date, start_date, bucket_value,
                               data.get("MVRY_DT", ""), data.get("FND_ID_CD", ""), data.get("FND_VAL_PHA_NBR", 0)])

        table_rows.sort(key=lambda x: (x[5], x[6], x[7]), reverse=True)
        table_rows = [row[:5] for row in table_rows]

        self.fund_history.load_table_data(table_rows)

    def _load_fund_summary_from_policy(self, policy):
        fund_rows = [
            row for row in policy.fetch_table("LH_POL_FND_VAL_TOT")
            if self._is_current_row(row) and str(row.get("FND_ID_CD", "")).strip()
        ]
        self._load_fund_totals(
            self.unimpaired_values, fund_rows, "CSV_AMT",
            "sum of its current buckets (LH_POL_FND_VAL_TOT.CSV_AMT)")

        loan_rows = [
            row for row in policy.fetch_table("LH_FND_VAL_LOAN")
            if self._is_current_row(row)
            and str(row.get("FND_ID_CD", "")).strip() not in ("", "LZ")
            and float(row.get("LN_PRI_AMT", 0) or 0) != 0
        ]
        self._load_fund_totals(
            self.impaired_values, loan_rows, "LN_PRI_AMT",
            "sum of its current loan collateral (LH_FND_VAL_LOAN.LN_PRI_AMT)")

    def _load_fund_totals(self, group, rows, amount_field: str, description: str):
        """One row per fund with its total; the amount's tip lists the rows summed."""
        by_fund = {}
        for row in rows:
            by_fund.setdefault(str(row.get("FND_ID_CD", "")).strip(), []).append(row)
        funds = sorted(by_fund)
        totals = [self._sum_numeric_rows(by_fund[fund], amount_field) for fund in funds]
        group.load_table_data(
            [[fund, format_currency(total)] for fund, total in zip(funds, totals)])
        for index, (fund, total) in enumerate(zip(funds, totals)):
            group.table.item(index, 1).setToolTip(tips.sum_tip(
                f"{fund} = {description}", "",
                self._bucket_parts(by_fund[fund], amount_field), total))

    def _load_premium_allocation_from_policy(self, policy):
        allocation_rows = []
        for fund_id, percent in sorted(policy.values.get_premium_allocation_dict().items()):
            clean_fund_id = str(fund_id).strip()
            try:
                display_percent = f"{float(percent) / 100:.2%}"
            except Exception:
                display_percent = str(percent)
            allocation_rows.append([clean_fund_id, display_percent])

        self.allocation_percent.load_table_data(allocation_rows)
