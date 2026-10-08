"""Withdrawal processing — RERUN CalcEngine cols AX..BU.

Computes one month's withdrawal WITHOUT mutating the policy: the engine applies
the resulting face decrease itself (after capturing the before-change guideline
solve), exactly as it does for an elective face decrease.

Mechanics (per the workbook formulas):
    AY  Max Net Allowed = MAX(0, MIN(CSV - holdback*priorMD - fee,
                                     SA - (minFace + fee) if DBO "A" else request))
        where CSV = AV - full surrender charge - policy debt.
    BA  Applied net withdrawal = MIN(request, max net).
    BG  Corridor amount = MAX(0, corridorRate*AV - total SA) — the slice of the
        death benefit driven by the corridor; an AV drop lowers it for free.
        ISWL plans use the whole-dollar (rounded) corridor DB.
    BH  The withdrawal reduces SA only under DBO "A" and only past the corridor.
    BM  Partial surrender charge: the NET amount allocated newest-coverage-first
        x each coverage's SCR/1000 (plancode-gated, sbln_PSC).
    BN  Gross withdrawal = net + (PSC if SA reduces) + fee.
    BP  Face decrease = GROSS (fee excluded only on an OriginalSA target basis);
        allocated newest-first by the caller (no extra SCR charge — the PSC is
        already inside the gross).
    BD/BE  Withdrawals to-date / YTD accumulate the NET amount.
    BC  Cost basis reduces by the NET amount.

Input basis (SuiteView extension — RERUN's vINPUT_Withdrawal is net-only):
    The inputs UI lets a withdrawal be entered Net (the client receives the
    amount; matches RERUN AX directly) or Gross (the amount is what leaves the
    account value, i.e. RERUN BN). A gross request is inverted to the net
    request the AX..BU chain consumes: net = gross - fee - PSC, with the PSC
    term found by a short fixed-point iteration (see _net_from_gross).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from suiteview.illustration.core.corridor_rates import corridor_death_benefit
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData


@dataclass
class WithdrawalResult:
    """One month's withdrawal computation (CalcEngine AX..BU)."""

    input_withdrawal: float = 0.0        # AX
    max_net_withdrawal: float = 0.0      # AY
    cost_basis_before_wd: float = 0.0    # AZ
    applied_net_withdrawal: float = 0.0  # BA
    remaining_distribution: float = 0.0  # BB (Sw2LnAtCostBasis only)
    cost_basis_after_wd: float = 0.0     # BC
    withdrawals_to_date: float = 0.0     # BD (net)
    withdrawals_ytd: float = 0.0         # BE (net)
    corridor_rate: float = 0.0           # BF
    corridor_amount: float = 0.0         # BG
    reduces_sa: bool = False             # BH
    sa_change_by_cov: Dict[int, float] = field(default_factory=dict)  # BI..BL (net allocation)
    partial_sc: float = 0.0              # BM
    gross_withdrawal: float = 0.0        # BN
    av_post_withdrawal: float = 0.0      # BO
    face_decrease: float = 0.0           # BP
    # Before/after GLP & GSP solves when the face decrease re-solved the
    # guideline premiums (filled by the engine after the recalc); empty
    # when the withdrawal did not move the specified amount.
    guideline_recalc: Dict[str, object] = field(default_factory=dict)
    guideline_before: Optional[object] = None
    guideline_before_pv_detail: Dict[str, object] = field(default_factory=dict)


def compute_withdrawal(
    av: float,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    scr_rates_by_phase: Dict[int, float],
    request: float,
    *,
    gross_request: float = 0.0,
    pct_of_av_surrender_charge: float = 0.0,
    corridor_rate: float,
    prior_total_md: float,
    policy_debt: float,
    cost_basis: float,
    withdrawals_to_date: float,
    withdrawals_ytd: float,
    is_anniversary: bool,
) -> WithdrawalResult:
    """Compute (not apply) one month's withdrawal.

    Args:
        av: Account value entering the month (after loan capitalize/repay).
        scr_rates_by_phase: This month's SCR per 1000 by coverage phase (AN..AP).
        request: The requested net withdrawal (AX — annual, anniversary months).
        gross_request: A gross-basis request — the amount that should leave the
            account value (RERUN BN) — inverted to net and added to ``request``.
        pct_of_av_surrender_charge: Full surrender charge that is a percentage of the
            account value (rule-5 ISWL), added to the per-unit charges in the CSV.
            The engine rejects a withdrawal request while it is non-zero.
        corridor_rate: This month's corridor factor (BF).
        prior_total_md: Prior month's total monthly deduction (SU11).
        policy_debt: Beginning total loan debt (Z..AE sum).
        cost_basis / withdrawals_to_date / withdrawals_ytd: running trackers.
        is_anniversary: True resets the YTD bucket (BE).
    """
    total_sa = policy.total_face
    # RERUN BG is the unrounded slice; ISWL plans carry CyberLife's whole-dollar
    # (rounded) corridor death benefit, as in the monthly deduction.
    corridor_db = (
        corridor_death_benefit(av, corridor_rate, config) if config.is_iswl
        else corridor_rate * av
    )
    corridor_amount = max(0.0, corridor_db - total_sa)
    fee = config.withdrawal_fee
    dbo = str(policy.db_option or "A").upper()

    request = max(request, 0.0)
    if gross_request > 0.0:
        request += _net_from_gross(
            gross_request, request, policy, config, scr_rates_by_phase,
            corridor_amount=corridor_amount, dbo=dbo)

    result = WithdrawalResult(
        input_withdrawal=request,
        cost_basis_before_wd=cost_basis,
        cost_basis_after_wd=cost_basis,
        withdrawals_to_date=withdrawals_to_date,
        withdrawals_ytd=0.0 if is_anniversary else withdrawals_ytd,
        corridor_rate=corridor_rate,
        corridor_amount=corridor_amount,
        av_post_withdrawal=av,
    )

    # AY — CSV less the MD holdback and fee; under DBO A the SA floor also
    # caps. Computed every month (RERUN has no request gate on the column).
    full_sc = pct_of_av_surrender_charge + sum(
        _full_surrender_charge_face(seg, config, policy)
        * scr_rates_by_phase.get(seg.coverage_phase, 0.0)
        / 1000.0
        for seg in policy.segments
    )
    full_sc = max(full_sc - ffl_withdrawal_surrender_credit(policy, config), 0.0)
    csv = av - full_sc - policy_debt
    sa_cap = (
        total_sa - (config.min_face_after_wd + fee)
        if dbo == "A"
        else result.input_withdrawal
    )
    result.max_net_withdrawal = max(
        0.0, min(csv - config.md_holdback * prior_total_md - fee, sa_cap)
    )
    if result.input_withdrawal <= 0.0:
        return result

    applied = min(result.input_withdrawal, result.max_net_withdrawal)
    result.applied_net_withdrawal = applied
    if applied <= 0.0:
        return result

    result.cost_basis_after_wd = cost_basis - applied
    result.withdrawals_to_date = withdrawals_to_date + applied
    result.withdrawals_ytd += applied

    # BH — under DBO A only the slice past the corridor-driven DB reduces SA.
    result.reduces_sa = applied > result.corridor_amount and dbo == "A"

    # BI..BL — allocate the NET amount newest-coverage-first (PSC basis).
    if result.reduces_sa:
        result.sa_change_by_cov = _sa_cuts_for_net(applied, policy)
        if config.partial_surrender_charge:
            result.partial_sc = _partial_sc(
                result.sa_change_by_cov, scr_rates_by_phase)

    # BN / BO / BP
    result.gross_withdrawal = applied + (
        result.partial_sc if result.reduces_sa else 0.0
    ) + fee
    result.av_post_withdrawal = av - result.gross_withdrawal
    if result.reduces_sa:
        fee_out = fee if config.sa_basis == "OriginalSA" else 0.0
        result.face_decrease = result.gross_withdrawal - fee_out
    return result


def _full_surrender_charge_face(seg, config: PlancodeConfig, policy=None) -> float:
    """Specified amount the full surrender charge applies to (see
    ``calc_engine.surrender_charge_units``): the original amount for OriginalSA and
    FFL UL per-unit plans, otherwise the current amount."""
    if config.sa_basis == "OriginalSA":
        return seg.original_face_amount
    if ffl_original_units_basis(seg, config, policy):
        return seg.original_face_amount
    return seg.face_amount


# Running FFL state, deliberately not dataclass fields (snapshots and policy goldens are
# unchanged). The credit is seeded at load from LH_POL_TOTALS.TOT_WTD_CRG_AMT
# (seed_ffl_withdrawal_credit) and grows with projected withdrawals; a snapshot reloaded
# offline starts without it.
_FFL_WITHDRAWAL_CREDIT = "_ffl_withdrawal_surrender_credit"
_FFL_CURRENT_UNITS_FALLBACK = "_ffl_current_units_surrender_basis"


def _ffl_withdrawal_credit_applies(policy, config) -> bool:
    return (str(getattr(policy, "company_code", "") or "").strip() == "26"
            and bool(getattr(config, "ffl_per_unit_surrender_charge", False))
            and not getattr(policy, _FFL_CURRENT_UNITS_FALLBACK, False))


def ffl_current_units_fallback(policy) -> bool:
    """FFL policy whose withdrawal credit could not be established (field or surrender rule
    unreadable, or a rollback to an earlier date): its surrender charge stays on current
    units (the 2d88241 basis), with no withdrawal credit."""
    return bool(getattr(policy, _FFL_CURRENT_UNITS_FALLBACK, False))


def ffl_original_units_basis(seg, config, policy=None) -> bool:
    """Whether an FFL per-unit coverage is charged on its original units.

    Every coverage with original units is, including one a decrease or withdrawal took
    to 0 units (decision #67: 000296011 = 2,252.00 on original units incl. the zeroed
    coverage less TOT_WTD_CRG_AMT 2,139.81 = 112.19). COLA coverages carry a 0 rate.
    Not for a policy on the current-units fallback.
    """
    if not getattr(config, "surrender_charge_on_original_units", False) or seg.original_face_amount <= 0:
        return False
    return not (policy is not None and ffl_current_units_fallback(policy))


def ffl_withdrawal_surrender_credit(policy, config) -> float:
    """Partial surrender charges already taken on FFL withdrawals (fee excluded).

    CyberLife's company-26 FFL full surrender charge after withdrawals is the charge on
    the original units less the partial surrender charges already taken (excluding the
    withdrawal fee), floored at 0: 5 of 6 FH_FIXED surrenders after a charged withdrawal
    fit to the cent (10/5/2026). The in-force part is TOT_WTD_CRG_AMT (decision #66).
    """
    if not _ffl_withdrawal_credit_applies(policy, config):
        return 0.0
    return float(getattr(policy, _FFL_WITHDRAWAL_CREDIT, 0.0))


def record_ffl_withdrawal_surrender_charge(policy, config, partial_sc: float) -> None:
    """Add a projected withdrawal's partial surrender charge (fee excluded) to the credit."""
    if partial_sc > 0.0 and _ffl_withdrawal_credit_applies(policy, config):
        setattr(policy, _FFL_WITHDRAWAL_CREDIT,
                float(getattr(policy, _FFL_WITHDRAWAL_CREDIT, 0.0)) + partial_sc)


TARGET_SURRENDER_RULE = "6"


def seed_ffl_withdrawal_credit(policy, config, total_withdrawal_charges, withdrawal_count: int,
                               full_surrender_rules) -> None:
    """Seed the credit from LH_POL_TOTALS.TOT_WTD_CRG_AMT (company-26 FFL only; decision #66).

    CyberLife's rule-6 full surrender charge subtracts "any previously deducted partial
    surrender target charges" (D10), which TOT_WTD_CRG_AMT (FUMWDCHG) accumulates since issue,
    adjusted by reversals and, under rule 6, excluding the flat withdrawal fee (D202). It
    needs no FH_FIXED history, so purged or pre-conversion withdrawals are still credited.

    ``total_withdrawal_charges`` is ``None`` when the field could not be read: a policy with
    withdrawals (TOT_WTD_QTY) then takes the current-units basis with no credit. A policy whose
    full surrender rules do not include rule 6 gets no credit (the field then also holds the
    fee); one whose rules are unreadable takes the current-units basis.
    """
    if not _ffl_withdrawal_credit_applies(policy, config):
        return
    if total_withdrawal_charges is None:
        if withdrawal_count:
            setattr(policy, _FFL_CURRENT_UNITS_FALLBACK, True)
        return
    credit = float(total_withdrawal_charges)
    if credit <= 0.0:
        return
    rules = {str(rule or "").strip() for rule in (full_surrender_rules or ())} - {"", "0"}
    if TARGET_SURRENDER_RULE not in rules:
        if not rules:
            setattr(policy, _FFL_CURRENT_UNITS_FALLBACK, True)
        return
    # A coverage already at 0 units keeps its original units whether a withdrawal or a
    # decrease removed it (decision #67), so it needs no fallback: the field credits only
    # the withdrawal charges actually taken.
    setattr(policy, _FFL_WITHDRAWAL_CREDIT, credit)


def reset_ffl_withdrawal_state(policy) -> None:
    """Clear the in-force FFL withdrawal credit and fallback (run from issue: no history)."""
    for name in (_FFL_WITHDRAWAL_CREDIT, _FFL_CURRENT_UNITS_FALLBACK):
        if hasattr(policy, name):
            delattr(policy, name)


def use_ffl_current_units_fallback(policy) -> None:
    """Value rollback to an earlier date: the seeded credit (TOT_WTD_CRG_AMT now) may cover
    withdrawals after it, so a credited FFL policy takes the current-units basis."""
    if float(getattr(policy, _FFL_WITHDRAWAL_CREDIT, 0.0)) > 0.0:
        delattr(policy, _FFL_WITHDRAWAL_CREDIT)
        setattr(policy, _FFL_CURRENT_UNITS_FALLBACK, True)


def _sa_cuts_for_net(applied: float, policy: IllustrationPolicyData) -> Dict[int, float]:
    """BI..BL — allocate a net amount newest-coverage-first."""
    cuts: Dict[int, float] = {}
    remaining = applied
    for seg in sorted(policy.segments, key=lambda s: -s.coverage_phase):
        if remaining <= 0.0 or seg.face_amount <= 0:
            continue
        cut = min(seg.face_amount, remaining)
        cuts[seg.coverage_phase] = cut
        remaining -= cut
    return cuts


def _partial_sc(cuts: Dict[int, float], scr_rates_by_phase: Dict[int, float]) -> float:
    """BM — partial surrender charge on a newest-first net allocation."""
    return sum(
        cut * scr_rates_by_phase.get(phase, 0.0) / 1000.0
        for phase, cut in cuts.items()
    )


def _net_from_gross(
    gross: float,
    net_request: float,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    scr_rates_by_phase: Dict[int, float],
    *,
    corridor_amount: float,
    dbo: str,
) -> float:
    """Invert a gross-basis request into the net request the AX chain consumes.

    "Gross" on the inputs UI means the entered amount is what leaves the
    account value — RERUN BN = net + PSC (when the SA reduces) + fee — while
    the engine input (AX) is a NET request. The PSC term is piecewise-linear
    in the net with slope SCR/1000 (a few percent at most), so a short
    fixed-point iteration lands within a fraction of a cent.

    ``net_request`` is any same-month net-basis request: the fee is charged
    once per monthly withdrawal event, so when bases mix in one month the fee
    and PSC are attributed to the gross portion (net-basis entries keep their
    exact cash-to-client meaning).
    """
    fee = config.withdrawal_fee
    net = max(0.0, gross - fee)
    if not config.partial_surrender_charge or dbo != "A":
        return net
    for _ in range(8):
        total = net_request + net
        psc = (
            _partial_sc(_sa_cuts_for_net(total, policy), scr_rates_by_phase)
            if total > corridor_amount
            else 0.0
        )
        adjusted = max(0.0, gross - fee - psc)
        if abs(adjusted - net) <= 1e-9:
            break
        net = adjusted
    return net
