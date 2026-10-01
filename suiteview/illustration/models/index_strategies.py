"""IUL index-strategy definitions and blended-rate math.

The strategy catalog ships in ``plancodes/index_strategies.json`` (ported from
the RERUN workbook by ``tools/rerun/extract_index_strategies.py``). Current
illustration rates and effective strategy parameters are overlaid from
schema ``rates`` FUND rows when a policy loads. A plancode with a catalog row is
an IUL plan illustrated with a **blended crediting rate**:
the user allocates premium across strategies, each carries its current
illustrated rate, and the engine credits one blended rate — RERUN INPUT rows
36–54 / CalcEngine UO–UQ.

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
MARKET_INDEX_BY_FUND = {
    "IX": "SP500",
    "IF": "SP500",
    "IS": "SP500",
    "IC": "SP500",
    "IP": "SP500",
    "IR": "SP500",
    "NX": "NASDAQ100",
    "M1": "SPMARC5",
}

@dataclass(frozen=True)
class StrategyInfo:
    """One allocation strategy as offered on a specific IUL plan."""

    fund_id: str
    label: str
    max_rate: Optional[float]      # AG49 maximum illustrated rate; None = not offered
    parameter: Optional[float]     # current cap / participation (informational)
    multiplier: float = 0.0        # IP/IR account-value multiplier
    asset_charge: float = 0.0      # IP/IR annual asset charge on AV
    offered: bool = False          # plan catalog availability, independent of rate load
    parameter_label: str = ""

    @property
    def is_offered(self) -> bool:
        return self.offered

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

        Index strategies default to the current illustrated rate. The fixed
        strategy defaults to the plan guaranteed rate when ``gint`` is given
        (falling back to its catalog rate otherwise).
        """
        defaults: Dict[str, float] = {}
        for s in self.strategies:
            if not s.is_offered:
                continue
            if s.fund_id == FIXED_FUND_ID:
                defaults[s.fund_id] = float(gint) if gint else float(s.max_rate)
            elif s.max_rate is not None:
                defaults[s.fund_id] = float(s.max_rate)
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
            offered=rates.get(fund_id) is not None,
            parameter_label=_parameter_label(fund_id),
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


def with_current_index_data(
    plan: PlanIndexStrategies,
    illustration_rates: Optional[Dict[str, Optional[float]]],
    strategy_parameters: Optional[Dict[str, Dict[str, float]]],
) -> PlanIndexStrategies:
    """Overlay illustration-date UL_Rates data onto a strategy catalog plan.

    ``None`` means no database lookup was performed (tests/manual policies), so
    the extracted catalog values remain available. An empty mapping means the
    lookup ran but found nothing; affected values become missing and validation
    reports the gap rather than silently using stale catalog data.
    """
    if illustration_rates is None and strategy_parameters is None:
        return plan

    strategies: List[StrategyInfo] = []
    for strategy in plan.strategies:
        if strategy.fund_id == FIXED_FUND_ID:
            strategies.append(strategy)
            continue

        current_rate = strategy.max_rate
        if illustration_rates is not None:
            current_rate = illustration_rates.get(strategy.fund_id)

        parameter = strategy.parameter
        multiplier = strategy.multiplier
        asset_charge = strategy.asset_charge
        if strategy_parameters is not None:
            values = strategy_parameters.get(strategy.fund_id)
            if values is None:
                parameter = None
                multiplier = 0.0
                asset_charge = 0.0
            else:
                parameter = values[_parameter_field(strategy.fund_id)]
                multiplier = values["multiplier"]
                asset_charge = values["asset_fee"]

        strategies.append(replace(
            strategy,
            max_rate=current_rate,
            parameter=parameter,
            multiplier=multiplier,
            asset_charge=asset_charge,
            parameter_label=_parameter_label(strategy.fund_id),
        ))
    return replace(plan, strategies=strategies)


def _parameter_field(fund_id: str) -> str:
    return {
        "IS": "specified_rate",
        "IF": "int_rate_spread",
        "M1": "participation",
    }.get(fund_id, "cap")


def _parameter_label(fund_id: str) -> str:
    return {
        "IS": "Spec",
        "IF": "Spread",
        "M1": "Part",
    }.get(fund_id, "Cap")


def historical_credited_rate(
    fund_id: str,
    market_return: float,
    parameters: Dict[str, float],
) -> float:
    """Apply RERUN's historical-lookback formula for one strategy/year."""
    fund_id = (fund_id or "").strip().upper()
    market_return = float(market_return)
    if fund_id in {"IX", "IC", "NX"}:
        return max(0.0, min(market_return, parameters["cap"]))
    if fund_id == "IF":
        return max(0.0, market_return - parameters["int_rate_spread"])
    if fund_id == "IS":
        return parameters["specified_rate"] if market_return > 0.0 else 0.0
    if fund_id in {"IP", "IR"}:
        capped = max(0.0, min(market_return, parameters["cap"]))
        return (
            (capped * (1.0 + parameters["multiplier"]) + 1.0)
            * (1.0 - parameters["asset_fee"])
            - 1.0
        )
    if fund_id == "M1":
        return max(0.0, market_return) * parameters["participation"]
    raise ValueError(f"No historical crediting formula is defined for fund {fund_id!r}.")


def compound_yield(annual_returns: List[float]) -> float:
    """Geometric annual yield for a consecutive return series."""
    if not annual_returns:
        raise ValueError("At least one annual return is required.")
    product = 1.0
    for annual_return in annual_returns:
        if annual_return <= -1.0:
            raise ValueError("An annual return cannot be less than or equal to -100%.")
        product *= 1.0 + annual_return
    return product ** (1.0 / len(annual_returns)) - 1.0


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


def guaranteed_blended_rate(allocations: Dict[str, float], gint: float) -> float:
    """The guaranteed-basis blended crediting rate (RERUN INPUT!B53).

    On guaranteed assumptions every index strategy guarantees only a 0% floor,
    so the blended guaranteed rate is the *fixed*-strategy allocation × the plan
    guaranteed interest rate — the index slices contribute nothing. Example:
    25% fixed + 75% index at GINT 2.5% → 0.25 × 0.025 = 0.625%.

    ``allocations`` are keyed by fund ID and may arrive decimal (0.25) or
    percent (25) form; they are normalized by their total like the allocations
    panel does. Note this is the free-AV crediting rate only — loan collateral
    keeps earning its guaranteed loan credit rate (handled in
    ``core/interest_calc``), so a 6% guaranteed loan credit is unaffected even
    when this blend floors near 0%.
    """
    if not allocations or not gint:
        return 0.0
    total = sum(float(v or 0.0) for v in allocations.values())
    if total <= 0.0:
        return 0.0
    scale = 100.0 if total > 1.5 else 1.0
    fixed_alloc = float(allocations.get(FIXED_FUND_ID, 0.0) or 0.0) / scale
    return fixed_alloc * float(gint)


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
    return BlendedRates(
        nominal=_trunc4(nominal),
        effective=_trunc4(effective),
        guaranteed=guaranteed_blended_rate(allocations, gint),
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
        if strat.is_offered and strat.max_rate is None:
            problems.append(
                f"No current illustrated rate was found for {strat.fund_id} "
                f"({strat.label}) as of the illustration date.")
        if (
            strat.is_offered
            and strat.fund_id != FIXED_FUND_ID
            and strat.parameter is None
        ):
            problems.append(
                f"No current strategy parameters were found for {strat.fund_id} "
                f"({strat.label}) as of the illustration date.")
        if (
            strat.is_offered
            and strat.max_rate is not None
            and rate > float(strat.max_rate) + 1e-9
        ):
            problems.append(
                f"{strat.fund_id} illustrated rate {rate * 100:.2f}% exceeds the "
                f"current illustrated rate {float(strat.max_rate) * 100:.2f}%.")
    return problems
