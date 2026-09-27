"""PolicyInformation activity section."""

from __future__ import annotations

from .base import PolicySection
from ..cl_polrec.policy_data_classes import TransactionInfo
from ..cl_polrec.policy_translations import translate_transaction_code
from datetime import date
from decimal import Decimal
from typing import List
from typing import Optional


class ActivitySection(PolicySection):
    """Cohesive PolicyInformation activity view."""

    CACHE_ATTRS = ('_activities',)
    PREMIUM_TRANSACTION_CODES = frozenset({"PR", "PI", "PA", "PF", "PT", "PB", "PW"})

    @property
    def issue_date(self) -> Optional[date]:
        """Policy issue date (falls back to first coverage issue date)."""
        dt = self._parse_date(self.data_item("LH_COV_PHA", "ISSUE_DT"))
        if dt is None:
            covs = self.coverages.get_coverages()
            if covs:
                dt = covs[0].issue_date
        return dt

    @property
    def paid_to_date(self) -> Optional[date]:
        """Premium paid-to date."""
        return self._parse_date(self._field("paid_to_date"))

    @property
    def next_anniversary_date(self) -> Optional[date]:
        """Next policy anniversary date."""
        return self._parse_date(self._field("next_anniversary_date"))

    @property
    def next_monthliversary_date(self) -> Optional[date]:
        """Next monthliversary date."""
        return self._parse_date(self._field("next_monthliversary_date"))

    @property
    def terminate_date(self) -> Optional[date]:
        """Policy termination date."""
        return self._parse_date(self._field("terminate_date"))

    @staticmethod
    def _completed_date_parts_years(date1: date, date2: date) -> int:
        """Python equivalent of VBA CompletedDateParts("YYYY", date1, date2).

        Counts the number of full years between date1 and date2.
        If date2 < date1, the dates are swapped (always returns positive).
        """
        if date1 > date2:
            date1, date2 = date2, date1
        # Guard against sentinel dates like 9999-12-31 that would overflow
        if date2.year >= 9999:
            return date2.year - date1.year
        k = 0
        while True:
            try:
                next_date = date1.replace(year=date1.year + k + 1)
            except ValueError:
                # Handles Feb 29 -> non-leap year
                next_date = date(date1.year + k + 1, date1.month, 28)
            if next_date > date2:
                break
            k += 1
        return k

    @property
    def policy_year(self) -> int:
        """Current policy year (VBA: CompletedDateParts("YYYY", CovIssueDate(1), ValuationDate) + 1)."""
        covs = self.coverages.get_coverages()
        base_issue_date = covs[0].issue_date if covs else None
        val_date = self.values.valuation_date
        if base_issue_date and val_date:
            years = self._completed_date_parts_years(base_issue_date, val_date)
            return years + 1
        return 0

    @property
    def policy_month(self) -> int:
        """Current month within the policy year (1-12).

        Uses coverage 1 issue date (consistent with policy_year).
        Accounts for the day of the month: if today's day is before
        the issue day, the new month hasn't started yet.
        """
        covs = self.coverages.get_coverages()
        base_issue_date = covs[0].issue_date if covs else None
        if not base_issue_date:
            return 0
        today = date.today()
        total_months = ((today.year - base_issue_date.year) * 12
                        + (today.month - base_issue_date.month))
        if today.day < base_issue_date.day:
            total_months -= 1
        return (total_months % 12) + 1

    @property
    def last_anniversary(self) -> Optional[date]:
        """Last policy anniversary date."""
        return self._parse_date(self._field("last_anniversary"))

    @property
    def next_monthliversary(self) -> Optional[date]:
        """Next monthliversary processing date."""
        return self.next_monthliversary_date

    @property
    def last_financial_date(self) -> Optional[date]:
        """Last financial processing date."""
        dt = self._parse_date(self._field("last_financial_date"))
        # Treat sentinel dates (e.g. 9999-12-31) as missing
        if dt and dt.year >= 9999:
            return None
        return dt

    def get_transactions(self, limit: int = None) -> List[TransactionInfo]:
        """Get transaction records from FH_FIXED, ordered by date descending."""
        transactions = []
        count = 0
        for row in self.fetch_table("FH_FIXED"):
            if limit and count >= limit:
                break

            trans_type = str(row.get("TRN_TYP_CD", "") or "").strip().upper()
            trans_subtype = str(row.get("TRN_SBY_CD", "") or "").strip().upper()
            trans_code = str(row.get("TRANS", "") or "").strip().upper()
            if not trans_code:
                trans_code = trans_type + trans_subtype

            gross_value = row.get("GROSS_AMT")
            if gross_value is None:
                gross_value = row.get("TOT_TRS_AMT")
            net_value = row.get("NET_AMT")
            if net_value is None:
                net_value = row.get("ACC_VAL_GRS_AMT")

            trans = TransactionInfo(
                trans_date=self._parse_date(row.get("ASOF_DT")),
                trans_code=trans_code,
                trans_type=trans_type,
                trans_subtype=trans_subtype,
                trans_desc=translate_transaction_code(trans_code),
                gross_amount=Decimal(str(gross_value)) if gross_value is not None else None,
                net_amount=Decimal(str(net_value)) if net_value is not None else None,
                sequence_number=int(row.get("SEQ_NO", 0) or 0),
                fund_id=str(row.get("FND_ID_CD", "") or ""),
                coverage_phase=int(row.get("COV_PHA_NBR", 0) or 0),
                raw_data=row
            )
            transactions.append(trans)
            count += 1
        return transactions

    def get_premium_transactions(self) -> List[TransactionInfo]:
        """Return unreversed policy premium transactions in issue-date order."""
        transactions = []
        for transaction in self.get_transactions():
            row = transaction.raw_data
            reversed_or_reversal = (
                str(row.get("FCB0_REV_IND", "") or "").strip() == "1"
                or str(row.get("FCB2_REV_APPL_IND", "") or "").strip() == "1"
            )
            if (
                transaction.trans_code in self.PREMIUM_TRANSACTION_CODES
                and not reversed_or_reversal
                and transaction.trans_date is not None
                and transaction.gross_amount is not None
            ):
                transactions.append(transaction)
        return sorted(
            transactions,
            key=lambda transaction: (
                transaction.trans_date,
                transaction.sequence_number,
            ),
        )

    @property
    def transaction_count(self) -> int:
        """Count of transaction records."""
        return self.data_item_count("FH_FIXED")

    def transaction_date(self, index: int) -> Optional[date]:
        """Get transaction date (0-based index)."""
        return self._parse_date(self.data_item("FH_FIXED", "ASOF_DT", index))

    def transaction_code(self, index: int) -> str:
        """Get transaction code (type + subtype) (0-based index)."""
        trans_type = str(self.data_item("FH_FIXED", "TRN_TYP_CD", index) or "")
        trans_subtype = str(self.data_item("FH_FIXED", "TRN_SBY_CD", index) or "")
        return trans_type + trans_subtype

    def transaction_type(self, index: int) -> str:
        """Get transaction type code (0-based index)."""
        return str(self.data_item("FH_FIXED", "TRN_TYP_CD", index) or "")

    def transaction_subtype(self, index: int) -> str:
        """Get transaction subtype code (0-based index)."""
        return str(self.data_item("FH_FIXED", "TRN_SBY_CD", index) or "")

    def transaction_description(self, index: int) -> str:
        """Get transaction description (translated code) (0-based index)."""
        return translate_transaction_code(self.transaction_code(index))

    def transaction_gross_amount(self, index: int) -> Optional[Decimal]:
        """Get transaction gross amount (0-based index)."""
        val = self.data_item("FH_FIXED", "TOT_TRS_AMT", index)
        return Decimal(str(val)) if val else None

    def transaction_net_amount(self, index: int) -> Optional[Decimal]:
        """Get transaction net amount (0-based index)."""
        val = self.data_item("FH_FIXED", "ACC_VAL_GRS_AMT", index)
        return Decimal(str(val)) if val else None

    def transaction_sequence(self, index: int) -> int:
        """Get transaction sequence number (0-based index)."""
        val = self.data_item("FH_FIXED", "SEQ_NO", index)
        return int(val) if val else 0

    def transaction_fund_id(self, index: int) -> str:
        """Get transaction fund ID (0-based index)."""
        return str(self.data_item("FH_FIXED", "FND_ID_CD", index) or "")

    def transaction_cov_phase(self, index: int) -> int:
        """Get transaction coverage phase (0-based index)."""
        val = self.data_item("FH_FIXED", "COV_PHA_NBR", index)
        return int(val) if val else 0
