"""Term Rate Workup builder — one IAF in, UL_Rates-ready TERM_* CSVs out.

Term rates are stored *pre-compiled*: rather than keeping select and ultimate
scales separately and resolving them at quote time, every (IssueAge, Duration)
cell is materialized into TERM_RATE_PREM / TERM_RATE_BEN. That is why these
two tables hold millions of rows, and why the compile step below is the heart
of this module.

The pipeline is:

1. Parse the IAF (:class:`suiteview.ratemanager.parser.IAFParser`).
2. Split rates into the base plan (plan_option ``**``) and one bucket per
   benefit plan_option (``30`` = PWoC, ``3N``, ...).
3. Within each bucket, split *select* rates (duration != 99, vary by issue
   age) from *ultimate* rates (duration == 99, vary by attained age).
4. Allocate a string index per (Sex, Rateclass, Band) combo — ``1001_PL`` for
   base premium, ``1001_30`` for benefit ``30``.
5. Compile: hold the first select rate for FIRSTLEVEL policy years, each
   later select rate for RENLEVEL years, then fill forward from the ultimate
   table by attained age until the ultimate rates run out.

Note how maturity is used. The extent of a compiled rate is normally decided
by the IAF's own data — the ultimate table simply runs out. Capping every
plan at its maturity would be wrong: B155R200 is a 20-year level term
(ME-AGE 020/DUR) whose ultimate rates correctly continue to attained age 79.
But a non-renewable plan (FIRSTLEVEL >= 999) has no natural end at all, so
the *AGE* maturity supplies the stopping point. The rule is therefore: apply
an AGE maturity as a ceiling on attained age, never apply a DUR maturity.
"""

from __future__ import annotations

import os
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from suiteview.ratemanager.parser import IAFParser, ParseResult
from suiteview.ratemanager.workup.term_spec import (
    MODEFACT_FIELDS, NON_RENEWABLE_LEVEL, TermWorkupSpec,
)
from suiteview.ratemanager.workup.writers import (
    ensure_dir, fmt_rate, write_csv, write_summary,
)

ComboKey = Tuple[str, str, str]        # (sex, rate_class, band) — output codes
ProgressCB = Optional[Callable[[float, str], None]]

# Placeholder rate the mainframe prints where a real rate is not yet loaded.
DUMMY_RATE = 9999.99

# The IAF encodes ultimate (attained-age) rates with this sentinel duration.
ULTIMATE_DURATION = 99

# Index suffix for base premium rates. Benefits use their plan_option code.
PREMIUM_SUFFIX = "PL"


# ---------------------------------------------------------------------------
# Locked output schemas (match the UL_Rates physical TERM_* tables)
# ---------------------------------------------------------------------------

POINT_PV_HEADERS = [
    "Plancode", "IssueVersion", "Index(MODEFACT)", "Index(BANDSPEC)", "FEE",
]
POINT_PVSRB_HEADERS = [
    "Plancode", "IssueVersion", "Sex", "Rateclass", "Band", "Index(PREM)",
]
POINT_BENEFIT_HEADERS = [
    "Plancode", "IssueVersion", "BenefitType", "Benefit",
    "Sex", "Rateclass", "Band", "Index(BEN)",
]
RATE_MODEFACT_HEADERS = ["Index(MODEFACT)", *MODEFACT_FIELDS]
# Physical column order in SQL Server puts Issue_Date last.
RATE_BANDSPECS_HEADERS = [
    "Index(BANDSPEC)", "SpecifiedAmount", "Band", "BandCode", "Issue_Date",
]
RATE_PREM_HEADERS = ["Index(PREM)", "Scale", "IssueAge", "Duration", "Rate"]
RATE_BEN_HEADERS = ["Index(BEN)", "Scale", "IssueAge", "Duration", "Rate"]

TERM_TABLE_FILES = [
    "TERM_POINT_PV", "TERM_POINT_PVSRB", "TERM_POINT_BENEFIT",
    "TERM_RATE_MODEFACT", "TERM_RATE_BANDSPECS",
    "TERM_RATE_PREM", "TERM_RATE_BEN",
]

TERM_TABLE_HEADERS: "OrderedDict[str, List[str]]" = OrderedDict([
    ("TERM_POINT_PV", POINT_PV_HEADERS),
    ("TERM_POINT_PVSRB", POINT_PVSRB_HEADERS),
    ("TERM_POINT_BENEFIT", POINT_BENEFIT_HEADERS),
    ("TERM_RATE_MODEFACT", RATE_MODEFACT_HEADERS),
    ("TERM_RATE_BANDSPECS", RATE_BANDSPECS_HEADERS),
    ("TERM_RATE_PREM", RATE_PREM_HEADERS),
    ("TERM_RATE_BEN", RATE_BEN_HEADERS),
])

# Benefit label, keyed by the first character of the IAF plan_option.
BENEFIT_TYPE_MAP = {
    "1": "ADB",     # Accidental Death Benefit
    "2": "ADnD",    # Accidental Death and Dismemberment
    "3": "PWoC",    # Premium Waiver of Cost
    "4": "PWoT",    # Premium Waiver of Target
    "7": "GIO",     # Guaranteed Increase Option
    "9": "PPB",     # Premium Payor Benefit
    "#": "ABR",     # Accelerated Benefit Rider
    "A": "CCV",     # Coverage Continuation Rider
    "U": "COLA",    # Cost of Living Adjustment
    "B": "LTC",     # Long Term Care
    "V": "GCO",     # Guaranteed Cash Out Rider
}


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class TermWorkupAnalysis:
    """Everything learned from the IAF before building."""

    iaf_result: Optional[ParseResult] = None
    plancode: str = ""
    issue_version: int = 1
    eff_date: str = ""
    # Derived from the plan header ME-AGE + its use code. Metadata only.
    maturity_use: str = ""            # "AGE" | "DUR"
    maturity_value: int = 0
    pay_age: int = 0
    pay_age_use: int = 0
    combos: List[ComboKey] = field(default_factory=list)
    ia_min: int = 0
    ia_max: int = 0
    select_durations: int = 0
    ultimate_age_min: int = 0
    ultimate_age_max: int = 0
    scales: List[Tuple[int, str]] = field(default_factory=list)
    banded: bool = False
    # (code, label, combo_count, select_durations, rate_count)
    benefits: List[Tuple[str, str, int, int, int]] = field(default_factory=list)
    benefit_combos: Dict[str, List[ComboKey]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    error: str = ""

    @property
    def maturity_label(self) -> str:
        if not self.maturity_use:
            return ""
        return f"{self.maturity_use} {self.maturity_value}"

    @property
    def max_attained_age(self) -> Optional[int]:
        """Ceiling on attained age implied by the maturity, if any.

        Only an AGE maturity bounds the rate schedule; a DUR maturity
        describes the level period and must not truncate a renewable plan.
        """
        if self.maturity_use == "AGE" and self.maturity_value:
            return self.maturity_value - 1
        return None

    def rate_space_summary(self) -> str:
        sexes = sorted({s for (s, _c, _b) in self.combos})
        classes = sorted({c for (_s, c, _b) in self.combos})
        bands = sorted({b for (_s, _c, b) in self.combos})
        scales = ", ".join(f"{n}={d}" for n, d in self.scales) or "none"
        return (
            f"Sexes {','.join(sexes)}  ·  Classes {' '.join(classes)}  ·  "
            f"Bands {' '.join(bands)}  ·  {len(self.combos)} combos  ·  "
            f"Issue ages {self.ia_min}–{self.ia_max}  ·  "
            f"Select durations {self.select_durations}  ·  "
            f"Ultimate ages {self.ultimate_age_min}–{self.ultimate_age_max}  ·  "
            f"Maturity {self.maturity_label}  ·  Scales: {scales}"
        )


@dataclass
class TermWorkupResult:
    output_path: str = ""
    table_counts: "OrderedDict[str, int]" = field(default_factory=OrderedDict)
    index_ranges: "OrderedDict[str, str]" = field(default_factory=OrderedDict)
    warnings: List[str] = field(default_factory=list)
    error: str = ""


# ---------------------------------------------------------------------------
# IAF code normalization
# ---------------------------------------------------------------------------

def clean_option(opt: str) -> str:
    """Normalize an IAF plan_option: '**' (the base plan) becomes ''."""
    return (opt or "").replace("*", "").strip()


def map_sex(code: str) -> str:
    """Output sex code: 1 → M, 2 → F; unisex codes (U, X, Y…) pass through."""
    return {"1": "M", "2": "F"}.get(code, code)


def benefit_label(code: str) -> str:
    """Derive the Benefit label from a plan_option ('30' → 'PWoC')."""
    if code:
        return BENEFIT_TYPE_MAP.get(code[0], code)
    return code


def _parse_mmddyyyy(value: str) -> datetime:
    try:
        return datetime.strptime((value or "").strip(), "%m/%d/%Y")
    except (AttributeError, ValueError):
        return datetime.min


def _maturity_from_product(product) -> Tuple[str, int]:
    """Maturity from the plan header ME-AGE and its use code.

    Use code 1 means the value is an attained age, 0 means a duration. This
    is the ME-AGE (benefit period), *not* PAY-AGE — B155O200 pays premium for
    only 20 years (PAY-AGE 020/0) but its benefit period runs to age 95.
    """
    if product is None:
        return "", 0
    return ("AGE" if product.me_age_use == 1 else "DUR"), product.me_age


def _build_scale_maps(result: ParseResult) -> Dict[str, Dict[tuple, int]]:
    """Map each (rate_type, scale_start) to a scale number, per plan_option.

    Guaranteed rates ('G') are always scale 0. Current rates ('0') are
    numbered newest-first within their option: 1, 2, ...
    """
    starts_by_option: Dict[str, set] = {}
    for rate in result.rates:
        if rate.rate_type != "0":
            continue
        starts_by_option.setdefault(
            clean_option(rate.plan_option), set()).add(rate.scale_start)

    scale_maps: Dict[str, Dict[tuple, int]] = {}
    for opt, starts in starts_by_option.items():
        scale_map: Dict[tuple, int] = {("G", None): 0}
        ordered = sorted(starts, key=_parse_mmddyyyy, reverse=True)
        for scale, start in enumerate(ordered, 1):
            scale_map[("0", start)] = scale
        scale_maps[opt] = scale_map
    return scale_maps


def _rate_scale(rate, scale_maps) -> Optional[int]:
    if rate.rate_type == "G":
        return 0
    opt = clean_option(rate.plan_option)
    return scale_maps.get(opt, {}).get((rate.rate_type, rate.scale_start))


def _usable(rate) -> bool:
    """Skip zero rates and the mainframe's 9999.99 placeholder."""
    return rate.rate != 0 and rate.rate != DUMMY_RATE


# ---------------------------------------------------------------------------
# Index allocation
# ---------------------------------------------------------------------------

def build_index_map(base_index: int, combos: List[ComboKey],
                    suffix: str) -> "OrderedDict[ComboKey, str]":
    """Allocate one string index per combo: base+1, base+2, … with a suffix.

    Base index 1000 over 90 sorted combos yields '1001_PL' … '1090_PL'. Each
    suffix is its own index space, so '1001_PL' and '1001_30' coexist.
    """
    mapping: "OrderedDict[ComboKey, str]" = OrderedDict()
    for offset, combo in enumerate(sorted(combos), 1):
        mapping[combo] = f"{base_index + offset}_{suffix}"
    return mapping


def resolve_benefit_combo(base_combo: ComboKey,
                          benefit_combos) -> Optional[ComboKey]:
    """Find the benefit combo serving *base_combo*, most specific first.

    Benefit rates are often less granular than base premium rates — a waiver
    that varies by sex and class but not band stores a single band '0' row
    that every base band must point at.
    """
    sex, rate_class, band = base_combo
    available = set(benefit_combos)
    for cls in (rate_class, "0", "*"):
        for bnd in (band, "0", "*"):
            for sx in (sex, "U", "0", "*"):
                candidate = (sx, cls, bnd)
                if candidate in available:
                    return candidate
    return None


# ---------------------------------------------------------------------------
# Extraction — bucket IAF rates into select / ultimate per index
# ---------------------------------------------------------------------------

def _extract_option(result: ParseResult, option: str,
                    index_map: "OrderedDict[ComboKey, str]", scale_maps):
    """Bucket one plan_option's rates by index.

    Returns ``(select, ultimate)`` where::

        select   = {(index, scale, issue_age): {duration: rate}}
        ultimate = {(index, scale): {attained_age: rate}}
    """
    select: Dict[tuple, Dict[int, float]] = defaultdict(dict)
    ultimate: Dict[tuple, Dict[int, float]] = defaultdict(dict)

    for rate in result.rates:
        if not _usable(rate):
            continue
        if clean_option(rate.plan_option) != option:
            continue
        combo = (map_sex(rate.gender), rate.rate_class, rate.band)
        index = index_map.get(combo)
        if index is None:
            continue
        scale = _rate_scale(rate, scale_maps)
        if scale is None:
            continue
        if rate.duration == ULTIMATE_DURATION:
            ultimate[(index, scale)][rate.attained_age] = rate.rate
        else:
            # IAF durations are 0-based; policy year 1 is duration 0.
            select[(index, scale, rate.issue_age)][rate.duration + 1] = rate.rate

    return select, ultimate


# ---------------------------------------------------------------------------
# Compilation — expand select + ultimate into (IssueAge, Duration) cells
# ---------------------------------------------------------------------------

def compile_rates(select_data, ultimate_data, first_level: int,
                  ren_level: int, max_attained_age: Optional[int] = None,
                  max_duration: Optional[int] = None) -> List[tuple]:
    """Expand select + ultimate rates into (index, scale, ia, duration, rate).

    For each (index, scale, issue age):

    1. Walk the select durations in order, holding the first for
       ``first_level`` policy years and each later one for ``ren_level``.
       When the IAF already carries several select durations the level period
       is baked in (one duration per policy year), so the hold counts are
       forced to 1 and the user's FIRSTLEVEL/RENLEVEL do not apply.
    2. Fill the remaining years from the ultimate table by attained age.
    3. Stop when the ultimate rates run out, or at an explicit cap.

    Combos with no select rates at all (common for waiver benefits) run
    straight off the ultimate table. A ``first_level`` of 999 or more marks a
    non-renewable rate that stays locked at its issue-age value — that path
    has no natural end, so it relies on ``max_attained_age`` /
    ``max_duration`` to stop.
    """
    compiled: List[tuple] = []
    seen_with_select = {(idx, scale) for (idx, scale, _ia) in select_data}
    for (index, scale, issue_age), dur_rates in select_data.items():
        compiled.extend(_compile_select_combo(
            index, scale, issue_age, dur_rates, ultimate_data.get((index, scale), {}),
            first_level, ren_level, max_attained_age, max_duration,
        ))
    for (index, scale), ult_ages in ultimate_data.items():
        if (index, scale) in seen_with_select:
            continue
        compiled.extend(_compile_ultimate_only_combo(
            index, scale, ult_ages, first_level, max_attained_age, max_duration,
        ))

    return _fill_missing_scales(compiled)


def _compile_select_combo(
    index,
    scale,
    issue_age,
    dur_rates,
    ult_ages,
    first_level,
    ren_level,
    max_attained_age,
    max_duration,
) -> List[tuple]:
    rows: List[tuple] = []
    duration = _append_select_duration_rows(
        rows, index, scale, issue_age, dur_rates, first_level, ren_level,
        max_attained_age, max_duration,
    )
    rows.extend(_ultimate_tail_rows(
        index, scale, issue_age, duration, ult_ages, max_attained_age, max_duration,
    ))
    return rows


def _append_select_duration_rows(
    rows,
    index,
    scale,
    issue_age,
    dur_rates,
    first_level,
    ren_level,
    max_attained_age,
    max_duration,
) -> int:
    duration = 1
    durations = sorted(dur_rates)
    eff_first, eff_ren = (1, 1) if len(durations) > 1 else (first_level, ren_level)
    for position, dur in enumerate(durations):
        hold = eff_first if position == 0 else eff_ren
        for _ in range(hold):
            attained = issue_age + duration - 1
            if _term_cap_reached(duration, attained, max_duration, max_attained_age):
                break
            rows.append((index, scale, issue_age, duration, dur_rates[dur]))
            duration += 1
    return duration


def _ultimate_tail_rows(
    index,
    scale,
    issue_age,
    duration,
    ult_ages,
    max_attained_age,
    max_duration,
) -> List[tuple]:
    if not ult_ages:
        return []
    rows: List[tuple] = []
    last_age = min(max(ult_ages), max_attained_age) if max_attained_age is not None else max(ult_ages)
    while issue_age + duration - 1 <= last_age:
        if max_duration is not None and duration > max_duration:
            break
        attained = issue_age + duration - 1
        if attained in ult_ages:
            rows.append((index, scale, issue_age, duration, ult_ages[attained]))
        duration += 1
    return rows


def _compile_ultimate_only_combo(
    index,
    scale,
    ult_ages,
    first_level,
    max_attained_age,
    max_duration,
) -> List[tuple]:
    first_age = min(ult_ages)
    last_age = min(max(ult_ages), max_attained_age) if max_attained_age is not None else max(ult_ages)
    rows: List[tuple] = []
    for issue_age in range(first_age, last_age + 1):
        if issue_age not in ult_ages:
            continue
        rows.extend(_ultimate_only_issue_rows(
            index, scale, issue_age, ult_ages, first_level, last_age,
            max_attained_age, max_duration,
        ))
    return rows


def _ultimate_only_issue_rows(
    index,
    scale,
    issue_age,
    ult_ages,
    first_level,
    last_age,
    max_attained_age,
    max_duration,
) -> List[tuple]:
    if first_level >= NON_RENEWABLE_LEVEL:
        limit = max_duration if max_duration is not None else 9999
        if max_attained_age is not None:
            limit = min(limit, max_attained_age - issue_age + 1)
        return [
            (index, scale, issue_age, duration, ult_ages[issue_age])
            for duration in range(1, limit + 1)
        ]
    rows: List[tuple] = []
    duration = 1
    for attained in range(issue_age, last_age + 1):
        if max_duration is not None and duration > max_duration:
            break
        if attained in ult_ages:
            rows.append((index, scale, issue_age, duration, ult_ages[attained]))
            duration += 1
    return rows


def _term_cap_reached(duration, attained, max_duration, max_attained_age) -> bool:
    return (
        (max_attained_age is not None and attained > max_attained_age)
        or (max_duration is not None and duration > max_duration)
    )


def _fill_missing_scales(compiled: List[tuple]) -> List[tuple]:
    """Ensure every index carries both scale 0 (guaranteed) and 1 (current).

    Plans that publish only one of the two get the other as a copy, so
    consumers never have to check which scales exist for an index.
    """
    scales_by_index: Dict[str, set] = defaultdict(set)
    for (index, scale, _ia, _dur, _rate) in compiled:
        scales_by_index[index].add(scale)

    single = {index: next(iter(scales))
              for index, scales in scales_by_index.items()
              if scales in ({0}, {1})}
    if not single:
        return compiled

    extras = [
        (index, 1 - scale, ia, dur, rate)
        for (index, scale, ia, dur, rate) in compiled
        if single.get(index) == scale
    ]
    compiled.extend(extras)
    return compiled


def _dedupe(rows: List[tuple]) -> List[tuple]:
    """Collapse rows sharing an (index, scale, issue age, duration) key.

    Several Sex/Rateclass/Band combos legitimately resolve to one index when
    their rates are identical; keep a single row per rate cell.
    """
    return list({row[:4]: row for row in rows}.values())


# ---------------------------------------------------------------------------
# Analyze
# ---------------------------------------------------------------------------

def analyze(spec: TermWorkupSpec,
            progress_cb: ProgressCB = None) -> TermWorkupAnalysis:
    """Parse the IAF and derive the plan's rate space."""
    if not spec.iaf_path or not os.path.isfile(spec.iaf_path):
        return TermWorkupAnalysis(error="Select an IAF file to analyze.")

    progress = _term_progress_adapter(progress_cb)
    result = _parse_term_iaf(spec, progress)
    if isinstance(result, TermWorkupAnalysis):
        return result

    progress(0.9, "Deriving rate space…")
    ana = TermWorkupAnalysis(iaf_result=result)
    _populate_product_analysis(ana, result.products[0])
    scan = _scan_term_rates(result)
    _apply_term_scan(ana, result, scan)
    if not ana.combos:
        ana.error = "No base premium rates found in this IAF."
        return ana
    if not scan["ultimate_ages"] and ana.select_durations <= 1:
        ana.warnings.append(
            "This IAF has a single select duration and no ultimate rates — "
            "compiled rates will only cover the FIRSTLEVEL period.")
    progress(1.0, "Analysis complete.")
    return ana


def _term_progress_adapter(progress_cb: ProgressCB):
    def progress(frac: float, msg: str = "") -> None:
        if progress_cb:
            progress_cb(frac, msg)
    return progress


def _parse_term_iaf(spec: TermWorkupSpec, progress):
    progress(0.05, "Parsing IAF…")
    result = IAFParser().parse(
        spec.iaf_path,
        progress_cb=lambda pct: progress(0.05 + pct * 0.8, "Parsing IAF…"),
    )
    if result.error:
        return TermWorkupAnalysis(error=result.error)
    if not result.products:
        return TermWorkupAnalysis(
            error="No plan records found — is this an IAF print file?")
    return result


def _populate_product_analysis(ana: TermWorkupAnalysis, product) -> None:
    ana.plancode = product.plancode.strip()
    try:
        ana.issue_version = int(product.version.strip() or "1")
    except ValueError:
        ana.issue_version = 1
    ana.eff_date = product.eff_date
    ana.maturity_use, ana.maturity_value = _maturity_from_product(product)
    ana.pay_age = product.pay_age
    ana.pay_age_use = product.pay_age_use


def _scan_term_rates(result) -> dict:
    base_combos: set = set()
    select_durations: set = set()
    issue_ages: set = set()
    ultimate_ages: set = set()
    per_benefit: Dict[str, dict] = {}

    for rate in result.rates:
        if not _usable(rate):
            continue
        combo = (map_sex(rate.gender), rate.rate_class, rate.band)
        option = clean_option(rate.plan_option)
        if option:
            bucket = per_benefit.setdefault(option, {
                "combos": set(), "durations": set(), "count": 0})
            bucket["combos"].add(combo)
            bucket["count"] += 1
            if rate.duration != ULTIMATE_DURATION:
                bucket["durations"].add(rate.duration + 1)
            continue
        base_combos.add(combo)
        if rate.duration == ULTIMATE_DURATION:
            ultimate_ages.add(rate.attained_age)
        else:
            select_durations.add(rate.duration + 1)
            issue_ages.add(rate.issue_age)
    return {
        "base_combos": base_combos,
        "select_durations": select_durations,
        "issue_ages": issue_ages,
        "ultimate_ages": ultimate_ages,
        "per_benefit": per_benefit,
    }


def _apply_term_scan(ana: TermWorkupAnalysis, result, scan: dict) -> None:
    ana.combos = sorted(scan["base_combos"])
    ana.ia_min = min(scan["issue_ages"]) if scan["issue_ages"] else 0
    ana.ia_max = max(scan["issue_ages"]) if scan["issue_ages"] else 0
    ana.select_durations = len(scan["select_durations"])
    ana.ultimate_age_min = min(scan["ultimate_ages"]) if scan["ultimate_ages"] else 0
    ana.ultimate_age_max = max(scan["ultimate_ages"]) if scan["ultimate_ages"] else 0
    ana.banded = {b for (_s, _c, b) in ana.combos} != {"0"}

    scale_maps = _build_scale_maps(result)
    base_map = scale_maps.get("", {})
    ana.scales = sorted(
        [(num, start) for (kind, start), num in base_map.items() if kind == "0"]
    )

    ana.benefit_combos = {
        code: sorted(bucket["combos"]) for code, bucket in scan["per_benefit"].items()
    }
    ana.benefits = sorted(
        (code, benefit_label(code), len(bucket["combos"]),
         len(bucket["durations"]), bucket["count"])
        for code, bucket in scan["per_benefit"].items()
    )


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def _reference_rows(spec: TermWorkupSpec) -> Tuple[List[list], List[list]]:
    """Rows for the two shared reference tables, when defining new entries.

    These tables are shared across every Term plancode, so the workup only
    emits rows when the user is defining a *new* modal-factor set or band
    structure; referencing an existing index emits nothing.
    """
    modefact_rows: List[list] = []
    if spec.modefact.is_new:
        modefact_rows.append(
            [spec.modefact.index]
            + [fmt_rate(spec.modefact.values.get(name, 0.0))
               for name in MODEFACT_FIELDS]
        )

    bandspec_rows: List[list] = []
    if spec.bandspec.is_new:
        for row in spec.bandspec.rows:
            bandspec_rows.append([
                spec.bandspec.index,
                fmt_rate(row.specified_amount),
                row.band,
                row.band_code,
                row.issue_date,
            ])
    return modefact_rows, bandspec_rows


def _benefit_pointer_rows(spec: TermWorkupSpec, analysis: TermWorkupAnalysis,
                          base_combos: List[ComboKey],
                          warnings: List[str]) -> Tuple[List[list], Dict[str, dict]]:
    """TERM_POINT_BENEFIT rows plus each benefit's combo → index map.

    The pointer table exposes the *base* plan's full combo space so a quote
    can look a benefit up with the same Sex/Rateclass/Band it used for the
    base premium, even when the benefit's own rates are less granular.
    """
    rows: List[list] = []
    index_maps: Dict[str, dict] = {}

    for selection in spec.selected_benefits:
        combos = analysis.benefit_combos.get(selection.code, [])
        if not combos:
            warnings.append(
                f"Benefit {selection.code} has no usable rates — skipped.")
            continue
        index_map = build_index_map(
            spec.base_index, combos, selection.code)
        index_maps[selection.code] = index_map
        label = selection.label or benefit_label(selection.code)

        unresolved = 0
        for combo in base_combos:
            source = resolve_benefit_combo(combo, combos)
            if source is None:
                unresolved += 1
                continue
            sex, rate_class, band = combo
            rows.append([
                spec.plancode, spec.issue_version, selection.code, label,
                sex, rate_class, band, index_map[source],
            ])
        if unresolved:
            warnings.append(
                f"Benefit {selection.code}: {unresolved} base combo(s) had no "
                f"matching benefit rate and were left out of TERM_POINT_BENEFIT.")

    return rows, index_maps


def build(spec: TermWorkupSpec, analysis: TermWorkupAnalysis,
          progress_cb: ProgressCB = None) -> TermWorkupResult:
    """Compile the analyzed IAF into the seven TERM_* tables."""

    def _p(frac: float, msg: str = "") -> None:
        if progress_cb:
            progress_cb(frac, msg)

    if analysis is None or analysis.iaf_result is None:
        return TermWorkupResult(error="Analyze the IAF before building.")
    if spec.base_index is None:
        return TermWorkupResult(error="A base index is required.")
    if not spec.output_dir:
        return TermWorkupResult(error="Choose an output folder.")

    result = analysis.iaf_result
    warnings: List[str] = list(analysis.warnings)
    scale_maps = _build_scale_maps(result)

    _p(0.05, "Allocating indexes…")
    base_index_map = build_index_map(
        spec.base_index, analysis.combos, PREMIUM_SUFFIX)

    if len(analysis.combos) > 999:
        return TermWorkupResult(error=(
            f"{len(analysis.combos)} rate combos exceed the 999 slots between "
            f"base indexes — allocate a wider base index range."))

    # ── Pointer tables ──────────────────────────────────────────────────
    pv_rows = [[
        spec.plancode, spec.issue_version,
        spec.modefact.index, spec.bandspec.index, fmt_rate(spec.fee),
    ]]

    pvsrb_rows = [
        [spec.plancode, spec.issue_version, sex, rate_class, band, index]
        for (sex, rate_class, band), index in base_index_map.items()
    ]

    benefit_rows, benefit_index_maps = _benefit_pointer_rows(
        spec, analysis, analysis.combos, warnings)

    modefact_rows, bandspec_rows = _reference_rows(spec)

    # ── Base premium rates ──────────────────────────────────────────────
    _p(0.2, "Compiling premium rates…")
    plan_max_attained = analysis.max_attained_age
    select_data, ultimate_data = _extract_option(
        result, "", base_index_map, scale_maps)
    prem_rows = _dedupe(compile_rates(
        select_data, ultimate_data, spec.first_level, spec.ren_level,
        max_attained_age=plan_max_attained))
    prem_rows.sort(key=lambda r: (r[0], r[1], r[2], r[3]))

    if plan_max_attained is not None and analysis.ultimate_age_max > plan_max_attained:
        warnings.append(
            f"The IAF carries premium rates to attained age "
            f"{analysis.ultimate_age_max}; they were cut off at "
            f"{plan_max_attained} by the maturity age "
            f"{analysis.maturity_value}.")
    if spec.first_level >= NON_RENEWABLE_LEVEL and plan_max_attained is None:
        warnings.append(
            "FIRSTLEVEL is 999 (non-renewable) but the IAF gives no maturity "
            "age, so there is nothing to stop the rate schedule — check the "
            "row counts before loading.")

    # ── Benefit rates ───────────────────────────────────────────────────
    _p(0.6, "Compiling benefit rates…")
    ben_rows: List[tuple] = []
    for selection in spec.selected_benefits:
        index_map = benefit_index_maps.get(selection.code)
        if not index_map:
            continue
        ben_select, ben_ultimate = _extract_option(
            result, selection.code, index_map, scale_maps)
        first_level, ren_level = selection.levels(
            spec.first_level, spec.ren_level)
        # A benefit that ceases earlier than the plan overrides the maturity.
        max_attained = (selection.cease_age - 1 if selection.cease_age
                        else plan_max_attained)
        ben_rows.extend(compile_rates(
            ben_select, ben_ultimate, first_level, ren_level,
            max_attained_age=max_attained,
            max_duration=selection.max_duration))
    ben_rows = _dedupe(ben_rows)
    ben_rows.sort(key=lambda r: (r[0], r[1], r[2], r[3]))

    # ── Write ───────────────────────────────────────────────────────────
    _p(0.85, "Writing output…")
    tables: "OrderedDict[str, List[list]]" = OrderedDict([
        ("TERM_POINT_PV", pv_rows),
        ("TERM_POINT_PVSRB", pvsrb_rows),
        ("TERM_POINT_BENEFIT", benefit_rows),
        ("TERM_RATE_MODEFACT", modefact_rows),
        ("TERM_RATE_BANDSPECS", bandspec_rows),
        ("TERM_RATE_PREM", [[i, s, ia, d, fmt_rate(r)]
                            for (i, s, ia, d, r) in prem_rows]),
        ("TERM_RATE_BEN", [[i, s, ia, d, fmt_rate(r)]
                           for (i, s, ia, d, r) in ben_rows]),
    ])

    output_path = _write_output(spec, analysis, tables, warnings)

    counts = OrderedDict((name, len(rows)) for name, rows in tables.items())
    _p(1.0, "Build complete.")
    return TermWorkupResult(
        output_path=output_path,
        table_counts=counts,
        index_ranges=_index_ranges(base_index_map, benefit_index_maps),
        warnings=warnings,
    )


def _index_ranges(base_index_map,
                  benefit_index_maps) -> "OrderedDict[str, str]":
    ranges: "OrderedDict[str, str]" = OrderedDict()
    if base_index_map:
        values = list(base_index_map.values())
        ranges["TERM_RATE_PREM"] = f"{values[0]} – {values[-1]}"
    for code, index_map in sorted(benefit_index_maps.items()):
        values = list(index_map.values())
        ranges[f"TERM_RATE_BEN ({code})"] = f"{values[0]} – {values[-1]}"
    return ranges


def _write_output(spec: TermWorkupSpec, analysis: TermWorkupAnalysis,
                  tables, warnings: List[str]) -> str:
    """Write the workup as a folder of CSVs named for their target tables."""
    folder = ensure_dir(os.path.join(
        spec.output_dir, f"{spec.plancode} TERM Workup"))
    for name, rows in tables.items():
        write_csv(os.path.join(folder, f"{name}.csv"),
                  TERM_TABLE_HEADERS[name], rows)
    write_summary(os.path.join(folder, "WORKUP_SUMMARY.txt"),
                  _summary_lines(spec, analysis, tables, warnings))
    return folder


def _summary_lines(spec: TermWorkupSpec, analysis: TermWorkupAnalysis,
                   tables, warnings: List[str]) -> List[str]:
    lines = [
        f"Term Rate Workup — {spec.plancode}",
        "=" * 60,
        f"Issue version   : {spec.issue_version}",
        f"Base index      : {spec.base_index}",
        f"FIRSTLEVEL      : {spec.first_level}",
        f"RENLEVEL        : {spec.ren_level}",
        f"Policy fee      : {spec.fee}",
        f"Index(MODEFACT) : {spec.modefact.index}"
        + ("  (new)" if spec.modefact.is_new else "  (existing)"),
        f"Index(BANDSPEC) : {spec.bandspec.index}"
        + ("  (new)" if spec.bandspec.is_new else "  (existing)"),
        f"Maturity (IAF)  : {analysis.maturity_label}",
        "",
        analysis.rate_space_summary(),
        "",
        "Rows written",
        "-" * 60,
    ]
    lines += [f"{name:<24}{len(rows):>12,}" for name, rows in tables.items()]
    if warnings:
        lines += ["", "Warnings", "-" * 60]
        lines += [f"- {w}" for w in warnings]
    return lines
