"""IUL index-strategy definitions and blended-rate math.

Data ships in ``plancodes/index_strategies.json`` (ported from the RERUN
workbook by ``tools/extract_index_strategies.py``). A plancode with a row in
that table is an IUL plan illustrated with a **blended crediting rate**: the
user allocates premium across strategies, each carries an illustrated rate
(index strategies default to the 6.25% placeholder capped at the AG49 maximum;
the fixed strategy defaults to the plan guaranteed rate), and the engine
credits one blended rate — RERUN INPUT rows 36–54 / CalcEngine UO–UQ.

Blend formulas (RERUN INPUT!B52 / E52 / B53):
  nominal     = TRUNC(Σ alloc% × illustrated rate, 4)
  effective   = same, but the multiplier strategies (IP/IR) contribute
                rate × (1 + multiplier) when the AG49 index allows (≤ 2)
  guaranteed  = fixed-strategy alloc % × plan GINT — index strategies
                guarantee a 0% floor
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

_DATA_PATH = Path(__file__).resolve().parent.parent / "plancodes" / "index_strategies.json"
_DATA_CACHE: Optional[dict] = None
_PLAN_CACHE: Dict[str, Optional["PlanIndexStrategies"]] = {}

FIXED_FUND_ID = "U1"
SWEEP_FUND_ID = "SW"

# Placeholder illustrated rate for index strategies until the illustrated-rate
# table is wired (per Robert, 2026-07-08). Fixed/sweep funds credit the plan
# guaranteed rate instead.
DEFAULT_INDEX_ILLUSTRATED_RATE = 0.0625


@dataclass(frozen=True)
class StrategyInfo:
    """One allocation strategy as offered on a specific IUL plan."""

    fund_id: str
    label: str
    max_rate: Optional[float]      # AG49 maximum illustrated rate; None = not offered
    parameter: Optional[float]     # current cap / participation (informational)
    multiplier: float = 0.0        # IP/IR account-value multiplier
    asset_charge: float = 0.0      # IP/IR annual asset charge on AV

    @property
    def is_offered(self) -> bool:
        return bool(self.max_rate)

    @property
    def is_multiplier(self) -> bool:
        return self.multiplier > 0.0


@dataclass(frozen=True)
class BlendedRates:
    """The three INPUT-sheet blend scalars plus the engine's asset-charge rate."""

    nominal: float
    effective: float
    guaranteed: float
    asset_charge_rate: float   # Σ IP/IR alloc × asset charge (0 when AG49 disallows)


@dataclass(frozen=True)
class PlanIndexStrategies:
    """Index-strategy configuration for one IUL plancode."""

    plancode: str
    product: str
    strategies: List[StrategyInfo]
    ag49_index: int
    loan_credit_spread: float

    def strategy(self, fund_id: str) -> Optional[StrategyInfo]:
        for strat in self.strategies:
            if strat.fund_id == fund_id:
                return strat
        return None

    def default_rates(self, gint: Optional[float] = None) -> Dict[str, float]:
        """Illustrated-rate defaults per strategy.

        Index strategies default to the 6.25% placeholder, capped at the AG49
        maximum. The fixed strategy defaults to the plan guaranteed rate when
        ``gint`` is given (falling back to its table rate otherwise).
        """
        defaults: Dict[str, float] = {}
        for s in self.strategies:
            if not s.is_offered:
                continue
            if s.fund_id == FIXED_FUND_ID:
                defaults[s.fund_id] = float(gint) if gint else float(s.max_rate)
            else:
                defaults[s.fund_id] = min(
                    DEFAULT_INDEX_ILLUSTRATED_RATE, float(s.max_rate))
        return defaults

    def default_allocations(self) -> Dict[str, float]:
        """100% fixed strategy — the safe default when no inforce allocation loads."""
        return {FIXED_FUND_ID: 1.0}

    @property
    def multiplier_active(self) -> bool:
        """Multiplier crediting/charges apply only under the early AG49 regimes."""
        return self.ag49_index <= 2


def _trunc4(value: float) -> float:
    """Excel TRUNC(value, 4) for the non-negative rates used here.

    Excel truncates its 15-significant-digit value, so a product like
    0.06 x 1.24 truncates to 0.0744 — not the binary-float 743.999… floor.
    Rounding away sub-1e-6 noise first mirrors that.
    """
    return math.floor(round(value * 10000.0, 6)) / 10000.0


def _load_data() -> dict:
    global _DATA_CACHE
    if _DATA_CACHE is None:
        with open(_DATA_PATH, "r", encoding="utf-8") as fh:
            _DATA_CACHE = json.load(fh)
    return _DATA_CACHE


def load_index_strategies(plancode: str) -> Optional[PlanIndexStrategies]:
    """Strategy configuration for ``plancode``, or None for a non-IUL plan."""
    plancode = (plancode or "").strip()
    if plancode in _PLAN_CACHE:
        return _PLAN_CACHE[plancode]

    data = _load_data()
    row = data.get("plancodes", {}).get(plancode)
    if row is None:
        _PLAN_CACHE[plancode] = None
        return None

    rates = row.get("illustrated_rates", {})
    params = row.get("strategy_parameters", {})
    multipliers = data.get("multiplier_strategies", {})
    strategies = []
    for entry in data.get("strategies", []):
        fund_id = entry["fund_id"]
        mult = multipliers.get(fund_id, {})
        strategies.append(StrategyInfo(
            fund_id=fund_id,
            label=entry["label"],
            max_rate=rates.get(fund_id),
            parameter=params.get(fund_id),
            multiplier=float(mult.get("multiplier") or 0.0),
            asset_charge=float(mult.get("asset_charge") or 0.0),
        ))

    ag49 = data.get("ag49", {})
    ag49_index = int(ag49.get("default_index", 2))
    spreads = ag49.get("loan_credit_spread_by_index", [0.0])
    spread = float(spreads[min(ag49_index, len(spreads)) - 1])

    plan = PlanIndexStrategies(
        plancode=plancode,
        product=row.get("product", ""),
        strategies=strategies,
        ag49_index=ag49_index,
        loan_credit_spread=spread,
    )
    _PLAN_CACHE[plancode] = plan
    return plan


def is_iul_plan(plancode: str) -> bool:
    return load_index_strategies(plancode) is not None


# ── AG49 regimes ──────────────────────────────────────────────
#
# RERUN Rates_Control CR78:CS83: the AG49 regime is looked up by policy issue
# date (Prior to AG49 / AG49 2015-09-01 / AG49A 2020-11-25 / AG49B 2023-05-01).
# CP79 floors RERUN's applicable index at 2 — even a pre-AG49 policy is
# illustrated under at least the original AG49 rules. The index gates the
# IP/IR multiplier crediting and asset charge (≤ 2 only) and selects the
# variable-loan credit spread (CP80 CHOOSE list).

def ag49_regimes() -> List[dict]:
    """The regime table: [{index, name, start: date}] ascending by start."""
    regimes = []
    for row in _load_data().get("ag49", {}).get("regimes", []):
        start = datetime.strptime(row["start"], "%Y-%m-%d").date()
        regimes.append({"index": int(row["index"]), "name": row["name"], "start": start})
    return regimes


def ag49_index_for_issue_date(issue_date: Optional[date]) -> int:
    """RERUN's applicable AG49 index for a policy: MAX(2, issue-date tier)."""
    regimes = ag49_regimes()
    if not regimes:
        return 2
    tier = regimes[0]["index"]
    if issue_date is not None:
        for regime in regimes:
            if issue_date >= regime["start"]:
                tier = regime["index"]
    return max(2, tier)


def current_ag49_index() -> int:
    """The latest regime's index — illustrating under today's rules."""
    regimes = ag49_regimes()
    return regimes[-1]["index"] if regimes else 2


def loan_credit_spread_for_index(ag49_index: int) -> float:
    """Variable-loan credit spread for an AG49 index (Rates_Control CP80)."""
    spreads = _load_data().get("ag49", {}).get("loan_credit_spread_by_index", [0.0])
    return float(spreads[min(max(ag49_index, 1), len(spreads)) - 1])


def plan_with_ag49_index(plan: PlanIndexStrategies, ag49_index: int) -> PlanIndexStrategies:
    """A copy of ``plan`` re-based on ``ag49_index`` (spread follows the index)."""
    if ag49_index == plan.ag49_index:
        return plan
    return replace(plan, ag49_index=ag49_index,
                   loan_credit_spread=loan_credit_spread_for_index(ag49_index))


def compute_blended_rates(
    plan: PlanIndexStrategies,
    allocations: Dict[str, float],
    rates: Dict[str, float],
    gint: float,
) -> BlendedRates:
    """The INPUT-sheet blend scalars from allocation % and illustrated rates.

    ``allocations`` and ``rates`` are decimal-form (0.25 = 25%), keyed by
    fund ID; strategies missing from either dict contribute zero.
    """
    nominal = 0.0
    effective = 0.0
    asset_charge = 0.0
    for strat in plan.strategies:
        alloc = float(allocations.get(strat.fund_id, 0.0) or 0.0)
        rate = float(rates.get(strat.fund_id, 0.0) or 0.0)
        if alloc <= 0.0:
            continue
        nominal += alloc * rate
        if strat.is_multiplier and plan.multiplier_active:
            effective += alloc * rate * (1.0 + strat.multiplier)
            asset_charge += alloc * strat.asset_charge
        else:
            effective += alloc * rate
    guaranteed = float(allocations.get(FIXED_FUND_ID, 0.0) or 0.0) * float(gint or 0.0)
    return BlendedRates(
        nominal=_trunc4(nominal),
        effective=_trunc4(effective),
        guaranteed=guaranteed,
        asset_charge_rate=asset_charge,
    )


def allocation_problems(
    plan: PlanIndexStrategies,
    allocations: Dict[str, float],
    rates: Dict[str, float],
) -> List[str]:
    """Validation messages mirroring the INPUT sheet's checks (empty = valid).

    - allocations must total exactly 100%
    - an allocation to a strategy the plan does not offer is invalid
    - an illustrated rate above the strategy's AG49 maximum is invalid
    """
    problems: List[str] = []
    total = sum(float(v or 0.0) for v in allocations.values())
    if abs(total - 1.0) > 1e-9:
        problems.append(f"Allocations total {total * 100:.2f}% — must equal 100%.")
    for strat in plan.strategies:
        alloc = float(allocations.get(strat.fund_id, 0.0) or 0.0)
        rate = float(rates.get(strat.fund_id, 0.0) or 0.0)
        if alloc > 0.0 and not strat.is_offered:
            problems.append(
                f"{strat.fund_id} ({strat.label}) is not available on this plan.")
        if strat.is_offered and rate > float(strat.max_rate) + 1e-9:
            problems.append(
                f"{strat.fund_id} illustrated rate {rate * 100:.2f}% exceeds the "
                f"current illustrated rate {float(strat.max_rate) * 100:.2f}%.")
    return problems
