"""CVAT net single premium (CyberLife ``NS`` target) and the minimum death benefit ratio.

A cash value accumulation test (CVAT, IRC 7702(b); ``LH_NON_TRD_POL.TFDF_CD`` 3/5) policy
must keep its death benefit at or above its cash value divided by the net single premium
for $1 of death benefit. CyberLife stores that NSP for the basic insured on
``LH_POL_TARGET`` (``TAR_TYP_CD = 'NS'``, the 58 segment) at each anniversary; the
minimum death benefit ratio is ``MDBR = 1 / NSP`` (per $1: ``face / NS``).

Two bases, each reproduced to the cent against the stored NS targets (see
``docs/Illustration_UL/RERUN_MANUAL.md`` § CVAT corridor):

**UL / IUL** (:class:`UlNspBasis`)

* mortality: each base coverage's guaranteed COI (schema ``rates`` COI scale G) per
  $1,000 per month, capped at 1000/12, as a monthly death rate ``q = Q / (1 + Q/1000)``;
  table ratings only on the plans in :data:`SUBSTANDARD_IN_NSP_PLANS`, flat extras never;
* interest: ``i = MAX(guaranteed rate, statutory 7702 rate)`` — 4% for contracts issued
  before 2021, 2% after — monthly, ``v = (1 + i)^(-1/12)``;
* monthly curtate (claims at the end of the month of death), endowment at age 100;
* ``A = v·q + v·(1 − q/1000)·A_next`` per $1,000.

**ISWL** (:class:`IswlNspBasis`; CyberDoc D10: ISL DEFRA NSPs use the valuation mortality
table)

* mortality: the coverage's valuation table (``LH_COV_PHA.MTL_FCT_TBL_CD``, CKAPTB32)
  annual ``q``;
* interest: the coverage's ``NSP_ITS_RT`` (statutory 7702 rate as a floor);
* annual curtate with immediate payment of claims, ``f = i / ROUND(ln(1+i), 7)``,
  endowment at age 100: ``A = f·v·q + v·(1 − q)·A_next``.

The NSP is computed once, as a present value at the calculation point, then rolled
forward with the Fackler recursion (``A_next = (A − f·v·q) / (v·(1 − q))``) — the exact
inverse of the backward step — instead of recomputing to maturity every month.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Callable, Dict, List, Optional, Sequence

from dateutil.relativedelta import relativedelta

from suiteview.illustration.constants import MONTHS_PER_YEAR, PER_THOUSAND
from suiteview.illustration.core.monthly_deduction import (
    _adjusted_coi_rate,
    _coi_rate_year,
    _rate_from_schedule,
    _segment_charge_inactive,
)
from suiteview.illustration.core.monthly_guideline import (
    DEEMED_MATURITY_AGE,
    statutory_guideline_rates,
)
from suiteview.illustration.core.parwl.nsp import NSPError, mortality_table
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData

CVAT_MATURITY_AGE = DEEMED_MATURITY_AGE
NSP_COI_CAP = PER_THOUSAND / MONTHS_PER_YEAR
UL_NSP_HELD_FOR_YEAR = True


class CvatNspError(ValueError):
    """The CVAT net single premium cannot be calculated for this policy."""


# ── Recursions ─────────────────────────────────────────────────────────────


def monthly_death_rate(coi_rate: float) -> float:
    """q per $1,000 from a monthly COI per $1,000 (COI is charged on the discounted
    NAR, so ``q = Q / (1 + Q/1000)``)."""
    return coi_rate / (1.0 + coi_rate / PER_THOUSAND)


def immediate_claims_factor(annual_rate: float) -> float:
    """``i / δ`` with CyberLife's force of interest rounded to 7 decimals."""
    if annual_rate <= 0.0:
        return 1.0
    return annual_rate / round(math.log(1.0 + annual_rate), 7)


def backward_step(next_nsp: float, q: float, v: float, claims_factor: float = 1.0) -> float:
    """NSP per $1,000 one period earlier: ``f·v·q + v·(1 − q/1000)·A_next`` (q per $1,000)."""
    return claims_factor * v * q + v * (1.0 - q / PER_THOUSAND) * next_nsp


def fackler_step(nsp: float, q: float, v: float, claims_factor: float = 1.0) -> float:
    """Fackler: NSP per $1,000 one period later, ``(A − f·v·q) / (v·(1 − q/1000))``."""
    survival = 1.0 - q / PER_THOUSAND
    if survival <= 0.0:
        return PER_THOUSAND
    return (nsp - claims_factor * v * q) / (v * survival)


def present_value(qs: Sequence[float], v: float, claims_factor: float = 1.0) -> float:
    """NSP per $1,000 at the first period of ``qs`` (q per $1,000 per period), the face
    endowing after the last period."""
    nsp = PER_THOUSAND
    for q in reversed(qs):
        nsp = backward_step(nsp, q, v, claims_factor)
    return nsp


def cvat_statutory_rate(policy: IllustrationPolicyData) -> float:
    """The statutory 7702 CVAT interest floor for the issue date."""
    return statutory_guideline_rates(policy.issue_date)[0]


# ── Substandard rule (UL) ──────────────────────────────────────────────────


@dataclass(frozen=True)
class SubstandardBasis:
    """Which substandard ratings enter the UL CVAT NSP mortality."""

    table: bool = False
    flat: bool = False


NO_SUBSTANDARD = SubstandardBasis()
_TABLE_ONLY = SubstandardBasis(table=True)

# Plans whose CVAT NSP includes table ratings (CyberLife PDF substandard rule, which is
# not in DB2). Every other CVAT UL plan excludes table ratings; no plan was seen to
# include flat extras. Determined plan by plan against the stored NS of rated policies.
SUBSTANDARD_IN_NSP_PLANS: Dict[str, SubstandardBasis] = {
    plan: _TABLE_ONLY for plan in ("1U147400", "1U147800", "1U147900", "1U148000", "1U148100")
}


def substandard_in_nsp(policy: IllustrationPolicyData) -> SubstandardBasis:
    """The plan's substandard basis for the UL CVAT NSP."""
    return SUBSTANDARD_IN_NSP_PLANS.get(str(policy.plancode or "").strip().upper(), NO_SUBSTANDARD)


# ISWL plans whose CVAT NSP is curtate (claims at the end of the year of death); every
# other CVAT ISWL plan pays claims immediately (``i/δ``). A plan rule, not a table one:
# the same NK/NL tables are immediate on B11SB* and curtate here.
CURTATE_ISWL_NSP_PLANS: frozenset = frozenset({
    "B11SP400", "B11SP40J", "B11SP500", "B11SW100", "B11SW200",
    "B71SP600", "B71SP60J", "B71SP700", "B71SP800", "B71SP900",
})


def iswl_immediate_claims(policy: IllustrationPolicyData) -> bool:
    return str(policy.plancode or "").strip().upper() not in CURTATE_ISWL_NSP_PLANS


# ── Coverage helpers ───────────────────────────────────────────────────────


def _base_segments(policy: IllustrationPolicyData) -> list:
    return [s for s in (policy.segments or [policy.base_segment]) if s is not None]


def _active_segments(policy: IllustrationPolicyData, on: date) -> list:
    return [s for s in _base_segments(policy)
            if s.face_amount > 0 and not _segment_charge_inactive(s, on)]


def _maturity_date(policy: IllustrationPolicyData) -> date:
    if policy.issue_date is None:
        raise CvatNspError("The CVAT net single premium needs the policy issue date.")
    return policy.issue_date + relativedelta(years=CVAT_MATURITY_AGE - policy.issue_age)


def months_to_maturity(policy: IllustrationPolicyData, start: date) -> int:
    """Whole months from ``start`` to the policy anniversary at attained age 100."""
    delta = relativedelta(_maturity_date(policy), start)
    return max(0, delta.years * MONTHS_PER_YEAR + delta.months)


def anniversary_on_or_before(policy: IllustrationPolicyData, on: date) -> date:
    years = max(0, relativedelta(on, policy.issue_date).years)
    return policy.issue_date + relativedelta(years=years)


# ── The two bases ──────────────────────────────────────────────────────────


@dataclass
class UlNspBasis:
    """Monthly guaranteed-COI basis (UL/IUL)."""

    policy: IllustrationPolicyData
    config: PlancodeConfig
    guaranteed: IllustrationRates
    substandard: Optional[SubstandardBasis] = None
    # Reloads guaranteed rates for the policy's current coverages (a run's coverage
    # changes add phases with their own COI schedules); None keeps ``guaranteed``.
    loader: Optional[Callable[[IllustrationPolicyData], IllustrationRates]] = None

    def __post_init__(self) -> None:
        if self.substandard is None:
            self.substandard = substandard_in_nsp(self.policy)
        self.annual_rate = max(float(self.policy.guaranteed_interest_rate or 0.0),
                               cvat_statutory_rate(self.policy))
        self.v = (1.0 + self.annual_rate) ** (-1.0 / MONTHS_PER_YEAR)
        self.claims_factor = 1.0
        self.months_per_step = 1

    def refresh(self) -> None:
        if self.loader is not None:
            self.guaranteed = self.loader(self.policy)

    def anchor(self, on: date) -> date:
        """CyberLife holds the anniversary NS (the stored target) for the policy year;
        the Fackler roll advances it month by month from one anniversary to the next."""
        return anniversary_on_or_before(self.policy, on) if UL_NSP_HELD_FOR_YEAR else on

    def qs(self, segment, start: date, steps: int) -> List[float]:
        """Monthly q per $1,000 for ``steps`` months from ``start``."""
        return [monthly_death_rate(c) for c in self.coi_stream(segment, start, steps)]

    def coi_stream(self, segment, start: date, steps: int) -> List[float]:
        schedule = self.guaranteed.segment_coi.get(segment.coverage_phase) or self.guaranteed.coi
        if not schedule or len(schedule) < 2:
            raise CvatNspError(
                f"No guaranteed COI schedule for coverage {segment.coverage_phase} of "
                f"{self.policy.plancode}; the CVAT net single premium cannot be calculated.")
        rated = replace(
            segment,
            table_rating=segment.table_rating if self.substandard.table else 0,
            flat_extra=segment.flat_extra if self.substandard.flat else 0.0,
        )
        stream = []
        for month in range(steps):
            month_date = start + relativedelta(months=month)
            if _segment_charge_inactive(segment, month_date):
                stream.append(0.0)
                continue
            raw = _rate_from_schedule(schedule, _coi_rate_year(segment, self.policy, month_date, 1))
            stream.append(min(_adjusted_coi_rate(raw, rated, self.config, month_date), NSP_COI_CAP))
        return stream

    def steps_to_maturity(self, start: date) -> int:
        return months_to_maturity(self.policy, start)


@dataclass
class IswlNspBasis:
    """Annual valuation-mortality-table basis (ISWL); immediate claims unless the plan
    is in :data:`CURTATE_ISWL_NSP_PLANS`."""

    policy: IllustrationPolicyData
    immediate_claims: Optional[bool] = None

    def __post_init__(self) -> None:
        base = _base_segments(self.policy)[0]
        rate = base.nsp_interest_rate
        if not base.nsp_mortality_table or rate is None:
            raise CvatNspError(
                f"{self.policy.plancode} coverage {base.coverage_phase} has no valuation mortality "
                "table (MTL_FCT_TBL_CD) or NSP interest rate (NSP_ITS_RT); the CVAT net single "
                "premium cannot be calculated.")
        if self.immediate_claims is None:
            self.immediate_claims = iswl_immediate_claims(self.policy)
        self.annual_rate = max(float(rate), cvat_statutory_rate(self.policy))
        self.v = 1.0 / (1.0 + self.annual_rate)
        self.claims_factor = immediate_claims_factor(self.annual_rate) if self.immediate_claims else 1.0
        self.months_per_step = MONTHS_PER_YEAR

    def refresh(self) -> None:
        """The table basis has nothing to reload."""

    def anchor(self, on: date) -> date:
        """ISWL NSPs move on policy anniversaries; mid-year months use the year's NSP."""
        return anniversary_on_or_before(self.policy, on)

    def qs(self, segment, start: date, steps: int) -> List[float]:
        """Annual q per $1,000 for ``steps`` policy years from the anniversary ``start``."""
        code = segment.nsp_mortality_table or _base_segments(self.policy)[0].nsp_mortality_table
        try:
            table = mortality_table(code)
        except NSPError as exc:
            raise CvatNspError(str(exc)) from exc
        age = self.policy.issue_age + relativedelta(start, self.policy.issue_date).years
        out = []
        for offset in range(steps):
            x = age + offset
            if x < table.first_age:
                raise CvatNspError(f"Mortality table {table.code} starts at age {table.first_age}.")
            out.append(PER_THOUSAND * (table.qx[x - table.first_age] if x <= table.last_age else 1.0))
        return out

    def steps_to_maturity(self, start: date) -> int:
        return max(0, relativedelta(_maturity_date(self.policy), start).years)


def nsp_basis(policy: IllustrationPolicyData, config: PlancodeConfig,
              guaranteed: Optional[IllustrationRates]):
    """The CVAT NSP basis for the policy's product family."""
    if config.is_iswl:
        return IswlNspBasis(policy)
    if guaranteed is None:
        raise CvatNspError("The UL CVAT net single premium needs the guaranteed COI rates.")
    return UlNspBasis(policy, config, guaranteed)


# ── NS at a point ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CoverageNsp:
    coverage_phase: int
    face: float
    nsp_per_thousand: float


@dataclass(frozen=True)
class NetSinglePremium:
    """The basic insured's NS at one date."""

    as_of: date
    annual_rate: float
    coverages: tuple[CoverageNsp, ...]

    @property
    def face(self) -> float:
        return sum(c.face for c in self.coverages)

    @property
    def amount(self) -> float:
        """NS dollars (unrounded); CyberLife stores it rounded to cents."""
        return sum(c.nsp_per_thousand * c.face / PER_THOUSAND for c in self.coverages)

    @property
    def per_thousand(self) -> float:
        return self.amount / self.face * PER_THOUSAND if self.face > 0 else PER_THOUSAND


def nsp_at(policy: IllustrationPolicyData, config: PlancodeConfig,
           guaranteed: Optional[IllustrationRates], as_of: date, *, basis=None) -> NetSinglePremium:
    """The basic insured's NSP at ``as_of`` by present value to age 100.

    ``guaranteed`` must be loaded at the guaranteed COI scale (``coi_scale=0``); ISWL
    does not use it. Coverages not yet issued on ``as_of`` are excluded.
    """
    basis = basis or nsp_basis(policy, config, guaranteed)
    start = basis.anchor(as_of)
    steps = basis.steps_to_maturity(start)
    coverages = tuple(
        CoverageNsp(segment.coverage_phase, float(segment.face_amount),
                    present_value(basis.qs(segment, start, steps), basis.v, basis.claims_factor))
        for segment in _active_segments(policy, as_of)
    )
    return NetSinglePremium(as_of, basis.annual_rate, coverages)


# ── The run-level corridor ─────────────────────────────────────────────────


@dataclass
class CvatCorridor:
    """The CVAT minimum death benefit ratio through a projection.

    :meth:`corridor_rate` computes the NSP once by present value at the first month it is
    asked for, then reaches each later month by Fackler steps (monthly for UL, at policy
    anniversaries for ISWL) on the same mortality. A change to the coverages' mortality
    basis (a new or removed coverage, class or rating change) restarts the present value
    at the change month; face changes only reweight the per-coverage NSPs.
    """

    basis: object
    anchor: Optional[date] = None
    nsp_by_phase: Dict[int, float] = field(default_factory=dict)
    _signature: tuple = ()

    @property
    def policy(self) -> IllustrationPolicyData:
        return self.basis.policy

    def _coverage_signature(self, on: date) -> tuple:
        return tuple(
            (s.coverage_phase, s.rate_class, s.table_rating, s.table_cease_date, s.flat_extra,
             s.issue_date) for s in _active_segments(self.policy, on))

    def _restart(self, anchor: date) -> None:
        self.basis.refresh()
        steps = self.basis.steps_to_maturity(anchor)
        self.nsp_by_phase = {
            s.coverage_phase: present_value(self.basis.qs(s, anchor, steps), self.basis.v,
                                            self.basis.claims_factor)
            for s in _active_segments(self.policy, anchor)
        }
        self.anchor = anchor
        self._signature = self._coverage_signature(anchor)

    def _roll_one(self) -> None:
        segments = {s.coverage_phase: s for s in _base_segments(self.policy)}
        for phase, nsp in self.nsp_by_phase.items():
            q = self.basis.qs(segments[phase], self.anchor, 1)[0]
            self.nsp_by_phase[phase] = fackler_step(nsp, q, self.basis.v, self.basis.claims_factor)
        self.anchor = self.anchor + relativedelta(months=self.basis.months_per_step)

    def nsp_by_coverage(self, on: date) -> Dict[int, float]:
        """NSP per $1,000 by coverage phase for the month starting ``on``."""
        target = self.basis.anchor(on)
        if self.anchor is None or target < self.anchor or self._coverage_signature(on) != self._signature:
            self._restart(target)
        while self.anchor < target:
            self._roll_one()
        return dict(self.nsp_by_phase)

    def ns_amount(self, on: date) -> float:
        nsps = self.nsp_by_coverage(on)
        return sum(nsps.get(s.coverage_phase, PER_THOUSAND) * s.face_amount / PER_THOUSAND
                   for s in _active_segments(self.policy, on))

    def corridor_rate(self, on: date) -> float:
        """MDBR — minimum death benefit per $1 of cash value: ``face / NS``."""
        face = sum(s.face_amount for s in _active_segments(self.policy, on))
        ns = self.ns_amount(on)
        if face <= 0.0 or ns <= 0.0:
            return 1.0
        return face / ns
