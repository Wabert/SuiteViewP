"""
SAP tab - queries the SAP.LDTI_TX7 ledger for the loaded policy.

Embedded in the Other Data tab; date inputs are shown before querying.
Provides a POSTING_DATE range (defaulting the start to two years before the
policy's valuation date), a SAP_LDTI_TX7 button that runs the query against the
"VRD Prod" SQL Server ODBC connection, and a filterable/searchable ledger grid.

If the user has no "VRD Prod" DSN configured, the query controls are disabled
and a red notice is shown.
"""

from datetime import date
from typing import Optional, TYPE_CHECKING

import pandas as pd
from dateutil.relativedelta import relativedelta

from .source_query_tab import SourceQueryTab
from suiteview.core.data_sources import VRD_PROD_DSN
from suiteview.polview.models.policy_sections.lookup import policy_attr

if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation


DISPLAY_COLUMNS = [
    "LDTI_TX7_ID",
    "COMPANY_CODE",
    "POLICY_NUMBER",
    "POSTING_DATE",
    "GL_ACCOUNT_NUMBER",
    "TRANSACTION_DATE",
    "CLAIM_NUMBER",
    "AMOUNT",
    "ITEM_TEXT",
    "REINSURANCE_CODE",
    "SOURCE_SYSTEM",
]

_DATE_COLUMNS = ("POSTING_DATE", "TRANSACTION_DATE")

_NO_ACCESS_MESSAGE = (
    "You do not have access to this database (VRD Prod) set up on your machine."
)


class SapTab(SourceQueryTab):
    """SAP.LDTI_TX7 ledger viewer for the loaded policy."""

    dsn = VRD_PROD_DSN
    date_label = "POSTING_DATE"
    query_button_text = "SAP_LDTI_TX7"
    no_access_message = _NO_ACCESS_MESSAGE
    no_records_message = None
    hide_grid_on_no_access = False
    include_no_access_state = False

    def _configure_grid(self) -> None:
        self.grid.set_numeric_formatting(column_decimals={"AMOUNT": 2})

    def _empty_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(columns=DISPLAY_COLUMNS)

    def _default_start_date(self, policy: Optional["PolicyInformation"]) -> date:
        """Default the start to two years before valuation date."""
        base = policy_attr(policy, "valuation_date", None) if policy is not None else None
        return (base or date.today()) - relativedelta(years=2)

    def _build_query_request(
        self,
        policy: "PolicyInformation",
        date_from: Optional[date],
        date_to: Optional[date],
    ):
        company = str(getattr(policy, "company_code", "") or "").strip()
        policy_no = str(getattr(policy, "policy_number", "") or "").strip()

        where = ["COMPANY_CODE = ?", "POLICY_NUMBER = ?"]
        params = [company, policy_no]
        if date_from is not None:
            where.append("POSTING_DATE >= ?")
            params.append(date_from.isoformat())
        if date_to is not None:
            where.append("POSTING_DATE < ?")
            params.append((date_to + relativedelta(days=1)).isoformat())

        sql = (
            "SELECT LDTI_TX7_ID, COMPANY_CODE, POLICY_NUMBER, POSTING_DATE, "
            "GL_ACCOUNT_NUMBER, TRANSACTION_DATE, CLAIM_NUMBER, AMOUNT, ITEM_TEXT, "
            "REINSURANCE_CODE, SOURCE_SYSTEM "
            "FROM SAP.LDTI_TX7 "
            "WHERE " + " AND ".join(where) + " "
            "ORDER BY POSTING_DATE DESC"
        )
        return sql, tuple(params)

    def _query_status_text(self, request) -> str:
        return "Querying SAP.LDTI_TX7 …"

    def _dataframe_from_rows(self, columns: list[str], rows: list[tuple]) -> pd.DataFrame:
        df = pd.DataFrame(rows, columns=columns or DISPLAY_COLUMNS)
        if not df.empty:
            if "AMOUNT" in df.columns:
                df["AMOUNT"] = pd.to_numeric(df["AMOUNT"], errors="coerce")
            for col in _DATE_COLUMNS:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
        return df

    def _success_status(self, df: pd.DataFrame) -> str:
        return f"{len(df):,} row(s) returned."

    def _treat_exception_as_no_access(self, exc: Exception) -> bool:
        return False
