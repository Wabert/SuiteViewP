"""
CL_POLREC — Cyberlife Policy Record Modules
=============================================
System-layer modules mirroring Cyberlife mainframe policy records.

Most business logic has been moved to PolicyInformation.  Only a few
delegate classes are still used:

  BasePolicyRecords  — attribute-style access to base policy fields
  LoanRecords        — loan and APL data
  TotalRecords       — fund totals and specified amounts
"""

from .cyberlife_base import PolicyDataAccessor, parse_date

# Only the delegate classes still referenced by PolicyInformation
from .CL_POLREC_20_77 import LoanRecords
from .CL_POLREC_60_62_63_64_75 import TotalRecords

__all__ = [
    "PolicyDataAccessor",
    "parse_date",
    "LoanRecords",
    "TotalRecords",
]
