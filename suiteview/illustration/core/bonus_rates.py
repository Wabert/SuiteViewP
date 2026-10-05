"""Bonus interest rate loader — reads from tRates_IntBonus.json.

Replaces the UL_Rates DB bonus lookups (BONUSDUR / BONUSAV) with a
locally-maintained JSON table keyed by (Plancode, EffectiveDate).
Engine runs resolve the New York excess-over-guaranteed cap with
:meth:`BonusConfig.capped_for`; :func:`load_bonus_config` is the raw table row.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import List, Optional

from suiteview.illustration.models.index_strategies import load_index_strategies


_TABLE_PATH = Path(__file__).resolve().parent.parent / "plancodes" / "tRates_IntBonus.json"
_CACHE: Optional[List[dict]] = None
_CACHE_MTIME_NS: Optional[int] = None


@dataclass
class BonusConfig:
    """Resolved bonus rates effective for a specific plancode and date."""

    bonus_dur_rate: float = 0.0
    bonus_dur_threshold: int = 0
    bonus_av_rate: float = 0.0
    bonus_av_threshold: float = 0.0
    bonus_dur_rate_guar: float = 0.0
    bonus_av_rate_guar: float = 0.0
    # New York form (IUL14NY 1U145900, RERUN v21 Rates_Control!ET73): the
    # duration bonus is MIN(BonusDurRate, fixed account rate - GINT), floored at 0.
    bonus_dur_cap_to_excess_over_guar: bool = False
    # Second duration tier (ANICO1996 PULU 1U135900/1U135Q00: 0.75% from policy year 21;
    # not 1U135H00). From the year after ``bonus_dur_threshold2`` it REPLACES tier 1; it
    # is not added to it. A threshold of 0 means the plan has no second tier.
    bonus_dur_rate2: float = 0.0
    bonus_dur_threshold2: int = 0
    bonus_dur_rate2_guar: float = 0.0
    # CyberLife reward type C (mod AN0230): each tier is earned only by passing the
    # eligibility test at its start; see ``core.bonus_eligibility``.
    bonus_conditional: bool = False
    # Highest duration tier the policy has earned (0 = none). None = every tier
    # applies (unconditional plans, or eligibility not resolved).
    bonus_max_tier: Optional[int] = None

    def duration_tiers(self) -> tuple[tuple[int, float], ...]:
        """The duration bonus schedule as ``(threshold year, rate)`` pairs, ascending.

        A tier applies in policy years after its threshold and replaces the tier before it.
        """
        tiers = [(self.bonus_dur_threshold, self.bonus_dur_rate)]
        if self.bonus_dur_threshold2 > 0:
            tiers.append((self.bonus_dur_threshold2, self.bonus_dur_rate2))
        return tuple(tiers)

    def duration_bonus(self, rate_year: int) -> float:
        """Duration bonus in ``rate_year``: the latest tier started, capped at ``bonus_max_tier``."""
        rate = 0.0
        for tier, (threshold, tier_rate) in enumerate(self.duration_tiers(), start=1):
            if self.bonus_max_tier is not None and tier > self.bonus_max_tier:
                break
            if rate_year > threshold:
                rate = tier_rate
        return rate if rate > 0 else 0.0

    def guaranteed(self) -> "BonusConfig":
        """Return the bonus config used by the guaranteed projection."""
        return BonusConfig(
            bonus_dur_rate=self.bonus_dur_rate_guar,
            bonus_dur_threshold=self.bonus_dur_threshold,
            bonus_av_rate=self.bonus_av_rate_guar,
            bonus_av_threshold=self.bonus_av_threshold,
            bonus_dur_cap_to_excess_over_guar=self.bonus_dur_cap_to_excess_over_guar,
            bonus_dur_rate2=self.bonus_dur_rate2_guar,
            bonus_dur_threshold2=self.bonus_dur_threshold2,
            bonus_conditional=self.bonus_conditional,
            bonus_max_tier=self.bonus_max_tier,
        )

    def with_excess_cap(self, fixed_rate: float, guaranteed_rate: float) -> "BonusConfig":
        """Apply the New York cap: ``min(bonus_dur_rate, max(0, fixed - GINT))``.

        A no-op for plans without ``BonusDurCapToExcessOverGuar``. The capped
        rate is one scalar per run, added to every crediting rate (declared/UK
        and blended/UP alike), as in RERUN.
        """
        if not self.bonus_dur_cap_to_excess_over_guar:
            return self
        # Round away binary noise (0.031 - 0.025 = 0.006000000000000002).
        excess = round(max(0.0, float(fixed_rate) - float(guaranteed_rate)), 12)
        return replace(self, bonus_dur_rate=min(self.bonus_dur_rate, excess),
                       bonus_dur_rate2=min(self.bonus_dur_rate2, excess))

    def capped_for(self, policy) -> "BonusConfig":
        """:meth:`with_excess_cap` at the policy's fixed account rate and GINT.

        Pass the policy on the basis being projected: the guaranteed-basis
        policy's fixed rate is GINT, so a capped guaranteed bonus is zero.
        """
        if not self.bonus_dur_cap_to_excess_over_guar:
            return self
        return self.with_excess_cap(
            fixed_account_rate(policy), policy.guaranteed_interest_rate or 0.0)


def fixed_account_rate(policy) -> float:
    """RERUN ``sINPUT_Fixed_Int_Rate`` — the rate the NY bonus cap measures.

    IUL: the fixed-strategy illustrated rate (``iul_declared_rate``, the WAIR
    declared rate), defaulting to GINT exactly as ``build_iul_context`` does.
    Declared-rate plans: the illustrated current rate.
    """
    if load_index_strategies(policy.plancode) is None:
        return float(policy.current_interest_rate or 0.0)
    declared = getattr(policy, "iul_declared_rate", None)
    if declared is None:
        return float(policy.guaranteed_interest_rate or 0.0)
    return float(declared)


def _load_table() -> List[dict]:
    """Load and cache the tRates_IntBonus JSON table."""
    global _CACHE, _CACHE_MTIME_NS
    mtime_ns = _TABLE_PATH.stat().st_mtime_ns
    if _CACHE is None or _CACHE_MTIME_NS != mtime_ns:
        with open(_TABLE_PATH, "r", encoding="utf-8") as f:
            _CACHE = json.load(f)
        _CACHE_MTIME_NS = mtime_ns
    return _CACHE


def load_bonus_config(plancode: str, valuation_date: date) -> BonusConfig:
    """Load the bonus configuration effective as of the valuation date.

    Finds the entry for the given plancode with the latest EffectiveDate
    that is on or before the valuation date.

    Args:
        plancode: Product plan code (e.g., "1U143900").
        valuation_date: Policy valuation date.

    Returns:
        BonusConfig with resolved rates. All zeros if no entry found.
    """
    table = _load_table()
    normalized_plancode = str(plancode or "").strip().upper()

    # Filter for this plancode
    entries = [
        row for row in table
        if str(row.get("Plancode", "")).strip().upper() == normalized_plancode
    ]
    if not entries:
        return BonusConfig()

    # Sort by effective date descending to find latest applicable
    entries.sort(key=lambda r: r["EffectiveDate"], reverse=True)

    for entry in entries:
        eff = date.fromisoformat(entry["EffectiveDate"])
        if eff <= valuation_date:
            return BonusConfig(
                bonus_dur_rate=float(entry.get("BonusDurRate", 0)),
                bonus_dur_threshold=int(entry.get("BonusDurThreshold", 0)),
                bonus_av_rate=float(entry.get("BonusAVRate", 0)),
                bonus_av_threshold=float(entry.get("BonusAVThreshold", 0)),
                bonus_dur_rate_guar=float(entry.get("BonusDurRateGuar", 0)),
                bonus_av_rate_guar=float(entry.get("BonusAVRateGuar", 0)),
                bonus_dur_cap_to_excess_over_guar=bool(
                    entry.get("BonusDurCapToExcessOverGuar", False)),
                bonus_dur_rate2=float(entry.get("BonusDurRate2", 0)),
                bonus_dur_threshold2=int(entry.get("BonusDurThreshold2", 0)),
                bonus_dur_rate2_guar=float(entry.get("BonusDurRate2Guar", 0)),
                bonus_conditional=bool(entry.get("BonusConditional", False)),
            )

    return BonusConfig()
