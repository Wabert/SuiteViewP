"""Premium application — Stage 1 of the monthly pipeline.

Follows RERUN CalcEngine cols 367-403.
"""
from __future__ import annotations

from dataclasses import dataclass

from suiteview.illustration.core.rate_loader import IllustrationRates, get_rate
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData


@dataclass
class PremiumResult:
    """Intermediate output of apply_premium()."""

    gross_premium: float = 0.0
    prem_under_target: float = 0.0
    prem_over_target: float = 0.0
    target_load: float = 0.0
    excess_load: float = 0.0
    flat_load: float = 0.0
    total_premium_load: float = 0.0
    net_premium: float = 0.0
    av_after_premium: float = 0.0
    premiums_ytd: float = 0.0
    premiums_to_date: float = 0.0
    cost_basis: float = 0.0


def apply_premium(
    av_beginning: float,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    rate_year: int,
    premiums_ytd: float,
    premiums_to_date: float,
    cost_basis: float,
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

    Returns:
        PremiumResult with all premium-stage outputs.
    """
    gross_premium = policy.modal_premium

    if gross_premium <= 0:
        return PremiumResult(
            av_after_premium=av_beginning,
            premiums_ytd=premiums_ytd,
            premiums_to_date=premiums_to_date,
            cost_basis=cost_basis,
        )

    # ── CTP split (CalcEngine cols 395-396) ───────────────────
    ctp = policy.ctp
    prem_ytd_before = premiums_ytd
    prem_ytd_after = prem_ytd_before + gross_premium

    prem_under_target = max(min(ctp - prem_ytd_before, gross_premium), 0.0)
    if prem_ytd_after > ctp:
        prem_over_target = max(min(gross_premium, prem_ytd_after - ctp), 0.0)
    else:
        prem_over_target = 0.0

    # ── Premium load (CalcEngine cols 397-400) ────────────────
    target_load = 0.0
    excess_load = 0.0
    flat_load = 0.0

    if config.premium_load == "Table":
        tpp_rate = get_rate(rates, "tpp", rate_year)
        epp_rate = get_rate(rates, "epp", rate_year)
        target_load = prem_under_target * tpp_rate
        excess_load = prem_over_target * epp_rate
    else:
        # Flat percentage load
        try:
            flat_pct = float(config.premium_load)
        except (ValueError, TypeError):
            flat_pct = 0.0
        target_load = gross_premium * flat_pct

    if config.prem_flat_load > 0 and gross_premium > 0:
        flat_load = config.prem_flat_load

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
        prem_under_target=prem_under_target,
        prem_over_target=prem_over_target,
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
