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
from typing import Dict

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


def compute_withdrawal(
    av: float,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    scr_rates_by_phase: Dict[int, float],
    request: float,
    *,
    gross_request: float = 0.0,
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
        corridor_rate: This month's corridor factor (BF).
        prior_total_md: Prior month's total monthly deduction (SU11).
        policy_debt: Beginning total loan debt (Z..AE sum).
        cost_basis / withdrawals_to_date / withdrawals_ytd: running trackers.
        is_anniversary: True resets the YTD bucket (BE).
    """
    total_sa = policy.total_face
    corridor_amount = max(0.0, corridor_rate * av - total_sa)
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
    full_sc = sum(
        seg.face_amount * scr_rates_by_phase.get(seg.coverage_phase, 0.0) / 1000.0
        for seg in policy.segments
        if seg.face_amount > 0
    )
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
        fee_out = fee if config.target_sa_basis == "OriginalSA" else 0.0
        result.face_decrease = result.gross_withdrawal - fee_out
    return result


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
