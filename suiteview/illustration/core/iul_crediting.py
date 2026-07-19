"""Engine-side IUL crediting — AG49 asset charge, variable-loan spread, WAIR.

RERUN CalcEngine reference (docs/Illustration_UL/IUL_AG49_WAIR.md and
docs/Illustration_UL/calcengine_map_v20.tsv):

    SS..SX   blended asset charge for the IP/IR multiplier strategies —
             computed and deducted only under AG49 regimes 1-2 (the SX CHOOSE).
    VV       variable-loan accrual rate — MAX(input rate, blended rate − the
             regime's loan credit spread) once AG49 applies (index > 1).
    US..VL   the TAV block: a one-year simplified projection of account value
             (premiums capped by 7702, loan repayments, loan balances) whose
             ONLY purpose is the Weighted Average Interest Rate. The WAIR
             weights the sweep-minimum slice at the declared rate, the loaned
             slice at the loan credit rate, and the remaining (indexed) slice
             at the blend; it is recomputed once per policy year and held
             (VJ carries forward), with the valuation-date row using the
             policy's actual inputs instead (VI).

The AG49 regime resolution itself (CP79 = MAX(2, issue-date tier), CP80 loan
spread CHOOSE) lives in ``models/index_strategies`` — this module only consumes
it via :func:`build_iul_context`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from suiteview.illustration.models.index_strategies import (
    ag49_index_for_issue_date,
    current_ag49_index,
    load_index_strategies,
    loan_credit_spread_for_index,
)


@dataclass(frozen=True)
class IULCreditingContext:
    """Per-run IUL crediting inputs, resolved once in ``project()``.

    ``None`` (no context) means a declared-rate plan — every function in this
    module treats a missing context as "feature off".
    """

    ag49_index: int            # resolved applicable index (CP79 / current regime)
    loan_credit_spread: float  # CP80 CHOOSE(index, 0, 0.01, 0.005, 0.005)
    asset_charge_rate: float   # SU — Σ IP/IR alloc × asset charge; 0 when index > 2
    declared_rate: float       # UJ — fixed/sweep declared crediting rate
    wair_enabled: bool         # sIntCalcMethod = 3 (WAIR replaces the blend credit)
    guaranteed_basis: bool     # sAssumptionCode = 3 → VK caps the WAIR at UK


def build_iul_context(policy, options) -> Optional[IULCreditingContext]:
    """Resolve the run's IUL crediting context, or None for a non-IUL plan.

    Regime resolution (app semantics, per the spec): "Use Policy AG49 Regime"
    unchecked → the current regime (index 4, AG49B); checked → MAX(2, issue-date
    tier) — RERUN CP79 floors at the original AG49 rules even for pre-2015
    issues.
    """
    plan = load_index_strategies(policy.plancode)
    if plan is None:
        return None

    if options.use_policy_ag49_regime:
        ag49_index = ag49_index_for_issue_date(policy.issue_date)
    else:
        ag49_index = current_ag49_index()

    raw_asset_rate = getattr(policy, "iul_asset_charge_rate", None)
    if raw_asset_rate is None:
        raw_asset_rate = _asset_charge_from_allocations(
            plan, getattr(policy, "premium_allocations", None))
    # SU: the blended asset rate is zero outside regimes 1-2.
    asset_charge_rate = float(raw_asset_rate) if ag49_index <= 2 else 0.0

    declared = getattr(policy, "iul_declared_rate", None)
    if declared is None:
        # Fallback: the plan guaranteed rate — the fixed strategy's default
        # illustrated rate. The Inputs tab overrides this with the actual
        # fixed-strategy illustrated rate for a run.
        declared = policy.guaranteed_interest_rate or 0.0

    return IULCreditingContext(
        ag49_index=ag49_index,
        loan_credit_spread=loan_credit_spread_for_index(ag49_index),
        asset_charge_rate=asset_charge_rate,
        declared_rate=float(declared),
        wair_enabled=bool(getattr(options, "iul_wair_crediting", False)),
        guaranteed_basis=bool(getattr(options, "guaranteed_assumption", False)),
    )


def _asset_charge_from_allocations(plan, allocations: Optional[Dict[str, float]]) -> float:
    """Σ IP/IR allocation × asset charge (SU before the regime gate).

    Allocations may arrive in decimal (0.25) or percent (25) form from DB2
    (FND_ALC_PCT scale unverified) — normalize by the total like the
    allocations panel does.
    """
    if not allocations:
        return 0.0
    cleaned = {
        str(fund): float(value)
        for fund, value in allocations.items()
        if value is not None and float(value) > 0.0
    }
    total = sum(cleaned.values())
    if total <= 0.0:
        return 0.0
    scale = 100.0 if total > 1.5 else 1.0
    charge = 0.0
    for strat in plan.strategies:
        alloc = cleaned.get(strat.fund_id, 0.0) / scale
        if alloc > 0.0 and strat.asset_charge > 0.0:
            charge += alloc * strat.asset_charge
    return charge


# ── Asset charge (SS..SX) ─────────────────────────────────────


def monthly_asset_charge(
    ctx: Optional[IULCreditingContext],
    av_before_deduction: float,
    reg_loan_principal: float,
    reg_loan_accrued: float,
) -> float:
    """SV = MAX(0, SU/12 × (OO − MS − MT)) — the monthly blended asset charge.

    OO is the AV before the monthly deduction (after premium/force-out); MS/MT
    are the regular-loan principal and accrued interest AFTER the loan repay —
    the charge base is the unloaned AV. Deducted from AV only under regimes 1-2
    (SX's CHOOSE; SU is already zero above index 2, the gate here is
    belt-and-braces).
    """
    if ctx is None or ctx.ag49_index > 2 or ctx.asset_charge_rate <= 0.0:
        return 0.0
    return max(
        0.0,
        ctx.asset_charge_rate / 12.0
        * (av_before_deduction - reg_loan_principal - reg_loan_accrued),
    )


# ── Variable-loan accrual rate (VV) ───────────────────────────


def variable_loan_accrual_rate(
    ctx: Optional[IULCreditingContext],
    input_rate: Optional[float],
    blended_rate: float,
) -> float:
    """The variable-loan interest accrual rate (RERUN VV).

    Under AG49 (index > 1): MAX(input variable loan rate, blended index rate UO
    − the regime's loan credit spread). Pre-AG49 (index 1) and declared-rate
    plans use the input rate as-is. Note the resolved index is always ≥ 2
    (CP79 floors at AG49), so the spread branch is the live one in practice.
    """
    rate = float(input_rate or 0.0)
    if ctx is None:
        return rate
    if ctx.ag49_index > 1:
        return max(rate, float(blended_rate or 0.0) - ctx.loan_credit_spread)
    return rate


# ── WAIR (US..VL) ─────────────────────────────────────────────


@dataclass(frozen=True)
class TAVProjection:
    """The one-year TAV projection intermediates (UU..VG)."""

    forecast_premium: float   # UV — annualized scheduled premium + lumpsum
    loan_repayment: float     # VC — premium diverted to the loan (ApplyPremToLoan)
    capped_premium: float     # VE — premium capped by the 7702 annual room
    tav: float                # VF — begin AV + net capped premium
    tav_display: float        # VG — MAX(0, VF)


def project_tav(
    *,
    begin_av: float,               # BO — AV post withdrawal at the BOY row
    planned_premium: float,        # vPlannedPremium — per-payment scheduled premium
    payments_per_year: int,        # LT — modal payments in the policy year
    lumpsum: float,                # vLumpsum — unscheduled deposit this month
    policy_month: int,             # E — 1..12 (anniversary = 1)
    fixed_ln_principal: float,     # UW — begin regular(+preferred) loan principal
    fixed_ln_accrued: float,       # UX — begin regular(+preferred) loan accrued
    vbl_ln_principal: float,       # UY — begin variable loan principal
    vbl_ln_accrued: float,         # UZ — begin variable loan accrued
    reg_loan_charge_rate: float,   # sRates_LNCRG
    vbl_loan_rate: float,          # the VV accrual rate (see note below)
    apply_prem_to_loan: bool,      # sInput_ApplyPremToLoan
    is_cvat: bool,                 # sINPUT_Guideline = "CVAT" skips the NK cap
    annual_cap: float,             # NK — Annual Cap1 (guideline/7-pay annual room)
    premium_load: float,           # OG — TPP rate (PolicyRates!AW10)
) -> TAVProjection:
    """One-year TAV projection (RERUN US..VG), computed on beginning-of-year rows.

    Note on VB: RERUN's literal formula projects the variable loan at
    ``MAX(sINPUT_Variable_Loan_Rate, UG12 − 0.01)`` where UG is *Reg Impaired
    Int — a dollar amount*, and 0.01 is the AG49 spread hardcoded. That is a
    workbook bug (UG for UO); the intent is the variable-loan accrual rate, so
    this takes the VV rate (``variable_loan_accrual_rate``) directly.
    """
    uu = float(planned_premium) * float(payments_per_year)
    uv = uu + float(lumpsum)
    year_frac = (13.0 - float(policy_month)) / 12.0
    va = fixed_ln_principal * (1.0 + reg_loan_charge_rate * year_frac) + fixed_ln_accrued
    vb = vbl_ln_principal * (1.0 + vbl_loan_rate * year_frac) + vbl_ln_accrued
    vc = min(uv, va + vb) if apply_prem_to_loan else 0.0
    vd = uv - vc
    ve = max(0.0, vd if is_cvat else min(vd, annual_cap))
    vf = begin_av + ve * (1.0 - premium_load)
    return TAVProjection(
        forecast_premium=uv,
        loan_repayment=vc,
        capped_premium=ve,
        tav=vf,
        tav_display=max(0.0, vf),
    )


def weighted_average_rate(
    *,
    av: float,
    swam: float,
    reg_ln_principal: float,
    reg_ln_accrued: float,
    pref_ln_principal: float = 0.0,
    pref_ln_accrued: float = 0.0,
    reg_loan_credit_rate: float,
    pref_loan_credit_rate: float = 0.0,
    declared_plus_bonus: float,    # UK
    blend_plus_bonus: float,       # UP
) -> float:
    """The three-slice WAIR (RERUN VI on the valuation row, VJ on anniversaries).

        ( MIN(SWAM, AV)·UK
        + fixed loan principal·loan credit rate
        + (AV − fixed principal − fixed accrued − MIN(SWAM, AV))·UP ) / AV

    The sweep-minimum slice earns the declared rate, the loaned slice the loan
    credit rate, and the remaining (indexed) slice the blend — the indexed
    slice may go negative and is deliberately not floored (matches RERUN).
    RERUN's VJ weights only the regular bucket (TY·sRates_LNCRD); preferred
    loans are folded in here at their own credit rate — identical on plans
    without preferred loans.
    """
    if av <= 0.0:
        return 0.0
    sweep_slice = min(swam, av)
    loaned_credit = (
        reg_ln_principal * reg_loan_credit_rate
        + pref_ln_principal * pref_loan_credit_rate
    )
    indexed_slice = av - (
        reg_ln_principal + reg_ln_accrued + pref_ln_principal + pref_ln_accrued
    ) - sweep_slice
    return (
        sweep_slice * declared_plus_bonus
        + loaned_credit
        + indexed_slice * blend_plus_bonus
    ) / av


def cap_wair(ctx: IULCreditingContext, wair: float, declared_plus_bonus: float) -> float:
    """VK — the guaranteed-basis run caps the WAIR at the declared rate + bonus."""
    if ctx.guaranteed_basis:
        return min(wair, declared_plus_bonus)
    return wair


def wair_interest(av: float, wair: float, days: float) -> float:
    """VL = MAX(0, vAV × ((1 + vWAIR)^(days/365) − 1)) — the WAIR interest credit.

    Replaces the blended-rate credit entirely (RERUN VO CHOOSE method 3): the
    loaned/unloaned split is already inside the WAIR weighting, so there is no
    separate impaired interest.
    """
    return max(0.0, av * ((1.0 + wair) ** (days / 365.0) - 1.0))
