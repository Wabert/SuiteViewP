"""View-model shaping for the PolView Targets & Accumulators tab."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from suiteview.polview.models.policy_sections.lookup import policy_attr

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TargetsViewModel:
    doli_data: dict[str, Any]
    accum_data: dict[str, Any]
    tamra_period: dict[str, Any]
    tamra_years: list[dict[str, Any]]
    commission_targets: list[dict[str, Any]]
    policy_targets: list[dict[str, Any]]
    coverages: list[dict[str, Any]]
    renewal_rates: list[dict[str, Any]]
    is_advanced: bool
    commission_unavailable: bool
    minimum_premium_unavailable: bool


def guaranteed_cash_value(policy) -> dict[str, Any]:
    """Return a cache-safe GCV payload with a visible reason on calculation failure."""
    try:
        return policy.rates.guaranteed_cash_value()
    except (ValueError, TypeError, ArithmeticError) as exc:
        logger.warning(
            "Guaranteed cash value not calculated for %s: %s",
            policy.policy_number,
            exc,
            exc_info=True,
        )
        return {"value": None, "details": [], "reason": f"Not calculated: {exc}"}


def _doli_data(policy, is_advanced: bool) -> dict[str, Any]:
    if not is_advanced:
        return {"is_advanced": False}

    gsp_val = policy.targets.gsp
    glp_val = policy.targets.glp
    accum_glp_val = policy.targets.accumulated_glp_target
    corr_pct = policy.product.corridor_percent
    corr_pct_display = ""
    if corr_pct is not None:
        try:
            corr_pct_display = f"{float(corr_pct) / 100:.2f}"
        except Exception:
            corr_pct_display = str(corr_pct)

    prem_pay_years = ""
    max_annual = None
    min_qual_glp = None
    gpt_cvat = policy.product.gpt_cvat

    if gpt_cvat in ("GP", "GPT"):
        try:
            status_code = int(policy.status.status_code or "99")
            val_date = policy.values.valuation_date
            if (status_code < 97 and val_date is not None
                    and accum_glp_val is not None and glp_val is not None
                    and str(accum_glp_val) != "Null" and str(glp_val) != "Null"):
                age_at_mat = policy.coverages.age_at_maturity
                att_age = policy.coverages.attained_age
                if age_at_mat is not None and att_age is not None:
                    ins_def_mat_age = min(100, age_at_mat)
                    prem_pay_yrs = max(0, ins_def_mat_age - att_age - 1)
                    prem_pay_years = str(prem_pay_yrs)
                    accum_glp_at_mat = float(glp_val) * prem_pay_yrs + float(accum_glp_val)
                    premium_td_f = float(policy.billing.premium_td)
                    accum_wds_f = float(policy.values.total_withdrawals)
                    if prem_pay_yrs > 0:
                        max_annual = (accum_glp_at_mat - (premium_td_f - accum_wds_f)) / prem_pay_yrs
                        min_qual = -(float(accum_glp_val) - (premium_td_f - accum_wds_f)) / prem_pay_yrs
                        if min_qual < 0:
                            min_qual_glp = min_qual
                    else:
                        max_annual = 0
        except Exception:
            pass

    return {
        "is_advanced": True,
        "tefra_defra": policy.product.tefra_defra,
        "gpt_cvat": gpt_cvat,
        "gsp": gsp_val,
        "glp": glp_val,
        "accum_glp": accum_glp_val,
        "corr_pct": corr_pct_display,
        "prem_pay_years": prem_pay_years,
        "max_annual_level_qual_prem": max_annual,
        "min_qualifying_glp": min_qual_glp,
        "base_nsp": policy.targets.nsp_base,
        "other_nsp": policy.targets.nsp_other,
    }


def _prem_allowed_gpt(policy, is_advanced: bool):
    is_cvat = (not is_advanced) or str(policy.product.gpt_cvat).upper() not in ("GP", "GPT")
    if is_cvat:
        return "N/A"
    try:
        guideline_limit = max(float(policy.targets.gsp or 0), float(policy.targets.accumulated_glp_target or 0))
        return max(0.0, guideline_limit - float(policy.billing.premium_td or 0) + float(policy.values.total_withdrawals or 0))
    except Exception:
        return "N/A"


def build_targets_view_model(policy) -> TargetsViewModel:
    """Collect policy data for TargetsTab without touching widgets."""
    rules = policy_attr(policy, "product_rules", None)
    is_advanced = bool(rules.is_advanced if rules is not None else policy.product.is_advanced_product)
    reg_prem = float(policy.billing.total_regular_premium or 0)
    add_prem = float(policy.billing.total_additional_premium or 0)
    prem_ytd = float(policy.billing.premium_ytd or 0)
    cost_basis_val = float(policy.values.cost_basis or 0) if policy.values.policy_totals_count > 0 else None
    accum_wds_val = float(policy.values.total_withdrawals or 0) if policy.values.policy_totals_count > 0 else None
    tamra_per_rows = policy.fetch_table("LH_TAMRA_7_PY_PER")
    com_targets = policy.fetch_table("LH_COM_TARGET")
    pol_targets = policy.fetch_table("LH_POL_TARGET")
    return TargetsViewModel(
        doli_data=_doli_data(policy, is_advanced),
        accum_data={
            "premiums_paid": reg_prem + add_prem,
            "reg_prem": reg_prem,
            "additional_prem": add_prem,
            "prem_ytd": prem_ytd,
            "cost_basis": cost_basis_val,
            "accum_wds": accum_wds_val,
            "prem_allowed_gpt": _prem_allowed_gpt(policy, is_advanced),
            "gcv": guaranteed_cash_value(policy),
        },
        tamra_period=tamra_per_rows[0] if tamra_per_rows else {},
        tamra_years=policy.fetch_table("LH_TAMRA_7_PY_YR"),
        commission_targets=com_targets,
        policy_targets=pol_targets,
        coverages=policy.fetch_table("LH_COV_PHA"),
        renewal_rates=policy.fetch_table("LH_COV_INS_RNL_RT"),
        is_advanced=is_advanced,
        commission_unavailable=is_advanced and len(com_targets) == 0,
        minimum_premium_unavailable=is_advanced and len(pol_targets) == 0,
    )
