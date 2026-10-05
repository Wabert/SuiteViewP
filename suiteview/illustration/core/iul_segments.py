"""IUL segment ("bucket") crediting — a development-only account-value method.

The blended method credits one rate to the whole account value. This method
follows CyberLife's account structure instead (IUL14 Series product
specification, "Accounts / Policy Value" and "Deduction Hierarchy"):

* Net premium goes to the **Sweep Account**, which earns the declared rate.
* Each monthliversary the sweep value above the **Sweep Account Minimum**
  (12 x last month's monthly deduction) moves to the Fixed Account and to new
  one-year **Indexed Segments** by the premium allocation percentages.
  CyberLife sweeps on the 1st of the calendar month; this model sweeps on the
  monthliversary (Robert Haessly's 2026-10-05 simplification).
* A segment earns nothing until it matures twelve months later, when it is
  credited at the illustrated rate locked on its start date. Maturing value
  first refills the sweep account to its minimum (in deduction-hierarchy order
  across strategies); the rest renews in the same strategy, in the same new
  segment that receives that month's sweep money.
* Charges, withdrawals, fixed-loan collateral (including capitalized loan
  interest) and force-outs are drawn Sweep -> Fixed -> each index strategy in
  the product's hierarchy order, newest segment first (LIFO). An amount drawn
  from a segment forfeits its index credit.
* Loan repayments release collateral to the sweep account. Interest credited
  on loan collateral is paid to the sweep account (modelling assumption).

The engine keeps every other calculation (NAR, COI, MD, surrender charge,
loan interest, lapse); it reads the account total, which this module keeps
equal to the engine AV. See ``docs/Illustration_UL/IUL_SEGMENT_CREDITING.md``.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Dict, List, Optional, Tuple

from dateutil.relativedelta import relativedelta

from suiteview.illustration.constants import DAYS_PER_YEAR, MONEY_EPSILON
from suiteview.illustration.models.index_strategies import (
    FIXED_FUND_ID,
    SWEEP_FUND_ID,
    load_index_strategies,
    plan_with_ag49_index,
    with_current_index_data,
)

# Default allocation when the policy carries none (product specifications:
# "100% to the One-Year Point-to-Point with 0% Floor Indexed Strategy").
DEFAULT_INDEX_FUND_ID = "IX"

# Index strategies in deduction-hierarchy order (after Sweep and Fixed), by
# product family. Source: Product Specification [IUL14 Series].pdf, p.13.
# Further products are added only after their hierarchy is validated.
_HIERARCHY_BY_PRODUCT_PREFIX: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("IUL14", ("IS", "IC", "IF", "IX")),
)

SEGMENT_TERM_MONTHS = 12

ACCOUNT_SWEEP = "Sweep"
ACCOUNT_FIXED = "Fixed"
ACCOUNT_COLLATERAL = "Collateral"


def segment_hierarchy(product: str) -> Optional[Tuple[str, ...]]:
    """Index strategies in deduction order for ``product``, or None if unsupported."""
    name = (product or "").strip().upper()
    for prefix, order in _HIERARCHY_BY_PRODUCT_PREFIX:
        if name.startswith(prefix):
            return order
    return None


@dataclass(frozen=True)
class IndexSegment:
    """One open indexed segment (CyberLife fund value phase)."""

    segment_id: int
    fund_id: str
    start_date: date
    maturity_date: date
    value: float
    rate: float          # annual index credit locked on the start date
    slot: int            # policy month (1-12) the segment matures/renews in
    seeded: bool = False  # loaded from the inforce record, not created by the run


@dataclass(frozen=True)
class SegmentAccounts:
    """Account balances at one point in time."""

    sweep: float = 0.0
    fixed: float = 0.0
    collateral: float = 0.0
    segments: Tuple[IndexSegment, ...] = ()
    sweep_min: float = 0.0
    next_segment_id: int = 1

    @property
    def index_total(self) -> float:
        return sum(seg.value for seg in self.segments)

    @property
    def total(self) -> float:
        return self.sweep + self.fixed + self.collateral + self.index_total

    def fund_total(self, fund_id: str) -> float:
        return sum(seg.value for seg in self.segments if seg.fund_id == fund_id)


@dataclass(frozen=True)
class SegmentEvent:
    """One account movement, for the Segment Ledger debug view."""

    date: Optional[date]
    step: str
    account: str          # Sweep / Fixed / Collateral / fund ID
    event: str
    amount: float         # signed: + into the account, - out of it
    balance_after: float
    segment_id: Optional[int] = None
    segment_start: Optional[date] = None
    rate: Optional[float] = None
    note: str = ""


@dataclass(frozen=True)
class SegmentCreditingContext:
    """Per-run inputs for segment crediting, resolved once in ``project()``."""

    product: str
    hierarchy: Tuple[str, ...]
    allocations: Dict[str, float]      # decimal fractions by fund ID, sums to 1
    index_rates: Dict[str, float]      # annual credit locked on new segments
    asset_charges: Dict[str, float]    # charge on each new segment's amount
    declared_rate: float               # sweep / fixed account rate (before bonus)
    guaranteed_basis: bool


def build_segment_context(policy, options, iul_ctx) -> Optional[SegmentCreditingContext]:
    """Resolve the run's segment crediting context; None when the option is off."""
    if not getattr(options, "iul_segment_crediting", False):
        return None
    from suiteview.core.build_env import has_developer_access

    if not has_developer_access():
        raise ValueError(
            "IUL segment crediting is available only when SuiteView runs from source "
            "(development mode).")
    if getattr(options, "iul_wair_crediting", False):
        raise ValueError("IUL segment crediting and WAIR crediting cannot both be selected.")
    if options.interim_opening is not None:
        raise ValueError("IUL segment crediting does not support an interim opening value.")
    plan = load_index_strategies(policy.plancode)
    if plan is None or iul_ctx is None:
        raise ValueError(
            f"IUL segment crediting requires an IUL plan; {policy.plancode} has no "
            "index strategies.")
    hierarchy = segment_hierarchy(plan.product)
    if hierarchy is None:
        raise ValueError(
            f"IUL segment crediting is configured for IUL14 products only; "
            f"{policy.plancode} is {plan.product}.")
    plan = plan_with_ag49_index(
        with_current_index_data(
            plan, policy.index_illustration_rates, policy.index_strategy_parameters),
        iul_ctx.ag49_index)
    allocations = normalized_allocations(policy.premium_allocations)
    unknown = sorted(
        fund for fund in allocations
        if fund not in hierarchy and fund != FIXED_FUND_ID)
    if unknown:
        raise ValueError(
            f"Allocation to {', '.join(unknown)} has no place in the {plan.product} "
            "deduction hierarchy.")
    rates = dict(plan.default_rates(policy.guaranteed_interest_rate))
    rates.update({
        str(fund): float(rate)
        for fund, rate in (policy.index_illustration_rates or {}).items()
        if rate is not None
    })
    guaranteed = bool(getattr(options, "guaranteed_assumption", False))
    index_rates: Dict[str, float] = {}
    asset_charges: Dict[str, float] = {}
    for fund in hierarchy:
        strategy = plan.strategy(fund)
        rate = 0.0 if guaranteed else float(rates.get(fund, 0.0) or 0.0)
        charge = 0.0
        if strategy is not None and strategy.is_multiplier and plan.multiplier_active:
            rate *= 1.0 + strategy.multiplier
            charge = strategy.asset_charge
        index_rates[fund] = rate
        asset_charges[fund] = charge
    return SegmentCreditingContext(
        product=plan.product,
        hierarchy=hierarchy,
        allocations=allocations,
        index_rates=index_rates,
        asset_charges=asset_charges,
        declared_rate=iul_ctx.declared_rate,
        guaranteed_basis=guaranteed,
    )


def normalized_allocations(allocations: Optional[Dict[str, float]]) -> Dict[str, float]:
    """Positive allocations as decimal fractions summing to 1 (sweep excluded).

    DB2 allocations may arrive in percent form; scaling by the total handles
    both. No allocation means the product default (100% IX).
    """
    cleaned = {
        str(fund).strip(): float(value)
        for fund, value in (allocations or {}).items()
        if value is not None and float(value) > 0.0 and str(fund).strip() != SWEEP_FUND_ID
    }
    total = sum(cleaned.values())
    if total <= 0.0:
        return {DEFAULT_INDEX_FUND_ID: 1.0}
    return {fund: value / total for fund, value in cleaned.items()}


def segment_maturity(start: date) -> date:
    return start + relativedelta(months=SEGMENT_TERM_MONTHS)


def seed_accounts(
    *,
    context: SegmentCreditingContext,
    account_value: float,
    fund_values: Dict[str, float],
    fund_segments,
    collateral: float,
    sweep_min: float,
    valuation_date: date,
    slot_for_date,
) -> Tuple[SegmentAccounts, List[SegmentEvent]]:
    """Opening accounts from the inforce record.

    ``fund_segments`` are the open index segments (fund, start date, value).
    Index fund value without segment detail opens as one segment started on
    the valuation date. Any difference between the record's funds and the
    starting account value is placed in the sweep account and reported.
    """
    events: List[SegmentEvent] = []
    segments: List[IndexSegment] = []
    next_id = 1
    detailed = {str(seg.fund_id).strip() for seg in fund_segments}
    for seg in sorted(fund_segments, key=lambda item: (item.start_date, item.fund_id)):
        fund = str(seg.fund_id).strip()
        maturity = segment_maturity(seg.start_date)
        segments.append(IndexSegment(
            segment_id=next_id, fund_id=fund, start_date=seg.start_date,
            maturity_date=maturity, value=float(seg.value),
            rate=context.index_rates.get(fund, 0.0),
            slot=slot_for_date(maturity), seeded=True,
        ))
        next_id += 1
    for fund, value in sorted(fund_values.items()):
        fund = str(fund).strip()
        if fund in (SWEEP_FUND_ID, FIXED_FUND_ID) or fund in detailed or abs(value) <= MONEY_EPSILON:
            continue
        maturity = segment_maturity(valuation_date)
        segments.append(IndexSegment(
            segment_id=next_id, fund_id=fund, start_date=valuation_date,
            maturity_date=maturity, value=float(value),
            rate=context.index_rates.get(fund, 0.0),
            slot=slot_for_date(maturity), seeded=True,
        ))
        events.append(SegmentEvent(
            valuation_date, "Seed", fund, "No segment detail", float(value), float(value),
            segment_id=next_id, segment_start=valuation_date,
            note="Fund total opened as one segment started on the valuation date."))
        next_id += 1
    accounts = SegmentAccounts(
        sweep=float(fund_values.get(SWEEP_FUND_ID, 0.0) or 0.0),
        fixed=float(fund_values.get(FIXED_FUND_ID, 0.0) or 0.0),
        collateral=float(collateral),
        segments=tuple(segments),
        sweep_min=float(sweep_min),
        next_segment_id=next_id,
    )
    difference = float(account_value) - accounts.total
    if abs(difference) > MONEY_EPSILON:
        accounts = replace(accounts, sweep=accounts.sweep + difference)
        events.append(SegmentEvent(
            valuation_date, "Seed", ACCOUNT_SWEEP, "Seeding difference", difference,
            accounts.sweep,
            note="Starting account value less sweep, fixed, segments and collateral."))
    return accounts, events


@dataclass
class _Totals:
    """Running per-month totals for the Accounts debug view."""

    values: Dict[str, float] = field(default_factory=dict)

    def add(self, key: str, amount: float) -> None:
        self.values[key] = self.values.get(key, 0.0) + amount


class SegmentMonth:
    """Mutable working copy of the accounts for one projected month."""

    def __init__(
        self,
        context: SegmentCreditingContext,
        accounts: SegmentAccounts,
        month_date: date,
        policy_month: int,
    ) -> None:
        self.context = context
        self.month_date = month_date
        self.policy_month = policy_month
        self.sweep = accounts.sweep
        self.fixed = accounts.fixed
        self.collateral = accounts.collateral
        self.segments: List[IndexSegment] = list(accounts.segments)
        self.sweep_min = accounts.sweep_min
        self.next_segment_id = accounts.next_segment_id
        self.events: List[SegmentEvent] = []
        self.totals = _Totals()
        self.opening = accounts
        self.maturity_interest = 0.0

    # ── state ────────────────────────────────────────────────

    @property
    def total(self) -> float:
        return self.sweep + self.fixed + self.collateral + sum(s.value for s in self.segments)

    def accounts(self) -> SegmentAccounts:
        return SegmentAccounts(
            sweep=self.sweep,
            fixed=self.fixed,
            collateral=self.collateral,
            segments=tuple(s for s in self.segments if abs(s.value) > MONEY_EPSILON),
            sweep_min=self.sweep_min,
            next_segment_id=self.next_segment_id,
        )

    def _event(self, step, account, event, amount, balance, seg=None, rate=None, note=""):
        self.events.append(SegmentEvent(
            self.month_date, step, account, event, amount, balance,
            segment_id=seg.segment_id if seg is not None else None,
            segment_start=seg.start_date if seg is not None else None,
            rate=rate, note=note))

    # ── maturity ─────────────────────────────────────────────

    def mature(self, bonus_rate: float) -> float:
        """Credit, refill the sweep from, and renew segments maturing this month.

        Returns the index interest credited.
        """
        maturing = [s for s in self.segments if s.maturity_date <= self.month_date]
        if not maturing:
            return 0.0
        self.segments = [s for s in self.segments if s.maturity_date > self.month_date]
        matured: Dict[str, float] = {}
        interest_total = 0.0
        for seg in maturing:
            rate = seg.rate + bonus_rate
            interest = max(0.0, seg.value * rate) if seg.value > 0.0 else 0.0
            interest_total += interest
            matured[seg.fund_id] = matured.get(seg.fund_id, 0.0) + seg.value + interest
            self._event("Maturity", seg.fund_id, "Index credit", interest, seg.value + interest,
                        seg=seg, rate=rate)
            self.totals.add(f"{seg.fund_id} Maturity Interest", interest)
        self.totals.add("Maturity Interest", interest_total)
        self.maturity_interest += interest_total
        need = max(0.0, self.sweep_min - self.sweep)
        for fund in self._ordered(matured):
            available = matured[fund]
            if need <= MONEY_EPSILON or available <= 0.0:
                continue
            refill = min(need, available)
            matured[fund] -= refill
            need -= refill
            self.sweep += refill
            self.totals.add("Refill to Sweep", refill)
            self._event("Maturity", ACCOUNT_SWEEP, f"Refill from {fund}", refill, self.sweep)
            self._event("Maturity", fund, "Refill sweep", -refill, matured[fund])
        for fund in self._ordered(matured):
            amount = matured[fund]
            if amount > MONEY_EPSILON:
                self.totals.add("Renewed", amount)
                self._add_to_new_segment(fund, amount, "Maturity", "Renewal")
            elif amount < -MONEY_EPSILON:
                self.sweep += amount
                self._event("Maturity", ACCOUNT_SWEEP, f"Negative {fund} maturity", amount, self.sweep)
        return interest_total

    def _ordered(self, by_fund: Dict[str, float]) -> List[str]:
        """Funds present in ``by_fund``, in deduction-hierarchy order."""
        order = [fund for fund in self.context.hierarchy if fund in by_fund]
        return order + sorted(f for f in by_fund if f not in self.context.hierarchy)

    def _add_to_new_segment(self, fund: str, amount: float, step: str, event: str) -> None:
        charge_rate = self.context.asset_charges.get(fund, 0.0)
        charge = amount * charge_rate if charge_rate > 0.0 else 0.0
        seg = next(
            (s for s in self.segments if s.fund_id == fund and s.start_date == self.month_date),
            None)
        if seg is None:
            seg = IndexSegment(
                segment_id=self.next_segment_id, fund_id=fund, start_date=self.month_date,
                maturity_date=segment_maturity(self.month_date), value=0.0,
                rate=self.context.index_rates.get(fund, 0.0), slot=self.policy_month,
            )
            self.next_segment_id += 1
            self.segments.append(seg)
        index = self.segments.index(seg)
        seg = replace(seg, value=seg.value + amount - charge)
        self.segments[index] = seg
        self._event(step, fund, event, amount, seg.value + charge, seg=seg, rate=seg.rate)
        if charge > 0.0:
            self.totals.add("Asset Charges", charge)
            self._event(step, fund, "Segment asset charge", -charge, seg.value, seg=seg,
                        rate=charge_rate)

    # ── cash flows ───────────────────────────────────────────

    def deposit(self, amount: float, step: str) -> None:
        """Money into the policy goes to the sweep account."""
        if amount <= 0.0:
            return
        self.sweep += amount
        self.totals.add("Sweep In", amount)
        self._event(step, ACCOUNT_SWEEP, "Deposit", amount, self.sweep)

    def draw(self, amount: float, step: str) -> None:
        """Take ``amount`` out of the accounts in deduction-hierarchy order."""
        remaining = amount
        if remaining <= 0.0:
            return
        self.totals.add(f"Draw {step}", amount)
        if self.sweep > 0.0:
            take = min(self.sweep, remaining)
            self.sweep -= take
            remaining -= take
            self.totals.add("Draw Sweep", take)
            self._event(step, ACCOUNT_SWEEP, "Draw", -take, self.sweep)
        if remaining > MONEY_EPSILON and self.fixed > 0.0:
            take = min(self.fixed, remaining)
            self.fixed -= take
            remaining -= take
            self.totals.add("Draw Fixed", take)
            self._event(step, ACCOUNT_FIXED, "Draw", -take, self.fixed)
        for fund in self.context.hierarchy:
            if remaining <= MONEY_EPSILON:
                break
            newest_first = sorted(
                (s for s in self.segments if s.fund_id == fund and s.value > 0.0),
                key=lambda s: (s.start_date, s.segment_id), reverse=True)
            for seg in newest_first:
                if remaining <= MONEY_EPSILON:
                    break
                take = min(seg.value, remaining)
                remaining -= take
                updated = replace(seg, value=seg.value - take)
                self.segments[self.segments.index(seg)] = updated
                self.totals.add(f"Draw {fund}", take)
                self._event(step, fund, "Draw (LIFO)", -take, updated.value, seg=updated)
        if remaining > MONEY_EPSILON:
            self.sweep -= remaining
            self.totals.add("Draw Sweep", remaining)
            self._event(step, ACCOUNT_SWEEP, "Draw beyond accounts", -remaining, self.sweep,
                        note="All accounts exhausted; the sweep account goes negative.")

    def sync_total(self, target_av: float, step: str) -> None:
        """Bring the account total to the engine AV after a cash-flow step."""
        difference = target_av - self.total
        if difference > MONEY_EPSILON:
            self.deposit(difference, step)
        elif difference < -MONEY_EPSILON:
            self.draw(-difference, step)

    def sync_collateral(self, target: float, step: str) -> None:
        """Move value between collateral and the accounts as fixed-loan principal changes."""
        change = target - self.collateral
        if change > MONEY_EPSILON:
            self.draw(change, step)
            self.collateral += change
            self.totals.add("Collateral In", change)
            self._event(step, ACCOUNT_COLLATERAL, "Loan collateral", change, self.collateral)
        elif change < -MONEY_EPSILON:
            self.collateral += change
            self.sweep -= change
            self.totals.add("Collateral Released", -change)
            self._event(step, ACCOUNT_COLLATERAL, "Collateral released", change, self.collateral)
            self._event(step, ACCOUNT_SWEEP, "Collateral released", -change, self.sweep)

    # ── sweep and interest ───────────────────────────────────

    def set_sweep_min(self, value: float) -> None:
        self.sweep_min = max(0.0, float(value))

    def sweep_out(self) -> None:
        """Move sweep value above the minimum to Fixed and new segments."""
        excess = self.sweep - self.sweep_min
        if excess <= MONEY_EPSILON:
            return
        self.sweep -= excess
        self.totals.add("Swept Out", excess)
        self._event("Sweep", ACCOUNT_SWEEP, "Sweep to allocations", -excess, self.sweep)
        allocations = self.context.allocations
        funds = list(allocations)
        allocated = 0.0
        for position, fund in enumerate(funds):
            # The last allocation takes the remainder so no cent is lost to rounding.
            amount = (excess - allocated) if position == len(funds) - 1 else excess * allocations[fund]
            allocated += amount
            if amount <= 0.0:
                continue
            if fund == FIXED_FUND_ID:
                self.fixed += amount
                self.totals.add("Fixed In", amount)
                self._event("Sweep", ACCOUNT_FIXED, "Sweep in", amount, self.fixed)
            else:
                self.totals.add(f"{fund} Swept In", amount)
                self._add_to_new_segment(fund, amount, "Sweep", "Sweep in")

    def credit_interest(
        self,
        declared_period_rate: float,
        declared_annual_rate: float,
        collateral_interest: float,
        step: str = "Interest",
    ) -> float:
        """Credit sweep/fixed interest and pay collateral interest to the sweep.

        Indexed segments earn nothing until they mature. Negative balances earn
        no interest. Returns the interest credited this call.
        """
        sweep_interest = max(0.0, self.sweep) * declared_period_rate
        fixed_interest = max(0.0, self.fixed) * declared_period_rate
        self.sweep += sweep_interest
        self.fixed += fixed_interest
        self.totals.add("Sweep Interest", sweep_interest)
        self.totals.add("Fixed Interest", fixed_interest)
        if sweep_interest:
            self._event(step, ACCOUNT_SWEEP, "Interest", sweep_interest, self.sweep,
                        rate=declared_annual_rate)
        if fixed_interest:
            self._event(step, ACCOUNT_FIXED, "Interest", fixed_interest, self.fixed,
                        rate=declared_annual_rate)
        if collateral_interest:
            self.sweep += collateral_interest
            self.totals.add("Collateral Interest", collateral_interest)
            self._event(step, ACCOUNT_SWEEP, "Loan collateral interest", collateral_interest,
                        self.sweep)
        return sweep_interest + fixed_interest + collateral_interest

    # ── output ───────────────────────────────────────────────

    def finish(self, engine_av: float) -> Dict[str, object]:
        """The month's ``MonthlyState.iul_segment_detail``."""
        accounts = self.accounts()
        summary = {
            "Sweep BOM": self.opening.sweep,
            "Fixed BOM": self.opening.fixed,
            "Collateral BOM": self.opening.collateral,
            "Index BOM": self.opening.index_total,
            **self.totals.values,
            "Sweep Min": self.sweep_min,
            "Sweep EOM": accounts.sweep,
            "Fixed EOM": accounts.fixed,
            "Collateral EOM": accounts.collateral,
            "Index EOM": accounts.index_total,
            "Accounts Total": accounts.total,
            "Engine AV": engine_av,
            "Difference": engine_av - accounts.total,
        }
        for fund in self.context.hierarchy:
            summary[f"{fund} EOM"] = accounts.fund_total(fund)
        return {"accounts": accounts, "events": list(self.events), "summary": summary}


def period_rate(annual_rate: float, days_in_month: float) -> float:
    """Monthly period rate on the engine's day basis (365/12 days = monthly compounding)."""
    return (1.0 + annual_rate) ** (days_in_month / DAYS_PER_YEAR) - 1.0


def opening_detail(accounts: SegmentAccounts, events: List[SegmentEvent], context) -> Dict[str, object]:
    """Month-zero detail for the inforce row."""
    summary = {
        "Sweep EOM": accounts.sweep,
        "Fixed EOM": accounts.fixed,
        "Collateral EOM": accounts.collateral,
        "Index EOM": accounts.index_total,
        "Sweep Min": accounts.sweep_min,
        "Accounts Total": accounts.total,
    }
    for fund in context.hierarchy:
        summary[f"{fund} EOM"] = accounts.fund_total(fund)
    return {"accounts": accounts, "events": list(events), "summary": summary}
