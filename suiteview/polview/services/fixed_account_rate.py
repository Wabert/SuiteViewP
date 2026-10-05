"""Current fixed-account crediting rate of an advanced product, for PolView.

The rate the policy's fixed (declared-rate) fund earns now, with and without the
duration bonus, for every advanced product (UL, IUL, ISWL). Shown on the Account
Values tab as Fixed Crediting Rate / Fixed Rate ex Bonus. For IUL the rate excluding
bonus is also the fixed-account rate (``IllustrationPolicyData.iul_declared_rate``)
of PolView's in-force projections (Interim AV Quote, surrender values, GLP Exception
forecast), where it drives the IUL14NY (1U145900) bonus cap
``min(bonus, fixed rate - GINT)``; other products' projections are not changed.

Source, in order:

1. **The policy's current fixed-fund buckets** (DB2 ``LH_POL_FND_VAL_TOT``,
   ``MVRY_DT`` 12/31/9999): ``VAL_PHA_ITS_RT`` is the rate CyberLife credits, bonus
   included. The fixed funds are IUL ``U1`` (fixed strategy) / ``SW`` (sweep); for
   other products the funds the coverage fixed-fund control names with a CIRF rate
   key (``LH_COV_FXD_FND_CTL.FND_ID_CD`` / ``CUR_ITS_RT_SER_NBR``, e.g. ISWL ``I1`` /
   ``ELGRP0001``), else every control fund but the 0% ``GP`` holding fund. The rate
   excluding the
   bonus removes the plan's duration bonus in effect this policy year
   (``tRates_IntBonus``; for the New York cap the inverse of ``d + min(B, d - GINT)``).
   A plan without a ``tRates_IntBonus`` row has no bonus: both rates are equal.
2. **The plan's CIRF declared rate** (UL_Rates schema ``rates``, the plan's CIRF fund:
   ``PLAN_DEF.CIRF_KEY``, or for multi-fund IUL keys the fixed fund named by
   ``PLAN_ATTR FUND_KEYS``, e.g. IULFIX14), plus the bonus, when the policy has no
   current fixed-fund bucket.

The bucket is preferred because it is what CyberLife actually credits: on
2026-10-03 the FFL keys (``IULFIX14@26``, ``IULFIX14B@26``) carry a 4.10% CINT row
effective 01/01/2026, yet FFL buckets still credit 3.80% (``ITS_RT_STR_DT``
09/01/2023, the 3.80% row). Both are reported so a disagreement is visible, and a
CIRF key with no UL_Rates rate (e.g. ISWL ``ELGRP0001`` on 2026-10-04) is named.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from suiteview.illustration.core.bonus_eligibility import with_recorded_stage
from suiteview.illustration.core.bonus_rates import BonusConfig, load_bonus_config
from suiteview.illustration.core.declared_rates import (
    DeclaredRate,
    policy_guaranteed_rate,
    ul_current_declared_rate,
)
from suiteview.illustration.models.index_strategies import (
    FIXED_FUND_ID,
    SWEEP_FUND_ID,
    is_iul_plan,
)
from suiteview.illustration.models.plan_facts import load_plan_facts
from suiteview.polview.models.policy_sections.lookup import policy_attr

IUL_FIXED_ACCOUNT_FUNDS = (FIXED_FUND_ID, SWEEP_FUND_ID)
FIXED_FUND_CONTROL_TABLE = "LH_COV_FXD_FND_CTL"
# CyberLife's 0% holding fund (negative account value / no-key placeholder): never credited.
HOLDING_FUND = "GP"
SOURCE_BUCKET = "bucket"
SOURCE_CIRF = "cirf"
_RATE_TOLERANCE = 1e-9


@dataclass(frozen=True)
class FixedBucketRate:
    """The rate on a current fixed-fund bucket (decimal)."""

    rate: float
    rate_start: Optional[date]
    funds: tuple[str, ...]


@dataclass(frozen=True)
class FixedAccountRate:
    """An advanced policy's current fixed-fund rate (decimals)."""

    plancode: str
    is_iul: bool
    credited_rate: float
    declared_rate: float
    bonus_rate: float
    bonus: BonusConfig
    policy_year: int
    gint: Optional[float]
    source: str
    bucket: Optional[FixedBucketRate]
    cirf: Optional[DeclaredRate]
    fixed_funds: tuple[str, ...] = ()
    cirf_key: str = ""

    @property
    def cirf_disagrees(self) -> bool:
        """The CIRF declared rate differs from the rate the buckets are credited."""
        return (self.source == SOURCE_BUCKET and self.cirf is not None
                and abs(self.cirf.rate - self.declared_rate) > 5e-6)


@dataclass(frozen=True)
class FixedRateUnavailable:
    reason: str


def _code(row, column: str) -> str:
    return str(row.get(column) or "").strip()


def _rate_key(row) -> str:
    key = _code(row, "CUR_ITS_RT_SER_NBR")
    return key if key.isprintable() else ""


def fixed_fund_ids(pi, is_iul: bool) -> tuple[str, ...]:
    """The policy's fixed (declared-rate) fund ids.

    IUL: ``U1``/``SW`` (the fixed-fund control also lists the index strategies).
    Other advanced products: the funds the coverage fixed-fund control names with a
    CIRF rate key (``CUR_ITS_RT_SER_NBR``); when none has a key, every control fund
    except the 0% ``GP`` holding fund.
    """
    if is_iul:
        return IUL_FIXED_ACCOUNT_FUNDS
    rows = [row for row in pi.fetch_table(FIXED_FUND_CONTROL_TABLE) or [] if _code(row, "FND_ID_CD")]
    keyed = {_code(row, "FND_ID_CD") for row in rows if _rate_key(row)}
    funds = keyed or {_code(row, "FND_ID_CD") for row in rows} - {HOLDING_FUND}
    return tuple(sorted(funds))


def policy_cirf_key(pi, funds: tuple[str, ...]) -> str:
    """The CIRF key on the fixed funds' control rows (``CUR_ITS_RT_SER_NBR``), if one."""
    keys = sorted({
        _rate_key(row) for row in pi.fetch_table(FIXED_FUND_CONTROL_TABLE) or []
        if _code(row, "FND_ID_CD") in funds and _rate_key(row)
    })
    return keys[0] if len(keys) == 1 else ""


def fixed_bucket_rate(pi, funds: tuple[str, ...] = IUL_FIXED_ACCOUNT_FUNDS) -> Optional[FixedBucketRate]:
    """The current bucket rate of the given fixed funds, or None without one.

    Unimpaired buckets are preferred; with several rates the most recently started
    rate (``ITS_RT_STR_DT``) is the current one.
    """
    rows = [
        row for row in pi.fetch_table("LH_POL_FND_VAL_TOT") or []
        if "9999" in str(row.get("MVRY_DT", ""))
        and _code(row, "FND_ID_CD") in funds
        and row.get("VAL_PHA_ITS_RT") is not None
    ]
    unimpaired = [row for row in rows if _code(row, "IMPAIRED_IND") != "1"]
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
        funds=tuple(sorted({_code(row, "FND_ID_CD") for row in rows})),
    )


def bonus_in_effect(bonus: BonusConfig, policy_year: int, account_value: float) -> float:
    """Uncapped bonus the engine adds in ``policy_year`` (see ``interest_calc``)."""
    rate = bonus.duration_bonus(policy_year)
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


def _declared_rate_floor(pi, is_iul: bool, gint: Optional[float]) -> float:
    """The floor under the CIRF declared rate: the policy's fixed-fund guarantee
    (``LH_COV_FXD_FND_CTL.GUA_FND_ITS_RT``) for declared-rate UL, as the illustration
    floors it; the plan GINT for IUL and ISWL. ANICO1996 (GINT 4%) policies past year
    10 guarantee 3.00%/3.25%, so CIRF shows 3.00%, not 4.00%."""
    if is_iul or str(pi.product.product_type or "").upper() == "ISWL":
        return float(gint or 0.0)
    return policy_guaranteed_rate(pi, gint)


def fixed_account_rate(pi, as_of: date):
    """The advanced policy's current fixed-fund rate.

    Returns :class:`FixedRateUnavailable` when neither a fixed-fund bucket nor a CIRF
    rate is available. Schema ``rates`` errors propagate to the caller.
    """
    plancode = str(pi.coverages.base_plancode or "").strip().upper()
    if not plancode:
        return FixedRateUnavailable("The policy has no base plancode.")
    is_iul = is_iul_plan(plancode)
    facts = load_plan_facts(plancode)
    gint = facts.gint if facts is not None else None
    plan_key = facts.cint_key if facts is not None else ""
    floor = _declared_rate_floor(pi, is_iul, gint)
    cirf = None
    if facts is not None:
        cirf = ul_current_declared_rate(
            pi.company_code or "", plancode, as_of, floor,
            cint_key=plan_key,
            rga_indicator=str(policy_attr(pi, "reins_partner", "") or ""))
    funds = fixed_fund_ids(pi, is_iul)
    cirf_key = policy_cirf_key(pi, funds) or plan_key
    policy_year = int(pi.activity.policy_year or 1)
    bonus = with_recorded_stage(
        load_bonus_config(plancode, pi.values.valuation_date or as_of),
        pi.product.prospective_bonus_code)
    av = float(pi.values.mv_av(0) or 0.0)
    uncapped = bonus_in_effect(bonus, policy_year, av)
    ny_cap = bonus.bonus_dur_cap_to_excess_over_guar
    bucket = fixed_bucket_rate(pi, funds)
    if bucket is not None:
        declared = declared_from_credited(bucket.rate, uncapped, ny_cap, gint)
        credited, source = bucket.rate, SOURCE_BUCKET
    elif cirf is not None:
        declared = cirf.rate
        credited, source = round(declared + capped_bonus(uncapped, ny_cap, declared, gint), 10), SOURCE_CIRF
    else:
        fund_text = "/".join(funds) if funds else "none named in LH_COV_FXD_FND_CTL"
        key_text = f"CIRF key {cirf_key}" if cirf_key else "its CIRF key (none on PLAN_DEF)"
        return FixedRateUnavailable(
            f"{plancode} has no current fixed-fund bucket (fixed funds: {fund_text}) and "
            f"UL_Rates schema rates has no CIRF declared rate for {key_text}.")
    return FixedAccountRate(
        plancode=plancode,
        is_iul=is_iul,
        credited_rate=credited,
        declared_rate=declared,
        bonus_rate=round(credited - declared, 10),
        bonus=bonus,
        policy_year=policy_year,
        gint=gint,
        source=source,
        bucket=bucket,
        cirf=cirf,
        fixed_funds=funds,
        cirf_key=cirf_key,
    )


def apply_fixed_rate(ill_policy, fixed) -> None:
    """IUL: use the resolved fixed rate (excluding bonus) as the projection's fixed rate.

    Other products keep their projection basis; the rate is display-only for them.
    """
    if isinstance(fixed, FixedAccountRate) and fixed.is_iul:
        ill_policy.iul_declared_rate = fixed.declared_rate
