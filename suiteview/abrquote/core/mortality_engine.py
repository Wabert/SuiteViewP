"""
ABR Quote — Mortality Engine (calc.monthly equivalent).

Computes monthly mortality rates using:
    1. 2008 VBT Select lookup (per 1,000)
    2. Mortality improvement adjustment
    3. Table rating multiplication
    4. Flat extra addition
    5. Uniform Distribution of Deaths (UDD) monthly conversion

Replicates the "calc.monthly" sheet from the ABR Quote workbook.
"""

from __future__ import annotations

import logging
from typing import List

from ..models.abr_constants import MAX_DURATION_YEARS, get_vbt_block
from ..models.abr_data import MortalityParams
from ..models.abr_database import get_abr_database


logger = logging.getLogger(__name__)


class MortalityEngine:
    """Compute monthly mortality rates replicating calc.monthly sheet.

    Usage:
        params = MortalityParams(issue_age=33, sex="F", rate_class="N", ...)
        engine = MortalityEngine(params)
        monthly_rates = engine.compute_monthly_rates()
    """

    def __init__(self, params: MortalityParams):
        self.params = params
        self._vbt_block = get_vbt_block(params.sex, params.rate_class)
        self._get_qx = get_abr_database().get_vbt_qx

    def compute_monthly_rates(self) -> List[float]:
        """Compute monthly qx for all months from current to maturity.

        Delegates to compute_detailed_table() — the single source of truth
        for the mortality calculation pipeline — and extracts just the
        monthly qx values.

        Returns:
            List of monthly qx values. Length = (maturity_age - issue_age) * 12
            minus (policy_month - 1). Each value is the probability of death
            in that month, range [0, 1].
        """
        detail = self.compute_detailed_table()
        return [row["qx_monthly"] for row in detail]

    def compute_life_expectancy(self) -> float:
        """Compute curtate future life expectancy + 0.5 (UDD complete LE).

        Uses the full monthly mortality schedule to compute the expected
        remaining lifetime from the current policy month.

        Returns:
            Complete life expectancy in years.
        """
        monthly_rates = self.compute_monthly_rates()
        if not monthly_rates:
            return 0.0

        # Curtate LE = sum of t_px for each year
        # We sum monthly survival, then convert
        tp_x = 1.0
        life_months = 0.0

        for qx_m in monthly_rates:
            px_m = 1.0 - qx_m
            tp_x *= px_m
            life_months += tp_x

        # Convert to years and add 0.5 for complete LE (UDD approximation)
        curtate_le_years = life_months / 12.0
        return curtate_le_years + 0.5

    def compute_survival_probability(self, years: int) -> float:
        """Compute probability of surviving exactly `years` years from now.

        Args:
            years: Number of years to compute survival for.

        Returns:
            Probability of surviving to end of `years`, range [0, 1].
        """
        monthly_rates = self.compute_monthly_rates()
        months = years * 12
        if months > len(monthly_rates):
            months = len(monthly_rates)

        tp_x = 1.0
        for t in range(months):
            tp_x *= (1.0 - monthly_rates[t])

        return tp_x

    # ── Private helpers ─────────────────────────────────────────────────

    def _apply_multiplier(self, qx: float) -> float:
        """Apply mortality multiplier to VBT rate.

        For Chronic/Critical riders this is 75% (MORTALITY_MULTIPLIER);
        for Terminal riders this is 100% (MORTALITY_MULTIPLIER_TERMINAL).

        Formula:  qx_multiplied = qx_vbt × mortality_multiplier
        """
        return qx * self.params.mortality_multiplier

    def _apply_improvement(self, qx: float, attained_age: int) -> float:
        """Apply compounding mortality improvement factor.

        Formula:  qx_improved = qx × (1 - MI%)^(min(cap, att_age) - starting_att_age)

        Where starting_att_age is the attained age at the quote effective date
        (i.e. $H$2 in the workbook), NOT the original issue age.
        The exponent is effectively the number of years from the quote date.
        """
        p = self.params
        if p.improvement_rate == 0:
            return qx

        starting_att_age = p.issue_age + ((p.policy_month - 1) // 12)
        exponent = min(p.improvement_cap, attained_age) - starting_att_age
        if exponent > 0:
            improvement_factor = (1.0 - p.improvement_rate) ** exponent
            return qx * improvement_factor

        return qx

    def _apply_table_rating(self, qx: float, abs_month: int) -> tuple[float, float]:
        """Apply table rating multiplier within applicable month ranges.

        Table rating formula: qx_rated = qx × (1 + table_rating × 0.25)
        Applied only within the specified month range for each table period.

        Returns:
            (qx_after_table, effective_table_rating)
        """
        p = self.params
        effective_rating = 0.0

        # Table rating period 1
        if (p.table_rating_1 > 0
                and p.table_1_start_month <= abs_month <= p.table_1_last_month):
            factor = 1.0 + p.table_rating_1 * 0.25
            qx = min(1.0, qx * factor)
            effective_rating += p.table_rating_1

        # Table rating period 2 (for mid-policy rating changes)
        if (p.table_rating_2 > 0
                and p.table_2_start_month <= abs_month <= p.table_2_last_month):
            factor = 1.0 + p.table_rating_2 * 0.25
            qx = min(1.0, qx * factor)
            effective_rating += p.table_rating_2

        # Additional table periods (from direct user inputs)
        for rating, start_m, last_m in p.additional_tables:
            if rating > 0 and start_m <= abs_month <= last_m:
                factor = 1.0 + rating * 0.25
                qx = min(1.0, qx * factor)
                effective_rating += rating

        return qx, effective_rating

    def _apply_flat_extra(self, qx: float, abs_month: int,
                          duration_year: int) -> tuple[float, float]:
        """Apply flat extra mortality addition.

        Flat extra is per $1,000 per year, added to annual qx.
        Applied only within the applicable duration.

        Returns:
            (qx_after_flat, effective_flat_per_1000)
        """
        p = self.params
        effective_flat = 0.0

        # Flat extra period 1
        if p.flat_extra_1 > 0 and p.flat_1_start_month <= abs_month <= p.flat_1_duration:
            qx = min(1.0, qx + p.flat_extra_1 / 1000.0)
            effective_flat += p.flat_extra_1

        # Flat extra period 2
        if p.flat_extra_2 > 0 and abs_month <= p.flat_2_duration:
            qx = min(1.0, qx + p.flat_extra_2 / 1000.0)
            effective_flat += p.flat_extra_2

        # Additional flat extras (from direct user inputs)
        for flat_amt, start_m, last_m in p.additional_flats:
            if flat_amt > 0 and start_m <= abs_month <= last_m:
                qx = min(1.0, qx + flat_amt / 1000.0)
                effective_flat += flat_amt

        return qx, effective_flat

    def compute_detailed_table(self) -> list[dict]:
        """Compute monthly mortality with ALL intermediate values exposed.

        Returns a list of dicts (one per month) with keys:
            month               – absolute policy month
            duration_year       – policy year (1-based)
            month_in_year       – month within year (1-12)
            attained_age        – issue_age + duration_year - 1
            qx_vbt              – raw VBT lookup (decimal)
            qx_multiplied       – after mortality multiplier (e.g. ×75%)
            qx_improved         – after mortality improvement
            qx_table_rated      – after table rating
            qx_flat_extra       – after flat extra (final annual qx)
            qx_capped           – after cap at [0, 1]
            qx_monthly          – UDD monthly qx
            px_monthly          – monthly survival = 1 - qx_monthly
            cum_survival        – cumulative survival to end of this month
            table_rating_applied – effective table rating for this month
            flat_extra_applied   – effective flat extra ($/1000) for this month
        """
        p = self.params
        total_months = (p.maturity_age - p.issue_age) * 12
        start_month = p.policy_month

        rows: list[dict] = []
        cum_survival = 1.0

        # Fixed starting attained age for VBT lookup and improvement
        # (equivalent to $H$2 in the Excel workbook)
        starting_att_age = p.issue_age + ((p.policy_month - 1) // 12)

        # Starting duration year (equivalent to $B$7 in Excel)
        starting_duration_year = (p.policy_month - 1) // 12 + 1

        for t in range(total_months - start_month + 1):
            abs_month = start_month + t
            quote_month = t + 1  # 1-based from quote effective date
            duration_year = (abs_month - 1) // 12 + 1
            month_in_year = ((abs_month - 1) % 12) + 1
            attained_age = p.issue_age + duration_year - 1

            # ── Terminal Illness shortcut ────────────────────────────────
            # When Terminal is selected, mortality is a flat 50% per year.
            # No VBT lookup, no improvement, no table rating, no flat extra.
            if p.is_terminal:
                qx_annual = 0.5
                qx_monthly = self._udd_monthly(qx_annual, month_in_year)
                qx_monthly = min(1.0, max(0.0, qx_monthly))
                px_monthly = 1.0 - qx_monthly
                cum_survival *= px_monthly
                rows.append({
                    "quote_month": quote_month,
                    "month": abs_month,
                    "duration_year": duration_year,
                    "month_in_year": month_in_year,
                    "attained_age": attained_age,
                    "qx_vbt": qx_annual,
                    "qx_multiplied": qx_annual,
                    "qx_improved": qx_annual,
                    "qx_table_rated": qx_annual,
                    "qx_flat_extra": qx_annual,
                    "qx_capped": qx_annual,
                    "qx_monthly": qx_monthly,
                    "px_monthly": px_monthly,
                    "cum_survival": cum_survival,
                    "table_rating_applied": 0.0,
                    "flat_extra_applied": 0.0,
                })
                continue

            # VBT select table lookup:
            #   Excel: OFFSET(vFN_Mortality, E - $B$7, $H$2)
            #   Row offset = policy_year - starting_policy_year = 0-based duration
            #   Column = starting attained age (fixed)
            # So VBT duration = duration_year - starting_duration_year + 1 (1-based)
            vbt_duration = duration_year - starting_duration_year + 1

            if duration_year > MAX_DURATION_YEARS:
                rows.append({
                    "quote_month": quote_month,
                    "month": abs_month, "duration_year": duration_year,
                    "month_in_year": month_in_year, "attained_age": attained_age,
                    "qx_vbt": 1.0, "qx_improved": 1.0, "qx_multiplied": 1.0,
                    "qx_table_rated": 1.0, "qx_flat_extra": 1.0,
                    "qx_capped": 1.0, "qx_monthly": 1.0,
                    "px_monthly": 0.0, "cum_survival": 0.0,
                    "table_rating_applied": 0.0, "flat_extra_applied": 0.0,
                })
                cum_survival = 0.0
                continue

            # Step 1: VBT lookup — FIXED starting_att_age + increasing vbt_duration
            qx_per_1000 = self._get_qx(self._vbt_block, starting_att_age, vbt_duration)
            if qx_per_1000 is None:
                rows.append({
                    "quote_month": quote_month,
                    "month": abs_month, "duration_year": duration_year,
                    "month_in_year": month_in_year, "attained_age": attained_age,
                    "qx_vbt": 1.0, "qx_improved": 1.0, "qx_multiplied": 1.0,
                    "qx_table_rated": 1.0, "qx_flat_extra": 1.0,
                    "qx_capped": 1.0, "qx_monthly": 1.0,
                    "px_monthly": 0.0, "cum_survival": 0.0,
                    "table_rating_applied": 0.0, "flat_extra_applied": 0.0,
                })
                cum_survival = 0.0
                continue

            qx_vbt = qx_per_1000 / 1000.0

            # Step 2: Mortality multiplier (75% for Chronic/Critical, 100% for Terminal)
            qx_multiplied = self._apply_multiplier(qx_vbt)

            # Step 3: Mortality improvement — (1 - MI%)^(years from quote date)
            qx_improved = self._apply_improvement(qx_multiplied, attained_age)

            # Step 4: Table rating
            qx_table_rated, eff_table = self._apply_table_rating(qx_improved, abs_month)

            # Step 5: Flat extra
            qx_flat_extra, eff_flat = self._apply_flat_extra(qx_table_rated, abs_month, duration_year)

            # Cap
            qx_capped = min(1.0, max(0.0, qx_flat_extra))

            # Step 6: UDD monthly
            qx_monthly = self._udd_monthly(qx_capped, month_in_year)
            qx_monthly = min(1.0, max(0.0, qx_monthly))

            px_monthly = 1.0 - qx_monthly
            cum_survival *= px_monthly

            rows.append({
                "quote_month": quote_month,
                "month": abs_month,
                "duration_year": duration_year,
                "month_in_year": month_in_year,
                "attained_age": attained_age,
                "qx_vbt": qx_vbt,
                "qx_multiplied": qx_multiplied,
                "qx_improved": qx_improved,
                "qx_table_rated": qx_table_rated,
                "qx_flat_extra": qx_flat_extra,
                "qx_capped": qx_capped,
                "qx_monthly": qx_monthly,
                "px_monthly": px_monthly,
                "cum_survival": cum_survival,
                "table_rating_applied": eff_table,
                "flat_extra_applied": eff_flat,
            })

        return rows

    @staticmethod
    def _udd_monthly(qx_annual: float, month_in_year: int) -> float:
        """Uniform Distribution of Deaths: convert annual qx to monthly.

        Formula: qx_monthly = (qx/12) / (1 - (m-1) × (qx/12))
        where m is the month within the policy year (1-12).

        This assumes deaths are uniformly distributed within each year,
        then derives the conditional monthly probability.
        """
        if qx_annual >= 1.0:
            return 1.0
        if qx_annual <= 0.0:
            return 0.0

        frac = qx_annual / 12.0
        denominator = 1.0 - (month_in_year - 1) * frac

        if denominator <= 0:
            return 1.0

        result = frac / denominator
        return min(1.0, result)
