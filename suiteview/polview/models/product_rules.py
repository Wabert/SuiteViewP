"""Product-family rules for PolView policy data.

Traditional/Advanced branching affects source tables, rate presentation,
support tools and valuation dates. This module centralizes those rules behind a
small strategy object instead of scattering indicator checks through UI code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class ProductRules:
    """Behavior that varies by product family."""

    product_type: str
    is_advanced: bool
    value_table: str
    loan_tables: tuple[str, ...]
    valuation_uses_monthly_value: bool
    supports_glp_exception: bool
    supports_reinstatement: bool
    rate_family: str

    def display_rate(self, coverage) -> Optional[Decimal]:
        """Return the rate PolView displays for a coverage row."""
        if self.is_advanced and getattr(coverage, "coi_rate", None) is not None:
            return coverage.coi_rate
        return getattr(coverage, "premium_rate", None)

    def coi_rate_divisor(self) -> Decimal | None:
        """Stored renewal-rate divisor for displayed advanced COI rates."""
        if not self.is_advanced:
            return None
        if self.rate_family == "ISWL":
            return Decimal("100")
        return Decimal("100000")

    def valuation_date(self, policy) -> Optional[date]:
        """Apply this product family's valuation-date source rule."""
        if self.valuation_uses_monthly_value:
            mv_dt = policy._parse_date(policy.data_item("LH_POL_MVRY_VAL", "MVRY_DT"))
            if mv_dt and mv_dt.year < 9999:
                return mv_dt
        return policy.traditional_valuation_date()


class TraditionalRules(ProductRules):
    def __init__(self, product_type: str = "WL", rate_family: str | None = None) -> None:
        super().__init__(
            product_type=product_type,
            is_advanced=False,
            value_table="TH_COV_PHA",
            loan_tables=("LH_CSH_VAL_LOAN",),
            valuation_uses_monthly_value=False,
            supports_glp_exception=False,
            supports_reinstatement=False,
            rate_family=rate_family or product_type,
        )


class WholeLifeRules(TraditionalRules):
    def __init__(self) -> None:
        super().__init__("WL", "WL")


class DIRules(TraditionalRules):
    def __init__(self) -> None:
        super().__init__("DI", "DI")


class AdvancedRules(ProductRules):
    def __init__(
        self,
        product_type: str = "UL",
        *,
        supports_reinstatement: bool = True,
        rate_family: str | None = None,
    ) -> None:
        super().__init__(
            product_type=product_type,
            is_advanced=True,
            value_table="LH_POL_MVRY_VAL",
            loan_tables=("LH_FND_VAL_LOAN",),
            valuation_uses_monthly_value=True,
            supports_glp_exception=True,
            supports_reinstatement=supports_reinstatement,
            rate_family=rate_family or product_type,
        )


class ISWLRules(AdvancedRules):
    def __init__(self) -> None:
        super().__init__("ISWL", supports_reinstatement=False, rate_family="ISWL")


def product_rules_for(
    *,
    non_traditional_indicator: str,
    product_line_code: str,
    plancode: str,
    plancode_group: str | None = None,
) -> ProductRules:
    """Build the strategy from the policy's product identifiers."""
    non_trd = str(non_traditional_indicator or "").strip()
    product_line = str(product_line_code or "").strip().upper()
    plan = str(plancode or "").strip().upper()
    group = str(plancode_group or "").strip().upper()

    if non_trd == "1":
        if product_line == "I":
            return ISWLRules()
        return AdvancedRules("UL", supports_reinstatement=True, rate_family="UL")
    if not plan:
        return TraditionalRules("UNKNOWN", "UNKNOWN")

    if product_line == "S":
        return DIRules()
    if group and group != "NOT FOUND":
        if group == "WL":
            return WholeLifeRules()
        return TraditionalRules(group, group)
    if any(part in plan for part in ("TRM", "TERM", "TM", "RT", "ART", "YRT")):
        return TraditionalRules("TERM", "TERM")
    return WholeLifeRules()
