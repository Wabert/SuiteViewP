"""
ABR Quote — Actuarial Present Value (APV) Engine.

Computes PVFB (Present Value of Future Benefits) and PVFP (Present Value
of Future Premiums) using a monthly cash-flow projection.

Replicates the "ABA monthly calc." sheet from the ABR Quote workbook.

Key formulas:
    monthly_rate = (1 + annual_rate)^(1/12) - 1
    continuous_mort_adj = monthly_rate / ln(1 + monthly_rate)
    PVFB = Σ(face/1000 × q'x × tp'x × v^(t+1)) × cont_adj × 1000
    PVFP = Σ(prem_rate × v^t × tp'x)  [at year boundaries only]
    Actuarial_Discount = Face - (PVFB - PVFP)
"""

from __future__ import annotations

import logging
import math
from typing import List

from ..models.abr_data import ABRPolicyData, APVResult

logger = logging.getLogger(__name__)


class APVEngine:
    """Compute Actuarial Present Value of future benefits and premiums.

    Usage:
        engine = APVEngine(annual_interest_rate=0.0545, policy_data=policy)
        result = engine.compute(monthly_qx, premium_schedule)
    """

    def __init__(self, annual_interest_rate: float, policy_data: ABRPolicyData):
        self.annual_rate = annual_interest_rate
        self.policy = policy_data

        # Monthly interest rate: (1 + i)^(1/12) - 1
        self.monthly_rate = (1.0 + annual_interest_rate) ** (1.0 / 12.0) - 1.0

        # Continuous mortality adjustment factor
        # = monthly_rate / ln(1 + monthly_rate)
        if self.monthly_rate > 0:
            self.cont_mort_adj = self.monthly_rate / math.log(1.0 + self.monthly_rate)
        else:
            self.cont_mort_adj = 1.0

    def compute(
        self,
        monthly_qx: List[float],
        premium_schedule: List[float],
        is_terminal: bool = True,
    ) -> APVResult:
        """Compute PVFB, PVFP, and actuarial discount.

        Delegates to compute_detailed_table() — the single source of truth
        for the APV calculation pipeline — and extracts the summary values.

        Args:
            monthly_qx: Monthly mortality rates from MortalityEngine.
                         Index 0 = first month from current policy month.
            premium_schedule: Annual premium rates per $1,000 for each
                              policy year (list of up to 82 values).
            is_terminal: If True and state is FL, set PVFP=0.

        Returns:
            APVResult with PVFB, PVFP, and actuarial discount.
        """
        _rows, summary = self.compute_detailed_table(
            monthly_qx, premium_schedule, is_terminal,
        )

        return APVResult(
            pvfb=round(summary["pvfb_adjusted"], 6),
            pvfp=round(summary["pvfp"], 6),
            pvfd=0.0,
            actuarial_discount=summary["actuarial_discount"],
            monthly_interest_rate=self.monthly_rate,
            continuous_mort_adj=self.cont_mort_adj,
            annual_interest_rate=self.annual_rate,
        )

    def compute_detailed_table(
        self,
        monthly_qx: List[float],
        premium_schedule: List[float],
        is_terminal: bool = True,
    ) -> list[dict]:
        """Compute APV with ALL intermediate values exposed per month.

        Returns a list of dicts (one per month) with keys:
            month           – absolute policy month
            t               – 0-based time index
            qx_monthly      – monthly mortality rate
            px_monthly      – monthly survival = 1 - qx
            tp_x            – cumulative survival at START of month
            v_benefit       – discount factor for benefit v^(t+1)
            v_premium       – discount factor for premium v^t
            pvdb_t          – PV of death benefit this month (before adj)
            pvdb_cum        – running PVFB subtotal (before cont_adj × 1000)
            prem_rate       – premium rate applied (0 if not year boundary)
            pvfp_t          – PV of premium this month
            pvfp_cum        – running PVFP subtotal
            tp_x_end        – cumulative survival at END of month
        """
        p = self.policy
        face_units = p.face_amount / 1000.0
        # Convert month-within-year to absolute policy month since issue
        current_month = (p.policy_year - 1) * 12 + p.policy_month
        maturity_duration = (p.maturity_age - p.issue_age) * 12

        rows: list[dict] = []
        pvfb_cum = 0.0
        pvfp_cum = 0.0
        tp_x = 1.0

        for t in range(len(monthly_qx)):
            abs_month = current_month + t
            if abs_month > maturity_duration:
                break

            qx = monthly_qx[t]
            px = 1.0 - qx

            # Discount factors
            v_benefit = 1.0 / (1.0 + self.monthly_rate) ** (t + 1)
            v_premium = 1.0 / (1.0 + self.monthly_rate) ** t if t > 0 else 1.0

            # PVDB component
            pvdb_t = face_units * qx * tp_x * v_benefit
            pvfb_cum += pvdb_t

            # PVFP component
            # Premium is applied at t=0 and on each subsequent policy
            # anniversary month.  The premium_schedule should already
            # contain the properly prorated first-year value (matching
            # the Future Premiums for Acceleration table).
            prem_rate = 0.0
            pvfp_t = 0.0
            if t == 0 or (abs_month - 1) % 12 == 0:
                year_idx = (abs_month - 1) // 12
                if year_idx < len(premium_schedule):
                    prem_rate = premium_schedule[year_idx]
                    pvfp_t = prem_rate * v_premium * tp_x
                    pvfp_cum += pvfp_t

            tp_x_end = tp_x * px

            rows.append({
                "month": abs_month,
                "t": t,
                "qx_monthly": qx,
                "px_monthly": px,
                "tp_x": tp_x,
                "v_benefit": v_benefit,
                "v_premium": v_premium,
                "pvdb_t": pvdb_t,
                "pvdb_cum": pvfb_cum,
                "prem_rate": prem_rate,
                "pvfp_t": pvfp_t,
                "pvfp_cum": pvfp_cum,
                "tp_x_end": tp_x_end,
            })

            tp_x = tp_x_end

        # Add summary row info
        pvfb_final = pvfb_cum * self.cont_mort_adj * 1000.0
        is_fl_terminal = p.issue_state.upper() == "FL" and is_terminal
        pvfp_final = 0.0 if is_fl_terminal else pvfp_cum

        return rows, {
            "pvfb_raw": pvfb_cum,
            "cont_mort_adj": self.cont_mort_adj,
            "pvfb_adjusted": pvfb_final,
            "pvfp": pvfp_final,
            "actuarial_discount": round(p.face_amount - (pvfb_final - pvfp_final), 2),
            "monthly_rate": self.monthly_rate,
            "annual_rate": self.annual_rate,
        }

    def compute_full_acceleration(
        self,
        admin_fee: float,
        apv_summary: dict,
    ) -> dict:
        """Compute full accelerated benefit.

        Args:
            admin_fee: Administrative fee to deduct.
            apv_summary: Summary dict from compute_detailed_table().

        Returns dict with:
            eligible_db, actuarial_discount, admin_fee,
            accelerated_benefit, benefit_ratio
        """
        face = self.policy.face_amount
        actuarial_discount = apv_summary["actuarial_discount"]

        accel_benefit = round(face - actuarial_discount - admin_fee, 2)
        benefit_ratio = accel_benefit / face if face > 0 else 0.0

        return {
            "eligible_db": face,
            "actuarial_discount": actuarial_discount,
            "admin_fee": admin_fee,
            "accelerated_benefit": accel_benefit,
            "benefit_ratio": round(benefit_ratio, 6),
        }

    def compute_partial_acceleration(
        self,
        full_result: dict,
        min_face: float = 50_000.0,
        admin_fee: float = 250.0,
    ) -> dict:
        """Compute max partial accelerated benefit.

        Partial acceleration = Face - MinFace, with proportional discount.

        Args:
            full_result: Dict from compute_full_acceleration().
            min_face: Minimum remaining face amount ($50,000 default).
            admin_fee: Administrative fee (same as full).

        Returns dict with partial acceleration values.
        """
        face = self.policy.face_amount
        eligible_partial = face - min_face

        if eligible_partial <= 0:
            return {
                "eligible_db": 0.0,
                "actuarial_discount": 0.0,
                "admin_fee": admin_fee,
                "accelerated_benefit": 0.0,
                "benefit_ratio": 0.0,
            }

        # Proportional discount
        full_eligible = full_result["eligible_db"]
        full_discount = full_result["actuarial_discount"]

        if full_eligible > 0:
            partial_discount = round(
                (eligible_partial / full_eligible) * full_discount, 2
            )
        else:
            partial_discount = 0.0

        accel_benefit = round(eligible_partial - partial_discount - admin_fee, 2)
        benefit_ratio = accel_benefit / eligible_partial if eligible_partial > 0 else 0.0

        return {
            "eligible_db": eligible_partial,
            "actuarial_discount": partial_discount,
            "admin_fee": admin_fee,
            "accelerated_benefit": accel_benefit,
            "benefit_ratio": round(benefit_ratio, 6),
        }
