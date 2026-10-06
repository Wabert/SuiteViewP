"""PolView Rates views read from UL_Rates schema ``rates`` (the new rate tables).

Where a rate is shown follows its assignment table and ``RATE_TYPE.STRUCTURE``:

* **Coverage** - CELL rates with ``BENEFIT = ''`` for the coverage's plancode, the
  coverage's dividends (DIV), and, for a coverage whose plancode is not the base
  plan's, that plancode's PLAN rates. The policy-level charges (MFEE, premium loads)
  of the base plancode are on Policy instead. The coverages' **Scales** sheet lists
  every scale and dated schedule behind those rates, with the cell each one came from.
* **Benefit** - CELL rates whose ``BENEFIT`` is the benefit's type + subtype, on the
  plancode of the coverage the benefit is attached to.
* **Policy** - PLAN rates of the base plancode with the base coverage's policy-level
  CELL charges; its FUND rates split into fixed and index funds (one row per index
  rate start with each parameter in its own column); and its mode factors.

A coverage's rate key is its rate sex (``1`` -> ``M``, ``2`` -> ``F``, other CyberLife
codes kept as they are, as the loaders store them), its renewal rate class, the band
its amount falls in (``PLAN_BAND``), the issue state and, for sub-series keyed rates
(CV), the coverage's life sub-series. When the exact cell is not loaded the lookup
falls back, in order, to unisex ``U``, class ``0`` then ``*``, band ``0`` and state
``**``; a unisex ``U`` coverage on a rate type loaded under one sex only uses that
sex's cells (as CyberLife and the UL engine do). Every fallback used is listed on the
Scales sheet. Nothing else is guessed: a rate with no cell is reported as missing.

``DATE_MEANING`` ``ISSUE`` rates use the schedule window in effect on the issue date;
``CALENDAR`` rates use the window in effect on each row's Date (the start of that
policy year). Rate columns are grouped by scale - C current, G guaranteed, S shadow
account - with the scale in the band above the column and the rate type below it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from dateutil.relativedelta import relativedelta

from suiteview.core.rates import cyberlife_rate_user
from suiteview.core.rates_errors import RatesError
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
SCALE_NAMES = {"C": "Current", "G": "Guaranteed", "S": "Shadow account"}
# Header band over a scale's rate columns (Robert Haessly, 9/27/2026: spelled out, not C/G/S).
SCALE_BAND_LABELS = {"C": "Current", "G": "Guaranteed", "S": "Shadow"}
SINGLE_VALUE_GRAINS = frozenset({"IA", "SCALAR"})
# Point-in-time values: duration 0 is the issue date, so a row's Year n shows duration n - 1
# (the value at the row's Date), as the WL cash-value display does.
POINT_IN_TIME_RATE_TYPES = frozenset({"CV", "FACE_AMT"})
RATE_TYPE_ORDER = (
    "COI", "JointCOI", "JS_Q", "JS_Q 01", "Rated q 00", "Rated q 01",
    "EPU", "MFEE", "SCR", "SCR_PCT", "PREMLOAD_PCT", "PREMLOAD_EXS", "PREMLOAD_FLAT",
    "SHADOW_INT", "CV", "FACE_AMT", "PREM", "ADJ_PREM", "PUI", "PUI_A", "PUI_B", "PUI_C",
    "PUI_D", "PUI_E", "PUI_F", "MTP", "CTP", "PTP", "STP", "MTP_TBL1", "CTP_TBL1", "PTP_TBL1",
    "GCO_MIN", "GLP", "GSP", "SEVEN_PAY", "SEVEN_NSP", "LIFETIME_PREM", "ANN_BEN_PREM",
    "CORR", "GINT", "DB_DISCOUNT", "AV_CHARGE", "TABLE_COI_FACTOR", "SNET_PERIOD", "SCR_FLAT",
    "LOAN_REG_CHG", "LOAN_REG_CRD", "LOAN_PREF_CHG", "LOAN_PREF_CRD", "ANN_SURR_PCT",
    "ANN_FREE_WD_PCT",
)
# CELL rates charged once per policy (monthly policy fee, premium loads): shown on Policy
# Rates from the base coverage's cell, not on the base plancode's Cov NN grids
# (Robert Haessly, 9/28/2026).
POLICY_LEVEL_RATE_TYPES = frozenset({"MFEE", "PREMLOAD_PCT", "PREMLOAD_EXS", "PREMLOAD_FLAT"})
# rates.FUND.FUND_TYPE of an indexed account; every other fund type is a fixed (declared-rate) fund.
INDEX_FUND_TYPE = "INDEX"
INDEX_PARAMETER_PREFIX = "IDX_"
INDEX_PARAMETER_ORDER = ("CAP", "FLOOR", "PART", "SPREAD", "MULT", "ASSET", "SPEC")
DIV_RECORD_LABELS = {"D": "", "R": " RPU", "L": " DR-L", "P": " DR-P", "T": " TERM"}
DIV_GROUPS = tuple(f"Dividend{suffix}" for suffix in DIV_RECORD_LABELS.values())
# Top header band of a rate column, in display order: scales first, then dividends,
# then CyberLife's stored joint survivor rate and check.
JOINT_GROUP = "CyberLife"
COLUMN_GROUPS = (*SCALE_ORDER, *DIV_GROUPS, JOINT_GROUP)
GAP = (" ", " ")
SCALES_HEADER = ["Coverage", "Plancode", "Rate Type", "Scale", "Scale Name", "Effective From",
                 "Effective To", "Rates By", "Policy Years", "Cell", "Notes"]


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
    band_display: str
    system_band: str
    rein: str = ""
    extra_meta: List[tuple] = field(default_factory=list)


@dataclass(frozen=True)
class Column:
    """One rate column: ``group`` (C/G/S or a dividend group) above ``label`` (the rate type)."""
    group: str
    label: str
    value: Callable[[int, date], object]

    @property
    def key(self) -> str:
        return f"{self.group} {self.label}"


@dataclass
class ScaleEntry:
    """One scale of one rate type behind a coverage grid (a row group on the Scales sheet)."""
    rate_type: str
    scale: str
    windows: List[object]          # ScheduleWindow / DivSchedule rows; [] = no dates (PLAN)
    date_meaning: str              # ISSUE / CALENDAR / NONE
    cell: str
    notes: str = ""


@dataclass
class Parts:
    """Single values, missing rates, duration columns and scales from one rate source."""
    single: List[tuple] = field(default_factory=list)   # (scale, rate type, value)
    missing: List[tuple] = field(default_factory=list)  # (name, reason)
    columns: List[Column] = field(default_factory=list)
    scales: List[ScaleEntry] = field(default_factory=list)
    max_year: int = 0

    def extend(self, other: "Parts") -> None:
        self.single += other.single
        self.missing += other.missing
        self.columns += other.columns
        self.scales += other.scales
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


def _scale_index(scale: str) -> int:
    return SCALE_ORDER.index(scale) if scale in SCALE_ORDER else len(SCALE_ORDER)


def ordered_columns(columns: Sequence[Column]) -> List[Column]:
    """All C columns, then G, then S (rate types in house order), then dividend groups."""
    def key(pair):
        position, column = pair
        group = COLUMN_GROUPS.index(column.group) if column.group in COLUMN_GROUPS else len(COLUMN_GROUPS)
        within = rate_type_sort_key(column.label) if column.group in SCALE_ORDER else (0, "")
        return (group, within, position)
    return [column for _, column in sorted(enumerate(columns), key=key)]


def column_layout(header: Sequence[str]) -> Tuple[Dict[str, str], List[tuple]]:
    """Header labels and scale groups for a schema grid's column keys (``"C COI"``).

    Returns ``({key: rate type}, [(band label, [keys])])`` for ``FilterTableView``'s
    ``set_header_labels`` / ``set_column_groups``; scale bands are spelled out
    (``SCALE_BAND_LABELS``) and other columns are left as they are.
    """
    labels: Dict[str, str] = {}
    groups: List[tuple] = []
    for key in header:
        group = next((g for g in sorted(COLUMN_GROUPS, key=len, reverse=True)
                      if str(key).startswith(g + " ")), None)
        if group is None:
            continue
        labels[key] = str(key)[len(group) + 1:]
        band = SCALE_BAND_LABELS.get(group, group)
        if groups and groups[-1][0] == band:
            groups[-1][1].append(key)
        else:
            groups.append((band, [key]))
    return labels, groups


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
                plan_subseries: Sequence[SubseriesRow] = (), *,
                single_sex_fallback: bool = False) -> Tuple[Optional[CellAssignment], List[str]]:
    """The assignment for one rate type, and notes on each fallback used (or why none).

    Sub-series keyed rows (CV) match the coverage's sub-series with sex and class
    ignored (``rates.fn_RATE_SUB``); without one, ``PLAN_SUBSERIES`` maps sex/class to it.

    ``single_sex_fallback``: a unisex (``U``) key with no cell, on a rate type whose
    cells are all loaded under one other sex (the rates do not vary by sex), uses that
    sex's cells - CyberLife's behavior on the unisex UL plans loaded under M only.
    Never applies to sub-series keyed rows, nor when the cells span several sexes.
    """
    chosen, notes = _choose_cell(assignments, rate_type, key, plan_subseries)
    if chosen is not None or not single_sex_fallback or key.sex != UNISEX:
        return chosen, notes
    rows = [a for a in assignments if a.rate_type == rate_type]
    sexes = {a.sex for a in rows}
    if len(sexes) != 1 or UNISEX in sexes or any(a.subseries for a in rows):
        return chosen, notes
    sex = next(iter(sexes))
    retry, retry_notes = _choose_cell(assignments, rate_type, replace(key, sex=sex), plan_subseries)
    if retry is None:
        return chosen, notes
    return retry, [f"sex {sex} (policy {UNISEX}; plan loaded under one sex)", *retry_notes]


def _choose_cell(assignments: Sequence[CellAssignment], rate_type: str, key: RateKey,
                 plan_subseries: Sequence[SubseriesRow]) -> Tuple[Optional[CellAssignment], List[str]]:
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


def _year_ranges(years: Sequence[int]) -> str:
    """``[1, 2, 3, 7]`` -> ``"1-3, 7"``."""
    ranges: List[list] = []
    for year in years:
        if ranges and year == ranges[-1][1] + 1:
            ranges[-1][1] = year
        else:
            ranges.append([year, year])
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in ranges)


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


def _band_context(repo, policy, cov, plan: PlanDef) -> Tuple[str, str, str]:
    """(band, band display, system band) for a coverage, banded as ``cov_band`` bands it.

    The system band is the CyberLife band code (``PLAN_BAND.SOURCE_BAND``); when the
    coverage's stored ``RT_BAN_CD`` differs from it, the stored code is shown beside it.
    """
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
    where = f" (on {band_plan.plancode})" if band_plan.plancode != plan.plancode else ""
    stored = _stored_band_code(policy, cov.cov_pha_nbr)
    if spec is None:
        by_stored = _band_for_source(bands, on, stored)
        if by_stored is not None:
            # No usable limits: the coverage's own CyberLife band code, mapped by PLAN_BAND.SOURCE_BAND.
            return by_stored.band, by_stored.band + where, stored
        return "", f"Not found{where}: {note}", stored
    if note == "unbanded":
        system = spec.source_band if not stored or stored == UNBANDED else f"{stored} (plan is unbanded)"
        return spec.band, spec.band + where, system
    system = spec.source_band if not stored or stored == spec.source_band else \
        f"{spec.source_band} (policy record {stored})"
    return spec.band, spec.band + where, system


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
    band, band_display, system_band = _band_context(repo, policy, cov, plan)
    subseries = str(policy.rates.data_item("LH_COV_PHA", "LIF_PLN_SUB_SRE_CD", cov_index - 1) or "").strip()
    key = RateKey(rates_sex(raw_sex), rate_class, band, str(policy.product.issue_state or "").strip().upper(),
                  subseries)
    extra = [("Table", cov.table_rating_code or "none")]
    return CellContext(
        label=f"Cov {cov_index:02d}", plan=plan, plan_note=plan_note, plancode=cov.plancode, benefit="",
        issue_date=cov.issue_date, issue_age=int(cov.issue_age),
        years=_years_between(cov.issue_date, cov.maturity_date), key=key,
        band_display=band_display, system_band=system_band, rein=_rein_for(policy), extra_meta=extra,
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
        key=key, band_display=cov_ctx.band_display, system_band=cov_ctx.system_band,
        rein=cov_ctx.rein, extra_meta=extra,
    )


# -- rate parts --------------------------------------------------------------------

def cell_parts(repo: RatesSchemaRepository, ctx: CellContext,
               assignments: Optional[Sequence[CellAssignment]] = None,
               keep: Optional[Callable[[str], bool]] = None) -> Parts:
    """CELL rates for a coverage (benefit '') or benefit: single values, columns and scales.

    ``keep``, when given, limits the rate types read (e.g. the policy-level charges).
    """
    if assignments is None:
        assignments = repo.cell_assignments(ctx.plan.company, ctx.plancode)
    rows = [a for a in assignments if a.benefit == ctx.benefit and     (keep is None or keep(a.rate_type))]
    parts = Parts()
    if not rows:
        return parts
    subseries = repo.plan_subseries(ctx.plan.company, ctx.plancode) if any(a.subseries for a in rows) else ()
    rate_types = repo.rate_types()
    chosen: Dict[str, Tuple[CellAssignment, List[str]]] = {}
    for rate_type in sorted({a.rate_type for a in rows}, key=rate_type_sort_key):
        assignment, notes = choose_cell(rows, rate_type, ctx.key, subseries, single_sex_fallback=True)
        if assignment is None:
            parts.missing.append((rate_type, "; ".join(notes)))
            continue
        chosen[rate_type] = (assignment, notes)
    windows = repo.schedule_windows([a.schedule_id for a, _ in chosen.values()])
    set_ids = [w.rate_set_id for w in windows]
    sets = repo.rate_sets(set_ids)
    values = repo.rate_values(set_ids, ctx.issue_age)
    by_schedule: Dict[int, List[ScheduleWindow]] = {}
    for window in windows:
        by_schedule.setdefault(window.schedule_id, []).append(window)
    for rate_type, (assignment, notes) in chosen.items():
        definition = rate_types.get(rate_type)
        date_meaning = definition.date_meaning if definition is not None else "ISSUE"
        schedule = by_schedule.get(assignment.schedule_id, [])
        for scale in SCALE_ORDER:
            scale_windows = sorted((w for w in schedule if w.scale == scale), key=lambda w: w.effective_from)
            if not scale_windows:
                continue
            parts.scales.append(ScaleEntry(rate_type, scale, scale_windows, date_meaning,
                                           cell_key_text(assignment), "; ".join(notes)))
            _add_scaled(parts, scale, rate_type, scale_windows, sets, values, ctx, date_meaning == "CALENDAR")
    return parts


def _add_scaled(parts: Parts, scale: str, rate_type: str, windows: List[ScheduleWindow],
                sets: Dict[int, RateSetInfo], values: Dict[int, dict], ctx: CellContext, calendar: bool) -> None:
    point = rate_type in POINT_IN_TIME_RATE_TYPES
    grains = {sets[w.rate_set_id].grain for w in windows if w.rate_set_id in sets}
    if not calendar:
        window = _window_on(windows, ctx.issue_date)
        if window is None:
            parts.missing.append((f"{scale} {rate_type}", f"no window covers issue date {_iso(ctx.issue_date)} "
                                                          f"({_window_text(windows)})"))
            return
        grain = sets[window.rate_set_id].grain
        data = values.get(window.rate_set_id, {})
        if grain in SINGLE_VALUE_GRAINS:
            value = rate_at(grain, data, ctx.issue_age, 1)
            parts.single.append((scale, rate_type,
                                 fmt(value) if value is not None else f"none at issue age {ctx.issue_age}"))
            return
        parts.max_year = max(parts.max_year, last_year(grain, data, ctx.issue_age, point))
        parts.columns.append(Column(scale, rate_type, lambda year, _on, g=grain, d=data: fmt(
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

    parts.columns.append(Column(scale, rate_type, value))


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
    ordered = sorted(chosen.items(), key=lambda item: (_scale_index(item[0][1]), rate_type_sort_key(item[0][0])))
    for (rate_type, scale), a in ordered:
        info = sets.get(a.rate_set_id)
        data = values.get(a.rate_set_id, {})
        parts.scales.append(ScaleEntry(rate_type, scale, [], "NONE", f"plan rate, state {a.state}"))
        if info is None:
            parts.missing.append((f"{scale} {rate_type}", f"rate set {a.rate_set_id} not found"))
            continue
        if info.grain in SINGLE_VALUE_GRAINS:
            value = rate_at(info.grain, data, issue_age, 1)
            parts.single.append((scale, rate_type,
                                 fmt(value) if value is not None else f"none at issue age {issue_age}"))
            continue
        parts.max_year = max(parts.max_year, last_year(info.grain, data, issue_age))
        parts.columns.append(Column(scale, rate_type, lambda year, _on, g=info.grain, d=data: fmt(
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
    cell = f"{chosen.div_key} '{chosen.user_key}' ({chosen.sex}/{chosen.rate_class}/{chosen.band}/{chosen.state})"
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
        group = f"Dividend{DIV_RECORD_LABELS.get(record, f' {record}')}"
        if not cohort:
            parts.missing.append((group, f"no cohort on or before issue date {_iso(ctx.issue_date)}"))
            continue
        parts.scales.append(ScaleEntry(
            f"DIV{DIV_RECORD_LABELS.get(record, f' {record}')}", "Dividend", cohort, "CALENDAR",
            f"{cell}, cohort from {_iso(cohort[0].issue_date_from)}", "; ".join(notes)))
        for schedule in cohort:
            data = values.get(schedule.rate_set_id, {})
            if data:
                parts.max_year = max(parts.max_year, max((d for a, d in data if a == ctx.issue_age), default=0))
        for label, attr in (("DIV", "div_rate"), ("PUA", "pua_rate"), ("OYT", "oyt_rate")):
            if not any(getattr(v, attr) is not None for s in cohort for (a, _), v in values.get(s.rate_set_id, {}).items()
                       if a == ctx.issue_age):
                continue
            parts.columns.append(Column(group, label, _div_value(cohort, values, ctx.issue_age, attr)))
        participating = {s.pua_participating for s in cohort}
        if participating == {"0"}:
            parts.single.append((group, "PUA DIV", "PUAs earn no dividend"))
        elif participating == {"1"}:
            parts.single.append((group, "PUA DIV", "PUAs use the base rates"))
        elif "2" in participating:
            parts.columns.append(Column(group, "PUA DIV", _pua_div_value(cohort, pua_schedules, values,
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
    meta = [
        GAP, ("Policy", policy.policy_number), ("Plancode", ctx.plancode), ("Family", ctx.plan.product_family),
        ("IssueDate", _iso(ctx.issue_date)), ("IssueAge", ctx.issue_age), ("Sex", ctx.key.sex or "blank"),
        ("Rateclass", ctx.key.rate_class or "blank"), ("Band", ctx.band_display),
        ("System Band", ctx.system_band or "blank"), ("State", ctx.key.state or "blank"),
    ]
    if ctx.key.subseries:
        meta.append(("Sub-series", ctx.key.subseries))
    if ctx.rein:
        meta.append(("Reinsurance", ctx.rein))
    meta.extend(ctx.extra_meta)
    return meta


def single_rates_title(group: str) -> str:
    return f"Single rates ({group})"


def _parts_meta(parts: Parts) -> List[tuple]:
    meta: List[tuple] = []
    by_group: Dict[str, List[tuple]] = {}
    for group, rate_type, value in parts.single:
        by_group.setdefault(group, []).append((rate_type, value))
    for group in sorted(by_group, key=lambda g: COLUMN_GROUPS.index(g) if g in COLUMN_GROUPS else len(COLUMN_GROUPS)):
        lines = sorted(by_group[group], key=lambda line: rate_type_sort_key(line[0]))
        meta += [GAP, (single_rates_title(group), "")] + [(f"  {name}", value) for name, value in lines]
    if parts.missing:
        meta += [GAP, ("Missing", "")] + [(f"  {name}", reason) for name, reason in parts.missing]
    return meta


def assemble(meta: List[tuple], columns: List[Column], start: date, issue_age: Optional[int],
             years: Optional[int], attained_label: str = "Age") -> List[List]:
    """The house layout: RateFields/RateInfo metadata beside Date/Age/Year and rate columns.

    Rate columns are keyed ``"<group> <rate type>"`` (e.g. ``"C COI"``); ``column_layout``
    turns the keys into the scale band and rate-type labels the grid shows.
    """
    columns = ordered_columns(columns)
    rows = max(years or 0, len(meta), 1)
    matrix = [["RateFields", "RateInfo", "Date", attained_label, "Year", *[c.key for c in columns]]]
    for year in range(1, rows + 1):
        on = _row_date(start, year)
        field_name, info = meta[year - 1] if year - 1 < len(meta) else ("", "")
        age = issue_age + year - 1 if issue_age is not None else ""
        matrix.append([field_name, info, on.strftime("%m/%d/%Y"), age, year,
                       *[column.value(year, on) for column in columns]])
    return matrix


def is_policy_level(rate_type: str) -> bool:
    return rate_type in POLICY_LEVEL_RATE_TYPES


def _coverage_parts(repo: RatesSchemaRepository, policy: "PolicyInformation", cov_index: int,
                    include_policy_level: bool = False):
    """A coverage's rates; the base plancode's policy-level charges only when asked (Scales)."""
    ctx = coverage_context(repo, policy, cov_index)
    on_base = ctx.plancode == policy.coverages.base_plancode
    keep = None if include_policy_level or not on_base else (lambda rate_type: not is_policy_level(rate_type))
    parts = cell_parts(repo, ctx, keep=keep)
    parts.extend(div_parts(repo, ctx))
    if not on_base:
        parts.extend(plan_parts(repo, ctx.plan, ctx.key.state, ctx.issue_age))
    return ctx, parts


def build_coverage_matrix(repo: RatesSchemaRepository, policy: "PolicyInformation", cov_index: int) -> List[List]:
    ctx, parts = _coverage_parts(repo, policy, cov_index)
    if not parts.columns and not parts.single and not parts.missing:
        raise RatesNotLoaded(
            f"No coverage-level rates (CELL with benefit blank, DIV) are loaded for {ctx.plancode} in "
            f"{SOURCE_LABEL}. Its PLAN rates and policy-level charges (MFEE, premium loads) are under "
            "Policy and its benefit rates under Benefits."
        )
    joint_meta: List[tuple] = []
    if policy.rates.cov_is_joint_survivor(cov_index):
        joint, joint_meta = joint_survivor_parts(policy, cov_index)
        parts.extend(joint)
    years = ctx.years or parts.max_year
    return assemble(_context_meta(policy, ctx) + joint_meta + _parts_meta(parts), parts.columns,
                    ctx.issue_date, ctx.issue_age, years)


def joint_survivor_parts(policy: "PolicyInformation", cov_index: int) -> Tuple[Parts, List[tuple]]:
    """A joint survivor coverage's blended COI (VP/MS JSURVCOI) beside its schema rates.

    The 12 FFL second-to-die plans have no base COI cell: the grid's own ``JS_Q``
    column is the primary insured's (person 00) single-life rate. This adds the
    joint insured's JS_Q, the blended ``JointCOI`` per scale (and each life's rated q
    when extras apply), and CyberLife's stored rate and check on the current policy
    year row, which PolView highlights.
    """
    js = policy.rates.rates_joint_survivor(cov_index)

    def by_year(series, rounding: Optional[int] = None):
        def value(year: int, _on: date) -> object:
            if not 1 <= year <= js.horizon:
                return ""
            item = series[year - 1]
            return round(item, rounding) if rounding is not None else item
        return value

    columns = []
    for scale in ("C", "G"):
        schedule = js.schedule.current if scale == "C" else js.schedule.guaranteed
        years = js.schedule.current_years if scale == "C" else js.schedule.guaranteed_years
        columns += [Column(scale, "JointCOI", by_year(schedule)),
                    Column(scale, "JS_Q 01", by_year(js.js_q[scale][1]))]
        if js.ratings:
            # Display-only rounding of float noise (e.g. 0.0372626999999...).
            columns += [Column(scale, "Rated q 00", by_year([y.qx for y in years], 9)),
                        Column(scale, "Rated q 01", by_year([y.qy for y in years], 9))]

    def on_policy_year(value_now):
        return lambda year, _on: value_now if year == js.policy_year else ""

    stored = js.stored_rate if js.stored_rate is not None else "NULL"
    columns += [Column(JOINT_GROUP, "RNL_RT", on_policy_year(stored)),
                Column(JOINT_GROUP, "Check", on_policy_year(js.comparison_text))]
    meta = [GAP, *policy.rates.joint_survivor_fields(cov_index, js)]
    return Parts(columns=columns, max_year=js.horizon), meta


def _policy_years(entry: ScaleEntry, start: date, issue_date: date, rows: int) -> str:
    """The policy years (grid rows) that use this scale entry's windows."""
    if not entry.windows:
        return "all"
    if entry.date_meaning != "CALENDAR":
        return "all (issue date)" if _window_on(entry.windows, issue_date) is not None else "none"
    years = [year for year in range(1, rows + 1) if _window_on(entry.windows, _row_date(start, year)) is not None]
    return _year_ranges(years) if years else "none"


def build_scales_matrix(repo: RatesSchemaRepository, policy: "PolicyInformation") -> List[List]:
    """Every scale and dated schedule behind the Coverages grids, one row per window."""
    body = []
    rates_by = {"CALENDAR": "each policy year's date", "ISSUE": "issue date", "NONE": "no dates"}
    for cov_index, cov in enumerate(policy.coverages.get_coverages(), start=1):
        try:
            ctx, parts = _coverage_parts(repo, policy, cov_index, include_policy_level=True)
        except RatesNotLoaded as exc:
            body.append([f"Cov {cov_index:02d}", cov.plancode, "", "", "", "", "", "", "", "", str(exc)])
            continue
        rows = max(ctx.years or parts.max_year, 1)
        entries = sorted(parts.scales, key=lambda e: (
            COLUMN_GROUPS.index(e.scale) if e.scale in COLUMN_GROUPS else len(COLUMN_GROUPS),
            rate_type_sort_key(e.rate_type)))
        on_base = ctx.plancode == policy.coverages.base_plancode
        for entry in entries:
            name = SCALE_NAMES.get(entry.scale, entry.scale)
            used = _policy_years(entry, ctx.issue_date, ctx.issue_date, rows)
            windows = entry.windows or [None]
            notes = entry.notes
            if on_base and is_policy_level(entry.rate_type):
                notes = "; ".join(n for n in ("shown on Policy Rates", notes) if n)
            for window in windows:
                years = used if window is None or len(windows) == 1 else _policy_years(
                    ScaleEntry(entry.rate_type, entry.scale, [window], entry.date_meaning, ""),
                    ctx.issue_date, ctx.issue_date, rows)
                body.append([
                    ctx.label, ctx.plancode, entry.rate_type, entry.scale if entry.scale in SCALE_ORDER else "",
                    name, _iso(window.effective_from) if window else "",
                    (_iso(window.effective_to) or "open") if window else "",
                    rates_by.get(entry.date_meaning, entry.date_meaning), years, entry.cell, notes,
                ])
        for name, reason in parts.missing:
            body.append([ctx.label, ctx.plancode, name, "", "", "", "", "", "", "", f"Missing: {reason}"])
    if not body:
        raise RatesNotLoaded(f"No coverage rates are loaded in {SOURCE_LABEL} for this policy.")
    return [SCALES_HEADER, *body]


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


def _base_coverage_index(policy: "PolicyInformation", plancode: str) -> int:
    """The first coverage on the base plancode (its cell keys the policy-level charges)."""
    for index, cov in enumerate(policy.coverages.get_coverages(), start=1):
        if cov.plancode == plancode:
            return index
    return 1


def _policy_charge_parts(repo: RatesSchemaRepository, policy: "PolicyInformation",
                         plan: PlanDef, plancode: str) -> Tuple[Parts, List[tuple]]:
    """The base coverage's policy-level CELL charges (MFEE, premium loads) and their key lines."""
    assignments = [a for a in repo.cell_assignments(plan.company, plancode)
                   if not a.benefit and is_policy_level(a.rate_type)]
    if not assignments:
        return Parts(), []
    cov_index = _base_coverage_index(policy, plancode)
    try:
        ctx = coverage_context(repo, policy, cov_index)
    except RatesNotLoaded as exc:
        return Parts(missing=[("Policy charges", str(exc))]), []
    parts = cell_parts(repo, ctx, assignments)
    meta = [GAP, ("Charges cell", ctx.label), ("  Sex", ctx.key.sex or "blank"),
            ("  Rateclass", ctx.key.rate_class or "blank"), ("  Band", ctx.band_display)]
    return parts, meta


def build_policy_matrix(repo: RatesSchemaRepository, policy: "PolicyInformation") -> List[List]:
    """Base plancode PLAN rates plus the base coverage's policy-level CELL charges."""
    cov = _coverage(policy, 1)
    plancode = policy.coverages.base_plancode or cov.plancode
    plan, _plan_note = _plan_for(repo, policy, plancode)
    if cov.issue_date is None or cov.issue_age is None:
        raise RatesNotLoaded("Coverage 1 has no issue date or issue age for a rate lookup.")
    state = str(policy.product.issue_state or "").strip().upper()
    parts = plan_parts(repo, plan, state, int(cov.issue_age))
    if not parts.scales:
        parts.missing.append(("PLAN", f"no PLAN rates are loaded for {plancode}"))
    charges, charge_meta = _policy_charge_parts(repo, policy, plan, plancode)
    parts.extend(charges)
    meta = [
        GAP, ("Policy", policy.policy_number), ("Plancode", plancode), ("Family", plan.product_family),
        ("Role", plan.coverage_role), ("IssueDate", _iso(cov.issue_date)), ("IssueAge", cov.issue_age),
        ("State", state or "blank"),
    ] + charge_meta
    if plan.facts:
        meta += [GAP, ("Plan facts", "PLAN_DEF")] + [(f"  {name}", fmt(value)) for name, value in plan.facts]
    attrs = repo.plan_attrs(plan.company, plan.plancode)
    if attrs:
        meta += [GAP, ("Plan attributes", "PLAN_ATTR")] + [(f"  {a.attr}", a.value) for a in attrs]
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


def _fund_rows(repo: RatesSchemaRepository, policy: "PolicyInformation", index: bool):
    """``(plancode, assignment, rates)`` for the policy's fixed or index funds, in assignment order.

    Rates sort current, guaranteed then shadow; then rate type and newest rate start first.
    """
    for plancode, plan, _note in _loaded_plans(repo, policy):
        assignments = [a for a in repo.fund_assignments(plan.company, plancode)
                       if (a.fund_type == INDEX_FUND_TYPE) == index]
        by_key: Dict[str, list] = {}
        for rate in repo.fund_rates([a.fund_key for a in assignments]):
            by_key.setdefault(rate.fund_key, []).append(rate)
        for a in assignments:
            rates = sorted(by_key.get(a.fund_key, []),
                           key=lambda r: (_scale_index(r.scale), rate_type_sort_key(r.rate_type),
                                          -r.rate_start.toordinal(), r.period))
            yield plancode, a, rates


def _held_funds(policy: "PolicyInformation") -> set:
    return {fund.strip() for fund in policy.values.get_fund_values_dict()}


def build_fixed_fund_matrix(repo: RatesSchemaRepository, policy: "PolicyInformation") -> List[List]:
    """Every FUND rate of the policy's fixed (non-index) funds, one row per rate, newest start first."""
    held = _held_funds(policy)
    header = ["Plancode", "Fund", "Held", "Rein Block", "Fund Key", "Fund Type", "Rate Type", "Scale",
              "Rate Start", "Period", "Guar Months", "Guar End", "Rate"]
    body = []
    for plancode, a, rates in _fund_rows(repo, policy, index=False):
        for r in rates or [None]:
            body.append([
                plancode, a.fund, "Yes" if a.fund in held else "", a.rein_block or "direct", a.fund_key,
                a.fund_type,
                *(["", "", "", "", "", "", "no rates loaded"] if r is None else [
                    r.rate_type, r.scale, _iso(r.rate_start), r.period, fmt(r.guarantee_months),
                    _iso(r.guarantee_end_date), fmt(r.rate)]),
            ])
    if not body:
        raise RatesNotLoaded(f"No fixed-fund rates are loaded in {SOURCE_LABEL} for this policy's plancodes.")
    return [header, *body]


def index_parameter_label(rate_type: str) -> str:
    """``IDX_CAP`` -> ``CAP``; other rate types keep their name."""
    if rate_type.startswith(INDEX_PARAMETER_PREFIX):
        return rate_type[len(INDEX_PARAMETER_PREFIX):]
    return rate_type


def _index_parameter_sort_key(rate_type: str) -> tuple:
    label = index_parameter_label(rate_type)
    if label in INDEX_PARAMETER_ORDER:
        return (0, INDEX_PARAMETER_ORDER.index(label), label)
    return (1, 0, rate_type)


def _joined(values: Iterable[object]) -> object:
    """One value, or every distinct loaded value joined with `` / `` so a conflict is visible."""
    distinct = list(dict.fromkeys(v for v in values if v not in ("", None)))
    if not distinct:
        return ""
    return distinct[0] if len(distinct) == 1 else " / ".join(str(v) for v in distinct)


def build_index_fund_matrix(repo: RatesSchemaRepository, policy: "PolicyInformation") -> List[List]:
    """The policy's index funds: one row per fund, scale, rate start and period, with every
    index parameter (cap, floor, participation, ...) in its own column; newest start first.

    A parameter with no rate for a row's start is blank. Guarantee columns appear only
    when a rate carries a guarantee; a fund with no rates is listed with a Note.
    """
    held = _held_funds(policy)
    funds = list(_fund_rows(repo, policy, index=True))
    if not funds:
        raise RatesNotLoaded(f"No index-fund rates are loaded in {SOURCE_LABEL} for this policy's plancodes.")
    all_rates = [r for _, _, rates in funds for r in rates]
    parameters = sorted({r.rate_type for r in all_rates}, key=_index_parameter_sort_key)
    guarantees = any(r.guarantee_months is not None or r.guarantee_end_date for r in all_rates)
    unloaded = any(not rates for _, _, rates in funds)
    header = ["Plancode", "Fund", "Held", "Rein Block", "Fund Key", "Scale", "Rate Start", "Period",
              *[index_parameter_label(p) for p in parameters]]
    if guarantees:
        header += ["Guar Months", "Guar End"]
    if unloaded:
        header.append("Note")
    body = []
    for plancode, a, rates in funds:
        lead = [plancode, a.fund, "Yes" if a.fund in held else "", a.rein_block or "direct", a.fund_key]
        if not rates:
            body.append(lead + [""] * (len(header) - len(lead) - 1) + ["no rates loaded"])
            continue
        grouped: Dict[tuple, list] = {}
        for r in rates:
            grouped.setdefault((r.scale, r.rate_start, r.period), []).append(r)
        for (scale, start, period) in sorted(grouped, key=lambda k: (_scale_index(k[0]), -k[1].toordinal(), k[2])):
            row_rates = grouped[(scale, start, period)]
            row = lead + [scale, _iso(start), period]
            row += [_joined(fmt(r.rate) for r in row_rates if r.rate_type == p) for p in parameters]
            if guarantees:
                row += [_joined(fmt(r.guarantee_months) for r in row_rates),
                        _joined(_iso(r.guarantee_end_date) for r in row_rates)]
            if unloaded:
                row.append("")
            body.append(row)
    return [header, *body]


def build_modal_matrix(repo: RatesSchemaRepository, policy: "PolicyInformation") -> List[List]:
    """PLAN_MODEFACT mode factors and fees of the base plancode.

    Modal factors apply at the policy level, so rider plancodes' rows are not shown.
    """
    header = ["Plancode", "Market Org", "Bill Form", "Fee Amount From", "Fee Amount To", "Mode", "Prem Factor",
              "Fee Factor", "Policy Fee", "Fee Add", "Fee Rule", "Collection Fee", "Coll Add",
              "Multiply Order", "Rating Order", "Rounding"]
    plancode = str(policy.coverages.base_plancode or "").strip()
    if not plancode:
        raise RatesNotLoaded("This policy has no base coverage plancode, so no mode factors can be shown.")
    plan, _note = _plan_for(repo, policy, plancode)
    body = []
    for m in repo.modal_factors(plan.company, plancode):
        body.append([plancode, m.market_org or "all", m.billing_form, fmt(m.fee_amount_from),
                     fmt(m.fee_amount_to), m.mode, fmt(m.prem_factor), fmt(m.fee_factor),
                     fmt(m.policy_fee_annual), m.policy_fee_add, m.policy_fee_rule, fmt(m.collection_fee),
                     m.collection_fee_add, m.multiply_order, m.rating_order, m.rounding_rule])
    if not body:
        raise RatesNotLoaded(
            f"No mode factors (PLAN_MODEFACT) are loaded in {SOURCE_LABEL} for base plancode {plancode}.")
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
        charge_label = f"Cov {_base_coverage_index(policy, plancode):02d}" if plancode == base_plancode else None
        for ctx in contexts:
            rows = [a for a in assignments if a.benefit == ctx.benefit]
            for rate_type in {a.rate_type for a in rows}:
                label = ctx.label
                if charge_label and not ctx.benefit and is_policy_level(rate_type):
                    if ctx.label != charge_label:
                        continue
                    label = "Policy Rates"
                chosen, _ = choose_cell(rows, rate_type, ctx.key, subseries, single_sex_fallback=True)
                if chosen is not None:
                    used.setdefault(chosen, []).append(label)
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
            leaf = "Index Fund Rates" if f.fund_type == INDEX_FUND_TYPE else "Fixed Fund Rates"
            for rate_type, fund_scales in sorted(fund_types.get(f.fund_key, {}).items(),
                                                 key=lambda item: rate_type_sort_key(item[0])):
                body.append([plancode, "FUND", f"fund {f.fund}" + (f" rein {f.rein_block}" if f.rein_block else ""),
                             rate_type, "", "", "", "", "", f.fund_key,
                             "".join(s for s in SCALE_ORDER if s in fund_scales), leaf, "CALENDAR"])

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
