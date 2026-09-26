"""
TAICyberTAIFd tab - queries dbo.TAICyberTAIFd in the UL_Rates database.

Embedded in the Other Data tab; date inputs are shown before querying.
Provides a LastUpdate date range (defaulting the start to one month ago), a
TAICyberTAIFd button that runs the query against the "UL_Rates" SQL Server ODBC
connection, and a filterable/searchable grid.

Matching is on policy number only (Pol), not company code.  Every column is
displayed with LastUpdate moved to the front and rows ordered LastUpdate DESC.

If the user has no "UL_Rates" DSN configured (or the database refuses the
connection) the canvas states access is not available; if the policy has no
records, a single placeholder row says so.
"""

from datetime import date
from typing import Optional, TYPE_CHECKING

import pandas as pd
from dateutil.relativedelta import relativedelta

from .source_query_tab import SourceQueryTab
from suiteview.core.data_sources import UL_RATES_DSN

if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation


TABLE_NAME = "dbo.TAICyberTAIFd"
POLICY_COLUMN = "Pol"
DATE_COLUMN = "LastUpdate"

_NO_ACCESS_MESSAGE = (
    "You do not have access to this database (UL_Rates) set up on your machine."
)
_NO_RECORDS_MESSAGE = "No records for this policy number found in TAICyberTAIFd."


class TaiFdTab(SourceQueryTab):
    """dbo.TAICyberTAIFd viewer for the loaded policy."""

    dsn = UL_RATES_DSN
    date_label = "LastUpdate"
    query_button_text = "TAICyberTAIFd"
    no_access_message = _NO_ACCESS_MESSAGE
    no_records_message = _NO_RECORDS_MESSAGE

    def _default_start_date(self, policy: Optional["PolicyInformation"]) -> date:
        """Default the start to one month ago; leave the end blank."""
        return date.today() - relativedelta(months=1)

    def _build_query_request(
        self,
        policy: "PolicyInformation",
        date_from: Optional[date],
        date_to: Optional[date],
    ):
        policy_no = str(getattr(policy, "policy_number", "") or "").strip()

        where = [f"[{POLICY_COLUMN}] = ?"]
        params = [policy_no]
        if date_from is not None:
            where.append(f"[{DATE_COLUMN}] >= ?")
            params.append(date_from.isoformat())
        if date_to is not None:
            where.append(f"[{DATE_COLUMN}] < ?")
            params.append((date_to + relativedelta(days=1)).isoformat())

        sql = (
            f"SELECT * FROM {TABLE_NAME} "
            f"WHERE {' AND '.join(where)} "
            f"ORDER BY [{DATE_COLUMN}] DESC"
        )
        return sql, tuple(params)

    def _query_status_text(self, request) -> str:
        return f"Querying {TABLE_NAME} …"

    def _dataframe_from_rows(self, columns: list[str], rows: list[tuple]) -> pd.DataFrame:
        df = pd.DataFrame(rows, columns=columns)
        if DATE_COLUMN in df.columns:
            ordered = [DATE_COLUMN] + [c for c in df.columns if c != DATE_COLUMN]
            df = df[ordered]
        return df
