"""PolView Rates views read from UL_Rates schema ``rates`` (the new rate tables).

Where a rate is shown follows its assignment table and ``RATE_TYPE.STRUCTURE``:

* **Coverage** - CELL rates with ``BENEFIT = ''`` for the coverage's plancode, the
  coverage's dividends (DIV), and, for a coverage whose plancode is not the base
  plan's, that plancode's PLAN rates.
* **Benefit** - CELL rates whose ``BENEFIT`` is the benefit's type + subtype, on the
  plancode of the coverage the benefit is attached to.
* **Policy** - PLAN rates of the base plancode, its FUND rates and mode factors.

A coverage's rate key is its rate sex (``1`` -> ``M``, ``2`` -> ``F``, other CyberLife
codes kept as they are, as the loaders store them), its renewal rate class, the band
its amount falls in (``PLAN_BAND``), the issue state and, for sub-series keyed rates
(CV), the coverage's life sub-series. When the exact cell is not loaded the lookup
falls back, in order, to unisex ``U``, class ``0`` then ``*``, band ``0`` and state
``**``; every fallback used is listed in the grid. Nothing else is guessed: a rate
with no cell is reported as missing.

``DATE_MEANING`` ``ISSUE`` rates use the schedule window in effect on the issue date;
``CALENDAR`` rates use the window in effect on each row's Date (the start of that
policy year). Scales are shown as stored: C current, G guaranteed, S shadow account.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from dateutil.relativedelta import relativedelta

from suiteview.core.rates import RatesError, cyberlife_rate_user
from suiteview.core.rates_schema import (
    BandSpec, CellAssignment, DivAssignment, DivSchedule, PlanDef, RateSetInfo,
    RatesSchemaRepository, ScheduleWindow, SubseriesRow,
)

from .fixed_premium_rates import _rate

if TYPE_CHECKING:
    from .policy_information import PolicyInformation

SOURCE_LABEL = "UL_Rates schema rates"
SEX_FOR_RATES = {"1": "M", "2": "F"}
UNISEX = "U"
CLASS_FALLBACKS = ("0", "*")
UNBANDED = "0"
ALL_STATES = "**"
SCALE_ORDER = ("C", "G", "S")
SINGLE_VALUE_GRAINS = frozenset({"IA", "SCALAR"})
# Point-in-time values: duration 0 is the issue date, so a row's Year n shows duration n - 1
# (the value at the row's Date), as the WL cash-value display does.
POINT_IN_TIME_RATE_TYPES = frozenset({"CV", "FACE_AMT"})
RATE_TYPE_ORDER = (
    "COI", "EPU", "MFEE", "SCR", "SCR_PCT", "PREMLOAD_PCT", "PREMLOAD_EXS", "PREMLOAD_FLAT",
    "SHADOW_INT", "CV", "FACE_AMT", "PREM", "ADJ_PREM", "PUI", "PUI_A", "PUI_B", "PUI_C",
    "PUI_D", "PUI_E", "PUI_F", "MTP", "CTP", "PTP", "STP", "MTP_TBL1", "CTP_TBL1", "PTP_TBL1",
    "GCO_MIN", "GLP", "GSP", "SEVEN_PAY", "SEVEN_NSP", "LIFETIME_PREM", "ANN_BEN_PREM",
    "CORR", "GINT", "DB_DISCOUNT", "AV_CHARGE", "TABLE_COI_FACTOR", "SNET_PERIOD", "SCR_FLAT",
    "LOAN_REG_CHG", "LOAN_REG_CRD", "LOAN_PREF_CHG", "LOAN_PREF_CRD", "ANN_SURR_PCT",
    "ANN_FREE_WD_PCT",
)
DIV_RECORD_LABELS = {"D": "", "R": " RPU", "L": " DR-L", "P": " DR-P", "T": " TERM"}
GAP = (" ", " ")


class RatesNotLoaded(Exception):
    """The requested rates are not in schema ``rates`` (an expected state, not a failure)."""


@dataclass(frozen=True)
class RateKey:
    sex: str
    rate_class: str
    band: str
    state: str
    subseries: str = ""


@dataclass
class CellContext:
    """Everything a CELL/DIV lookup needs for one coverage or benefit."""
    label: str
    plan: PlanDef
    plan_note: str
    plancode: str
    benefit: str
    issue_date: date
    issue_age: int
    years: Optional[int]
    key: RateKey
    raw_sex: str
    band_text: str
    stored_band: str = ""
    rein: str = ""
    extra_meta: List[tuple] = field(default_factory=list)


@dataclass(frozen=True)
class Column:
    name: str
    value: Callable[[int, date], object]


@dataclass
class Parts:
    """Metadata lines and duration columns contributed by one rate source."""
    single: List[tuple] = field(default_factory=list)
    used: List[tuple] = field(default_factory=list)
    missing: List[tuple] = field(default_factory=list)
    windows: List[tuple] = field(default_factory=list)
    columns: List[Column] = field(default_factory=list)
    max_year: int = 0

    def extend(self, other: "Parts") -> None:
        self.single += other.single
        self.used += other.used
        self.missing += other.missing
        self.windows += other.windows
        self.columns += other.columns
        self.max_year = max(self.max_year, other.max_year)


# -- small pure helpers ----------------------------------------------------------

def rates_sex(code: str) -> str:
    """Rates-schema sex for a CyberLife rate sex code (1 -> M, 2 -> F, others verbatim)."""
    text = str(code or "").strip().upper()
    return SEX_FOR_RATES.get(text, text)


def rate_type_sort_key(rate_type: str) -> tuple:
    try:
        return (RATE_TYPE_ORDER.index(rate_type), rate_type)
    except ValueError:
        return (len(RATE_TYPE_ORDER), rate_type)


def fmt(value) -> object:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return _rate(value)
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return value


def _iso(value: Optional[date]) -> str:
    return value.strftime("%Y-%m-%d") if value else ""


def _row_date(start: date, year: int) -> date:
    return start + relativedelta(years=year - 1)


def _window_text(windows: Sequence) -> str:
    return ", ".join(
        f"{_iso(w.effective_from)}..{_iso(w.effective_to) if w.effective_to else ''}"
        for w in sorted(windows, key=lambda w: w.effective_from)
    )


def resolve_plan(plans: Sequence[PlanDef], policy_company: str) -> Tuple[Optional[PlanDef], str]:
    """The PLAN_DEF row for a policy company, with a note when another company's row is used.

    Exact company first; then the company's verified CyberLife rate-file user (01 -> 00);
    then a plancode loaded under a single company, labelled as such.
    """
    company = str(policy_company or "").strip().zfill(2)
    by_company = {plan.company: plan for plan in plans}
    if company in by_company:
        return by_company[company], ""
    try:
        user = cyberlife_rate_user(company)
    except RatesError:
        user = ""
    if user and user in by_company:
        return by_company[user], f"CyberLife rate user of policy company {company}"
    if len(plans) == 1:
        plan = plans[0]
        return plan, f"the only company loaded - policy company {company} is not loaded"
    if plans:
        loaded = ", ".join(sorted(by_company))
        return None, f"loaded under companies {loaded}, not policy company {company}"
    return None, ""


def band_for_amount(bands: Sequence[BandSpec], on: Optional[date], amount) -> Tuple[Optional[BandSpec], str]:
    """``rates.fn_BAND``: the band spec with the latest start on/before ``on`` and the
    lowest upper limit at or above ``amount``. An unbanded plan returns its band 0."""
    limited = [b for b in bands if b.upper_limit is not None]
    if not limited:
        numbered = sorted({b.band for b in bands if b.band != UNBANDED})
        if numbered:
            return None, f"PLAN_BAND has no limits for bands {'/'.join(numbered)}"
        unbanded = [b for b in bands if b.band == UNBANDED]
        if unbanded:
            return unbanded[0], "unbanded"
        return None, "no PLAN_BAND rows"
    if on is None:
        return None, "no issue date for the band lookup"
    starts = sorted({b.issue_date_from for b in limited if b.issue_date_from <= on})
    if not starts:
        return None, f"no band spec starts on or before {_iso(on)}"
    if amount is None:
        return None, "no amount for the band lookup"
    amount = Decimal(str(amount))
    fits = sorted(
        (b for b in limited if b.issue_date_from == starts[-1] and b.upper_limit >= amount),
        key=lambda b: b.upper_limit,
    )
    if not fits:
        return None, f"amount {amount:,.0f} is above every band limit"
    return fits[0], ""


def _candidates(first: str, fallbacks: Iterable[str]) -> List[str]:
    return list(dict.fromkeys([first, *fallbacks]))


def choose_cell(assignments: Sequence[CellAssignment], rate_type: str, key: RateKey,
                plan_subseries: Sequence[SubseriesRow] = ()) -> Tuple[Optional[CellAssignment], List[str]]:
    """The assignment for one rate type, and notes on each fallback used (or why none).

    Sub-series keyed rows (CV) match the coverage's sub-series with sex and class
    ignored (``rates.fn_RATE_SUB``); without one, ``PLAN_SUBSERIES`` maps sex/class to it.
    """
    rows = [a for a in assignments if a.rate_type == rate_type]
    if not rows:
        return None, []
    keyed = [a for a in rows if a.subseries]
    notes: List[str] = []
    sexes = _candidates(key.sex, [UNISEX])
    classes = _candidates(key.rate_class, CLASS_FALLBACKS)
    if keyed:
        by_policy = [a for a in rows if a.subseries == key.subseries] if key.subseries else []
        if by_policy:
            rows, sexes, classes = by_policy, [None], [None]
            notes.append(f"sub-series {key.subseries}")
        else:
            mapped = {s.subseries for s in plan_subseries if s.sex == key.sex and s.rate_class == key.rate_class}
            rows = [a for a in rows if not a.subseries or a.subseries in mapped]
            if not rows:
                loaded = ", ".join(sorted({a.subseries for a in keyed}))
                return None, [f"no cell for sub-series {key.subseries or '(blank)'} (loaded {loaded})"]
            if mapped:
                notes.append(f"sub-series {'/'.join(sorted(mapped))} from PLAN_SUBSERIES")
    for sex in sexes:
        for rate_class in classes:
            for band in _candidates(key.band, [UNBANDED]):
                matches = [
                    a for a in rows
                    if (sex is None or a.sex == sex) and (rate_class is None or a.rate_class == rate_class)
                    and a.band == band and a.state in (key.state, ALL_STATES)
                ]
                if not matches:
                    continue
                chosen = min(matches, key=lambda a: (a.state != key.state, a.subseries == ""))
                if sex is not None and sex != key.sex:
                    notes.append(f"sex {sex} (policy {key.sex or 'blank'})")
                if rate_class is not None and rate_class != key.rate_class:
                    notes.append(f"class {rate_class} (policy {key.rate_class or 'blank'})")
                if band != key.band:
                    notes.append(f"band {band} (policy {key.band or 'none'})")
                if chosen.state != ALL_STATES:
                    notes.append(f"state {chosen.state}")
                return chosen, notes
    loaded = (
        f"loaded sex {'/'.join(sorted({a.sex for a in rows}))}, "
        f"class {'/'.join(sorted({a.rate_class for a in rows}))}, "
        f"band {'/'.join(sorted({a.band for a in rows}))}"
    )
    return None, [f"no cell for {key.sex or '?'}/{key.rate_class or '?'}/{key.band or '?'} ({loaded})"]


def cell_key_text(a: CellAssignment) -> str:
    parts = [a.sex, a.rate_class, a.band, a.state]
    if a.subseries:
        parts.append(f"sub {a.subseries}")
    return "/".join(parts)


def rate_at(grain: str, values: Dict[tuple, Decimal], issue_age: int, year: int, point_in_time: bool = False):
    """One rate from a rate set's values for policy year ``year`` (1-based)."""
    duration = year - 1 if point_in_time else year
    if grain == "IA_DUR":
        return values.get((issue_age, duration))
    if grain == "DUR":
        return values.get((0, duration))
    if grain == "AA":
        return values.get((issue_age + year - 1, 0))
    if grain == "IA":
        return values.get((issue_age, 0))
    if grain == "SCALAR":
        return values.get((0, 0))
    return None


def last_year(grain: str, values: Dict[tuple, Decimal], issue_age: int, point_in_time: bool = False) -> int:
    """The last policy year a rate set has a value for (0 when it has none)."""
    if not values:
        return 0
    if grain in ("IA_DUR", "DUR"):
        return max(d for _, d in values) + (1 if point_in_time else 0)
    if grain == "AA":
        return max(0, max(a for a, _ in values) - issue_age + 1)
    return 1


def _window_on(windows: Sequence, on: date):
    return next((w for w in windows if w.covers(on)), None)


# -- policy facts ------------------------------------------------------------------

def _plan_for(repo: RatesSchemaRepository, policy: "PolicyInformation", plancode: str) -> Tuple[PlanDef, str]:
    plan, note = resolve_plan(repo.plan_defs(plancode), policy.company_code)
    if plan is None:
        detail = f" ({note})" if note else ""
        raise RatesNotLoaded(
            f"Plancode {plancode} is not loaded in {SOURCE_LABEL} yet{detail}. "
            "Its rates are still under Legacy (dbo)."
        )
    return plan, note


def _coverage(policy: "PolicyInformation", cov_index: int):
    covs = policy.coverages.get_coverages()
    if not 1 <= cov_index <= len(covs):
        raise ValueError(f"Coverage index {cov_index} is out of range.")
    return covs[cov_index - 1]


def _cov_index_for_phase(policy: "PolicyInformation", phase: int) -> Optional[int]:
    for index, cov in enumerate(policy.coverages.get_coverages(), start=1):
        if cov.cov_pha_nbr == phase:
            return index
    return None


def _years_between(start: Optional[date], end: Optional[date]) -> Optional[int]:
    if start and end and end > start:
        return end.year - start.year
    return None


def _stored_band_code(policy: "PolicyInformation", phase: int) -> str:
    """RT_BAN_CD on the coverage's renewal-rate rows (current row first)."""
    rows = [
        r for r in policy.rates.fetch_table("LH_COV_INS_RNL_RT")
        if int(r.get("COV_PHA_NBR", 0) or 0) == phase and str(r.get("JT_INS_IND", "") or "").strip() in ("", "0")
    ]
    rows.sort(key=lambda r: str(r.get("PRM_RT_TYP_CD", "") or "").strip() != "C")
    for row in rows:
        code = str(row.get("RT_BAN_CD", "") or "").strip()
        if code:
            return code
    return ""


def _band_context(repo, policy, cov, plan: PlanDef) -> Tuple[str, str, str, List[BandSpec]]:
    """(band, description, stored band text, band specs) for a coverage, as ``cov_band`` bands it."""
    from suiteview.core.band_rules import rider_bands_as_base

    base_plancode = policy.coverages.base_plancode
    bands_as_base = cov.is_base or rider_bands_as_base(cov.plancode)
    band_plan = plan
    if bands_as_base and not cov.is_base:
        band_plan, _ = _plan_for(repo, policy, base_plancode)
    amount = policy.coverages.base_band_specified_amount if bands_as_base else cov.face_amount
    on = policy.activity.issue_date if bands_as_base else cov.issue_date
    on = on or cov.issue_date
    bands = repo.plan_bands(band_plan.company, band_plan.plancode)
    spec, note = band_for_amount(bands, on, amount)
    amount_text = "" if amount is None else f"{Decimal(str(amount)):,.0f}"
    where = f" on {band_plan.plancode}" if band_plan.plancode != plan.plancode else ""
    stored = _stored_band_code(policy, cov.cov_pha_nbr)
    if spec is None:
        by_stored = _band_for_source(bands, on, stored)
        if by_stored is not None:
            # No usable limits: the coverage's own CyberLife band code, mapped by PLAN_BAND.SOURCE_BAND.
            text = f"{by_stored.band} (CyberLife {stored}, stored RT_BAN_CD){where}; {note}"
            return by_stored.band, text, "", bands
        return "", f"Not found{where}: {note}", "", bands
    text = f"{spec.band} (CyberLife {spec.source_band}) for {amount_text}{where}"
    if note:
        text = f"{spec.band} ({note})"
    stored_text = ""
    if stored and note == "unbanded":
        stored_text = "" if stored == UNBANDED else f"{stored} (plan is unbanded)"
    elif stored:
        same_spec = [b for b in bands if b.issue_date_from == spec.issue_date_from and b.source_band == stored]
        mapped = same_spec[0].band if same_spec else "not in PLAN_BAND"
        flag = "" if mapped == spec.band else "  <-- differs"
        stored_text = f"{stored} -> {mapped}{flag}"
    return spec.band, text, stored_text, bands


def _band_for_source(bands: Sequence[BandSpec], on: Optional[date], source_band: str) -> Optional[BandSpec]:
    """The band whose CyberLife code is ``source_band`` in the latest spec on/before ``on``."""
    if not source_band:
        return None
    rows = [b for b in bands if b.source_band == source_band and (on is None or b.issue_date_from <= on)]
    return max(rows, key=lambda b: b.issue_date_from) if rows else None


def _rein_for(policy: "PolicyInformation") -> str:
    """Dividend REIN key: ``RGA`` for Orion/RGA policies (TH_USER_GENERIC.FUZGREIN_IND = R)."""
    return "RGA" if policy.support.reins_partner == "R" else ""


def coverage_context(repo: RatesSchemaRepository, policy: "PolicyInformation", cov_index: int) -> CellContext:
    cov = _coverage(policy, cov_index)
    plan, plan_note = _plan_for(repo, policy, cov.plancode)
    if cov.issue_date is None or cov.issue_age is None:
        raise RatesNotLoaded(f"Coverage {cov_index} has no issue date or issue age for a rate lookup.")
    raw_sex = policy.rates.cov_rate_sex_code(cov_index)
    rate_class = str(policy.rates.renewal_cov_rateclass_by_cov(cov_index) or "").strip().upper()
    band, band_text, stored_band, _ = _band_context(repo, policy, cov, plan)
    subseries = str(policy.rates.data_item("LH_COV_PHA", "LIF_PLN_SUB_SRE_CD", cov_index - 1) or "").strip()
    key = RateKey(rates_sex(raw_sex), rate_class, band, str(policy.product.issue_state or "").strip().upper(),
                  subseries)
    extra = [("Table", cov.table_rating_code or "none")]
    return CellContext(
        label=f"Cov {cov_index:02d}", plan=plan, plan_note=plan_note, plancode=cov.plancode, benefit="",
        issue_date=cov.issue_date, issue_age=int(cov.issue_age),
        years=_years_between(cov.issue_date, cov.maturity_date), key=key, raw_sex=raw_sex,
        band_text=band_text, stored_band=stored_band, rein=_rein_for(policy), extra_meta=extra,
    )


def _benefit_rate_class(policy, ben) -> str:
    """The benefit's own renewal rate class, when it has one (``0`` = not class-specific)."""
    for rate in policy.rates.get_benefit_renewal_rates(ben.cov_pha_nbr):
        if (rate.benefit_type.strip() == ben.benefit_type_cd.strip()
                and rate.benefit_subtype.strip() == ben.benefit_subtype_cd.strip()
                and rate.joint_indicator.strip() in ("", "0")
                and rate.rate_class.strip() not in ("", "0")):
            return rate.rate_class.strip().upper()
    return ""


def benefit_context(repo: RatesSchemaRepository, policy: "PolicyInformation", ben_index: int) -> CellContext:
    benefits = policy.benefits.get_benefits()
    if not 1 <= ben_index <= len(benefits):
        raise ValueError(f"Benefit index {ben_index} is out of range.")
    ben = benefits[ben_index - 1]
    cov_index = _cov_index_for_phase(policy, ben.cov_pha_nbr)
    if cov_index is None:
        raise RatesNotLoaded(f"Benefit {ben_index} is on coverage phase {ben.cov_pha_nbr}, which is not loaded.")
    cov_ctx = coverage_context(repo, policy, cov_index)
    issue_date = ben.issue_date or cov_ctx.issue_date
    if ben.issue_age is None:
        raise RatesNotLoaded(f"Benefit {ben_index} has no issue age for a rate lookup.")
    ben_class = _benefit_rate_class(policy, ben)
    key = cov_ctx.key if not ben_class else RateKey(
        cov_ctx.key.sex, ben_class, cov_ctx.key.band, cov_ctx.key.state, cov_ctx.key.subseries)
    extra = [
        ("Benefit", f"{ben.benefit_code} {ben.benefit_desc}".strip()),
        ("On coverage", f"Cov {cov_index:02d} ({cov_ctx.plancode})"),
        ("Class source", "benefit renewal rate" if ben_class else "coverage"),
        ("Cease date", _iso(ben.cease_date)),
    ]
    return CellContext(
        label=f"Ben {ben_index:02d}", plan=cov_ctx.plan, plan_note=cov_ctx.plan_note,
        plancode=cov_ctx.plancode, benefit=str(ben.benefit_code or "").strip(), issue_date=issue_date,
        issue_age=int(ben.issue_age), years=_years_between(issue_date, ben.cease_date) or cov_ctx.years,
        key=key, raw_sex=cov_ctx.raw_sex, band_text=cov_ctx.band_text, stored_band=cov_ctx.stored_band,
        rein=cov_ctx.rein, extra_meta=extra,
    )


# -- rate parts --------------------------------------------------------------------

def cell_parts(repo: RatesSchemaRepository, ctx: CellContext,
               assignments: Optional[Sequence[CellAssignment]] = None) -> Parts:
    """CELL rates for a coverage (benefit '') or benefit: single values, columns and notes."""
    if assignments is None:
        assignments = repo.cell_assignments(ctx.plan.company, ctx.plancode)
    rows = [a for a in assignments if a.benefit == ctx.benefit]
    parts = Parts()
    if not rows:
        return parts
    subseries = repo.plan_subseries(ctx.plan.company, ctx.plancode) if any(a.subseries for a in rows) else ()
    rate_types = repo.rate_types()
    chosen: Dict[str, CellAssignment] = {}
    for rate_type in sorted({a.rate_type for a in rows}, key=rate_type_sort_key):
        assignment, notes = choose_cell(rows, rate_type, ctx.key, subseries)
        if assignment is None:
            parts.missing.append((rate_type, "; ".join(notes)))
            continue
        chosen[rate_type] = assignment
        parts.used.append((rate_type, cell_key_text(assignment) + (f"  [{'; '.join(notes)}]" if notes else "")))
    windows = repo.schedule_windows([a.schedule_id for a in chosen.values()])
    set_ids = [w.rate_set_id for w in windows]
    sets = repo.rate_sets(set_ids)
    values = repo.rate_values(set_ids, ctx.issue_age)
    by_schedule: Dict[int, List[ScheduleWindow]] = {}
    for window in windows:
        by_schedule.setdefault(window.schedule_id, []).append(window)
    for rate_type, assignment in chosen.items():
        definition = rate_types.get(rate_type)
        calendar = definition is not None and definition.date_meaning == "CALENDAR"
        schedule = by_schedule.get(assignment.schedule_id, [])
        for scale in SCALE_ORDER:
            scale_windows = sorted((w for w in schedule if w.scale == scale), key=lambda w: w.effective_from)
            if scale_windows:
                _add_scaled(parts, f"{rate_type} {scale}", rate_type, scale_windows, sets, values, ctx, calendar)
    return parts


def _add_scaled(parts: Parts, name: str, rate_type: str, windows: List[ScheduleWindow],
                sets: Dict[int, RateSetInfo], values: Dict[int, dict], ctx: CellContext, calendar: bool) -> None:
    point = rate_type in POINT_IN_TIME_RATE_TYPES
    grains = {sets[w.rate_set_id].grain for w in windows if w.rate_set_id in sets}
    if len(windows) > 1 or windows[0].effective_from > date(1900, 1, 1):
        basis = "each row's Date" if calendar else f"issue date {_iso(ctx.issue_date)}"
        parts.windows.append((name, f"{_window_text(windows)} (by {basis})"))
    if not calendar:
        window = _window_on(windows, ctx.issue_date)
        if window is None:
            parts.missing.append((name, f"no window covers issue date {_iso(ctx.issue_date)} "
                                        f"({_window_text(windows)})"))
            return
        grain = sets[window.rate_set_id].grain
        data = values.get(window.rate_set_id, {})
        if grain in SINGLE_VALUE_GRAINS:
            value = rate_at(grain, data, ctx.issue_age, 1)
            parts.single.append((name, fmt(value) if value is not None else f"none at issue age {ctx.issue_age}"))
            return
        parts.max_year = max(parts.max_year, last_year(grain, data, ctx.issue_age, point))
        parts.columns.append(Column(name, lambda year, _on, g=grain, d=data: fmt(
            rate_at(g, d, ctx.issue_age, year, point))))
        return
    for window in windows:
        info = sets.get(window.rate_set_id)
        if info is not None:
            parts.max_year = max(parts.max_year, last_year(info.grain, values.get(window.rate_set_id, {}),
                                                           ctx.issue_age, point))
    if grains and grains <= SINGLE_VALUE_GRAINS:
        parts.max_year = max(parts.max_year, 1)

    def value(year: int, on: date) -> object:
        window = _window_on(windows, on)
        if window is None:
            return "NA"
        info = sets.get(window.rate_set_id)
        if info is None:
            return "NA"
        grain = info.grain
        rate = rate_at(grain, values.get(window.rate_set_id, {}), ctx.issue_age,
                       1 if grain in SINGLE_VALUE_GRAINS else year, point)
        return fmt(rate)

    parts.columns.append(Column(name, value))


def plan_parts(repo: RatesSchemaRepository, plan: PlanDef, state: str, issue_age: int) -> Parts:
    """PLAN rates (no dates): single values for SCALAR/IA grains, columns for DUR/AA."""
    parts = Parts()
    assignments = repo.plan_assignments(plan.company, plan.plancode)
    if not assignments:
        return parts
    chosen = {}
    for a in sorted(assignments, key=lambda a: a.state != state):
        if a.state in (state, ALL_STATES):
            chosen.setdefault((a.rate_type, a.scale), a)
    sets = repo.rate_sets([a.rate_set_id for a in chosen.values()])
    values = repo.rate_values([a.rate_set_id for a in chosen.values()], issue_age)
    ordered = sorted(chosen.items(), key=lambda item: (rate_type_sort_key(item[0][0]),
                                                       SCALE_ORDER.index(item[0][1])))
    for (rate_type, scale), a in ordered:
        name = f"{rate_type} {scale}"
        info = sets.get(a.rate_set_id)
        data = values.get(a.rate_set_id, {})
        parts.used.append((name, f"state {a.state}, rate set {a.rate_set_id}"))
        if info is None:
            parts.missing.append((name, f"rate set {a.rate_set_id} not found"))
            continue
        if info.grain in SINGLE_VALUE_GRAINS:
            value = rate_at(info.grain, data, issue_age, 1)
            parts.single.append((name, fmt(value) if value is not None else f"none at issue age {issue_age}"))
            continue
        parts.max_year = max(parts.max_year, last_year(info.grain, data, issue_age))
        parts.columns.append(Column(name, lambda year, _on, g=info.grain, d=data: fmt(
            rate_at(g, d, issue_age, year))))
    return parts


def choose_div(assignments: Sequence[DivAssignment], key: RateKey, rein: str) -> Tuple[Optional[DivAssignment], List[str]]:
    """The dividend assignment, with the same fallbacks as ``choose_cell`` (REIN '' unless RGA)."""
    reins = _candidates(rein, [""])
    for rein_value in reins:
        for sex in _candidates(key.sex, [UNISEX]):
            for rate_class in _candidates(key.rate_class, CLASS_FALLBACKS):
                for band in _candidates(key.band, [UNBANDED]):
                    matches = [a for a in assignments if a.rein == rein_value and a.sex == sex
                               and a.rate_class == rate_class and a.band == band
                               and a.state in (key.state, ALL_STATES)]
                    if matches:
                        chosen = min(matches, key=lambda a: a.state != key.state)
                        notes = []
                        if sex != key.sex:
                            notes.append(f"sex {sex}")
                        if rate_class != key.rate_class:
                            notes.append(f"class {rate_class}")
                        if band != key.band:
                            notes.append(f"band {band}")
                        if rein_value != rein:
                            notes.append(f"REIN '{rein_value}' (policy {rein})")
                        return chosen, notes
    return None, [f"no dividend key for {key.sex}/{key.rate_class}/{key.band}"]


def _cohort(schedules: Sequence[DivSchedule], issue_date: date) -> List[DivSchedule]:
    starts = [s.issue_date_from for s in schedules if s.issue_date_from <= issue_date]
    if not starts:
        return []
    start = max(starts)
    return sorted((s for s in schedules if s.issue_date_from == start), key=lambda s: s.effective_from)


def div_parts(repo: RatesSchemaRepository, ctx: CellContext) -> Parts:
    """Dividend columns (base DIV/PUA/OYT per record type, PUA-key dividend) for a coverage."""
    parts = Parts()
    assignments = repo.div_assignments(ctx.plan.company, ctx.plancode)
    if not assignments:
        return parts
    chosen, notes = choose_div(assignments, ctx.key, ctx.rein)
    if chosen is None:
        parts.missing.append(("DIV", "; ".join(notes)))
        return parts
    parts.used.append(("DIV", f"{chosen.div_key} user key '{chosen.user_key}' "
                              f"({chosen.sex}/{chosen.rate_class}/{chosen.band}/{chosen.state})"
                              + (f"  [{'; '.join(notes)}]" if notes else "")))
    schedules = [s for s in repo.div_schedules([chosen.div_key]) if s.user_key == chosen.user_key]
    by_record: Dict[str, List[DivSchedule]] = {}
    for schedule in schedules:
        by_record.setdefault(schedule.record_type, []).append(schedule)
    cohorts = {record: _cohort(rows, ctx.issue_date) for record, rows in by_record.items()}
    pua_keys = {(s.pua_key, s.pua_user_key or "") for rows in cohorts.values() for s in rows
                if s.pua_participating == "2" and s.pua_key}
    pua_schedules = [s for s in repo.div_schedules(sorted({k for k, _ in pua_keys}))
                     if (s.div_key, s.user_key) in pua_keys]
    set_ids = [s.rate_set_id for rows in cohorts.values() for s in rows] + [s.rate_set_id for s in pua_schedules]
    values = repo.div_values(set_ids, [ctx.issue_age, 0])
    for record in sorted(cohorts, key=lambda r: list(DIV_RECORD_LABELS).index(r) if r in DIV_RECORD_LABELS else 9):
        cohort = cohorts[record]
        suffix = DIV_RECORD_LABELS.get(record, f" {record}")
        if not cohort:
            parts.missing.append((f"DIV{suffix}", f"no cohort on or before issue date {_iso(ctx.issue_date)}"))
            continue
        parts.windows.append((f"DIV{suffix}", f"cohort from {_iso(cohort[0].issue_date_from)}; scales "
                                              f"{_window_text(cohort)} (by each row's Date)"))
        for schedule in cohort:
            data = values.get(schedule.rate_set_id, {})
            if data:
                parts.max_year = max(parts.max_year, max((d for a, d in data if a == ctx.issue_age), default=0))
        for label, attr in (("DIV", "div_rate"), ("PUA", "pua_rate"), ("OYT", "oyt_rate")):
            if not any(getattr(v, attr) is not None for s in cohort for (a, _), v in values.get(s.rate_set_id, {}).items()
                       if a == ctx.issue_age):
                continue
            parts.columns.append(Column(f"{label}{suffix}", _div_value(cohort, values, ctx.issue_age, attr)))
        participating = {s.pua_participating for s in cohort}
        if participating == {"0"}:
            parts.single.append((f"PUA DIV{suffix}", "PUAs earn no dividend"))
        elif participating == {"1"}:
            parts.single.append((f"PUA DIV{suffix}", "PUAs use the base rates"))
        elif "2" in participating:
            parts.columns.append(Column(f"PUA DIV{suffix}", _pua_div_value(cohort, pua_schedules, values,
                                                                           ctx.issue_date, ctx.issue_age)))
    return parts


def _div_value(cohort: List[DivSchedule], values: Dict[int, dict], issue_age: int, attr: str):
    def value(year: int, on: date) -> object:
        schedule = _window_on(cohort, on)
        if schedule is None:
            return "NA"
        cell = values.get(schedule.rate_set_id, {}).get((issue_age, year))
        return fmt(getattr(cell, attr)) if cell is not None else ""
    return value


def _pua_div_value(cohort, pua_schedules, values, issue_date, issue_age):
    def value(year: int, on: date) -> object:
        base = _window_on(cohort, on)
        if base is None or base.pua_participating != "2":
            return "NA"
        rows = [s for s in pua_schedules if s.div_key == base.pua_key and s.user_key == (base.pua_user_key or "")
                and s.record_type == base.record_type]
        schedule = _window_on(_cohort(rows, issue_date), on)
        if schedule is None:
            return "NA"
        cell = values.get(schedule.rate_set_id, {}).get((0, issue_age + year))
        return fmt(cell.div_rate) if cell is not None else ""
    return value


# -- matrices ----------------------------------------------------------------------

def _context_meta(policy, ctx: CellContext) -> List[tuple]:
    company = ctx.plan.company + (f" ({ctx.plan_note})" if ctx.plan_note else "")
    raw = ctx.raw_sex or "blank"
    meta = [
        GAP, ("Source", SOURCE_LABEL), ("Policy", policy.policy_number), ("Leaf", ctx.label),
        ("Plancode", ctx.plancode), ("Rates company", company), ("Family", ctx.plan.product_family),
        ("Description", ctx.plan.description), ("IssueDate", _iso(ctx.issue_date)), ("IssueAge", ctx.issue_age),
        ("Sex", f"{ctx.key.sex or 'blank'} (CyberLife {raw})"), ("Rateclass", ctx.key.rate_class or "blank"),
        ("Band", ctx.band_text),
    ]
    if ctx.stored_band:
        meta.append(("Stored band", ctx.stored_band))
    meta.append(("State", ctx.key.state or "blank"))
    if ctx.key.subseries:
        meta.append(("Sub-series", ctx.key.subseries))
    if ctx.rein:
        meta.append(("Reinsurance", ctx.rein))
    meta.extend(ctx.extra_meta)
    return meta


def _parts_meta(parts: Parts) -> List[tuple]:
    meta: List[tuple] = []
    for title, lines in (("Single rates", parts.single), ("Cells used", parts.used),
                         ("Missing", parts.missing), ("Dated schedules", parts.windows)):
        if lines:
            meta += [GAP, (title, "")] + [(f"  {name}", value) for name, value in lines]
    meta += [GAP, ("Scales", "C current, G guaranteed, S shadow account")]
    return meta


def assemble(meta: List[tuple], columns: List[Column], start: date, issue_age: Optional[int],
             years: Optional[int], attained_label: str = "Age") -> List[List]:
    """The house layout: RateFields/RateInfo metadata beside Date/Age/Year and rate columns."""
    rows = max(years or 0, len(meta), 1)
    matrix = [["RateFields", "RateInfo", "Date", attained_label, "Year", *[c.name for c in columns]]]
    for year in range(1, rows + 1):
        on = _row_date(start, year)
        field_name, info = meta[year - 1] if year - 1 < len(meta) else ("", "")
        age = issue_age + year - 1 if issue_age is not None else ""
        matrix.append([field_name, info, on.strftime("%m/%d/%Y"), age, year,
                       *[column.value(year, on) for column in columns]])
    return matrix


def build_coverage_matrix(repo: RatesSchemaRepository, policy: "PolicyInformation", cov_index: int) -> List[List]:
    ctx = coverage_context(repo, policy, cov_index)
    parts = cell_parts(repo, ctx)
    parts.extend(div_parts(repo, ctx))
    base_plancode = policy.coverages.base_plancode
    if ctx.plancode != base_plancode:
        parts.extend(plan_parts(repo, ctx.plan, ctx.key.state, ctx.issue_age))
    if not parts.columns and not parts.single and not parts.missing:
        raise RatesNotLoaded(
            f"No coverage-level rates (CELL with benefit blank, DIV) are loaded for {ctx.plancode} in "
            f"{SOURCE_LABEL}. Its PLAN rates are under Policy and its benefit rates under Benefits."
        )
    years = ctx.years or parts.max_year
    return assemble(_context_meta(policy, ctx) + _parts_meta(parts), parts.columns,
                    ctx.issue_date, ctx.issue_age, years)


def build_benefit_matrix(repo: RatesSchemaRepository, policy: "PolicyInformation", ben_index: int) -> List[List]:
    ctx = benefit_context(repo, policy, ben_index)
    assignments = repo.cell_assignments(ctx.plan.company, ctx.plancode)
    if not any(a.benefit == ctx.benefit for a in assignments):
        loaded = ", ".join(sorted({a.benefit for a in assignments if a.benefit})) or "none"
        raise RatesNotLoaded(
            f"No rates are loaded for benefit {ctx.benefit or '(blank)'} on {ctx.plancode} in "
            f"{SOURCE_LABEL} (loaded benefits: {loaded})."
        )
    parts = cell_parts(repo, ctx, assignments)
    years = ctx.years or parts.max_year
    return assemble(_context_meta(policy, ctx) + _parts_meta(parts), parts.columns,
                    ctx.issue_date, ctx.issue_age, years)


def build_policy_matrix(repo: RatesSchemaRepository, policy: "PolicyInformation") -> List[List]:
    cov = _coverage(policy, 1)
    plancode = policy.coverages.base_plancode or cov.plancode
    plan, plan_note = _plan_for(repo, policy, plancode)
    if cov.issue_date is None or cov.issue_age is None:
        raise RatesNotLoaded("Coverage 1 has no issue date or issue age for a rate lookup.")
    state = str(policy.product.issue_state or "").strip().upper()
    parts = plan_parts(repo, plan, state, int(cov.issue_age))
    meta = [
        GAP, ("Source", SOURCE_LABEL), ("Policy", policy.policy_number), ("Plancode", plancode),
        ("Rates company", plan.company + (f" ({plan_note})" if plan_note else "")),
        ("Family", plan.product_family), ("Role", plan.coverage_role), ("Description", plan.description),
        ("User code", plan.user_code), ("IssueDate", _iso(cov.issue_date)), ("IssueAge", cov.issue_age),
        ("State", state or "blank"),
    ]
    if plan.facts:
        meta += [GAP, ("Plan facts", "PLAN_DEF")] + [(f"  {name}", fmt(value)) for name, value in plan.facts]
    attrs = repo.plan_attrs(plan.company, plan.plancode)
    if attrs:
        meta += [GAP, ("Plan attributes", "PLAN_ATTR")] + [(f"  {a.attr}", a.value) for a in attrs]
    if not parts.used:
        parts.missing.append(("PLAN", f"no PLAN rates are loaded for {plancode}"))
    years = _years_between(cov.issue_date, cov.maturity_date) or parts.max_year
    return assemble(meta + _parts_meta(parts), parts.columns, cov.issue_date, int(cov.issue_age), years,
                    attained_label="AttainedAge")


def _loaded_plans(repo, policy) -> List[Tuple[str, PlanDef, str]]:
    seen, plans = set(), []
    for cov in policy.coverages.get_coverages():
        if cov.plancode in seen:
            continue
        seen.add(cov.plancode)
        try:
            plan, note = _plan_for(repo, policy, cov.plancode)
        except RatesNotLoaded:
            continue
        plans.append((cov.plancode, plan, note))
    return plans


def build_fund_matrix(repo: RatesSchemaRepository, policy: "PolicyInformation") -> List[List]:
    """Every FUND rate assigned to the policy's loaded plancodes, newest rate start first."""
    held = {fund.strip() for fund in policy.values.get_fund_values_dict()}
    header = ["Plancode", "Fund", "Held", "Rein Block", "Fund Key", "Fund Type", "Rate Type", "Scale",
              "Rate Start", "Period", "Guar Months", "Guar End", "Rate", "Description"]
    body = []
    for plancode, plan, _note in _loaded_plans(repo, policy):
        assignments = repo.fund_assignments(plan.company, plancode)
        rates = repo.fund_rates([a.fund_key for a in assignments])
        by_key: Dict[str, list] = {}
        for rate in rates:
            by_key.setdefault(rate.fund_key, []).append(rate)
        for a in assignments:
            rows = sorted(by_key.get(a.fund_key, []),
                          key=lambda r: (rate_type_sort_key(r.rate_type), r.scale, -r.rate_start.toordinal(), r.period))
            for r in rows or [None]:
                body.append([
                    plancode, a.fund, "Yes" if a.fund in held else "", a.rein_block or "direct", a.fund_key,
                    a.fund_type,
                    *(["", "", "", "", "", "", "no rates loaded"] if r is None else [
                        r.rate_type, r.scale, _iso(r.rate_start), r.period, fmt(r.guarantee_months),
                        _iso(r.guarantee_end_date), fmt(r.rate)]),
                    a.description,
                ])
    if not body:
        raise RatesNotLoaded(f"No FUND rates are loaded in {SOURCE_LABEL} for this policy's plancodes.")
    return [header, *body]


def build_modal_matrix(repo: RatesSchemaRepository, policy: "PolicyInformation") -> List[List]:
    """PLAN_MODEFACT mode factors and fees of the policy's loaded plancodes."""
    header = ["Plancode", "Market Org", "Bill Form", "Fee Amount From", "Fee Amount To", "Mode", "Prem Factor",
              "Fee Factor", "Policy Fee", "Fee Add", "Fee Rule", "Collection Fee", "Coll Add",
              "Multiply Order", "Rating Order", "Rounding"]
    body = []
    for plancode, plan, _note in _loaded_plans(repo, policy):
        for m in repo.modal_factors(plan.company, plancode):
            body.append([plancode, m.market_org or "all", m.billing_form, fmt(m.fee_amount_from),
                         fmt(m.fee_amount_to), m.mode, fmt(m.prem_factor), fmt(m.fee_factor),
                         fmt(m.policy_fee_annual), m.policy_fee_add, m.policy_fee_rule, fmt(m.collection_fee),
                         m.collection_fee_add, m.multiply_order, m.rating_order, m.rounding_rule])
    if not body:
        raise RatesNotLoaded(f"No mode factors (PLAN_MODEFACT) are loaded in {SOURCE_LABEL} for this policy.")
    return [header, *body]


def _space_contexts(repo, policy, plancode: str) -> List[CellContext]:
    """Coverage and benefit contexts on ``plancode``; leaves that cannot be keyed are skipped."""
    contexts: List[CellContext] = []
    coverages = policy.coverages.get_coverages()
    for index, cov in enumerate(coverages, start=1):
        if cov.plancode == plancode:
            try:
                contexts.append(coverage_context(repo, policy, index))
            except RatesNotLoaded:
                pass
    for index, ben in enumerate(policy.benefits.get_benefits(), start=1):
        cov_index = _cov_index_for_phase(policy, ben.cov_pha_nbr)
        if cov_index is not None and coverages[cov_index - 1].plancode == plancode:
            try:
                contexts.append(benefit_context(repo, policy, index))
            except RatesNotLoaded:
                pass
    return contexts


def build_rate_space_matrix(repo: RatesSchemaRepository, policy: "PolicyInformation") -> List[List]:
    """Every CELL, PLAN, FUND and DIV assignment of the policy's loaded plancodes, marked where used."""
    header = ["Plancode", "Structure", "Benefit", "Rate Type", "Sex", "Class", "Band", "State", "Sub-series",
              "Key", "Scales", "Used By", "Date Meaning"]
    rate_types = repo.rate_types()
    base_plancode = policy.coverages.base_plancode
    state = str(policy.product.issue_state or "").strip().upper()
    body = []
    for plancode, plan, _note in _loaded_plans(repo, policy):
        contexts = _space_contexts(repo, policy, plancode)
        cov_labels = [ctx.label for ctx in contexts if not ctx.benefit]

        assignments = repo.cell_assignments(plan.company, plancode)
        subseries = repo.plan_subseries(plan.company, plancode) if any(a.subseries for a in assignments) else ()
        used: Dict[object, List[str]] = {}
        for ctx in contexts:
            rows = [a for a in assignments if a.benefit == ctx.benefit]
            for rate_type in {a.rate_type for a in rows}:
                chosen, _ = choose_cell(rows, rate_type, ctx.key, subseries)
                if chosen is not None:
                    used.setdefault(chosen, []).append(ctx.label)
        scales: Dict[int, set] = {}
        for window in repo.schedule_windows([a.schedule_id for a in assignments]):
            scales.setdefault(window.schedule_id, set()).add(window.scale)
        for a in sorted(assignments, key=lambda a: (a.benefit, rate_type_sort_key(a.rate_type), a.sex,
                                                    a.rate_class, a.band, a.state, a.subseries)):
            definition = rate_types.get(a.rate_type)
            body.append([
                plancode, "CELL", a.benefit or "base", a.rate_type, a.sex, a.rate_class, a.band, a.state,
                a.subseries, a.schedule_id, "".join(s for s in SCALE_ORDER if s in scales.get(a.schedule_id, set())),
                ", ".join(used.get(a, [])), definition.date_meaning if definition else "",
            ])

        plan_rows = repo.plan_assignments(plan.company, plancode)
        exact = {(a.rate_type, a.scale) for a in plan_rows if a.state == state}
        plan_user = "Policy Rates" if plancode == base_plancode else ", ".join(cov_labels)
        for a in sorted(plan_rows, key=lambda a: (rate_type_sort_key(a.rate_type), a.scale, a.state)):
            applies = a.state == state or (a.state == ALL_STATES and (a.rate_type, a.scale) not in exact)
            body.append([plancode, "PLAN", "", a.rate_type, "", "", "", a.state, "", a.rate_set_id, a.scale,
                         plan_user if applies else "", "NONE"])

        funds = repo.fund_assignments(plan.company, plancode)
        fund_types: Dict[str, Dict[str, set]] = {}
        for rate in repo.fund_rates([f.fund_key for f in funds]):
            fund_types.setdefault(rate.fund_key, {}).setdefault(rate.rate_type, set()).add(rate.scale)
        for f in funds:
            for rate_type, fund_scales in sorted(fund_types.get(f.fund_key, {}).items(),
                                                 key=lambda item: rate_type_sort_key(item[0])):
                body.append([plancode, "FUND", f"fund {f.fund}" + (f" rein {f.rein_block}" if f.rein_block else ""),
                             rate_type, "", "", "", "", "", f.fund_key,
                             "".join(s for s in SCALE_ORDER if s in fund_scales), "Fund Rates", "CALENDAR"])

        divs = repo.div_assignments(plan.company, plancode)
        for ctx in contexts:
            if ctx.benefit:
                continue
            chosen, _ = choose_div(divs, ctx.key, ctx.rein)
            if chosen is not None:
                used.setdefault(chosen, []).append(ctx.label)
        for a in sorted(divs, key=lambda a: (a.sex, a.rate_class, a.band, a.state, a.rein)):
            body.append([plancode, "DIV", a.rein, "DIV", a.sex, a.rate_class, a.band, a.state, "",
                         f"{a.div_key} '{a.user_key}'", "", ", ".join(used.get(a, [])), "CALENDAR"])
    if not body:
        raise RatesNotLoaded(f"None of this policy's plancodes has rates in {SOURCE_LABEL}.")
    return [header, *body]
