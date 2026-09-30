"""Monthly par whole life projection from the in-force record.

The projection starts at the valuation date (the monthliversary CyberLife values are
processed to, on or after the last anniversary) and steps one monthliversary at a
time. Rules reproduced from CyberLife records (see ``docs/Illustration_UL/RERUN_MANUAL.md``
"RERUN participating whole life"):

* **Anniversary order** - deposit interest on the existing balance, the dividend
  earned for the completed year, its application, OYT renewal, loan interest
  (advance interest for the coming year, or arrears interest capitalized), then
  premiums and requested transactions of the day.
* **Dividends** - per coverage, ``round(units x cash rate, 2)`` plus, on paid-up
  additions, ``round(round(additions / 1000, 3) x PUA cash rate, 2)``. The PUA and OYT
  faces they buy come from the same per-unit dividend file values
  (``PUA/OYT per 1,000 of additions = trunc4(PUA cash x base PUA / base cash)``). On a
  PUA rider, the additions its own premium-bought PUAs buy that anniversary share in
  the rider's dividend-PUA dividend (CyberLife 000282131, 2025 and 2026).
* **Values on a monthliversary k months into policy year y** - base cash value
  ``units x round((CV[y-1] x (12-k) + CV[y] x k) / 12, 2)``; additions
  ``round(additions / 1000 x (NSP[x] x (12-k) + NSP[x+1] x k) / 12, 2)`` with ``x`` the
  attained age at the year's start (CyberLife 62Q1 quote). Reduced paid-up insurance is
  valued the same way at the coverage's RPU NSP basis.
* **Loans** - interest in advance: ``principal / (1 - r)`` at each anniversary, the
  interest unearned until the next anniversary refunded on payoff; in arrears:
  ``principal x r x months / 12`` accrued and capitalized at the anniversary.
* **Deposits** - ``round(balance x rate, 2)`` credited at the anniversary before the
  new dividend is added.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Tuple

from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.parwl.nsp import interpolated_nsp, net_single_premium
from suiteview.illustration.core.parwl.premiums import modal_premium, policy_mode, record_premium_date
from suiteview.illustration.core.parwl.rates import DividendRateSet, ParWLRateError, ParWLRates
from suiteview.illustration.models.parwl import (
    OYT_OPTIONS,
    ROLE_BASE,
    ROLE_TERM_RIDER,
    ParWLCoverage,
    ParWLInputs,
    ParWLMonth,
    ParWLPolicy,
    ParWLResult,
    ParWLYear,
)

CENT = Decimal("0.01")
NO_DIVIDEND_OPTIONS = frozenset({"", "0", "9"})
SUPPORTED_OPTIONS = frozenset({"1", "2", "3", "4", "5", "6", "7", "8"})


class ParWLProjectionError(ValueError):
    """The projection cannot continue (explains why)."""


def cents(value) -> float:
    """Half-up rounding to cents, as CyberLife rounds."""
    return float(Decimal(repr(float(value))).quantize(CENT, rounding=ROUND_HALF_UP))


def thousands3(amount: float) -> float:
    """Additions in thousands rounded to 3 decimals (CyberLife PUA_UNT_QTY)."""
    return float(Decimal(repr(float(amount) / 1000.0)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def add_months(start: date, months: int, day: int) -> date:
    target = start + relativedelta(months=months)
    return date(target.year, target.month, min(day, calendar.monthrange(target.year, target.month)[1]))


def completed_months(issue_date: date, when: date) -> int:
    delta = relativedelta(when, issue_date)
    return delta.years * 12 + delta.months


@dataclass
class _Additions:
    """A mutable paid-up additions group (one coverage phase and purchase source)."""

    phase: int
    source: str
    amount: float
    table: str
    interest: float
    nfo_code: str = "5"


@dataclass
class _Loan:
    principal: float = 0.0
    rate: float = 0.0
    in_advance: bool = True
    accrued: float = 0.0          # arrears interest not yet capitalized
    unearned: float = 0.0         # advance interest not yet earned
    unearned_months: int = 0


@dataclass
class _State:
    units: float
    rpu: bool
    premium_paying: bool
    waiver: bool
    additions: List[_Additions]
    oyt_face: float
    oyt_expiry: Optional[date]
    deposits: float
    loan: _Loan
    option: str
    secondary: str
    premium_credit: float = 0.0
    lapsed: bool = False
    notes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class DividendPiece:
    """One source of an anniversary dividend: units x per-unit cash, PUA and OYT values."""

    kind: str                     # base / additions / rider / rider additions
    phase: int
    source: str                   # CyberLife PTP_SRC_IND: 0 coverage units, 1 additions
    units: float                  # coverage units, or additions in thousands (3 decimals)
    cash_rate: float
    pua_rate: float
    oyt_rate: float

    @property
    def cash(self) -> float:
        return cents(self.units * self.cash_rate)

    @property
    def pua(self) -> float:
        return cents(self.units * self.pua_rate)

    @property
    def oyt(self) -> float:
        return cents(self.units * self.oyt_rate)


class ParWLEngine:
    """Project one par WL policy monthly; ``run`` returns current and guaranteed runs."""

    def __init__(self, policy: ParWLPolicy, rates: ParWLRates, inputs: Optional[ParWLInputs] = None):
        self.policy = policy
        self.rates = rates
        self.inputs = inputs or ParWLInputs()
        self.base = policy.base
        self.day = self.base.issue_date.day
        self.notes: List[str] = list(policy.notes) + list(rates.notes)
        self._validate()
        self.premium_adjustment = self._premium_adjustment()
        self.rider_units_include_purchase = self._rider_units_rule()
        self.rider_dividends_to_additions = self._rider_dividends_rule()
        self.direct_recognition = self._direct_recognition_phases()
        self.rider_duration_offset = self._rider_duration_offset()

    # -- setup ----------------------------------------------------------------------

    def _validate(self) -> None:
        if self.policy.is_eti:
            raise ParWLProjectionError(
                "The policy is on extended term insurance; ETI policies are not illustrated.")
        if self.policy.valuation_date < self.policy.last_anniversary:
            raise ParWLProjectionError("The valuation date is before the last anniversary.")
        option = self._start_option()
        if option not in SUPPORTED_OPTIONS | NO_DIVIDEND_OPTIONS:
            raise ParWLProjectionError(f"Dividend option {option} is not illustrated.")
        for change in self.inputs.option_changes:
            if change.option not in SUPPORTED_OPTIONS:
                raise ParWLProjectionError(f"Dividend option {change.option} is not illustrated.")
        if self.inputs.rpu_at is not None and self.inputs.rpu_at < self.policy.valuation_date:
            raise ParWLProjectionError("The reduced paid-up date is before the valuation date.")

    def _start_option(self) -> str:
        return (self.inputs.dividend_option or self.policy.dividend_option or "").strip()

    def _mode(self) -> str:
        return policy_mode(self.policy)

    def _rider_units_rule(self) -> bool:
        """Whether a PUA rider's dividend additions earn on the additions its own premium-bought
        additions buy that same anniversary.

        CyberLife does both: the NY riders (NB1PU300 on 000282131, NB1PUA00 on 000300582)
        include them, the 08129700/08129800 riders (12213682, 13510111, 13509776) do not.
        The rule is read from the record's last placed rider values; without them it
        follows company 26 (include) or 01 (exclude).
        """
        rider = self.policy.pua_rider
        default = self.policy.company_code == "26"
        if rider is None:
            return default
        placed = [r for r in self.policy.unapplied_dividends
                  if r.phase == rider.phase and r.source == "1" and r.earn_date == self.policy.last_anniversary]
        before = [a for a in self.policy.additions_before_anniversary
                  if a.phase == rider.phase and a.source == "0"]
        bought = [r for r in self.policy.unapplied_dividends
                  if r.phase == rider.phase and r.source == "0" and r.earn_date == self.policy.last_anniversary]
        if not placed or not before or not bought:
            return default
        units = placed[0].units
        held = sum(a.amount for a in before)
        purchase = cents(bought[0].units * bought[0].pua_per_unit)
        if abs(thousands3(held) - units) < 0.0005:
            return False
        if abs(thousands3(held + purchase) - units) < 0.0005:
            return True
        return default

    def _rider_dividends_rule(self) -> bool:
        """Whether a PUA rider's dividends always buy paid-up additions, whatever the
        policy's dividend option.

        The NY riders do (NB1PUA00 on 000299710 under option 6, NB1PU300 on 000284098
        under option 2: CyberLife applied their dividends as option 4); 08129700 on
        12197588 follows the policy's option 3. Read from the rider's newest applied
        dividends when the policy option is not 4; otherwise company 26 buys additions.
        """
        rider = self.policy.pua_rider
        if rider is None:
            return False
        applied = [r for r in self.policy.applied_dividends if r.phase == rider.phase and r.option.strip()]
        policy_option = (self.policy.dividend_option or "").strip()
        if applied and policy_option != "4":
            newest = max(r.earn_date for r in applied)
            return {r.option.strip() for r in applied if r.earn_date == newest} == {"4"}
        return self.policy.company_code == "26"

    def _direct_recognition_phases(self) -> Dict[int, bool]:
        """Coverage phases whose dividends CyberLife pays from the direct recognition
        records (L premium paying, P reduced paid-up), per the newest placed values
        (``DIR_RCG_DIV_IND``). Rider 08129700 on 12213682 is paid its L scale (2.74)."""
        latest: Dict[int, Tuple[date, bool]] = {}
        for rec in self.policy.unapplied_dividends:
            seen = latest.get(rec.phase)
            if seen is None or rec.earn_date > seen[0]:
                latest[rec.phase] = (rec.earn_date, rec.direct_recognition)
        return {phase: flag for phase, (_when, flag) in latest.items()}

    def record_type(self, phase: int, rpu: bool) -> str:
        """The dividend record type a coverage phase earns on (D/R, or L/P under direct recognition)."""
        if self.direct_recognition.get(phase):
            return "P" if rpu else "L"
        return "R" if rpu else "D"

    def _rider_duration_offset(self) -> int:
        """Duration offset of a PUA rider's dividend scale, read from the record.

        Rider 08129700 on 12213682 (issued with the base in 1990) is paid the rider scale
        four durations earlier than its policy year (2.74 / 4.03 = duration 32 in year 36).
        The offset that reproduces the per-unit values CyberLife placed at the last
        anniversary is kept for the projection; 0 when they already agree.
        """
        rider = self.policy.pua_rider
        if rider is None:
            return 0
        placed = [r for r in self.policy.unapplied_dividends
                  if r.phase == rider.phase and r.source == "0" and r.earn_date == self.policy.last_anniversary]
        dividends = self.rates.coverage(rider.phase).dividends
        if not placed or dividends is None:
            return 0
        rec = placed[0]
        duration = completed_months(rider.issue_date, rec.earn_date) // 12
        record = self.record_type(rider.phase, rec.rpu_values)

        def matches(offset: int) -> bool:
            try:
                s = dividends.rates(record, rec.earn_date, duration + offset, rider.issue_age)
            except ParWLRateError:
                return False
            return abs(s.base_div - rec.cash_per_unit) < 1e-6 and abs(s.base_pua - rec.pua_per_unit) < 1e-6

        if matches(0):
            return 0
        for step in range(1, 40):
            for offset in (-step, step):
                if matches(offset):
                    self.notes.append(
                        f"{rider.plancode} dividends follow its scale at duration {duration + offset} in policy "
                        f"year {duration} (offset {offset:+d}), as CyberLife placed them for "
                        f"{rec.earn_date:%m/%d/%Y}.")
                    return offset
        self.notes.append(f"{rider.plancode}: CyberLife's placed rider dividend ({rec.cash_per_unit}) is not on "
                          "its dividend scale; the rider's own policy year is used.")
        return 0

    def _premium_adjustment(self) -> float:
        """Billed premium less the calculated one (a forced premium), kept with the base premium."""
        policy = self.policy
        if not self._mode():
            raise ParWLProjectionError(f"Billing every {policy.billing_frequency} months is not illustrated.")
        if policy.premium_status not in ("22", "32") or not policy.modal_premium:
            return 0.0
        calculated = modal_premium(policy, self.rates, record_premium_date(policy)).total
        billed = cents(policy.modal_premium)
        if abs(calculated - billed) < 0.005:
            return 0.0
        difference = cents(billed - calculated)
        self.notes.append(
            f"Billed premium {billed:,.2f} differs from the calculated {calculated:,.2f} by {difference:,.2f}"
            f"{' (forced premium)' if policy.forced_premium else ''}; the difference is kept with the base premium.")
        return difference

    def _initial_state(self) -> _State:
        policy = self.policy
        additions = [
            _Additions(a.phase, a.source, a.amount, a.mortality_table, a.interest, a.nfo_code or "5")
            for a in policy.additions if a.amount
        ]
        loan = _Loan(rate=(policy.loan_rate or 0.0),
                     in_advance=policy.loan_type_code in ("0", "6") if policy.loan_type_code else True)
        if policy.loans:
            record = policy.loans[0]
            loan.principal = round(sum(l.principal for l in policy.loans), 2)
            loan.rate = record.rate or loan.rate
            loan.in_advance = record.in_advance
            k = self._month_of_year(policy.valuation_date)
            if record.in_advance:
                loan.unearned = cents(record.interest_amount * (12 - k) / 12.0) if record.capitalized else 0.0
                loan.unearned_months = 12 - k
            else:
                since = record.interest_paid_to or policy.last_anniversary
                months = max(0, completed_months(since, policy.valuation_date))
                loan.accrued = cents(loan.principal * loan.rate * months / 12.0)
        paying = policy.premium_status in ("22", "32", "21") and not policy.is_rpu
        return _State(
            units=self.base.units,
            rpu=policy.is_rpu,
            premium_paying=paying,
            waiver=policy.is_waiver,
            additions=additions,
            oyt_face=policy.oyt_amount,
            oyt_expiry=policy.oyt_expiry,
            deposits=policy.deposits,
            loan=loan,
            option=self._start_option(),
            secondary=(self.inputs.secondary_option or policy.secondary_dividend_option or "").strip(),
        )

    # -- calendar helpers -----------------------------------------------------------

    def record_state(self) -> _State:
        """The record's current state (the projection's starting point)."""
        return self._initial_state()

    def state_before_last_anniversary(self) -> _State:
        """The record's state going into its last anniversary (additions before processing)."""
        state = self._initial_state()
        for row in self.policy.additions_before_anniversary:
            group = next((g for g in state.additions if g.phase == row.phase and g.source == row.source), None)
            if group is not None:
                group.amount = row.amount
            else:
                state.additions.append(_Additions(row.phase, row.source, row.amount, row.mortality_table,
                                                  row.interest, row.nfo_code or "5"))
        return state

    def _month_of_year(self, when: date) -> int:
        return completed_months(self.base.issue_date, when) % 12

    def _policy_year(self, when: date) -> int:
        return completed_months(self.base.issue_date, when) // 12 + 1

    def _attained_age(self, cov: ParWLCoverage, when: date) -> int:
        return cov.issue_age + completed_months(cov.issue_date, when) // 12

    def _end_date(self) -> date:
        base = self.base
        end = base.maturity_date or add_months(base.issue_date, (121 - base.issue_age) * 12, self.day)
        if self.inputs.end_age is not None:
            by_age = add_months(base.issue_date, (int(self.inputs.end_age) - base.issue_age) * 12, self.day)
            end = min(end, by_age)
        return end

    # -- values -----------------------------------------------------------------------

    def _base_cash_value(self, state: _State, when: date, row: ParWLMonth) -> float:
        cov = self.base
        years = completed_months(cov.issue_date, when) // 12
        k = completed_months(cov.issue_date, when) % 12
        if state.rpu:
            table, interest = self._rpu_basis()
            start, end, mid = interpolated_nsp(table, interest, cov.issue_age + years, k)
            row.cv_per_unit_start, row.cv_per_unit_end = start * cov.value_per_unit / 1000.0, end * cov.value_per_unit / 1000.0
            row.cv_per_unit = mid * cov.value_per_unit / 1000.0
            return cents(state.units * row.cv_per_unit)
        rates = self.rates.coverage(cov.phase)
        start = rates.cash_value_per_unit(years)
        end = rates.cash_value_per_unit(years + 1)
        per_unit = cents((start * (12 - k) + end * k) / 12.0)
        row.cv_per_unit_start, row.cv_per_unit_end, row.cv_per_unit = start, end, per_unit
        return cents(state.units * per_unit)

    def _rpu_basis(self) -> Tuple[str, float]:
        cov = self.base
        if not cov.nsp_table or cov.nsp_interest is None:
            raise ParWLProjectionError(
                f"{cov.plancode} has no reduced paid-up NSP basis (NSP_RPU_TBL_CD / NSP_ITS_RT).")
        return cov.nsp_table, cov.nsp_interest

    def _additions_value(self, state: _State, when: date, row: ParWLMonth) -> float:
        total = 0.0
        for group in state.additions:
            if group.amount <= 0:
                continue
            cov = self._coverage(group.phase)
            years = completed_months(cov.issue_date, when) // 12
            k = completed_months(cov.issue_date, when) % 12
            start, end, mid = interpolated_nsp(group.table, group.interest, cov.issue_age + years, k)
            if cov.role == ROLE_BASE:
                row.nsp_start, row.nsp_end = start, end
            total += cents(group.amount / 1000.0 * mid)
        return cents(total)

    def _coverage(self, phase: int) -> ParWLCoverage:
        for cov in self.policy.coverages:
            if cov.phase == phase:
                return cov
        return self.base

    def _loan_payoff(self, loan: _Loan) -> float:
        return cents(max(0.0, loan.principal + loan.accrued - loan.unearned))

    def _term_rider_face(self, when: date) -> float:
        return cents(sum(c.face_amount for c in self.policy.coverages
                         if c.role == ROLE_TERM_RIDER and (c.maturity_date is None or when < c.maturity_date)))

    def _fill_values(self, state: _State, when: date, row: ParWLMonth) -> None:
        row.units = state.units
        row.rpu = state.rpu
        row.face = cents(state.units * self.base.value_per_unit)
        row.base_cv = self._base_cash_value(state, when, row)
        row.additions_cv = self._additions_value(state, when, row)
        row.additions = cents(sum(a.amount for a in state.additions))
        row.additions_dividend = cents(sum(a.amount for a in state.additions if a.phase == self.base.phase))
        row.additions_rider = cents(row.additions - row.additions_dividend)
        if state.oyt_expiry is not None and when >= state.oyt_expiry:
            state.oyt_face = 0.0
        row.oyt_face = state.oyt_face
        row.deposits = state.deposits
        row.term_rider_face = self._term_rider_face(when)
        row.loan_principal = cents(state.loan.principal)
        row.loan_accrued = cents(state.loan.accrued)
        row.loan_unearned = cents(state.loan.unearned)
        row.loan_payoff = self._loan_payoff(state.loan)
        row.premium_credit = state.premium_credit
        row.cash_value = cents(row.base_cv + row.additions_cv + row.deposits)
        row.surrender_value = cents(max(0.0, row.cash_value - row.loan_payoff))
        row.death_benefit = cents(max(0.0, row.face + row.additions + row.oyt_face + row.term_rider_face
                                      + row.deposits - row.loan_payoff))
        row.status = "Reduced paid-up" if state.rpu else ("Premium paying" if state.premium_paying else "Paid-up")

    # -- anniversary processing -----------------------------------------------------

    def _option_on(self, state: _State, when: date) -> None:
        for change in sorted(self.inputs.option_changes, key=lambda c: c.when):
            if change.when <= when:
                state.option = change.option
                if change.secondary:
                    state.secondary = change.secondary

    def _dividend_rates(self, cov: ParWLCoverage, record: str, when: date, duration: int) -> DividendRateSet:
        dividends = self.rates.coverage(cov.phase).dividends
        if dividends is None:
            raise ParWLRateError(f"{cov.plancode} has no dividend scale in schema rates.")
        return dividends.rates(record, when, duration, cov.issue_age)

    def _anniversary(self, state: _State, when: date, row: ParWLMonth, dividends: bool) -> None:
        row.anniversary = True
        duration = completed_months(self.base.issue_date, when) // 12   # the year just completed
        # 1. deposit interest on the existing balance
        if state.deposits > 0:
            rate = self._deposit_rate()
            row.deposit_interest = cents(state.deposits * rate)
            state.deposits = cents(state.deposits + row.deposit_interest)
        # 2. premium-reduction credit left from last year goes to the secondary option
        if state.premium_credit > 0:
            leftover = state.premium_credit
            state.premium_credit = 0.0
            self._apply_secondary(state, leftover, {}, row, "unused premium reduction")
        # 3. last year's OYT expires at the anniversary; this dividend may buy the next year's
        if state.oyt_expiry is not None and when >= state.oyt_expiry:
            state.oyt_face = 0.0
            state.oyt_expiry = None
        # 4. dividend for the completed year (none at maturity: the scale ends the year before)
        self._option_on(state, when)
        row.dividend_option = state.option
        matured = self.base.maturity_date is not None and when >= self.base.maturity_date
        if dividends and state.option not in NO_DIVIDEND_OPTIONS and duration >= 1 and not matured:
            self._dividend(state, when, duration, row)
        if row.dividend_to_oyt > 0:
            state.oyt_expiry = add_months(when, 12, self.day)
        # 5. loan interest
        self._loan_anniversary(state, row)
        # 6. premium status
        pay_up = self.base.pay_up_date
        if pay_up is not None and when >= pay_up:
            state.premium_paying = False

    def _deposit_rate(self) -> float:
        rate = self.inputs.deposit_rate if self.inputs.deposit_rate is not None else self.policy.deposit_rate
        if rate is None:
            raise ParWLProjectionError(
                "The dividend deposit interest rate is not on the record; enter it on the Illustration Inputs tab.")
        return rate

    def _dividend(self, state: _State, when: date, duration: int, row: ParWLMonth) -> None:
        record = self.record_type(self.base.phase, state.rpu)
        pieces = self.dividend_pieces(state, when, duration)
        row.dividend_year = duration
        row.dividend_record = record
        row.dividend_rate = self._dividend_rates(self.base, record, when, duration).base_div
        total = cents(sum(p.cash for p in pieces))
        row.dividend_base = next((p.cash for p in pieces if p.kind == "base"), 0.0)
        row.dividend_on_additions = cents(sum(p.cash for p in pieces if p.kind == "additions"))
        row.dividend_rider = cents(sum(p.cash for p in pieces if p.kind.startswith("rider")))
        row.dividend_total = total
        self._apply_dividend(state, when, pieces, total, row)

    def dividend_pieces(self, state: _State, when: date, duration: int) -> List["DividendPiece"]:
        """The dividend earned at ``when`` for policy year ``duration``, by source.

        The base coverage pays on its units and on its dividend additions held before
        the anniversary; a PUA rider pays on its premium-bought additions (as units)
        and on its dividend additions, including those the first part buys when the
        option is paid-up additions.
        """
        record = self.record_type(self.base.phase, state.rpu)
        base_rates = self._dividend_rates(self.base, record, when, duration)
        pieces: List[DividendPiece] = []
        base_units = state.units
        base_adds = sum(a.amount for a in state.additions if a.phase == self.base.phase)
        pua_units = thousands3(base_adds)
        if self._coverage_earns_dividend(state, when):
            pieces.append(DividendPiece("base", self.base.phase, "0", base_units, base_rates.base_div,
                                        base_rates.base_pua, base_rates.base_oyt))
        if pua_units:
            pieces.append(DividendPiece("additions", self.base.phase, "1", pua_units, base_rates.pua_div,
                                        base_rates.pua_pua, base_rates.pua_oyt))
        rider = self.policy.pua_rider
        if rider is not None:
            rider_rates = self._dividend_rates(
                rider, self.record_type(rider.phase, False), when,
                completed_months(rider.issue_date, when) // 12 + self.rider_duration_offset)
            bought = sum(a.amount for a in state.additions if a.phase == rider.phase and a.source == "1")
            bought_units = thousands3(bought)
            first = DividendPiece("rider", rider.phase, "0", bought_units, rider_rates.base_div,
                                  rider_rates.base_pua, rider_rates.base_oyt)
            if bought_units:
                pieces.append(first)
            rider_adds = sum(a.amount for a in state.additions if a.phase == rider.phase and a.source != "1")
            if (state.option == "4" or self.rider_dividends_to_additions) and self.rider_units_include_purchase:
                rider_adds += first.pua
            rider_add_units = thousands3(rider_adds)
            if rider_add_units:
                pieces.append(DividendPiece("rider additions", rider.phase, "1", rider_add_units,
                                            rider_rates.pua_div, rider_rates.pua_pua, rider_rates.pua_oyt))
        return pieces

    def _coverage_earns_dividend(self, state: _State, when: date) -> bool:
        """The base coverage earns its dividend only when its premiums are paid to the
        anniversary, it is paid up (pay-up date reached) or reduced paid-up.
        B111A100 14762446 (status 41, paid to 12/20/2023) was paid only its additions'
        dividend on 05/20/2026."""
        if state.rpu or state.premium_paying:
            return True
        pay_up = self.base.pay_up_date
        if pay_up is None or pay_up <= when:
            return True
        paid_to = self.policy.paid_to_date
        return paid_to is None or paid_to >= when

    def _add_additions(self, state: _State, phase: int, amount: float, source: str = "0") -> None:
        if amount <= 0:
            return
        for group in state.additions:
            if group.phase == phase and group.source == source:
                group.amount = cents(group.amount + amount)
                return
        cov = self._coverage(phase)
        template = next((g for g in state.additions if g.phase == phase), None) \
            or next((g for g in state.additions if g.phase == self.base.phase), None)
        if template is None:
            if not cov.nsp_table or cov.nsp_interest is None:
                raise ParWLProjectionError(
                    f"{cov.plancode} has no paid-up additions basis (no existing additions and no NSP table).")
            table, interest = cov.nsp_table, cov.nsp_interest
        else:
            table, interest = template.table, template.interest
        state.additions.append(_Additions(phase, source, cents(amount), table, interest))

    def _apply_dividend(self, state: _State, when: date, pieces: List[DividendPiece], total: float,
                        row: ParWLMonth) -> None:
        option = state.option
        if option != "4" and self.rider_dividends_to_additions:
            rider_pieces = [p for p in pieces if p.kind.startswith("rider")]
            if rider_pieces:
                for piece in rider_pieces:
                    self._add_additions(state, piece.phase, piece.pua)
                rider_cash = cents(sum(p.cash for p in rider_pieces))
                row.dividend_to_additions = cents(row.dividend_to_additions + rider_cash)
                row.additions_bought = cents(row.additions_bought + sum(p.pua for p in rider_pieces))
                pieces = [p for p in pieces if not p.kind.startswith("rider")]
                total = cents(total - rider_cash)
        if option == "4":
            for piece in pieces:
                self._add_additions(state, piece.phase, piece.pua)
            row.dividend_to_additions = total
            row.additions_bought = cents(sum(p.pua for p in pieces))
        elif option == "1":
            row.dividend_cash = total
        elif option == "3":
            state.deposits = cents(state.deposits + total)
            row.dividend_to_deposit = total
        elif option == "2":
            state.premium_credit = cents(state.premium_credit + total)
            row.dividend_to_premium = total
        elif option == "8":
            used = self._reduce_loan(state, total)
            row.dividend_to_loan = used
            if total - used > 0.004:
                self._apply_secondary(state, cents(total - used), {}, row, "loan paid off")
        elif option in OYT_OPTIONS:
            # The OYT is limited (6: to the base coverage's cash value at the next anniversary,
            # 7: to its face). The additions' OYT is bought first and the coverage's OYT takes
            # the room left (14139154: 1,590.00 = 362.60 + 1,227.40); the coverage's unused
            # dividend goes to the secondary option.
            base_piece = next((p for p in pieces if p.kind == "base"), None)
            limit = None
            if base_piece is not None and option == "6":
                years = completed_months(self.base.issue_date, when) // 12
                limit = cents(state.units * self.rates.coverage(self.base.phase).cash_value_per_unit(years + 1))
            elif base_piece is not None and option == "7":
                limit = cents(state.units * self.base.value_per_unit)
            others = [p for p in pieces if p is not base_piece]
            oyt_face = sum(p.oyt for p in others)
            used = sum(p.cash for p in others)
            leftover, share = 0.0, {}
            if base_piece is not None:
                room = base_piece.oyt if limit is None else max(0.0, min(base_piece.oyt, limit - oyt_face))
                fraction = room / base_piece.oyt if base_piece.oyt else 1.0
                oyt_face += room
                part = cents(base_piece.cash * fraction)
                used += part
                leftover = base_piece.cash - part
                if leftover > 0.004:
                    share[base_piece.phase] = base_piece.pua * (1.0 - fraction)
            state.oyt_face = cents(oyt_face)
            row.dividend_to_oyt = cents(used)
            if leftover > 0.004:
                self._apply_secondary(state, cents(leftover), share, row, "above the OYT limit")

    def _apply_secondary(self, state: _State, amount: float, pua_share: Dict[int, float], row: ParWLMonth,
                         why: str) -> None:
        secondary = state.secondary or "3"
        if secondary == "4" and pua_share:
            for phase, pua in pua_share.items():
                self._add_additions(state, phase, cents(pua))
            row.dividend_to_additions = cents(row.dividend_to_additions + amount)
            row.additions_bought = cents(row.additions_bought + sum(cents(v) for v in pua_share.values()))
        elif secondary == "4":
            self._buy_additions_with_cash(state, amount, row)
        elif secondary == "1":
            row.dividend_cash = cents(row.dividend_cash + amount)
        elif secondary == "8":
            used = self._reduce_loan(state, amount)
            row.dividend_to_loan = cents(row.dividend_to_loan + used)
            if amount - used > 0.004:
                state.deposits = cents(state.deposits + amount - used)
                row.dividend_to_deposit = cents(row.dividend_to_deposit + amount - used)
        else:
            state.deposits = cents(state.deposits + amount)
            row.dividend_to_deposit = cents(row.dividend_to_deposit + amount)
        row.notes = (row.notes + "; " if row.notes else "") + f"{amount:,.2f} to secondary option {secondary} ({why})"

    def _buy_additions_with_cash(self, state: _State, amount: float, row: ParWLMonth) -> None:
        group = next((g for g in state.additions if g.phase == self.base.phase), None)
        table, interest = (group.table, group.interest) if group else self._rpu_basis()
        age = self._attained_age(self.base, row.when)
        face = cents(amount * 1000.0 / net_single_premium(table, interest, age))
        self._add_additions(state, self.base.phase, face)
        row.dividend_to_additions = cents(row.dividend_to_additions + amount)
        row.additions_bought = cents(row.additions_bought + face)

    def _reduce_loan(self, state: _State, amount: float) -> float:
        loan = state.loan
        used = 0.0
        pay_interest = min(amount, loan.accrued)
        loan.accrued = cents(loan.accrued - pay_interest)
        used += pay_interest
        pay_principal = min(amount - used, max(0.0, loan.principal - loan.unearned))
        loan.principal = cents(loan.principal - pay_principal)
        used += pay_principal
        if loan.principal <= loan.unearned + 0.004:
            loan.principal = loan.unearned = 0.0
        return cents(used)

    def _loan_anniversary(self, state: _State, row: ParWLMonth) -> None:
        loan = state.loan
        if loan.principal <= 0 and loan.accrued <= 0:
            loan.unearned = 0.0
            return
        if loan.in_advance:
            loan.unearned = 0.0
            interest = cents(loan.principal * loan.rate / (1.0 - loan.rate))
            if self.inputs.pay_loan_interest:
                row.loan_interest_paid = interest
            else:
                loan.principal = cents(loan.principal + interest)
                loan.unearned = interest
                loan.unearned_months = 12
            row.loan_interest = interest
        else:
            interest = cents(loan.accrued)
            loan.accrued = 0.0
            if self.inputs.pay_loan_interest:
                row.loan_interest_paid = interest
            else:
                loan.principal = cents(loan.principal + interest)
            row.loan_interest = interest

    def _loan_month(self, state: _State) -> None:
        """Earn a month of advance interest, or accrue a month of arrears interest."""
        loan = state.loan
        if loan.principal <= 0:
            return
        if loan.in_advance:
            if loan.unearned_months > 0 and loan.unearned > 0:
                earned = cents(loan.unearned / loan.unearned_months)
                loan.unearned = cents(loan.unearned - earned)
                loan.unearned_months -= 1
        else:
            loan.accrued = loan.accrued + loan.principal * loan.rate / 12.0

    def _new_loan(self, state: _State, amount: float, when: date, row: ParWLMonth) -> None:
        loan = state.loan
        if loan.rate <= 0:
            raise ParWLProjectionError("The policy loan interest rate is not on the record.")
        row.new_loan = cents(row.new_loan + amount)
        if loan.in_advance:
            months = 12 - self._month_of_year(when)
            fraction = loan.rate * months / 12.0
            interest = cents(amount * fraction / (1.0 - fraction))
            loan.principal = cents(loan.principal + amount + interest)
            loan.unearned = cents(loan.unearned + interest)
            loan.unearned_months = months
            row.loan_interest = cents(row.loan_interest + interest)
        else:
            loan.principal = cents(loan.principal + amount)

    # -- premiums ---------------------------------------------------------------------

    def _premium_due(self, state: _State, when: date) -> bool:
        if not state.premium_paying or state.rpu:
            return False
        paid_to = self.policy.paid_to_date
        if paid_to is not None and when < paid_to:
            return False
        if self._month_of_year(when) % int(self.policy.billing_frequency) != 0:
            return False
        return True

    def _premium(self, state: _State, when: date, row: ParWLMonth) -> None:
        parts = modal_premium(self.policy, self.rates, when)
        row.base_premium = cents(parts.base + parts.rounding + (self.premium_adjustment if parts.base else 0.0))
        row.rider_premium = parts.rider
        row.benefit_premium = cents(parts.benefit + parts.extra)
        row.policy_fee = parts.fee
        row.premium_billed = cents(row.base_premium + row.rider_premium + row.benefit_premium + row.policy_fee)
        if row.premium_billed <= 0:
            return
        if state.waiver:
            row.notes = (row.notes + "; " if row.notes else "") + "premium waived"
            return
        credit = min(state.premium_credit, row.premium_billed)
        state.premium_credit = cents(state.premium_credit - credit)
        row.premium_by_dividend = cents(credit)
        row.premium_paid = cents(row.premium_billed - credit)

    def _rider_payment(self, state: _State, amount: float, when: date, row: ParWLMonth) -> None:
        rider = self.policy.pua_rider
        if rider is None:
            raise ParWLProjectionError("The policy has no paid-up additions rider for rider payments.")
        if rider.payments_ceased:
            raise ParWLProjectionError(f"{rider.plancode} no longer accepts payments.")
        rates = self.rates.coverage(rider.phase)
        age = self._attained_age(rider, when)
        pui = rates.pui.get(age)
        if pui is None:
            raise ParWLRateError(f"{rider.plancode} has no PUI purchase rate at attained age {age}.")
        face = cents(amount * 1000.0 / pui)
        self._add_additions(state, rider.phase, face, source="1")
        row.rider_payment = cents(row.rider_payment + amount)
        row.additions_bought_by_rider = cents(row.additions_bought_by_rider + face)

    # -- reduced paid-up --------------------------------------------------------------

    def _convert_to_rpu(self, state: _State, when: date, row: ParWLMonth) -> None:
        values = ParWLMonth(index=row.index, when=when, policy_year=row.policy_year,
                            month_of_year=row.month_of_year, attained_age=row.attained_age, projected=True)
        self._fill_values(state, when, values)
        available = [a for a in state.additions if a.nfo_code in ("3", "4", "5")]
        kept = [a for a in state.additions if a.nfo_code not in ("3", "4", "5")]
        net = values.base_cv + sum(
            cents(a.amount / 1000.0 * interpolated_nsp(a.table, a.interest,
                                                       self._coverage(a.phase).issue_age
                                                       + completed_months(self._coverage(a.phase).issue_date, when) // 12,
                                                       self._month_of_year(when))[2])
            for a in available) + state.deposits - values.loan_payoff
        if net <= 0:
            raise ParWLProjectionError(
                f"On {when:%m/%d/%Y} the net cash value ({net:,.2f}) buys no reduced paid-up insurance.")
        table, interest = self._rpu_basis()
        years = completed_months(self.base.issue_date, when) // 12
        _s, _e, nsp = interpolated_nsp(table, interest, self.base.issue_age + years, self._month_of_year(when))
        per_unit = nsp * self.base.value_per_unit / 1000.0
        units = float(Decimal(repr(net / per_unit)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))
        state.units = units
        state.rpu = True
        state.premium_paying = False
        state.additions = kept
        state.deposits = 0.0
        state.oyt_face = 0.0
        state.loan = _Loan(rate=state.loan.rate, in_advance=state.loan.in_advance)
        state.premium_credit = 0.0
        row.notes = (row.notes + "; " if row.notes else "") + (
            f"Reduced paid-up: net value {net:,.2f} / NSP {nsp:,.3f} = {units:,.3f} units "
            f"({units * self.base.value_per_unit:,.2f} paid-up face)")

    # -- run ------------------------------------------------------------------------

    def project(self, dividends: bool = True) -> List[ParWLMonth]:
        """One projection: monthly rows from the valuation date to the end date."""
        policy = self.policy
        state = self._initial_state()
        if not dividends:
            state.premium_credit = 0.0
        start = policy.valuation_date
        end = self._end_date()
        loans = self._dated(self.inputs.loans)
        repayments = self._dated(self.inputs.loan_repayments)
        payments = self._dated(self.inputs.rider_payments)
        rows: List[ParWLMonth] = []
        index = 0
        when = start
        while when <= end:
            year = self._policy_year(when)
            k = self._month_of_year(when)
            row = ParWLMonth(index=index, when=when, policy_year=year, month_of_year=k,
                             attained_age=self._attained_age(self.base, when), projected=True)
            if index > 0:
                self._loan_month(state)
                if k == 0:
                    self._anniversary(state, when, row, dividends)
            if when >= end and when == self._maturity():
                row.notes = (row.notes + "; " if row.notes else "") + "maturity"
            if self.inputs.rpu_at is not None and when == self.inputs.rpu_at and not state.rpu:
                self._convert_to_rpu(state, when, row)
            if self._premium_due(state, when) and when < end:
                self._premium(state, when, row)
            for amount in payments.get(when, ()):
                if not state.rpu:
                    self._rider_payment(state, amount, when, row)
            for amount in loans.get(when, ()):
                self._new_loan(state, amount, when, row)
            for amount in repayments.get(when, ()):
                paid = self._reduce_loan(state, amount)
                row.loan_repayment = cents(row.loan_repayment + paid)
            self._fill_values(state, when, row)
            rows.append(row)
            if row.loan_payoff > row.cash_value + 0.004 and row.loan_payoff > 0:
                row.notes = (row.notes + "; " if row.notes else "") + "loan exceeds the cash value: policy lapses"
                break
            index += 1
            when = add_months(start, index, self.day)
        return rows

    def _maturity(self) -> Optional[date]:
        return self.base.maturity_date

    def _dated(self, items) -> Dict[date, List[float]]:
        out: Dict[date, List[float]] = {}
        for item in items:
            if item.when < self.policy.valuation_date:
                raise ParWLProjectionError(f"Transaction dated {item.when:%m/%d/%Y} is before the valuation date.")
            if item.when.day != self.day and not self._is_month_end_anchor(item.when):
                raise ParWLProjectionError(
                    f"Transaction dated {item.when:%m/%d/%Y} is not on a monthliversary (day {self.day}).")
            out.setdefault(item.when, []).append(float(item.amount))
        return out

    def _is_month_end_anchor(self, when: date) -> bool:
        return when.day == calendar.monthrange(when.year, when.month)[1] and self.day > when.day

    def run(self) -> ParWLResult:
        months = self.project(dividends=self.inputs.dividends)
        guaranteed = self.project(dividends=False)
        years = build_years(months, guaranteed)
        return ParWLResult(self.policy, self.inputs, months, guaranteed, years, notes=list(dict.fromkeys(self.notes)))


def build_years(months: List[ParWLMonth], guaranteed: List[ParWLMonth]) -> List[ParWLYear]:
    """Annual ledger: each policy year's projected flows, and values at the year's end.

    Year ``Y`` runs from the anniversary starting it (premiums due that day belong to
    ``Y``) to the next anniversary, whose row carries the dividend earned for ``Y`` and
    the end-of-year values.
    """
    by_date = {m.when: m for m in guaranteed}
    flows: Dict[int, List[ParWLMonth]] = {}
    for row in months:
        flows.setdefault(row.policy_year, []).append(row)
    years: List[ParWLYear] = []
    for end_row in months[1:]:
        if end_row.month_of_year != 0:
            continue
        year = end_row.policy_year - 1
        rows = flows.get(year, [])
        g = by_date.get(end_row.when)
        years.append(ParWLYear(
            policy_year=year,
            end_date=end_row.when,
            age=end_row.attained_age,
            premium=cents(sum(m.premium_paid for m in rows)),
            rider_payments=cents(sum(m.rider_payment for m in rows)),
            loan_interest_paid=cents(sum(m.loan_interest_paid for m in rows)),
            new_loans=cents(sum(m.new_loan for m in rows)),
            loan_repayments=cents(sum(m.loan_repayment for m in rows)),
            dividend=end_row.dividend_total,
            dividend_cash=end_row.dividend_cash,
            guaranteed_cash_value=g.surrender_value if g else 0.0,
            guaranteed_death_benefit=g.death_benefit if g else 0.0,
            additions=end_row.additions,
            additions_cv=end_row.additions_cv,
            oyt_face=end_row.oyt_face,
            deposits=end_row.deposits,
            loan_balance=end_row.loan_payoff,
            cash_value=end_row.cash_value,
            surrender_value=end_row.surrender_value,
            death_benefit=end_row.death_benefit,
            rpu=end_row.rpu,
            additions_base=end_row.additions_dividend,
            additions_rider=end_row.additions_rider,
        ))
    return years


def project_parwl(policy: ParWLPolicy, rates: ParWLRates, inputs: Optional[ParWLInputs] = None) -> ParWLResult:
    """Run the current and guaranteed projections of ``policy``."""
    return ParWLEngine(policy, rates, inputs).run()
