"""
CL_POLREC_69 — Transaction Records (Record 69)
=================================================

DB2 tables
----------
Record 69 — Financial History
    FH_FIXED             Financial history transactions
"""

from __future__ import annotations

from decimal import Decimal
from datetime import date
from typing import List, Optional

from .cyberlife_base import PolicyDataAccessor, parse_date
from .policy_data_classes import TransactionInfo
from .policy_translations import translate_transaction_code


class TransactionRecords:
    """System-layer access for transaction history records."""

    TABLES = (
        "FH_FIXED",
    )

    def __init__(self, policy: PolicyDataAccessor) -> None:
        self._policy = policy

    def invalidate(self) -> None:
        pass

    # =====================================================================
    # TRANSACTIONS (FH_FIXED)
    # =====================================================================

    def get_transactions(self, limit: Optional[int] = None) -> List[TransactionInfo]:
        """Get transaction records from FH_FIXED, ordered by date descending."""
        transactions: List[TransactionInfo] = []
        count = 0
        for row in self._policy.fetch_table("FH_FIXED"):
            if limit and count >= limit:
                break
            trans_code = str(row.get("TRANS", "") or "")
            # TRANS contains the combined type+subtype code
            trans_type = trans_code[:2] if len(trans_code) >= 2 else trans_code
            trans_subtype = trans_code[2:] if len(trans_code) > 2 else ""
            trans = TransactionInfo(
                trans_date=parse_date(row.get("ASOF_DT")),
                trans_code=trans_code,
                trans_type=trans_type,
                trans_subtype=trans_subtype,
                trans_desc=translate_transaction_code(trans_code),
                gross_amount=Decimal(str(row["GROSS_AMT"])) if row.get("GROSS_AMT") else None,
                net_amount=Decimal(str(row["NET_AMT"])) if row.get("NET_AMT") else None,
                sequence_number=int(row.get("SEQ_NO", 0) or 0),
                fund_id=str(row.get("FUND_ID", "") or ""),
                coverage_phase=int(row.get("PHASE", 0) or 0),
                raw_data=row,
            )
            transactions.append(trans)
            count += 1
        return transactions

    @property
    def transaction_count(self) -> int:
        return self._policy.data_item_count("FH_FIXED")

    def transaction_date(self, index: int) -> Optional[date]:
        return parse_date(self._policy.data_item("FH_FIXED", "ASOF_DT", index))

    def transaction_code(self, index: int) -> str:
        return str(self._policy.data_item("FH_FIXED", "TRANS", index) or "")

    def transaction_type(self, index: int) -> str:
        code = self.transaction_code(index)
        return code[:2] if len(code) >= 2 else code

    def transaction_description(self, index: int) -> str:
        return translate_transaction_code(self.transaction_code(index))

    def transaction_gross_amount(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("FH_FIXED", "GROSS_AMT", index)
        return Decimal(str(val)) if val else None

    def transaction_net_amount(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("FH_FIXED", "NET_AMT", index)
        return Decimal(str(val)) if val else None

    def transaction_sequence(self, index: int) -> int:
        val = self._policy.data_item("FH_FIXED", "SEQ_NO", index)
        return int(val) if val else 0

    def transaction_fund_id(self, index: int) -> str:
        return str(self._policy.data_item("FH_FIXED", "FUND_ID", index) or "")

    def transaction_cov_phase(self, index: int) -> int:
        val = self._policy.data_item("FH_FIXED", "PHASE", index)
        return int(val) if val else 0
