"""Premium application — Stage 1 of the monthly pipeline.

Follows RERUN CalcEngine cols 367-403. ISWL plancodes split a fixed premium
instead (``_apply_iswl_premium``; rules in ``iswl_rates``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from suiteview.illustration.core.iswl_rates import split_iswl_premium
from suiteview.illustration.core.rate_loader import IllustrationRates, get_rate
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData


@dataclass
class PremiumResult:
    """Intermediate output of apply_premium()."""

    gross_premium: float = 0.0
    requested_premium: float = 0.0   # premium before guideline/TAMRA cap
    premium_cap: float = 0.0         # cap that was applied (inf if none)
    premium_capped: bool = False     # True when the cap reduced the premium
    prem_under_target: float = 0.0
    prem_over_target: float = 0.0
    tpp_rate: float = 0.0            # target/excess load rates — populated even
    epp_rate: float = 0.0            # when no premium is applied this month
    target_load: float = 0.0
    excess_load: float = 0.0
    flat_load: float = 0.0
    total_premium_load: float = 0.0
    net_premium: float = 0.0
    av_after_premium: float = 0.0
    premiums_ytd: float = 0.0
    premiums_to_date: float = 0.0
    cost_basis: float = 0.0
    # ISWL: the policy fee and benefit/rider premiums that come out of the gross
    # premium (target_load carries the rule-4 premium load). Zero for UL plans.
    policy_fee: float = 0.0
    benefit_premium: float = 0.0


def premium_load_rates(rates: IllustrationRates, rate_year: int) -> tuple[float, float]:
    """Target/excess premium-load rates for ``rate_year`` (PolicyRates AW/AX)."""
    return get_rate(rates, "tpp", rate_year), get_rate(rates, "epp", rate_year)


@dataclass(frozen=True)
class PremiumLoadSplit:
    """One gross premium split at the commission target and its loads."""

    gross: float = 0.0
    under_target: float = 0.0
    over_target: float = 0.0
    target_load: float = 0.0
    excess_load: float = 0.0
    flat_load: float = 0.0

    @property
    def total_load(self) -> float:
        return self.target_load + self.excess_load + self.flat_load

    @property
    def net(self) -> float:
        return self.gross - self.total_load


def split_premium_load(
    gross: float, *, premiums_ytd: float, ctp: float, tpp: float, epp: float, flat: float,
) -> PremiumLoadSplit:
    """CalcEngine cols 395-400: TPP up to the CTP, EPP above it, plus the flat load.

    ``premiums_ytd`` is the policy-year premium already paid before ``gross``.
    """
    if gross <= 0.0:
        return PremiumLoadSplit()
    ytd_after = premiums_ytd + gross
    under = max(min(ctp - premiums_ytd, gross), 0.0)
    over = max(min(gross, ytd_after - ctp), 0.0) if ytd_after > ctp else 0.0
    return PremiumLoadSplit(
        gross=gross, under_target=under, over_target=over,
        target_load=under * tpp, excess_load=over * epp,
        flat_load=flat if flat > 0 else 0.0,
    )


def gross_up_for_premium_load(
    net_required: float, *, premiums_ytd: float, ctp: float, tpp: float, epp: float, flat: float,
) -> PremiumLoadSplit:
    """Smallest whole-cent gross premium whose net after load covers ``net_required``.

    Inverts :func:`split_premium_load`: the part of the premium that fits under the
    remaining commission target (``ctp - premiums_ytd``) is loaded at ``tpp``, the
    rest at ``epp``, and the flat per-premium load is added once. The exact gross is
    rounded up to the cent, so the net after load is at least ``net_required`` and
    exceeds it by less than one cent.
    """
    if net_required <= 0.0:
        return PremiumLoadSplit()
    keep_target = 1.0 - tpp if abs(1.0 - tpp) > 1e-12 else 1.0
    keep_excess = 1.0 - epp if abs(1.0 - epp) > 1e-12 else 1.0
    flat_load = flat if flat > 0 else 0.0
    needed = net_required + flat_load
    room = max(ctp - premiums_ytd, 0.0)
    if needed <= room * keep_target:
        exact = needed / keep_target
    else:
        exact = room + (needed - room * keep_target) / keep_excess
    gross = math.ceil(round(exact * 100.0, 6)) / 100.0
    split = split_premium_load(
        gross, premiums_ytd=premiums_ytd, ctp=ctp, tpp=tpp, epp=epp, flat=flat)
    while split.net < net_required - 1e-9:
        gross = round(gross + 0.01, 2)
        split = split_premium_load(
            gross, premiums_ytd=premiums_ytd, ctp=ctp, tpp=tpp, epp=epp, flat=flat)
    return split


def apply_premium(
    av_beginning: float,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    rate_year: int,
    premiums_ytd: float,
    premiums_to_date: float,
    cost_basis: float,
    gross_premium_override: float | None = None,
    premium_cap: float | None = None,
    projection_date: date | None = None,
) -> PremiumResult:
    """Apply one month's premium to account value.

    Args:
        av_beginning: Account value at start of month (end of prior month).
        policy: Policy data (for modal_premium, ctp, etc.).
        config: Plancode configuration.
        rates: Pre-loaded rate arrays.
        rate_year: Current policy year for rate table lookup.
        premiums_ytd: Premiums paid year-to-date BEFORE this month.
        premiums_to_date: Cumulative lifetime premiums BEFORE this month.
        cost_basis: Tax cost basis BEFORE this month.
        gross_premium_override: Replaces modal premium when supplied.
        premium_cap: Guideline/TAMRA acceptance cap. The applied gross premium is
            limited to this amount (CalcEngine vAppliedScheduledPremium). None =
            no cap.
        projection_date: The month's date. ISWL needs it to drop ceased benefit
            and rider premiums from the bill.

    Returns:
        PremiumResult with all premium-stage outputs.
    """
    requested_premium = policy.modal_premium if gross_premium_override is None else gross_premium_override
    cap_display = premium_cap if premium_cap is not None else float("inf")

    gross_premium = requested_premium
    if premium_cap is not None:
        gross_premium = max(0.0, min(requested_premium, premium_cap))
    premium_capped = gross_premium < requested_premium - 1e-9

    if config.is_iswl:
        return _apply_iswl_premium(
            av_beginning, policy, rates, rate_year, premiums_ytd, premiums_to_date, cost_basis,
            requested_premium=requested_premium, gross_requested=gross_premium,
            cap_display=cap_display, premium_capped=premium_capped, projection_date=projection_date,
        )

    # Load rates (PolicyRates AW/AX) — resolved every month, independent of
    # whether a premium is applied, so the Values tab can always display them.
    tpp_rate, epp_rate = premium_load_rates(rates, rate_year)

    if gross_premium <= 0:
        return PremiumResult(
            requested_premium=requested_premium,
            premium_cap=cap_display,
            premium_capped=premium_capped,
            tpp_rate=tpp_rate,
            epp_rate=epp_rate,
            av_after_premium=av_beginning,
            premiums_ytd=premiums_ytd,
            premiums_to_date=premiums_to_date,
            cost_basis=cost_basis,
        )

    # ── CTP split and premium load (CalcEngine cols 395-400) ──
    # A plan without premium-load cells carries the table's flat load as level
    # tpp = epp schedules, so the split charges it on every premium.
    split = split_premium_load(
        gross_premium, premiums_ytd=premiums_ytd, ctp=policy.ctp,
        tpp=tpp_rate, epp=epp_rate, flat=config.prem_flat_load,
    )
    prem_under_target = split.under_target
    prem_over_target = split.over_target
    target_load = split.target_load
    excess_load = split.excess_load
    flat_load = split.flat_load

    total_premium_load = target_load + excess_load + flat_load
    net_premium = gross_premium - total_premium_load

    # ── Apply to AV ───────────────────────────────────────────
    av_after_premium = av_beginning + net_premium

    # ── Update tracking ───────────────────────────────────────
    new_premiums_ytd = premiums_ytd + gross_premium
    new_premiums_to_date = premiums_to_date + gross_premium
    new_cost_basis = cost_basis + gross_premium

    return PremiumResult(
        gross_premium=gross_premium,
        requested_premium=requested_premium,
        premium_cap=cap_display,
        premium_capped=premium_capped,
        prem_under_target=prem_under_target,
        prem_over_target=prem_over_target,
        tpp_rate=tpp_rate,
        epp_rate=epp_rate,
        target_load=target_load,
        excess_load=excess_load,
        flat_load=flat_load,
        total_premium_load=total_premium_load,
        net_premium=net_premium,
        av_after_premium=av_after_premium,
        premiums_ytd=new_premiums_ytd,
        premiums_to_date=new_premiums_to_date,
        cost_basis=new_cost_basis,
    )


def _apply_iswl_premium(
    av_beginning: float,
    policy: IllustrationPolicyData,
    rates: IllustrationRates,
    rate_year: int,
    premiums_ytd: float,
    premiums_to_date: float,
    cost_basis: float,
    *,
    requested_premium: float,
    gross_requested: float,
    cap_display: float,
    premium_capped: bool,
    projection_date: date | None,
) -> PremiumResult:
    """ISWL fixed premium: whole billed payments; only the rule-4 net is credited.

    The premium load, policy fee and benefit/rider premiums stay out of the account
    value (``iswl_rates`` documents the verified CyberLife rules).
    """
    basis = rates.iswl
    if basis is None:
        raise ValueError("ISWL premium needs the ISWL rate basis from schema rates.")
    load_pct = _iswl_load(basis, rate_year)
    if premium_capped and gross_requested > 0.0:
        raise ValueError(
            f"ISWL is a fixed-premium plan: the guideline/TAMRA premium limit reduced the "
            f"billed premium from {requested_premium:,.2f} to {gross_requested:,.2f}. "
            "Partial ISWL premiums are not supported.")
    split = split_iswl_premium(
        basis, gross_requested, float(policy.modal_premium or 0.0), rate_year, projection_date)
    return PremiumResult(
        gross_premium=split.gross_premium,
        requested_premium=requested_premium,
        premium_cap=cap_display,
        premium_capped=premium_capped,
        tpp_rate=load_pct,
        target_load=split.premium_load,
        total_premium_load=round(split.gross_premium - split.net_premium, 2),
        net_premium=split.net_premium,
        av_after_premium=av_beginning + split.net_premium,
        premiums_ytd=premiums_ytd + split.gross_premium,
        premiums_to_date=premiums_to_date + split.gross_premium,
        cost_basis=cost_basis + split.gross_premium,
        policy_fee=split.policy_fee,
        benefit_premium=split.benefit_premium,
    )


def _iswl_load(basis, rate_year: int) -> float:
    schedule = basis.load_pct
    index = min(max(int(rate_year), 1), len(schedule) - 1)
    return float(schedule[index])
