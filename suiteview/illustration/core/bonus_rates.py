"""Bonus interest rate loader — reads from tRates_IntBonus.json.

Replaces the UL_Rates DB bonus lookups (BONUSDUR / BONUSAV) with a
locally-maintained JSON table keyed by (Plancode, EffectiveDate).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional


_TABLE_PATH = Path(__file__).resolve().parent.parent / "plancodes" / "tRates_IntBonus.json"
_CACHE: Optional[List[dict]] = None


@dataclass
class BonusConfig:
    """Resolved bonus rates effective for a specific plancode and date."""

    bonus_dur_rate: float = 0.0
    bonus_dur_threshold: int = 0
    bonus_av_rate: float = 0.0
    bonus_av_threshold: float = 0.0


def _load_table() -> List[dict]:
    """Load and cache the tRates_IntBonus JSON table."""
    global _CACHE
    if _CACHE is None:
        with open(_TABLE_PATH, "r") as f:
            _CACHE = json.load(f)
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

    # Filter for this plancode
    entries = [row for row in table if row["Plancode"] == plancode]
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
            )

    return BonusConfig()
