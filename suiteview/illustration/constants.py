"""Shared actuarial constants for UL illustration calculations.

Keep these names tied to calculation meaning.  Do not use them as generic
substitutes for unrelated numbers or one-letter status/mode codes.
"""
from __future__ import annotations

from enum import Enum

MONTHS_PER_YEAR = 12
DAYS_PER_YEAR = 365
PER_THOUSAND = 1000.0
MONEY_EPSILON = 1e-9

# RERUN's "no limit" premium sentinel used in allowance min/max chains.
NO_LIMIT_PREMIUM = 999_999_999.0
INF = NO_LIMIT_PREMIUM


class DBOption(str, Enum):
    """Death-benefit option codes from CyberLife/RERUN."""

    LEVEL = "A"
    INCREASING = "B"
    RETURN_OF_PREMIUM = "C"


DB_OPTION_LEVEL = DBOption.LEVEL.value
DB_OPTION_INCREASING = DBOption.INCREASING.value
DB_OPTION_RETURN_OF_PREMIUM = DBOption.RETURN_OF_PREMIUM.value


class LapseBasis(str, Enum):
    """Plan lapse test basis codes."""

    SURRENDER_VALUE = "SV"
    ACCOUNT_VALUE = "AV"


LAPSE_BASIS_SURRENDER_VALUE = LapseBasis.SURRENDER_VALUE.value
LAPSE_BASIS_ACCOUNT_VALUE = LapseBasis.ACCOUNT_VALUE.value


class RateCode(str, Enum):
    """Configuration tokens for table-driven rates."""

    TABLE = "Table"


RATE_CODE_TABLE = RateCode.TABLE.value


class SpecifiedAmountBasis(str, Enum):
    """Specified amount bases used by plan code configuration."""

    CURRENT = "CurrentSA"
    ORIGINAL = "OriginalSA"


SA_BASIS_CURRENT = SpecifiedAmountBasis.CURRENT.value
SA_BASIS_ORIGINAL = SpecifiedAmountBasis.ORIGINAL.value
