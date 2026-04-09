"""
Advanced Product Values tab – Policy Info, Fund Values, Monthliversary,
and Fund History sections for UL/VUL products.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy

from ..formatting import format_currency, format_date
from ..widgets import StyledInfoTableGroup

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation


class AdvProdValuesTab(QWidget):
    """Tab for Advanced Product Values - matches VBA SuiteView layout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # === LEFT COLUMN ===
        left_column = QVBoxLayout()
        left_column.setSpacing(4)

        self.policy_info = StyledInfoTableGroup("Policy Info", columns=2, show_table=False)
        self.policy_info.setFixedSize(595, 160)
        self._setup_policy_info_fields()
        left_column.addWidget(self.policy_info)

        fund_values_row = QHBoxLayout()
        fund_values_row.setSpacing(4)

        self.unimpaired_values = StyledInfoTableGroup("Unimpaired Fund Values", show_info=False)
        self.unimpaired_values.setup_table(["FundID", "Amount"])
        self.unimpaired_values.setFixedSize(292, 156)
        fund_values_row.addWidget(self.unimpaired_values)

        self.impaired_values = StyledInfoTableGroup("Impaired Fund Values", show_info=False)
        self.impaired_values.setup_table(["FundID", "Amount"])
        self.impaired_values.setFixedSize(292, 156)
        fund_values_row.addWidget(self.impaired_values)

        left_column.addLayout(fund_values_row)

        self.mv_values = StyledInfoTableGroup("Monthliversary Values", show_info=False)
        self.mv_values.setup_table(["Eff Date", "Y", "M", "Interest", "AccountValue", "COIChrg", "OtherChrg", "Expenses", "NAR"])
        self.mv_values.setFixedWidth(595)
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

    def _setup_policy_info_fields(self):
        section = "AdvProdValues"
        self.policy_info.add_field("Total AV", "total_av", 85, 65, section, "total_av")
        self.policy_info.add_field("Short Pay Prem", "short_pay_prem", 85, 65, section, "short_pay_prem")
        self.policy_info.add_field("Unimpaired AV", "unimpaired_av", 85, 65, section, "unimpaired_av")
        self.policy_info.add_field("Short Pay Mode", "short_pay_mode", 85, 65, section, "short_pay_mode")
        self.policy_info.add_field("Impaired AV", "impaired_av", 85, 65, section, "impaired_av")
        self.policy_info.add_field("Short Pay Dur", "short_pay_dur", 85, 65, section, "short_pay_dur")
        self.policy_info._current_col = 1
        self.policy_info.add_field("SP Billing Cease", "sp_billing_cease_date", 85, 65, section, "sp_billing_cease_date")
        self.policy_info.add_field("CCV", "ccv", 85, 65, section, "ccv")
        self.policy_info.add_field("SP Prem Cease Age", "sp_prem_cease_age", 85, 65, section, "sp_prem_cease_age")
        self.policy_info.add_field("Guar Int Rate", "guar_int_rate", 85, 65, section, "guar_int_rate")
        self.policy_info.add_field("DB Dial-To Age", "db_dial_to_age", 85, 65, section, "db_dial_to_age")
        self.policy_info.add_field("Grace Rule Code", "grace_rule_code", 85, 65, section, "grace_rule_code")

    # ── PolicyInformation path ───────────────────────────────────────────

    def load_data_from_policy(self, policy: 'PolicyInformation'):
        # Clear old data first so stale values never remain when switching policies
        self.policy_info.clear_info()
        self.mv_values.load_table_data([])
        self.fund_history.load_table_data([])
        self.unimpaired_values.load_table_data([])
        self.impaired_values.load_table_data([])

        try:
            if not policy.is_advanced_product:
                return

            self._load_policy_info_from_policy(policy)
            self._load_monthliversary_from_policy(policy)
            self._load_fund_history_from_policy(policy)
            self._load_fund_summary_from_policy(policy)
        except Exception as e:
            import traceback, sys
            print(f"[AdvProdValuesTab] Error loading data: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    def _load_policy_info_from_policy(self, policy):
        mvav = policy.mv_av(0)
        if mvav:
            self.policy_info.set_value("total_av", format_currency(mvav))

        fund_rows = policy.fetch_table("LH_POL_FND_VAL_TOT")
        unimpaired_total = 0.0
        for row in fund_rows:
            if "9999" in str(row.get("MVRY_DT", "")):
                amt = row.get("CSV_AMT", 0)
                if amt:
                    try:
                        unimpaired_total += float(amt)
                    except Exception:
                        pass
        self.policy_info.set_value("unimpaired_av", format_currency(unimpaired_total))

        loan_rows = policy.fetch_table("LH_FND_VAL_LOAN")
        impaired_total = 0.0
        for row in loan_rows:
            fnd_id = str(row.get("FND_ID_CD", "")).strip()
            if "9999" in str(row.get("MVRY_DT", "")) and fnd_id != "LZ":
                amt = row.get("LN_PRI_AMT", 0)
                if amt:
                    try:
                        impaired_total += float(amt)
                    except Exception:
                        pass
        self.policy_info.set_value("impaired_av", format_currency(impaired_total))

        if policy.gav:
            self.policy_info.set_value("gav", format_currency(policy.gav))

        cov_target_rows = policy.fetch_table("LH_COV_TARGET")
        ccv_total = 0.0
        for row in cov_target_rows:
            if str(row.get("TAR_TYP_CD", "")).strip() == "XP":
                amt = row.get("TAR_PRM_AMT", 0)
                if amt:
                    try:
                        ccv_total += float(amt)
                    except Exception:
                        pass
        if ccv_total > 0:
            self.policy_info.set_value("ccv", format_currency(ccv_total))

        if policy.guaranteed_interest_rate:
            try:
                self.policy_info.set_value("guar_int_rate", f"{float(policy.guaranteed_interest_rate)/100:.2%}")
            except Exception:
                self.policy_info.set_value("guar_int_rate", str(policy.guaranteed_interest_rate))

        if policy.grace_rule_code:
            self.policy_info.set_value("grace_rule_code", policy.grace_rule_code)

        if policy.short_pay_premium:
            self.policy_info.set_value("short_pay_prem", format_currency(policy.short_pay_premium))
        if policy.short_pay_duration:
            self.policy_info.set_value("short_pay_dur", str(policy.short_pay_duration))
            if policy.short_pay_mode:
                self.policy_info.set_value("short_pay_mode", policy.short_pay_mode)
            if policy.sp_billing_cease_date:
                self.policy_info.set_value("sp_billing_cease_date", str(policy.sp_billing_cease_date))
            if policy.short_pay_premium and policy.sp_prem_cease_age:
                self.policy_info.set_value("sp_prem_cease_age", str(policy.sp_prem_cease_age))
        if policy.db_dial_to_age:
            self.policy_info.set_value("db_dial_to_age", str(policy.db_dial_to_age))

    def _load_monthliversary_from_policy(self, policy):
        mv_rows = policy.fetch_table("LH_POL_MVRY_VAL")

        issue_date = policy.cov_issue_date(1)
        issue_month = issue_date.month if issue_date else 1
        mv_rows = sorted(mv_rows, key=lambda x: str(x.get("MVRY_DT", "")), reverse=True)

        table_rows = []
        for data in mv_rows:
            eff_date = format_date(data.get("MVRY_DT"))
            pol_year = str(data.get("POL_DUR_NBR", "")).strip()

            mv_date = data.get("MVRY_DT")
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
            else:
                pol_month = str(data.get("POL_MTH_NBR", "")).strip()

            table_rows.append([
                eff_date, pol_year, pol_month,
                format_currency(data.get("TOT_CRE_ITS_AMT")),
                format_currency(data.get("CSV_AMT")),
                format_currency(data.get("CINS_AMT")),
                format_currency(data.get("OTH_PRM_AMT")),
                format_currency(data.get("EXP_CRG_AMT")),
                format_currency(data.get("NAR_AMT")),
            ])

        self.mv_values.load_table_data(table_rows)

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
        fund_rows = policy.fetch_table("LH_POL_FND_VAL_TOT")

        fund_totals = {}
        for row in fund_rows:
            if "9999" in str(row.get("MVRY_DT", "")):
                fnd_cd = str(row.get("FND_ID_CD", "")).strip()
                if fnd_cd:
                    fund_totals[fnd_cd] = fund_totals.get(fnd_cd, 0) + float(row.get("CSV_AMT", 0) or 0)

        self.unimpaired_values.load_table_data([[fnd, format_currency(amt)] for fnd, amt in sorted(fund_totals.items())])

        loan_rows = policy.fetch_table("LH_FND_VAL_LOAN")
        loan_totals = {}
        for row in loan_rows:
            if "9999" in str(row.get("MVRY_DT", "")):
                fnd_cd = str(row.get("FND_ID_CD", "")).strip()
                if fnd_cd and fnd_cd != "LZ":
                    amt = float(row.get("LN_PRI_AMT", 0) or 0)
                    if amt > 0:
                        loan_totals[fnd_cd] = loan_totals.get(fnd_cd, 0) + amt

        self.impaired_values.load_table_data([[fnd, format_currency(amt)] for fnd, amt in sorted(loan_totals.items())])
