"""
ABR Quote — Term Premium Calculator.

Computes annual and modal premiums using:
    - Base rate from TERM tables (UL_Rates ODBC, pointer-based)
    - Table rating additional rate
    - Flat extra additional rate
    - Policy fee (from TERM_POINT_PV.FEE)
    - Modal factors (premium + fee, from TERM_RATE_MODEFACT)

Replicates the "Term Premium Calculation" sheet logic.
"""

from __future__ import annotations

import math
import logging
from typing import Optional, List

def arithmetic_round(value: float, decimals: int = 2) -> float:
    """Standard arithmetic rounding (half away from zero)."""
    multiplier = 10 ** decimals
    return math.floor(value * multiplier + 0.5) / multiplier

from ..models.abr_constants import (
    PLAN_CODE_INFO,
    MODAL_LABELS,
)
from ..models.abr_data import ABRPolicyData, PremiumResult, RiderInfo
from ..models.abr_database import get_abr_database

# Benefit name mapping for TERM_POINT_BENEFIT.Benefit column
from suiteview.polview.models.cl_polrec.policy_translations import BENEFIT_TYPE_CODES

logger = logging.getLogger(__name__)


class PremiumCalculator:
    """Calculate term premiums for ABR quote.

    Usage:
        calc = PremiumCalculator(policy_data)
        result = calc.compute()
        schedule = calc.get_rate_schedule()
    """

    def __init__(self, policy: ABRPolicyData):
        self.policy = policy
        self.db = get_abr_database()

    def compute(self, policy_year: Optional[int] = None, band_override: Optional[str] = None) -> PremiumResult:
        """Compute premium for a given policy year (default: current year).

        Follows the Signature Term Product Spec rounding order:
            Step 1: round(base_rate × substandard_factor, 2)
            Step 2: + flat extra
            Step 3: round(step2 × face/1000, 2)
            Step 4: + rider annual premiums
            Step 5: + $60 policy fee

        Returns:
            PremiumResult with base rate, table rate, flat rate,
            annual premium, and modal premium.
        """
        p = self.policy
        year = policy_year or p.policy_year

        # ── Build lookup key ────────────────────────────────────────────
        band = band_override if band_override is not None else self.db.get_band(p.plan_code, p.face_amount, p.issue_date)
        sex = (p.rate_sex or p.sex).upper()  # rate_sex from 67 segment; fallback to true sex
        rate_class = p.rate_class.upper()
        plancode = p.plan_code.upper()

        lookup_key = f"{plancode} {sex} {rate_class} {band} {p.issue_age}"

        # ── Base rate lookup ────────────────────────────────────────────
        base_rate = self.db.get_term_rate(
            plancode, sex, rate_class, band, p.issue_age, year
        )

        if base_rate is None:
            logger.warning(f"No base rate found for key='{lookup_key}', year={year}")
            return PremiumResult(
                lookup_key=lookup_key,
                modal_label=MODAL_LABELS.get(p.billing_mode, "Unknown"),
            )

        # ── Step 1: base_rate × substandard_factor → round 2dp ─────────
        substandard_factor = 1.0 + p.table_rating * 0.25
        step1_rate = arithmetic_round(base_rate * substandard_factor, 2)
        table_rate = step1_rate - base_rate  # for display

        # ── Step 2: + flat extra ────────────────────────────────────────
        if p.flat_extra > 0 and p.flat_to_age > 0 and p.attained_age < p.flat_to_age:
            flat_rate = p.flat_extra
        else:
            flat_rate = 0.0
        step2_rate = step1_rate + flat_rate

        # ── Step 3: × (face / 1000) → round 2dp ────────────────────────
        step3_premium = arithmetic_round(step2_rate * p.face_per_thousand, 2)

        # ── Step 4: + rider / benefit annual premiums ───────────────────
        rider_total = self._compute_all_riders_premium(year)
        step4_premium = step3_premium + rider_total

        # ── Step 5: + policy fee ────────────────────────────────────────
        policy_fee = self.db.get_policy_fee(plancode)
        annual_premium = arithmetic_round(step4_premium + policy_fee, 2)

        # ── Modal premium (single factor applied to total) ──────────────
        modal_factor = self.db.get_modal_factor(plancode, p.billing_mode)
        modal_fee_factor = self.db.get_modal_fee_factor(plancode, p.billing_mode)
        modal_premium = arithmetic_round(annual_premium * modal_factor, 2)
        modal_label = MODAL_LABELS.get(p.billing_mode, "Annual")

        return PremiumResult(
            base_rate=base_rate,
            table_rate=table_rate,
            flat_rate=flat_rate,
            total_rate=step2_rate,
            policy_fee=policy_fee,
            annual_premium=annual_premium,
            modal_premium=modal_premium,
            modal_label=modal_label,
            lookup_key=lookup_key,
        )

    def get_rate_schedule(self) -> Optional[List[float]]:
        """Get full 82-year rate schedule for the policy's lookup key.

        Returns:
            List of 82 annual rates per $1,000, or None if not found.
        """
        p = self.policy
        band = self.db.get_band(p.plan_code, p.face_amount, p.issue_date)

        return self.db.get_term_rate_schedule(
            p.plan_code.upper(),
            (p.rate_sex or p.sex).upper(),  # rate_sex from 67 segment
            p.rate_class.upper(),
            band,
            p.issue_age,
        )

    def get_premium_schedule(self) -> List[float]:
        """Get per-$1,000 rate for each policy year (base + table + flat).

        Follows product spec rounding:
            Step 1: round(base_rate × substandard_factor, 2)
            Step 2: + flat extra for that year

        Returns list of per-$1,000 rates (up to 82 years).
        """
        rate_schedule = self.get_rate_schedule()
        if rate_schedule is None:
            return []

        p = self.policy
        substandard_factor = 1.0 + p.table_rating * 0.25

        result = []
        for year_idx, base_rate in enumerate(rate_schedule):
            year = year_idx + 1
            attained = p.issue_age + year - 1

            # Step 1: round(base × substandard_factor, 2)
            step1 = arithmetic_round(base_rate * substandard_factor, 2)

            # Step 2: + flat extra (only if attained age < flat_to_age)
            fe = 0.0
            if p.flat_extra > 0 and p.flat_to_age > 0 and attained < p.flat_to_age:
                fe = p.flat_extra
            step2 = step1 + fe

            result.append(step2)

        return result

    def get_annual_premium_schedule(self) -> List[float]:
        """Get full annual premium (in dollars) for each policy year.

        Applies ALL five steps of the Signature Term Product Spec:
            Step 1: round(base_rate × substandard_factor, 2)
            Step 2: + flat extra for that year
            Step 3: round(step2 × face/1000, 2)
            Step 4: + rider annual premiums
            Step 5: + policy fee

        Returns list of annual premiums (up to 82 years).
        """
        per_k_schedule = self.get_premium_schedule()
        if not per_k_schedule:
            return []

        p = self.policy
        policy_fee = self.db.get_policy_fee(p.plan_code)

        result = []
        for year_idx, rate in enumerate(per_k_schedule):
            year = year_idx + 1
            step3 = arithmetic_round(rate * p.face_per_thousand, 2)
            rider_total = self._compute_all_riders_premium(year)
            annual = step3 + rider_total + policy_fee
            result.append(annual)

        return result

    def get_base_annual_premium_schedule(self) -> List[float]:
        """Get annual premium for the primary coverage only (no riders/CTR/benefits).

        Applies Steps 1-3 + policy fee only (no rider premiums):
            Step 1: round(base_rate × substandard_factor, 2)
            Step 2: + flat extra for that year
            Step 3: round(step2 × face/1000, 2)
            Step 5: + policy fee

        This is used for the Future Premiums for Acceleration table,
        which should only reflect the primary insured coverage.

        Returns list of annual premiums (up to 82 years).
        """
        per_k_schedule = self.get_premium_schedule()
        if not per_k_schedule:
            return []

        p = self.policy
        policy_fee = self.db.get_policy_fee(p.plan_code)

        result = []
        for rate in per_k_schedule:
            step3 = arithmetic_round(rate * p.face_per_thousand, 2)
            annual = step3 + policy_fee
            result.append(annual)

        return result

    def compute_min_face_premium(self, min_face: float = 50_000.0,
                                     policy_year: Optional[int] = None) -> PremiumResult:
        """Compute premium for minimum face amount (for partial acceleration).

        After partial acceleration, the remaining face is the minimum
        ($50,000). This computes the premium on that remaining face,
        using the band that corresponds to min_face (which may differ
        from the original policy band).
        """
        # Create a copy of policy with reduced face
        from dataclasses import replace
        reduced = replace(self.policy, face_amount=min_face)
        calc = PremiumCalculator(reduced)
        return calc.compute(policy_year=policy_year)

    # ── Rider premium helpers ───────────────────────────────────────────

    def _compute_all_riders_premium(self, year: int) -> float:
        """Sum computed annual premiums for all riders at a given policy year."""
        p = self.policy
        if not p.riders:
            # Legacy fallback: use flat rider_annual_premium from CyberLife
            return p.rider_annual_premium

        total = 0.0
        for rider in p.riders:
            total += self.compute_rider_annual_premium(rider, year)
        return total

    def compute_rider_annual_premium(self, rider: RiderInfo, year: int) -> float:
        """Compute the annual premium for a single rider at a given policy year.

        BENEFIT type (benefit_type populated):
            Uses get_benefit_rate(plancode, benefit_type, benefit_subtype,
            sex, rate_class, band, issue_age, year) for rate lookup.
            Formula: round(rate × face/1000, 2)

        PW/CTR/OTHER types (legacy):
            PW: round(round(rate × pw_sub, 2) × face/1000, 2)
            CTR: round(rate × face/1000, 2)
            OTHER: fallback_premium (constant)

        Premium ceases at the rider's PREM_CEASE age.
        """
        if rider.rider_type == "OTHER":
            return rider.fallback_premium

        # Check premium cease
        p = self.policy
        cease_age = self.db.get_prem_cease_age(rider.plancode)
        attained_age = rider.issue_age + (year - 1) + (p.policy_year - 1)
        if attained_age >= cease_age:
            return 0.0

        band = self.db.get_band(rider.plancode, rider.face_amount, self.policy.issue_date)
        face_units = rider.face_amount / 1000.0

        # BENEFIT type: use benefit rate from TERM_POINT_BENEFIT
        if rider.rider_type == "BENEFIT" and rider.benefit_type:
            # TERM_POINT_BENEFIT stores BenefitType as combined
            # type+subtype (e.g. "30") and Benefit as the name
            # (e.g. "PWoC").
            ben_code = f"{rider.benefit_type}{rider.benefit_subtype or ''}"
            ben_name = BENEFIT_TYPE_CODES.get(rider.benefit_type, ben_code)
            rate = self.db.get_benefit_rate(
                rider.plancode, ben_code, ben_name,
                rider.sex, rider.rate_class, band,
                rider.issue_age, year,
            )
            if rate is None:
                # No benefit rate found — try premium rate as fallback
                rate = self.db.get_term_rate(
                    rider.plancode, rider.sex, rider.rate_class,
                    band, rider.issue_age, year,
                )
            if rate is None:
                return rider.fallback_premium
            # PW benefits (types 3/4) apply substandard factor
            if rider.benefit_type in ("3", "4"):
                if rider.benefit_rating_factor and rider.benefit_rating_factor > 0:
                    pw_sub = rider.benefit_rating_factor
                elif rider.table_rating == 1:
                    pw_sub = 1.50
                elif rider.table_rating == 2:
                    pw_sub = 2.25
                else:
                    pw_sub = 1.0
                step1 = arithmetic_round(rate * pw_sub, 2)
                return arithmetic_round(step1 * face_units, 2)
            return arithmetic_round(rate * face_units, 2)

        # Legacy PW/CTR paths
        rate = self.db.get_term_rate(
            rider.plancode, rider.sex, rider.rate_class,
            band, rider.issue_age, year,
        )
        if rate is None:
            logger.warning(
                f"No rider rate found: {rider.plancode} {rider.sex} "
                f"{rider.rate_class} band={band} age={rider.issue_age} yr={year}"
            )
            return rider.fallback_premium

        if rider.rider_type == "PW":
            if rider.table_rating == 1:
                pw_sub = 1.50
            elif rider.table_rating == 2:
                pw_sub = 2.25
            else:
                pw_sub = 1.0
            step1 = arithmetic_round(rate * pw_sub, 2)
            return arithmetic_round(step1 * face_units, 2)

        elif rider.rider_type == "CTR":
            return arithmetic_round(rate * face_units, 2)
            
        elif rider.rider_type == "COVERAGE":
            sub_factor = 1.0 + rider.table_rating * 0.25
            step1 = arithmetic_round(rate * sub_factor, 2)
            return arithmetic_round(step1 * face_units, 2)

        return rider.fallback_premium

    @staticmethod
    def get_plan_description(plan_code: str) -> str:
        """Return human-readable description for a plan code."""
        info = PLAN_CODE_INFO.get(plan_code.upper())
        if info:
            level_period, product = info
            return f"{product} ({level_period}-Year Level)"
        return plan_code
