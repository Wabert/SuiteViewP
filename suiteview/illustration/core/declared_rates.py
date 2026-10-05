"""Current declared crediting rate for fixed (declared-rate) UL plans.

Source: the plan's CIRF fund in UL_Rates schema ``rates`` (``RATE_ASSIGN_FUND`` ->
``RATE_VALUE_FUND``), current scale ``C``. The portfolio rate type ``CINT`` is used;
plans that only carry new-money/rollover rates use them when both agree. The latest
rate starting on or before the illustration date applies, floored at the guaranteed
rate. ``None`` means no usable CIRF rate is loaded, so callers keep the
guaranteed rate. RGA-reinsured policies (indicator ``R``) read the fund's ``R``
reinsurance block when one is loaded (CIRF ``<key> R``).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Optional, Sequence, Tuple

from suiteview.illustration.core.schema_reader import open_schema_reader
from suiteview.polview.models.schema_rates import resolve_plan

CIRF_FUND_TYPE = "CIRF"
PORTFOLIO_RATE_TYPE = "CINT"
NEW_MONEY_RATE_TYPES = ("CINT_NEW", "CINT_ROLL")
FIXED_FUND_CONTROL_TABLE = "LH_COV_FXD_FND_CTL"


def policy_guaranteed_rate(pi, plan_gint: Optional[float]) -> float:
    """A declared-rate UL policy's operative guaranteed crediting rate (decimal).

    CyberLife floors a declared-rate UL credit at the fixed fund's own guaranteed
    rate, ``LH_COV_FXD_FND_CTL.GUA_FND_ITS_RT`` (percent), not the plan GINT:
    1U135K00 U0482280/U0482386 credit 3.25% (fix R02, Robert 2026-10-01); the
    ANICO1996 4%-GINT plans guarantee 3.00% (3.25% Texas) after year 10 and
    PULU policies that never earned a bonus are credited exactly 3.00% (SR113413).
    ``LH_NON_TRD_POL.POL_GUA_ITS_RT`` is not that rate. With several fixed-fund rows
    the highest applies; with none the plan GINT does. Declared-rate UL only: IUL
    control rows include 6% loan-collateral funds."""
    rates = [
        float(row["GUA_FND_ITS_RT"])
        for row in pi.fetch_table(FIXED_FUND_CONTROL_TABLE) or []
        if row.get("GUA_FND_ITS_RT") is not None
    ]
    best = max(rates, default=0.0)
    return best / 100.0 if best > 0.0 else float(plan_gint or 0.0)


@dataclass(frozen=True)
class DeclaredRate:
    rate: float
    fund_key: str
    rate_type: str
    rate_start: date

    @property
    def source(self) -> str:
        return (f"CIRF {self.fund_key} {self.rate_type} current rate effective "
                f"{self.rate_start:%m/%d/%Y} (UL_Rates schema rates)")


def _latest(rates, rate_types: Sequence[str], as_of: date) -> Dict[str, Tuple[date, float]]:
    latest: Dict[str, Tuple[date, float]] = {}
    for rate in rates:
        if rate.scale != "C" or rate.rate_type not in rate_types or rate.rate_start > as_of:
            continue
        seen = latest.get(rate.rate_type)
        if seen is None or rate.rate_start > seen[0]:
            latest[rate.rate_type] = (rate.rate_start, float(rate.rate))
    return latest


def ul_current_declared_rate(
    company_code: str, plancode: str, as_of: date, guaranteed_rate: float,
    *, cint_key: str = "", rga_indicator: str = "", repo=None,
) -> Optional[DeclaredRate]:
    """Latest current-scale CIRF rate on ``as_of`` for one declared-rate UL plan.

    Reinsurance indicator ``R`` reads the CIRF fund's reinsurance block ``R``
    (CIRF ``<key> R``, e.g. ANICO2019 R); other policies read the direct block."""
    rein = "R" if (rga_indicator or "").strip().upper() == "R" else ""
    with open_schema_reader(repo) as reader:
        plan, _note = resolve_plan(reader.plan_defs(plancode), company_code)
        if plan is None:
            return None
        funds = [a for a in reader.fund_assignments(plan.company, plancode)
                 if a.fund_type == CIRF_FUND_TYPE]
        # CIRF publishes a '<key> R' block only where RGA-reinsured policies
        # are credited differently; elsewhere they share the direct block.
        blocks = {a.rein_block or "" for a in funds}
        block = rein if rein in blocks else ""
        funds = [a for a in funds if (a.rein_block or "") == block]
        key = str(cint_key or "").strip()
        preferred = [a for a in funds if a.fund_key == key or a.fund == key]
        funds = preferred or funds
        fund_keys = tuple(sorted({a.fund_key for a in funds}))
        if len(fund_keys) != 1:
            return None
        rates = reader.fund_rates(fund_keys)
    portfolio = _latest(rates, (PORTFOLIO_RATE_TYPE,), as_of)
    if portfolio:
        start, value = portfolio[PORTFOLIO_RATE_TYPE]
        rate_type = PORTFOLIO_RATE_TYPE
    else:
        new_money = _latest(rates, NEW_MONEY_RATE_TYPES, as_of)
        if not new_money or len({value for _start, value in new_money.values()}) != 1:
            return None
        start = max(start for start, _value in new_money.values())
        value = next(iter(new_money.values()))[1]
        rate_type = "/".join(sorted(new_money))
    return DeclaredRate(max(value, float(guaranteed_rate)), fund_keys[0], rate_type, start)
