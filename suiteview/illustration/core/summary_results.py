"""Authoritative Values > Summary projection rows.

The UI and regression runner both consume this module so displayed values and
stored regression expectations cannot drift apart.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Iterable

from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.policy_data import IllustrationPolicyData

SUMMARY_SCHEMA_VERSION = 3
LEAD_COLUMNS = ("Date", "Year", "Month", "Attained Age")
SHADOW_SUMMARY_COLUMNS = (
    "vShadow_TP", "Shadow COI", "Shadow EPU", "Rider Charges",
    "Shadow MD", "Shadow Int Rate", "vShadowEAV",
)
SUMMARY_COLUMNS = (
    "GrossWD", "DBO", "TotalSA", "PSC", "MonthlyMTP", "Accum MTP",
    "GLP", "GSP", "AccumGLP", "ForceOut", "Loan_Accr_Int", "Loan_Princ",
    "Loan Repay", "Premium", "PremTD", "Prem Load", "mAV", "NAAR",
    "Base COI", "Rider COI", "Benefit COI", "EPU", "MFEE", "MD",
    "Exception Prem", "AV", "New Loan", "Interest Rate", "Interest",
    "EAV", "SC", "ESV", "Var Loan", "Pref Loan", "Reg Loan",
    "Ending LB", "IllustratedDB",
) + SHADOW_SUMMARY_COLUMNS
ALL_COLUMNS = LEAD_COLUMNS + SUMMARY_COLUMNS


def _detail_float(mapping: dict, key: str) -> float:
    value = mapping.get(key, 0.0)
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _partial_surrender_charge(state: MonthlyState) -> float:
    return (
        state.wd_partial_sc
        + _detail_float(state.dbo_change_detail, "Total PSC DBO")
        + _detail_float(state.face_change_detail, "Total PSC Spec Dec")
    )


def _total_specified_amount(
    policy: IllustrationPolicyData,
    state: MonthlyState,
) -> float:
    for mapping, key in (
        (state.coverage_after_change, "CurrentSA"),
        (state.face_change_detail, "Total SA"),
        (state.dbo_change_detail, "Total SA"),
    ):
        value = mapping.get(key)
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    return float(policy.total_face or 0.0)


def _av_before_monthly_deduction(state: MonthlyState) -> float:
    return state.md_check_av_before_deduction or state.av_after_premium


def summary_values(
    policy: IllustrationPolicyData,
    state: MonthlyState,
) -> dict:
    """Return the Summary values for one monthly state."""
    return {
        "GrossWD": state.gross_withdrawal,
        "DBO": str(
            state.db_option
            or state.dbo_change_detail.get("DBO")
            or policy.db_option
            or ""
        ).upper(),
        "TotalSA": _total_specified_amount(policy, state),
        "PSC": _partial_surrender_charge(state),
        "MonthlyMTP": state.monthly_mtp,
        "Accum MTP": state.accumulated_mtp,
        "GLP": state.glp,
        "GSP": state.gsp,
        "AccumGLP": state.accumulated_glp,
        "ForceOut": state.guideline_forceout,
        "Loan_Accr_Int": (
            state.rg_loan_accrued + state.pf_loan_accrued
            + state.vbl_loan_accrued
        ),
        "Loan_Princ": (
            state.rg_loan_princ + state.pf_loan_princ + state.vbl_loan_princ
        ),
        "Loan Repay": state.applied_loan_repayment,
        "Premium": state.gross_premium,
        "PremTD": state.premiums_to_date,
        "Prem Load": state.total_premium_load,
        "mAV": _av_before_monthly_deduction(state),
        "NAAR": state.total_nar or state.nar,
        "Base COI": state.total_coi_charge or state.coi_charge,
        "Rider COI": state.rider_charges,
        "Benefit COI": state.benefit_charges,
        "EPU": state.epu_charge,
        "MFEE": state.mfee_charge,
        "MD": state.total_deduction,
        "Exception Prem": state.gp_exception_prem,
        "AV": state.av_after_exception,
        "New Loan": state.applied_new_loan,
        "Interest Rate": state.effective_annual_rate,
        "Interest": state.interest_credited,
        "EAV": state.av_end_of_month,
        "SC": state.surrender_charge,
        "ESV": state.ending_sv,
        "Var Loan": state.end_vbl_loan_princ + state.end_vbl_loan_accrued,
        "Pref Loan": state.end_pf_loan_princ + state.end_pf_loan_accrued,
        "Reg Loan": state.end_rg_loan_princ + state.end_rg_loan_accrued,
        "Ending LB": state.policy_debt,
        "IllustratedDB": state.ending_db or state.gross_db,
        "vShadow_TP": state.shadow_target_prem,
        "Shadow COI": state.shadow_coi,
        "Shadow EPU": state.shadow_epu,
        "Rider Charges": state.shadow_rider_charges,
        "Shadow MD": state.shadow_md,
        "Shadow Int Rate": state.shadow_int_rate,
        "vShadowEAV": state.shadow_eav,
    }


def project_summary_row(
    policy: IllustrationPolicyData,
    state: MonthlyState,
) -> dict:
    """Return one typed locator-plus-Summary row, rejecting invalid numbers."""
    row = {
        "Date": state.date,
        "Year": state.policy_year,
        "Month": state.policy_month,
        "Attained Age": state.attained_age,
    }
    row.update(summary_values(policy, state))
    for column, value in row.items():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(
                f"Summary row {state.date} column {column} is not finite: {value}")
    return row


def project_summary_rows(
    policy: IllustrationPolicyData,
    results: Iterable[MonthlyState],
) -> list[dict]:
    return [project_summary_row(policy, state) for state in results]


def json_safe_rows(rows: Iterable[dict]) -> list[dict]:
    """Convert typed Summary rows to strict JSON-compatible values."""
    encoded = []
    for row in rows:
        item = {}
        for column in ALL_COLUMNS:
            value = row[column]
            item[column] = value.isoformat() if isinstance(value, date) else value
        encoded.append(item)
    return encoded
