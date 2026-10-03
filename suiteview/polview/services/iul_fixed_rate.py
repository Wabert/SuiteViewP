"""Current IUL fixed-account crediting rate for PolView.

The rate an IUL policy's fixed account earns now, with and without the duration
bonus. Shown on the Account Values tab and used as the fixed-account rate
(``IllustrationPolicyData.iul_declared_rate``) by PolView's in-force projections
(Interim AV Quote, surrender values, GLP Exception forecast), where it drives the
IUL14NY (1U145900) bonus cap ``min(bonus, fixed rate - GINT)``.

Source, in order:

1. **The policy's current fixed-account buckets** (DB2 ``LH_POL_FND_VAL_TOT``,
   ``MVRY_DT`` 12/31/9999, funds ``U1`` fixed strategy / ``SW`` sweep):
   ``VAL_PHA_ITS_RT`` is the rate CyberLife credits, bonus included. The rate
   excluding the bonus removes the plan's duration bonus in effect this policy year
   (``tRates_IntBonus``; for the New York cap the inverse of ``d + min(B, d - GINT)``).
2. **The plan's CIRF declared rate** (UL_Rates schema ``rates``, the fixed fund named
   by ``PLAN_ATTR FUND_KEYS``, e.g. IULFIX14), plus the bonus, when the policy has no
   current fixed-account bucket.

The bucket is preferred because it is what CyberLife actually credits: on
2026-10-03 the FFL keys (``IULFIX14@26``, ``IULFIX14B@26``) carry a 4.10% CINT row
effective 01/01/2026, yet FFL buckets still credit 3.80% (``ITS_RT_STR_DT``
09/01/2023, the 3.80% row). Both are reported so a disagreement is visible.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from suiteview.illustration.core.bonus_rates import BonusConfig, load_bonus_config
from suiteview.illustration.core.declared_rates import DeclaredRate, ul_current_declared_rate
from suiteview.illustration.models.index_strategies import (
    FIXED_FUND_ID,
    SWEEP_FUND_ID,
    is_iul_plan,
)
from suiteview.illustration.models.plan_facts import load_plan_facts
from suiteview.polview.models.policy_sections.lookup import policy_attr

FIXED_ACCOUNT_FUNDS = (FIXED_FUND_ID, SWEEP_FUND_ID)
SOURCE_BUCKET = "bucket"
SOURCE_CIRF = "cirf"
_RATE_TOLERANCE = 1e-9


@dataclass(frozen=True)
class FixedBucketRate:
    """The rate on a current fixed-account bucket (decimal)."""

    rate: float
    rate_start: Optional[date]
    funds: tuple[str, ...]


@dataclass(frozen=True)
class IulFixedAccountRate:
    """An IUL policy's current fixed-account rate (decimals)."""

    plancode: str
    credited_rate: float
    declared_rate: float
    bonus_rate: float
    bonus: BonusConfig
    policy_year: int
    gint: Optional[float]
    source: str
    bucket: Optional[FixedBucketRate]
    cirf: Optional[DeclaredRate]

    @property
    def cirf_disagrees(self) -> bool:
        """The CIRF declared rate differs from the rate the buckets are credited."""
        return (self.source == SOURCE_BUCKET and self.cirf is not None
                and abs(self.cirf.rate - self.declared_rate) > 5e-6)


@dataclass(frozen=True)
class IulFixedRateUnavailable:
    reason: str


def fixed_bucket_rate(pi) -> Optional[FixedBucketRate]:
    """The current fixed-account (U1/SW) bucket rate, or None without one.

    Unimpaired buckets are preferred; with several rates the most recently started
    rate (``ITS_RT_STR_DT``) is the current one.
    """
    rows = [
        row for row in pi.fetch_table("LH_POL_FND_VAL_TOT") or []
        if "9999" in str(row.get("MVRY_DT", ""))
        and str(row.get("FND_ID_CD", "")).strip() in FIXED_ACCOUNT_FUNDS
        and row.get("VAL_PHA_ITS_RT") is not None
    ]
    unimpaired = [row for row in rows if str(row.get("IMPAIRED_IND", "")).strip() != "1"]
    rows = unimpaired or rows
    if not rows:
        return None
    latest = max(rows, key=lambda row: (str(row.get("ITS_RT_STR_DT") or ""),
                                        float(row.get("CSV_AMT") or 0)))
    start = latest.get("ITS_RT_STR_DT")
    if isinstance(start, str):
        start = date.fromisoformat(start[:10]) if start[:4].isdigit() else None
    return FixedBucketRate(
        rate=round(float(latest["VAL_PHA_ITS_RT"]) / 100.0, 10),
        rate_start=start,
        funds=tuple(sorted({str(row.get("FND_ID_CD", "")).strip() for row in rows})),
    )


def bonus_in_effect(bonus: BonusConfig, policy_year: int, account_value: float) -> float:
    """Uncapped bonus the engine adds in ``policy_year`` (see ``interest_calc``)."""
    rate = 0.0
    if bonus.bonus_dur_rate > 0 and policy_year > bonus.bonus_dur_threshold:
        rate += bonus.bonus_dur_rate
    if bonus.bonus_av_threshold > 0 and bonus.bonus_av_rate > 0 and account_value >= bonus.bonus_av_threshold:
        rate += bonus.bonus_av_rate
    return rate


def declared_from_credited(credited: float, bonus: float, ny_cap: bool, gint: Optional[float]) -> float:
    """The fixed rate excluding a bonus that is already in ``credited``.

    Without the New York cap ``credited = d + bonus``. With it
    ``credited = d + min(bonus, max(0, d - GINT))``: the full bonus when
    ``d - GINT >= bonus``, else ``credited = 2d - GINT`` (``d >= GINT``), else no bonus.
    """
    if bonus <= 0:
        return credited
    if not ny_cap:
        return round(credited - bonus, 10)
    guaranteed = float(gint or 0.0)
    full = credited - bonus
    if full - guaranteed >= bonus - _RATE_TOLERANCE:
        return round(full, 10)
    partial = (credited + guaranteed) / 2.0
    if partial >= guaranteed - _RATE_TOLERANCE:
        return round(partial, 10)
    return credited


def capped_bonus(bonus: float, ny_cap: bool, declared: float, gint: Optional[float]) -> float:
    """The bonus credited on top of ``declared`` (New York: capped at ``declared - GINT``)."""
    if not ny_cap:
        return bonus
    return min(bonus, round(max(0.0, declared - float(gint or 0.0)), 12))


def iul_fixed_account_rate(pi, as_of: date):
    """The policy's current IUL fixed-account rate.

    Returns ``None`` for a non-IUL plan and :class:`IulFixedRateUnavailable` when
    neither a fixed-account bucket nor a CIRF rate is available. Schema ``rates``
    errors propagate to the caller.
    """
    plancode = str(pi.coverages.base_plancode or "").strip().upper()
    if not plancode or not is_iul_plan(plancode):
        return None
    facts = load_plan_facts(plancode)
    gint = facts.gint if facts is not None else None
    cirf = None
    if facts is not None:
        cirf = ul_current_declared_rate(
            pi.company_code or "", plancode, as_of, float(gint or 0.0),
            cint_key=facts.cint_key,
            rga_indicator=str(policy_attr(pi, "reins_partner", "") or ""))
    policy_year = int(pi.activity.policy_year or 1)
    bonus = load_bonus_config(plancode, pi.values.valuation_date or as_of)
    av = float(pi.values.mv_av(0) or 0.0)
    uncapped = bonus_in_effect(bonus, policy_year, av)
    ny_cap = bonus.bonus_dur_cap_to_excess_over_guar
    bucket = fixed_bucket_rate(pi)
    if bucket is not None:
        declared = declared_from_credited(bucket.rate, uncapped, ny_cap, gint)
        credited, source = bucket.rate, SOURCE_BUCKET
    elif cirf is not None:
        declared = cirf.rate
        credited, source = round(declared + capped_bonus(uncapped, ny_cap, declared, gint), 10), SOURCE_CIRF
    else:
        return IulFixedRateUnavailable(
            f"{plancode} has no current fixed-account (U1/SW) bucket and no CIRF declared "
            "rate in UL_Rates schema rates.")
    return IulFixedAccountRate(
        plancode=plancode,
        credited_rate=credited,
        declared_rate=declared,
        bonus_rate=round(credited - declared, 10),
        bonus=bonus,
        policy_year=policy_year,
        gint=gint,
        source=source,
        bucket=bucket,
        cirf=cirf,
    )


def apply_fixed_rate(ill_policy, fixed) -> None:
    """Use the resolved fixed rate (excluding bonus) as the projection's IUL fixed rate."""
    if isinstance(fixed, IulFixedAccountRate):
        ill_policy.iul_declared_rate = fixed.declared_rate
