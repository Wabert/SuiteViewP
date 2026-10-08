"""PolicyInformation product section."""

from __future__ import annotations

from .base import PolicySection
from ..cl_polrec.policy_translations import DB_OPTION_CODES
from ..cl_polrec.policy_translations import DEF_OF_LIFE_INS_CODES
from ..cl_polrec.policy_translations import PRODUCT_LINE_CODES
from ..cl_polrec.policy_translations import translate_state_code
from ..product_rules import ProductRules
from ..product_rules import product_rules_for
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

FIXED_FUND_CONTROL_TABLE = "LH_COV_FXD_FND_CTL"


@dataclass(frozen=True)
class FundGuaranteedRate:
    """One fixed fund's guaranteed crediting rate (percent form, ``None`` if blank)."""

    fund_id: str
    coverage_phase: Optional[int]
    rate: Optional[Decimal]


try:
    from suiteview.polview.data.lookup import DataLookup as _DataLookup
    _data_lookup = _DataLookup()
except ImportError:
    _data_lookup = None  # type: ignore[assignment]


class ProductSection(PolicySection):
    """Cohesive PolicyInformation product view."""

    CACHE_ATTRS = ('_product_rules',)

    @property
    def issue_state_code(self) -> str:
        """Issue state code (raw numeric from ISSUE_ST_CD)."""
        return str(self._field("issue_state_code") or "")

    @property
    def issue_state(self) -> str:
        """Issue state abbreviation (e.g., 'AZ', 'NY')."""
        code = self.issue_state_code
        if code and code.isdigit():
            return translate_state_code(int(code))
        return code

    @property
    def resident_state_code(self) -> str:
        """Resident/premium-paying state code (raw numeric from PRM_PAY_ST_CD)."""
        return str(self._field("resident_state_code") or "")

    @property
    def resident_state(self) -> str:
        """Resident/premium-paying state abbreviation (e.g., 'AZ', 'NY')."""
        code = self.resident_state_code
        if code and code.isdigit():
            return translate_state_code(int(code))
        return code

    @property
    def state_code(self) -> str:
        """Alias for issue_state_code (deprecated - use issue_state_code instead)."""
        return self.issue_state_code

    @property
    def db_option_code(self) -> str:
        """Death benefit option code."""
        return str(self._field("db_option_code") or "")

    @property
    def db_option_description(self) -> str:
        """Death benefit option description."""
        return DB_OPTION_CODES.get(self.db_option_code, f"Unknown ({self.db_option_code})")

    @property
    def is_advanced_product(self) -> bool:
        """Whether this is an advanced product (UL/IUL/VUL)."""
        return self.product_rules.is_advanced

    @property
    def product_type(self) -> str:
        """
        Determine product type: WL, TERM, UL, IUL, VUL, ISWL, DI.

        Uses the official plancode table (DataLookup) as the primary source
        of truth.  Falls back to heuristic matching for plancodes not in
        the table.
        """
        plancode = str(self.data_item("LH_COV_PHA", "PLN_DES_SER_CD") or "").strip()
        if not plancode:
            return "UNKNOWN"
        return self.product_rules.product_type

    @property
    def is_indexed_ul(self) -> bool:
        """Base coverage's ANICO product indicator (TH_COV_PHA.AN_PRD_ID) is X - Index UL."""
        return str(self._field("annuity_product_id") or "").strip().upper() == "X"

    @property
    def display_product_type(self) -> str:
        """Product type for display: UL policies flagged Index UL show as IUL."""
        product_type = self.product_type
        if product_type == "UL" and self.is_indexed_ul:
            return "IUL"
        return product_type

    @property
    def product_line_code(self) -> str:
        """Product line type code."""
        return str(self._field("product_line_code") or "")

    @property
    def is_annuity(self) -> bool:
        """Whether the base coverage is an annuity (product line ``F``)."""
        return self.product_line_code.strip().upper() == "F"

    @property
    def major_line_of_business(self) -> str:
        """Major line of business code from the base coverage row, when present."""
        return str(self._field("major_line_of_business") or "")

    @property
    def product_rules(self) -> ProductRules:
        """Product-family strategy for product-specific policy rules."""
        if getattr(self, "_product_rules", None) is None:
            plancode = str(self.data_item("LH_COV_PHA", "PLN_DES_SER_CD") or "").strip()
            group = None
            if plancode and _data_lookup is not None:
                group = _data_lookup.get_plancode_group(plancode)
            self._product_rules = product_rules_for(
                non_traditional_indicator=str(self._field("non_traditional_indicator") or ""),
                product_line_code=str(self._field("product_line_code") or ""),
                plancode=plancode,
                plancode_group=group,
            )
        return self._product_rules

    def _product_rules_for_rate_display(self) -> ProductRules:
        """Return product rules, preserving legacy test doubles with only product_type."""
        try:
            rules = self.product_rules
            if rules.rate_family != "UNKNOWN":
                return rules
        except Exception:
            pass

        try:
            product_type = str(self.product_type or "").strip().upper()
        except Exception:
            product_type = ""

        if product_type == "WL":
            return product_rules_for(
                non_traditional_indicator="0",
                product_line_code="",
                plancode=product_type,
                plancode_group="WL",
            )
        if product_type == "ISWL":
            return product_rules_for(
                non_traditional_indicator="1",
                product_line_code="I",
                plancode=product_type,
            )
        if product_type in {"UL", "IUL", "VUL", "SGUL"}:
            return product_rules_for(
                non_traditional_indicator="1",
                product_line_code="U",
                plancode=product_type,
            )
        return product_rules_for(
            non_traditional_indicator="0",
            product_line_code="",
            plancode=product_type,
            plancode_group=product_type or None,
        )

    @property
    def product_line_description(self) -> str:
        """Product line description."""
        return PRODUCT_LINE_CODES.get(self.product_line_code, f"Unknown ({self.product_line_code})")

    @property
    def defra_indicator(self) -> str:
        """DEFRA indicator (not stored on LH_BAS_POL — use tefra_defra_code)."""
        return ""

    @property
    def def_of_life_ins_code(self) -> str:
        """Definition of Life Insurance code."""
        return str(self._field("definition_of_life_code") or "")

    @property
    def def_of_life_ins_description(self) -> str:
        """Definition of Life Insurance description."""
        return DEF_OF_LIFE_INS_CODES.get(self.def_of_life_ins_code, "")

    @property
    def guideline_single_premium(self) -> Optional[Decimal]:
        """Guideline Single Premium (GSP — not stored on LH_BAS_POL)."""
        return None

    @property
    def guideline_level_premium(self) -> Optional[Decimal]:
        """Guideline Level Premium (GLP — not stored on LH_BAS_POL)."""
        return None

    @property
    def guaranteed_interest_rate(self) -> Optional[Decimal]:
        """Policy guaranteed interest rate (LH_NON_TRD_POL.POL_GUA_ITS_RT), percent form.

        This is the policy-level rate used to discount the death benefit in
        the NAR calculation. The fixed funds' guaranteed crediting rate can
        differ; see :attr:`fund_guaranteed_interest_rates`.
        """
        val = self._field("guaranteed_interest_rate")
        return Decimal(str(val)) if val is not None else None

    @property
    def fund_guaranteed_interest_rates(self) -> tuple[FundGuaranteedRate, ...]:
        """Guaranteed crediting rate per fixed fund (LH_COV_FXD_FND_CTL.GUA_FND_ITS_RT).

        One entry per fund-control row, ordered by coverage phase then fund.
        Rates are percent form (``4.000`` = 4%). An empty tuple means the
        policy has no fixed funds; a failed table read raises.
        """
        rows = self.fetch_table(FIXED_FUND_CONTROL_TABLE)
        rates = [
            FundGuaranteedRate(
                fund_id=str(row.get("FND_ID_CD") or "").strip(),
                coverage_phase=self._parse_optional_int(row.get("COV_PHA_NBR")),
                rate=self._parse_optional_decimal(row.get("GUA_FND_ITS_RT")),
            )
            for row in rows
        ]
        return tuple(sorted(
            rates, key=lambda r: (r.coverage_phase is None, r.coverage_phase or 0, r.fund_id)))

    @property
    def corridor_percent(self) -> Optional[Decimal]:
        """Corridor percentage for death benefit calculation."""
        val = self._field("corridor_percent")
        return Decimal(str(val)) if val is not None else Decimal("100")

    @property
    def grace_rule_code(self) -> str:
        """Grace period rule code."""
        return str(self._field("grace_rule_code") or "")

    @property
    def prospective_bonus_code(self) -> str:
        """Prospective (conditional) interest-bonus stage, LH_NON_TRD_POL.PRO_BNS_RS_CD.

        CyberLife mod AN0230: ``0`` no bonus earned, ``5`` tier 1 earned at the 11th
        anniversary, ``6`` tier 2 earned at the 21st. Blank when not recorded.
        """
        return str(self._field("prospective_bonus_code") or "").strip()

    @property
    def full_surrender_charge_rules(self) -> tuple[str, str]:
        """Full surrender charge rules, LH_NON_TRD_POL FUL_SRD_FST_CRG_CD / FUL_SRD_2ND_CRG_CD
        (D10 CKDRECUL 05: e.g. ``6`` surrender target, ``5`` free-surrender percent)."""
        return (str(self._field("full_surrender_first_charge_rule") or "").strip(),
                str(self._field("full_surrender_second_charge_rule") or "").strip())

    @property
    def tefra_defra_code(self) -> str:
        """TEFRA/DEFRA indicator code."""
        return str(self.data_item("LH_NON_TRD_POL", "TFDF_CD") or "")

    @property
    def tefra_defra(self) -> str:
        """TEFRA or DEFRA description."""
        code = self.tefra_defra_code
        if code in ("1",):
            return "TEFRA"
        elif code in ("2", "3", "5"):
            return "DEFRA"
        return code

    @property
    def gpt_cvat(self) -> str:
        """GPT or CVAT test type."""
        code = self.tefra_defra_code
        if code in ("1", "2", "4"):
            return "GPT"
        elif code in ("3", "5"):
            return "CVAT"
        return code
