from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.illustration_policy_service import build_illustration_data


@dataclass
class MonthlyDeductionCheck:
    policy_number: str
    valuation_date: str
    system_md: float
    calculated_md: float
    variance: float
    system_coi: float
    system_expense: float
    system_other: float
    calculated_coi: float
    calculated_epu: float
    calculated_mfee: float
    calculated_av_charge: float
    calculated_benefits: float
    calculated_riders: float
    av_after_deduction: float
    av_before_deduction: float
    av_variance: float


def calculate_last_monthly_deduction_check(
    policy_number: str,
    region: str = "CKPR",
) -> MonthlyDeductionCheck:
    policy = build_illustration_data(policy_number, region=region)
    inforce = IllustrationEngine().project(policy, months=0)[0]
    return MonthlyDeductionCheck(
        policy_number=policy.policy_number,
        valuation_date=str(policy.valuation_date or ""),
        system_md=inforce.system_monthly_deduction,
        calculated_md=inforce.md_check_calculated_deduction,
        variance=inforce.md_check_deduction_variance,
        system_coi=inforce.system_coi_charge,
        system_expense=inforce.system_expense_charge,
        system_other=inforce.system_other_charge,
        calculated_coi=inforce.total_coi_charge,
        calculated_epu=inforce.epu_charge,
        calculated_mfee=inforce.mfee_charge,
        calculated_av_charge=inforce.av_charge,
        calculated_benefits=inforce.benefit_charges,
        calculated_riders=inforce.rider_charges,
        av_after_deduction=inforce.av_after_deduction,
        av_before_deduction=inforce.md_check_av_before_deduction,
        av_variance=inforce.md_check_av_variance,
    )


def calculate_last_monthly_deduction_checks(
    policy_numbers: Iterable[str],
    region: str = "CKPR",
) -> List[MonthlyDeductionCheck]:
    return [
        calculate_last_monthly_deduction_check(policy_number, region=region)
        for policy_number in policy_numbers
    ]