"""
CL_POLREC — Cyberlife Policy Record Modules
=============================================
System-layer modules mirroring Cyberlife mainframe policy records.

Each module maps to one or more Cyberlife policy record numbers and their
corresponding DB2 tables.  Classes in this layer speak the language of the
admin system using ALL_CAPS DB2 field names.

Modules
-------
cyberlife_base                  — PolicyDataAccessor protocol + parse_date()
policy_translations             — Merged constants + translation functions
CL_POLREC_01_51_66              — Base policy (Records 01, 51, 66)
CL_POLREC_02_03_09_67           — Coverages (Records 02, 03, 09, 67)
CL_POLREC_04                    — Benefits (Record 04)
CL_POLREC_05_06_07_08_68        — Changes (Records 05-08, 68)
CL_POLREC_12_13_14_15_18_19_74  — Dividends (Records 12-15, 18-19, 74)
CL_POLREC_20_77                 — Loans (Records 20, 77)
CL_POLREC_32_33_35              — Billing (Records 32, 33, 35)
CL_POLREC_38_48                 — Agents (Records 38, 48)
CL_POLREC_52                    — User fields (Record 52)
CL_POLREC_55_57_65              — Funds (Records 55, 57, 65)
CL_POLREC_58_59                 — Targets (Records 58, 59)
CL_POLREC_60_62_63_64_75        — Totals (Records 60, 62-64, 75)
CL_POLREC_69                    — Transactions (Record 69)
CL_POLREC_89_90                 — Persons (Records 89, 90)
"""

from .cyberlife_base import PolicyDataAccessor, parse_date

# Record module classes — populated as modules are created
from .CL_POLREC_01_51_66 import BasePolicyRecords
from .CL_POLREC_02_03_09_67 import CoverageRecords
from .CL_POLREC_04 import BenefitRecords
from .CL_POLREC_05_06_07_08_68 import ChangeRecords
from .CL_POLREC_12_13_14_15_18_19_74 import DividendRecords
from .CL_POLREC_20_77 import LoanRecords
from .CL_POLREC_32_33_35 import BillingRecords
from .CL_POLREC_38_48 import AgentRecords
from .CL_POLREC_52 import UserFieldRecords
from .CL_POLREC_55_57_65 import FundRecords
from .CL_POLREC_58_59 import TargetRecords
from .CL_POLREC_60_62_63_64_75 import TotalRecords
from .CL_POLREC_69 import TransactionRecords
from .CL_POLREC_89_90 import PersonRecords

__all__ = [
    "PolicyDataAccessor",
    "parse_date",
    "BasePolicyRecords",
    "CoverageRecords",
    "BenefitRecords",
    "ChangeRecords",
    "DividendRecords",
    "LoanRecords",
    "BillingRecords",
    "AgentRecords",
    "UserFieldRecords",
    "FundRecords",
    "TargetRecords",
    "TotalRecords",
    "TransactionRecords",
    "PersonRecords",
]
