"""
Rate Workup builder — orchestrates all four rate files into one output set.

The master rate space is derived from the base plancode's current COI rates in
the IAF: the (Sex, Rateclass, Band) combos. Every other rate family (targets,
benefits, surrender charges, expense-per-unit) is projected onto that space:

  * Benefits (IAF riders + MPF supplementals) — usually unbanded; every base
    band of a (sex, class) points to the same rate index (dedup handles it).
  * SCR (CKULTB04) — keyed additionally by State. States whose schedule
    matches the majority collapse into a single State='AA' row; only states
    whose schedule actually differs get their own POINT_PVSRB rows
    ("AA + exception states" — matches Rates._scr_uses_state()).
  * EPU (CKULTB01) — wildcard sex/class/band records expand onto the space;
    MONTHDUR is a high-duration bracket in months (120 = first 10 years),
    HIGH AGE a high-issue-age bracket. No covering bracket → charge 0.
  * CyberLife sex codes are matched against the IAF's ('M'→'1', 'F'→'2',
    'U'/'X'/'V'→unisex 'Y'); wildcards '*'/'**' match anything.

Anything that cannot be projected (a raw combo no base combo matches, a base
combo with no SCR/EPU rates, unmapped rate types) lands in ``warnings`` —
never silently dropped.
"""

from __future__ import annotations

import os
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from suiteview.polview.models.cl_polrec.policy_translations import STATE_CODE_TO_ABBR
from suiteview.ratemanager import ckultb01_parser, ckultb04_parser, mpf_parser
from suiteview.ratemanager.benefit_db import BenefitDBSpec, build_benefit_rows
from suiteview.ratemanager.benefit_exporter import benefit_summary
from suiteview.ratemanager.ckultb04_db import _schedule_rows, _signature
from suiteview.ratemanager.mpf_exporter import summarize as mpf_summarize
from suiteview.ratemanager.parser import IAFParser, ParseResult
from suiteview.ratemanager.rate_reformatter import RateReformatter
from suiteview.ratemanager.workup.spec import BenefitSelection, WorkupSpec
from suiteview.ratemanager.workup.writers import (
    ensure_dir, fmt_rate, write_csv, write_summary, write_workbook,
)

ComboKey = Tuple[str, str, str]        # (sex, rate_class, band) — IAF codes
ProgressCB = Optional[Callable[[float, str], None]]

# HIGH_DURATION at/above this is the CKULTB04 "0 thereafter" terminal marker.
_SCR_SENTINEL_DUR = 900

# ---------------------------------------------------------------------------
# Locked output schemas (match the UL_Rates physical tables)
# ---------------------------------------------------------------------------

PVSRB_HEADERS = [
    "Plancode", "IssueVersion", "Sex", "Rateclass", "Band", "State",
    "Index(PREMLOAD)", "Index(TRGPREM)", "Index(MFEE)", "Index(SCR)",
    "Index(COI)", "Index(EPU)", "Index(GLP)", "MORTID", "Index(SHDINT)",
    "Index(TRAD_CV)",
]
COI_HEADERS = ["Index(COI)", "Scale", "IssueAge", "Duration", "Rate"]
TRGPREM_HEADERS = [
    "Index(TRGPREM)", "IssueAge", "Rate(MTP)", "Rate(CTP)",
    "Rate(TBL4PREM)", "Rate(TBL1MTP)", "Rate(TBL1CTP)",
]
SCR_HEADERS = ["Index(SCR)", "IssueAge", "Duration", "Rate"]
EPU_HEADERS = ["Index(EPU)", "Scale", "IssueAge", "Duration", "Rate"]
POINT_BENEFIT_HEADERS = [
    "Plancode", "BenefitType", "Benefit", "IssueVersion",
    "Sex", "Rateclass", "Band", "Index(BENCOI)", "Index(BENTRG)",
]
BENCOI_HEADERS = ["Index(BENCOI)", "Scale", "IssueAge", "Duration", "Rate"]
BENTRG_HEADERS = ["Index(BENTRG)", "IssueAge", "Rate(MTP)", "Rate(CTP)"]

TABLE_FILES = [
    "POINT_PVSRB", "RATE_COI", "RATE_TRGPREM", "RATE_SCR", "RATE_EPU",
    "POINT_BENEFIT", "RATE_BENCOI", "RATE_BENTRG",
]


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class WorkupAnalysis:
    """Everything learned from the source files before building."""
    iaf_result: Optional[ParseResult] = None
    plancode: str = ""
    issue_version: str = "1"
    pay_age: int = 121
    combos: List[ComboKey] = field(default_factory=list)
    ia_min: int = 0
    ia_max: int = 85
    select_period: int = 0
    current_scales: List[Tuple[int, str]] = field(default_factory=list)
    iaf_benefits: List[Tuple[str, int, int]] = field(default_factory=list)
    mpf_codes: List[Tuple[str, str, int, int]] = field(default_factory=list)
    scr_plans: List[Tuple[str, int]] = field(default_factory=list)
    scr_states: Dict[str, List[str]] = field(default_factory=dict)
    epu_groups: List[Tuple[str, str, str, int]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error: str = ""

    def rate_space_summary(self) -> str:
        sexes = sorted({s for (s, _c, _b) in self.combos})
        classes = sorted({c for (_s, c, _b) in self.combos})
        bands = sorted({b for (_s, _c, b) in self.combos})
        scales = ", ".join(
            f"{n}={d}" for n, d in self.current_scales) or "none"
        return (
            f"Sexes {','.join(sexes)}  ·  Classes {' '.join(classes)}  ·  "
            f"Bands {' '.join(bands)}  ·  Issue ages {self.ia_min}–{self.ia_max}  ·  "
            f"Select period {self.select_period}  ·  Scales: {scales}"
        )


@dataclass
class WorkupResult:
    output_path: str = ""
    table_counts: "OrderedDict[str, int]" = field(default_factory=OrderedDict)
    index_ranges: "OrderedDict[str, str]" = field(default_factory=OrderedDict)
    warnings: List[str] = field(default_factory=list)
    error: str = ""


# ---------------------------------------------------------------------------
# CyberLife code normalization / matching
# ---------------------------------------------------------------------------

def _sex_candidates(base_sex: str) -> List[str]:
    """Raw sex codes that can satisfy an IAF base sex, most specific first."""
    if base_sex == "1":
        return ["1", "M"]
    if base_sex == "2":
        return ["2", "F"]
    if base_sex == "Y":
        return ["Y", "U", "X", "V", "3"]
    return [base_sex]


def _match_raw(base_combo: ComboKey, raw_keys) -> Optional[tuple]:
    """Find the raw (sex, class, band) key that serves *base_combo*.

    Class and band specificity win over the sex-code spelling: the sex
    candidates ('F' for '2', 'M' for '1', …) are equivalent encodings tried
    at the same tier, while '0' (unbanded storage) and '*' (wildcard) are
    true fallbacks tried only after the exact value.
    """
    s, c, b = base_combo
    for cls in (c, "0", "*"):
        for band in (b, "0", "*"):
            for sex in _sex_candidates(s) + ["*", "**"]:
                key = (sex, cls, band)
                if key in raw_keys:
                    return key
    return None


# Benefit type/subtype letters → digits for the benefit index convention.
SUBTYPE_LETTER_MAP = {
    "#": "4", "C": "2", "D": "3", "F": "6", "G": "5", "I": "1",
    "L": "7", "M": "8", "P": "1", "Q": "2", "A": "5", "U": "6",
}


def benefit_start_index(base_index: int, code: str) -> Optional[int]:
    """The conventional starting index for a benefit: the plancode's base
    index with the 2-digit benefit type code inserted and two zeros appended.

    Base 13400 + benefit '12' → 1341200 (= (13400 + 12) × 100). Letters in
    the type/subtype convert via ``SUBTYPE_LETTER_MAP`` ('4M' → 48 →
    1344800). Returns None when a character has no mapping — the user must
    supply the index manually.
    """
    digits = []
    for ch in (code or "").strip():
        if ch.isdigit():
            digits.append(ch)
        elif ch in SUBTYPE_LETTER_MAP:
            digits.append(SUBTYPE_LETTER_MAP[ch])
        else:
            return None
    if not digits:
        return None
    return (base_index + int("".join(digits))) * 100


def _condense(values: List[int]) -> str:
    """Condense sorted ints into range strings: [0,1,2,3,90,91] → '0-3,90-91'."""
    if not values:
        return ""
    parts = []
    start = prev = values[0]
    for v in values[1:]:
        if v == prev + 1:
            prev = v
            continue
        parts.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = v
    parts.append(str(start) if start == prev else f"{start}-{prev}")
    return ",".join(parts)


def _sex_out(sex: str) -> str:
    """Output sex code: 1 → M, 2 → F; anything else (unisex X/Y/T/U…) as-is."""
    return {"1": "M", "2": "F"}.get(sex, sex)


def _band_out_map(combos: List[ComboKey]) -> Dict[str, str]:
    """Output band codes: letters become 1, 2, 3, …

    Bands X and Y (when present) sort FIRST — a band set of X, Y, A, B, C
    maps to X=1, Y=2, A=3, B=4, C=5. Band '0' (unbanded) stays '0'.
    """
    letters = sorted({b for (_s, _c, b) in combos if b not in ("0", "")})
    ordered = [b for b in ("X", "Y") if b in letters]
    ordered += [b for b in letters if b not in ("X", "Y")]
    mapping = {b: str(i + 1) for i, b in enumerate(ordered)}
    mapping["0"] = "0"
    return mapping


def _state_abbr(raw: str, warnings: List[str], seen_bad: set) -> str:
    """CKULTB numeric state code → 2-letter abbreviation ('**' → 'AA')."""
    raw = (raw or "").strip()
    if raw in ("**", "AA", ""):
        return "AA"
    try:
        return STATE_CODE_TO_ABBR.get(int(raw), raw)
    except ValueError:
        if raw not in seen_bad:
            seen_bad.add(raw)
            warnings.append(f"Unrecognized state code '{raw}' kept as-is.")
        return raw


# ---------------------------------------------------------------------------
# Analyze — parse/scan every supplied file
# ---------------------------------------------------------------------------

def analyze(spec: WorkupSpec, progress_cb: ProgressCB = None) -> WorkupAnalysis:
    """Parse the IAF and scan the optional files; derive the rate space."""
    def _p(frac: float, msg: str = "") -> None:
        if progress_cb:
            progress_cb(frac, msg)

    ana = WorkupAnalysis()

    if not spec.iaf_path or not os.path.isfile(spec.iaf_path):
        ana.error = "An IAF file is required — it defines the rate space."
        return ana

    _p(0.0, "Parsing IAF…")
    result = IAFParser().parse(
        spec.iaf_path, progress_cb=lambda f: _p(f * 0.45, ""))
    if result.error:
        ana.error = f"IAF parse failed: {result.error}"
        return ana
    ana.iaf_result = result

    reformatter = RateReformatter(result)
    computed = reformatter.compute()
    ana.plancode = reformatter.plancode
    ana.issue_version = reformatter.issue_version or "1"
    ana.pay_age = reformatter.pay_age
    ana.combos = computed["combos"]
    ana.ia_min = computed["ia_min"]
    ana.ia_max = computed["ia_max"]
    ana.select_period = computed["select_period"]
    ana.current_scales = computed["current_scales"]
    ana.warnings.extend(reformatter.warnings)
    ana.iaf_benefits = benefit_summary(result)
    _p(0.5, f"IAF: {len(ana.combos)} combos, {len(ana.iaf_benefits)} benefit code(s)")

    if not ana.combos:
        ana.error = "No base current-COI combos found in the IAF."
        return ana

    if spec.mpf_path and os.path.isfile(spec.mpf_path):
        _p(0.5, "Scanning MPF…")
        ana.mpf_codes = mpf_summarize(
            spec.mpf_path, progress_cb=lambda f: _p(0.5 + f * 0.15, ""))
        _p(0.65, f"MPF: {len(ana.mpf_codes)} premium code(s)")

    if spec.scr_path and os.path.isfile(spec.scr_path):
        _p(0.65, "Scanning CKULTB04 plan codes…")
        ana.scr_plans, ana.scr_states = _scan_ckultb04(
            spec.scr_path, progress_cb=lambda f: _p(0.65 + f * 0.17, ""))
        _p(0.82, f"CKULTB04: {len(ana.scr_plans)} plan code(s)")

    if spec.epu_path and os.path.isfile(spec.epu_path):
        _p(0.82, "Scanning CKULTB01 plan/rule groups…")
        ana.epu_groups = ckultb01_parser.list_plan_groups(
            spec.epu_path, progress_cb=lambda f: _p(0.82 + f * 0.17, ""))
        _p(0.99, f"CKULTB01: {len(ana.epu_groups)} plan/freq/rule group(s)")

    _p(1.0, "Analysis complete.")
    return ana


def _scan_ckultb04(path: str, progress_cb=None):
    """One streaming pass: plan codes with counts + distinct states per plan.

    The states feed the UI's state-code confirmation dialog before a build.
    """
    counts: Dict[str, int] = {}
    states: Dict[str, set] = defaultdict(set)
    for rec in ckultb04_parser.iter_records(path, progress_cb=progress_cb):
        pc = rec["PLAN_CODE"]
        counts[pc] = counts.get(pc, 0) + 1
        states[pc].add(rec["STATE_CODE"].strip())
    return sorted(counts.items()), {pc: sorted(s) for pc, s in states.items()}


# ---------------------------------------------------------------------------
# SCR (CKULTB04) — AA + exception states
# ---------------------------------------------------------------------------

def _build_scr(
    spec: WorkupSpec,
    combos: List[ComboKey],
    warnings: List[str],
    progress_cb: Callable[[float], None],
):
    """Project the CKULTB04 surrender charges onto the base combo space.

    Returns ``(combo_state_index, scr_rows, group_count)`` where
    ``combo_state_index[combo] = {'AA': idx, '<exception state>': idx, ...}``.
    """
    raw: Dict[tuple, Dict[str, Dict[int, Dict[int, float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(dict)))
    bad_states: set = set()

    for rec in ckultb04_parser.iter_records(spec.scr_path, progress_cb=progress_cb):
        if rec["PLAN_CODE"] != spec.scr_plan:
            continue
        dur = rec["HIGH_DURATION"]
        if dur >= _SCR_SENTINEL_DUR:
            continue
        raw_state = rec["STATE_CODE"].strip()
        # User-confirmed mapping wins; '**' → 'AA' and the CyberLife numeric
        # state table are the fallbacks.
        state = spec.state_map.get(raw_state) or _state_abbr(
            raw_state, warnings, bad_states)
        key = (rec["SEX_CODE"], rec["RATE_CLASS"], rec["BAND_CODE"])
        raw[key][state][rec["HIGH_ISSUE_AGE"]][dur] = rec["CHARGE_PCT"]

    combo_state_index: Dict[ComboKey, Dict[str, int]] = {}
    groups: "OrderedDict[tuple, int]" = OrderedDict()
    scr_rows: List[list] = []
    next_idx = spec.base_index
    matched_raw: set = set()
    missing: List[str] = []

    def _index_for(schedule) -> int:
        nonlocal next_idx
        sig = _signature(schedule)
        idx = groups.get(sig)
        if idx is None:
            idx = next_idx
            groups[sig] = idx
            scr_rows.extend(_schedule_rows(idx, schedule, spec.maturity_age))
            next_idx += 1
        return idx

    for combo in combos:
        rk = _match_raw(combo, raw.keys())
        if rk is None:
            missing.append("/".join(combo))
            continue
        matched_raw.add(rk)
        by_state = raw[rk]

        # Group states by identical schedule; majority group → 'AA'.
        sig_states: Dict[tuple, List[str]] = defaultdict(list)
        for state, sched in by_state.items():
            sig_states[_signature(sched)].append(state)
        majority_sig = max(sig_states, key=lambda s: len(sig_states[s]))

        entry: Dict[str, int] = {}
        for sig, states in sig_states.items():
            sched = by_state[states[0]]
            idx = _index_for(sched)
            if sig == majority_sig:
                entry["AA"] = idx
            else:
                for st in states:
                    entry[st] = idx
        combo_state_index[combo] = entry

    if missing:
        warnings.append(
            f"SCR: no CKULTB04 rates for {len(missing)} base combo(s): "
            + ", ".join(missing[:8]) + ("…" if len(missing) > 8 else ""))
    unmatched = sorted(set(raw.keys()) - matched_raw)
    if unmatched:
        warnings.append(
            f"SCR: {len(unmatched)} CKULTB04 combo(s) matched no base combo "
            "and were ignored: "
            + ", ".join("/".join(k) for k in unmatched[:8])
            + ("…" if len(unmatched) > 8 else ""))

    return combo_state_index, scr_rows, len(groups)


# ---------------------------------------------------------------------------
# EPU (CKULTB01) — MONTHDUR / HIGH AGE bracket expansion
# ---------------------------------------------------------------------------

def _build_epu(
    spec: WorkupSpec,
    combos: List[ComboKey],
    ia_min: int,
    ia_max: int,
    max_att_age: int,
    warnings: List[str],
    progress_cb: Callable[[float], None],
):
    """Project the CKULTB01 expense charges onto the base combo space.

    Returns ``(combo_index, epu_rows, group_count)``.
    """
    raw, stats = _read_epu_raw(spec, progress_cb)
    _warn_epu_source(stats, warnings)

    combo_index: Dict[ComboKey, int] = {}
    groups: "OrderedDict[tuple, int]" = OrderedDict()
    epu_rows: List[list] = []
    next_idx = spec.base_index
    matched_raw: set = set()
    missing: List[str] = []

    for combo in combos:
        rk = _match_raw(combo, raw.keys())
        if rk is None:
            missing.append("/".join(combo))
            continue
        matched_raw.add(rk)
        content = _epu_content(raw[rk], ia_min, ia_max, max_att_age)

        sig = tuple(content)
        idx = groups.get(sig)
        if idx is None:
            idx = next_idx
            groups[sig] = idx
            for scale in (0, 1):   # 0 = guaranteed charge, 1 = current charge
                for ia, dur, charge, guar in content:
                    epu_rows.append([idx, scale, ia, dur, guar if scale == 0 else charge])
            next_idx += 1
        combo_index[combo] = idx

    _warn_unmatched_epu(raw, matched_raw, missing, warnings)
    return combo_index, epu_rows, len(groups)


def _read_epu_raw(spec: WorkupSpec, progress_cb: Callable[[float], None]):
    raw: Dict[tuple, Dict[Tuple[int, int], Tuple[str, float, float]]] = defaultdict(dict)
    stats = {"eff_dates": set(), "nonsentinel_max": 0, "state_skipped": 0}
    for rec in ckultb01_parser.iter_records(spec.epu_path, progress_cb=progress_cb):
        if (rec["PLAN_CODE"], rec["FREQ_TYPE"], rec["RULE_CODE"]) != (
                spec.epu_plan, spec.epu_freq, spec.epu_rule):
            continue
        if rec["STATE_CODE"].strip() not in ("**", "AA", ""):
            stats["state_skipped"] += 1
            continue
        _add_epu_record(raw, stats, rec)
    return raw, stats


def _add_epu_record(raw, stats, rec) -> None:
    key = (rec["SEX_CODE"], rec["RATE_CLASS"], rec["BAND_CODE"])
    bracket = (rec["MONTH_DUR"], rec["HIGH_AGE"])
    eff = rec["EFFECTIVE_DATE"]
    stats["eff_dates"].add(eff)
    prev = raw[key].get(bracket)
    if prev is None or _mdY(eff) > _mdY(prev[0]):
        raw[key][bracket] = (eff, rec["CHARGE"], rec["GUAR_CHARGE"])
    if rec["MAXIMUM"] < 9_999_999.0 or rec["GUAR_MAX"] < 9_999_999.0:
        stats["nonsentinel_max"] += 1


def _warn_epu_source(stats, warnings: List[str]) -> None:
    if stats["state_skipped"]:
        warnings.append(
            f"EPU: {stats['state_skipped']:,} CKULTB01 rows with a specific state were "
            "ignored (only '**' all-state rows are loaded).")
    if stats["nonsentinel_max"]:
        warnings.append(
            f"EPU: {stats['nonsentinel_max']:,} rows carry a real MAXIMUM/GUAR MAX cap "
            "(not 9,999,999) — caps are NOT loaded into RATE_EPU.")
    eff_dates = stats["eff_dates"]
    if len(eff_dates) > 1:
        warnings.append(
            "EPU: multiple effective dates present "
            f"({', '.join(sorted(eff_dates))}) — most recent kept per bracket.")


def _epu_content(raw_combo, ia_min: int, ia_max: int, max_att_age: int):
    brackets = [
        (md, ha, charge, guar)
        for (md, ha), (_eff, charge, guar) in raw_combo.items()
    ]
    content: List[Tuple[int, int, float, float]] = []
    for ia in range(ia_min, ia_max + 1):
        max_dur = max_att_age - ia + 1
        if max_dur < 1:
            continue
        for dur in range(1, max_dur + 1):
            best = _best_epu_bracket(brackets, dur * 12, ia)
            content.append((ia, dur, 0.0, 0.0) if best is None else (ia, dur, best[2], best[3]))
    return content


def _best_epu_bracket(brackets, months: int, issue_age: int):
    best = None
    for md, ha, charge, guar in brackets:
        if md >= months and ha >= issue_age:
            candidate = (md, ha, charge, guar)
            if best is None or (candidate[0], candidate[1]) < (best[0], best[1]):
                best = candidate
    return best


def _warn_unmatched_epu(raw, matched_raw: set, missing: List[str], warnings: List[str]) -> None:
    if missing:
        warnings.append(
            f"EPU: no CKULTB01 rates for {len(missing)} base combo(s): "
            + ", ".join(missing[:8]) + ("…" if len(missing) > 8 else ""))
    unmatched = sorted(set(raw.keys()) - matched_raw)
    if unmatched:
        warnings.append(
            f"EPU: {len(unmatched)} CKULTB01 combo(s) matched no base combo "
            "and were ignored: "
            + ", ".join("/".join(k) for k in unmatched[:8])
            + ("…" if len(unmatched) > 8 else ""))


def _mdY(date_str: str) -> tuple:
    """MM/DD/YYYY → sortable (yyyy, mm, dd); bad dates sort first."""
    try:
        mm, dd, yyyy = date_str.strip().split("/")
        return (int(yyyy), int(mm), int(dd))
    except (ValueError, AttributeError):
        return (0, 0, 0)


# ---------------------------------------------------------------------------
# MPF-linked benefits — BENCOI from the MPF, BENTRG from the IAF
# ---------------------------------------------------------------------------

def _mpf_items_for_code(
    grouped, premcode: str, benefit: str = "",
) -> Dict[tuple, dict]:
    """``{(sex, cls, band): age_table}`` for one MPF premium code.

    A single premium code can carry more than one benefit type (e.g. ``GR2``
    holds both ``3#`` and ``39``), and each type repeats the same
    (sex, class, band) keys. Keying by combo alone lets one benefit's table
    silently overwrite another's — including its age range — so charges stop
    at the wrong attained age. ``benefit`` keeps only the records for the
    benefit being built; when the code doesn't carry that type (a code picked
    manually for a different benefit) we fall back to every record so it still
    loads.
    """
    exact: Dict[tuple, dict] = {}
    every: Dict[tuple, dict] = {}
    for (_company, rec_benefit, sex, cls, band, pc), table in grouped.items():
        if pc != premcode:
            continue
        every[(sex, cls, band)] = table
        if benefit and rec_benefit == benefit:
            exact[(sex, cls, band)] = table
    return exact or every


def _build_linked_benefit(
    result: ParseResult,
    sel: BenefitSelection,
    mpf_items: Dict[tuple, dict],
    combos: List[ComboKey],
    start_index: int,
    plancode: str,
    issue_version: str,
    warnings: List[str],
):
    """One benefit whose charges live in the MPF: COI from the MPF premium
    code, targets from the IAF benefit code.

    Returns ``(pointer_rows, bencoi_rows, bentrg_rows, block_size)`` where
    ``block_size`` is how many indexes the benefit consumed.
    """
    from suiteview.ratemanager.benefit_db import (
        _benefit_rates_by_combo, _bentrg_rows, _map_key,
        _target_issue_age_range,
    )

    _validate_linked_benefit(sel)
    ctp = _benefit_rates_by_combo(result, sel.code, "T")
    mtp = _benefit_rates_by_combo(result, sel.code, "M")
    trg_keys = set(ctp) | set(mtp)

    coi_index, bencoi_rows, coi_groups, missing, pct_converted = _linked_bencoi(
        sel, mpf_items, combos, trg_keys, ctp, mtp, start_index,
        _map_key, _target_issue_age_range,
    )
    trg_index, bentrg_rows, trg_groups = _linked_bentrg(
        combos, trg_keys, ctp, mtp, start_index, _map_key, _bentrg_rows,
    )
    pointer_rows = _linked_pointer_rows(
        plancode, sel, issue_version, combos, coi_index, trg_index,
    )
    _warn_linked_benefit(sel, mpf_items, missing, pct_converted, warnings)

    block = max(len(coi_groups), len(trg_groups))
    return pointer_rows, bencoi_rows, bentrg_rows, block


def _validate_linked_benefit(sel: BenefitSelection) -> None:
    if sel.cease_age is None:
        raise ValueError(f"Benefit {sel.code}: cease age is required.")
    if sel.cease_age <= 0:
        raise ValueError(f"Benefit {sel.code}: cease age must be greater than 0.")


def _linked_bencoi(
    sel,
    mpf_items,
    combos,
    trg_keys,
    ctp,
    mtp,
    start_index,
    map_key,
    issue_range,
):
    rows: List[list] = []
    groups: "OrderedDict[tuple, int]" = OrderedDict()
    index: Dict[ComboKey, int] = {}
    missing: List[str] = []
    pct_converted = 0
    for combo in combos:
        raw_key = _match_raw(combo, mpf_items.keys())
        if raw_key is None:
            missing.append("/".join(combo))
            continue
        converted, pct_count = _linked_mpf_table(mpf_items[raw_key])
        pct_converted += pct_count
        target_key = map_key(combo, trg_keys)
        c_rates = ctp.get(target_key, {}) if target_key else {}
        m_rates = mtp.get(target_key, {}) if target_key else {}
        issue_age_range = issue_range(m_rates, c_rates)
        sig = (tuple(sorted(converted.items())), sel.renewable, issue_age_range, sel.cease_age)
        idx = groups.get(sig)
        if idx is None:
            idx = start_index + len(groups)
            groups[sig] = idx
            rows.extend(_linked_bencoi_rows(idx, converted, sel, issue_age_range))
        index[combo] = idx
    return index, rows, groups, missing, pct_converted


def _linked_mpf_table(table) -> tuple[Dict[int, float], int]:
    converted: Dict[int, float] = {}
    pct_count = 0
    for age, (value, _state, is_pct) in table.items():
        converted[age] = value / 100.0 if is_pct else value
        pct_count += 1 if is_pct else 0
    return mpf_parser.fill_forward_age_table(converted), pct_count


def _linked_bencoi_rows(idx, rates, sel, issue_age_range):
    rows: List[list] = []
    for scale in (0, 1):
        for ia, dur, rate in _expand_attained_table(
            rates, sel.renewable, issue_age_range, sel.cease_age
        ):
            rows.append([idx, scale, ia, dur, rate])
    return rows


def _linked_bentrg(combos, trg_keys, ctp, mtp, start_index, map_key, bentrg_rows):
    rows: List[list] = []
    groups: "OrderedDict[tuple, int]" = OrderedDict()
    index: Dict[ComboKey, int] = {}
    for combo in combos:
        key = map_key(combo, trg_keys)
        c_rates = ctp.get(key, {}) if key else {}
        m_rates = mtp.get(key, {}) if key else {}
        if not c_rates and not m_rates:
            continue
        sig = (tuple(sorted(m_rates.items())), tuple(sorted(c_rates.items())))
        idx = groups.get(sig)
        if idx is None:
            idx = start_index + len(groups)
            groups[sig] = idx
            rows.extend(bentrg_rows(idx, m_rates, c_rates))
        index[combo] = idx
    return index, rows, groups


def _linked_pointer_rows(plancode, sel, issue_version, combos, coi_index, trg_index):
    rows: List[list] = []
    for combo in combos:
        ci = coi_index.get(combo)
        ti = trg_index.get(combo)
        if ci is None and ti is None:
            continue
        rows.append([
            plancode, sel.code, sel.mpf_code, issue_version,
            combo[0], combo[1], combo[2],
            ci if ci is not None else "",
            ti if ti is not None else "",
        ])
    return rows


def _warn_linked_benefit(sel, mpf_items, missing, pct_converted, warnings):
    if not mpf_items:
        warnings.append(
            f"Benefit {sel.code}: MPF code '{sel.mpf_code}' not found in the "
            "MPF file — no BENCOI rates loaded.")
    elif missing:
        warnings.append(
            f"Benefit {sel.code} (MPF {sel.mpf_code}): no rates for "
            f"{len(missing)} base combo(s): "
            + ", ".join(missing[:8]) + ("…" if len(missing) > 8 else ""))
    if pct_converted:
        warnings.append(
            f"Benefit {sel.code} (MPF {sel.mpf_code}): {pct_converted:,} "
            "percent premiums converted to decimals (5.64% → 0.0564).")


def _expand_attained_table(
    table: Dict[int, float],
    renewable: bool,
    issue_age_range: Optional[Tuple[int, int]] = None,
    cease_age: Optional[int] = None,
):
    """Expand an attained-age table into ``(issue_age, duration, rate)`` rows.

    Mirrors the MPF Supplemental renewal logic: renewable → the rate at
    attained age issue+d-1; non-renewable → the issue-age rate held level.
    """
    ages = sorted(table)
    if not ages:
        return []
    max_age = ages[-1]
    if cease_age is None:
        raise ValueError("Cease age is required for benefits.")
    if cease_age <= 0:
        raise ValueError("Cease age must be greater than 0.")
    duration_max_age = min(max_age, cease_age - 1)
    ia_min, ia_max = ages[0], max_age
    if issue_age_range is not None:
        ia_min = max(ia_min, issue_age_range[0])
        ia_max = min(ia_max, issue_age_range[1])
    rows = []
    for ia in range(ia_min, ia_max + 1):
        if ia not in table:
            continue
        for dur in range(1, duration_max_age - ia + 2):
            att = ia + dur - 1
            if renewable:
                if att in table:
                    rows.append((ia, dur, table[att]))
            else:
                rows.append((ia, dur, table[ia]))
    return rows


# ---------------------------------------------------------------------------
# Build — single pass over everything
# ---------------------------------------------------------------------------

def build(
    spec: WorkupSpec,
    analysis: WorkupAnalysis,
    progress_cb: ProgressCB = None,
) -> WorkupResult:
    """Generate the full workup output set from an analyzed spec."""
    res = WorkupResult()
    warnings: List[str] = list(analysis.warnings)
    progress = _progress_adapter(progress_cb)

    try:
        _validate_base_index(spec)
        base = _build_base_tables(spec, analysis, warnings, progress)
        benefit = _build_benefit_tables(spec, analysis, base, warnings, progress)
        scr_state_index, scr_rows = _build_scr_tables(spec, base.combos, warnings, progress)
        epu_index, epu_rows = _build_epu_tables(spec, base, warnings, progress)
        band_map = _band_out_map(base.combos)
        pvsrb_rows = _pvsrb_rows(
            analysis.plancode, analysis.issue_version or "1", base, scr_state_index,
            epu_index, band_map,
        )
        _convert_point_benefit_rows(benefit.point_rows, band_map)
        tables = _workup_tables(base, benefit, pvsrb_rows, scr_rows, epu_rows)
        _finalize_workup_result(spec, analysis, res, warnings, tables, progress)

        res.warnings = warnings
        progress(1.0, "Workup complete.")

    except Exception as exc:      # surface, never swallow
        import traceback
        res.error = f"{exc}\n{traceback.format_exc()}"

    return res


@dataclass
class _BaseBuild:
    result: ParseResult
    plancode: str
    issue_version: str
    combos: List[ComboKey]
    coi_map: Dict[ComboKey, int]
    trg_map: Dict[ComboKey, int]
    ia_min: int
    ia_max: int
    max_att_age: int
    coi_rows: List[list]
    trg_rows: List[list]


@dataclass
class _BenefitBuild:
    point_rows: List[list]
    bencoi_rows: List[list]
    bentrg_rows: List[list]


def _progress_adapter(progress_cb: ProgressCB):
    def progress(frac: float, msg: str = "") -> None:
        if progress_cb:
            progress_cb(frac, msg)
    return progress


def _validate_base_index(spec: WorkupSpec) -> None:
    if spec.base_index is None:
        raise ValueError("Base Index is required before building rates.")
    if spec.base_index <= 0:
        raise ValueError("Base Index must be greater than 0.")


def _build_base_tables(
    spec: WorkupSpec,
    analysis: WorkupAnalysis,
    warnings: List[str],
    progress,
) -> _BaseBuild:
    result = analysis.iaf_result
    progress(0.0, "Building base COI and target tables…")
    reformatter = RateReformatter(
        result, starting_index=spec.base_index, trg_starting_index=spec.base_index,
    )
    computed = reformatter.compute()
    coi_rows = _coi_rows(reformatter, computed, warnings)
    trg_rows = _target_rows(reformatter, computed)
    progress(0.2, f"Base: {len(coi_rows):,} COI rows, {len(trg_rows):,} target rows")
    return _BaseBuild(
        result, analysis.plancode, analysis.issue_version or "1",
        computed["combos"], computed["coi_index"], computed["trg_index"],
        computed["ia_min"], computed["ia_max"], reformatter.max_att_age,
        coi_rows, trg_rows,
    )


def _coi_rows(reformatter: RateReformatter, computed, warnings: List[str]) -> List[list]:
    removed: set = set()
    rows: List[list] = []
    ia_min, ia_max = computed["ia_min"], computed["ia_max"]
    guaranteed = reformatter.guaranteed_coi_rows(computed["coi_reps"], ia_min, ia_max)
    current = reformatter.current_coi_rows(
        computed["coi_reps"], computed["select_period"], ia_min, ia_max,
    )
    for idx, scale, ia, dur, rate in reformatter.filter_artifact_issue_ages(guaranteed, removed):
        rows.append([idx, scale, ia, dur, fmt_rate(rate)])
    for idx, scale, ia, dur, rate in reformatter.filter_artifact_issue_ages(current, removed):
        rows.append([idx, scale, ia, dur, fmt_rate(rate)])
    if removed:
        dropped_ages = sorted({ia for (_i, _s, ia) in removed})
        warnings.append(
            f"COI: dropped {len(removed)} artifact issue-age series "
            f"(first duration > 1) — issue ages {_condense(dropped_ages)} "
            "lie outside the product's true issue range.")
    return rows


def _target_rows(reformatter: RateReformatter, computed) -> List[list]:
    rows: List[list] = []
    for idx, ia, ctp, tbl1ctp, mtp, tbl1mtp, tbl4prem in reformatter.target_rows(
            computed["trg_reps"], computed["ia_min"], computed["ia_max"]):
        rows.append([
            idx, ia, fmt_rate(mtp), fmt_rate(ctp), fmt_rate(tbl4prem),
            fmt_rate(tbl1mtp), fmt_rate(tbl1ctp),
        ])
    return rows


def _build_benefit_tables(
    spec: WorkupSpec,
    analysis: WorkupAnalysis,
    base: _BaseBuild,
    warnings: List[str],
    progress,
) -> _BenefitBuild:
    grouped = _linked_mpf_groups(spec, warnings, progress)
    if spec.benefits:
        progress(0.35, f"Building {len(spec.benefits)} benefit(s)…")
    point_rows: List[list] = []
    bencoi_rows: List[list] = []
    bentrg_rows: List[list] = []
    for benefit in spec.benefits:
        built = _build_one_workup_benefit(spec, base, benefit, grouped, warnings)
        point_rows.extend(built[0])
        bencoi_rows.extend(_fmt_bencoi_rows(built[1]))
        bentrg_rows.extend(_fmt_bentrg_rows(built[2]))
    progress(0.55, "")
    return _BenefitBuild(point_rows, bencoi_rows, bentrg_rows)


def _linked_mpf_groups(spec: WorkupSpec, warnings: List[str], progress):
    if not any(benefit.mpf_code for benefit in spec.benefits):
        return None
    if spec.mpf_path and os.path.isfile(spec.mpf_path):
        progress(0.2, "Reading MPF for linked benefit charges…")
        return mpf_parser.group_by_combo(
            mpf_parser.iter_records(
                spec.mpf_path, progress_cb=lambda frac: progress(0.2 + frac * 0.15, ""))
        )
    warnings.append(
        "Benefits are linked to MPF codes but no MPF file was supplied — "
        "their BENCOI rates were NOT loaded.")
    return None


def _build_one_workup_benefit(spec, base, benefit, grouped, warnings):
    start = benefit.start_index or benefit_start_index(spec.base_index, benefit.code)
    if not start:
        warnings.append(
            f"Benefit {benefit.code}: no start index — the type code has "
            "no numeric mapping; set the index manually. Skipped.")
        return [], [], []
    if benefit.mpf_code and grouped is not None:
        return _build_linked_benefit(
            base.result, benefit,
            _mpf_items_for_code(grouped, benefit.mpf_code, benefit.code),
            base.combos, start, base.plancode, base.issue_version, warnings)
    db_spec = BenefitDBSpec(
        code=benefit.code, renewable=benefit.renewable,
        start_index=start, cease_age=benefit.cease_age,
    )
    point, coi, trg, _counts = build_benefit_rows(base.result, [db_spec])
    return point, coi, trg, 0


def _fmt_bencoi_rows(rows) -> List[list]:
    return [[idx, scale, ia, dur, fmt_rate(rate)] for idx, scale, ia, dur, rate in rows]


def _fmt_bentrg_rows(rows) -> List[list]:
    return [
        [idx, ia, fmt_rate(mtp) if mtp != "" else "", fmt_rate(ctp) if ctp != "" else ""]
        for idx, ia, mtp, ctp in rows
    ]


def _build_scr_tables(spec, combos, warnings, progress):
    if not (spec.scr_path and os.path.isfile(spec.scr_path) and spec.scr_plan):
        progress(0.75, "")
        return {}, []
    progress(0.55, f"Building SCR from CKULTB04 plan '{spec.scr_plan}'…")
    state_index, raw_rows, _groups = _build_scr(
        spec, combos, warnings, progress_cb=lambda frac: progress(0.55 + frac * 0.2, ""))
    progress(0.75, "")
    return state_index, [[i, ia, dur, fmt_rate(rate)] for i, ia, dur, rate in raw_rows]


def _build_epu_tables(spec, base, warnings, progress):
    if not (spec.epu_path and os.path.isfile(spec.epu_path) and spec.epu_plan):
        progress(0.9, "")
        return {}, []
    progress(0.75, f"Building EPU from CKULTB01 plan '{spec.epu_plan}' rule '{spec.epu_rule}'…")
    epu_index, raw_rows, _groups = _build_epu(
        spec, base.combos, base.ia_min, base.ia_max, base.max_att_age, warnings,
        progress_cb=lambda frac: progress(0.75 + frac * 0.15, ""))
    progress(0.9, "")
    return epu_index, [[i, s, ia, dur, fmt_rate(rate)] for i, s, ia, dur, rate in raw_rows]


def _pvsrb_rows(plancode, issue_version, base, scr_state_index, epu_index, band_map):
    rows: List[list] = []
    for combo in base.combos:
        sex, rate_class, band = combo
        state_map = scr_state_index.get(combo, {"AA": ""})
        for state in ["AA"] + sorted(st for st in state_map if st != "AA"):
            rows.append([
                plancode, issue_version, _sex_out(sex), rate_class,
                band_map.get(band, band), state, "", base.trg_map.get(combo, ""),
                "", state_map.get(state, ""), base.coi_map.get(combo, ""),
                epu_index.get(combo, ""), "", "", "", "",
            ])
    return rows


def _convert_point_benefit_rows(point_benefit_rows, band_map) -> None:
    for row in point_benefit_rows:
        row[4] = _sex_out(row[4])
        row[6] = band_map.get(row[6], row[6])


def _workup_tables(base, benefit, pvsrb_rows, scr_rows, epu_rows):
    return OrderedDict([
        ("POINT_PVSRB", (PVSRB_HEADERS, pvsrb_rows)),
        ("RATE_COI", (COI_HEADERS, base.coi_rows)),
        ("RATE_TRGPREM", (TRGPREM_HEADERS, base.trg_rows)),
        ("RATE_SCR", (SCR_HEADERS, scr_rows)),
        ("RATE_EPU", (EPU_HEADERS, epu_rows)),
        ("POINT_BENEFIT", (POINT_BENEFIT_HEADERS, benefit.point_rows)),
        ("RATE_BENCOI", (BENCOI_HEADERS, benefit.bencoi_rows)),
        ("RATE_BENTRG", (BENTRG_HEADERS, benefit.bentrg_rows)),
    ])


def _finalize_workup_result(spec, analysis, res, warnings, tables, progress) -> None:
    for name, (_headers, rows) in tables.items():
        res.table_counts[name] = len(rows)
    res.index_ranges = _index_ranges(spec, tables)
    summary_lines = _summary_lines(spec, analysis, res, warnings)
    progress(0.9, "Writing output…")
    if spec.fmt == "excel":
        ensure_dir(spec.output_dir)
        out_path = os.path.join(spec.output_dir, f"{analysis.plancode} - Workup DB.xlsx")
        sheets = OrderedDict(tables)
        sheets["WORKUP_SUMMARY"] = (["Summary"], [[line] for line in summary_lines])
        write_workbook(out_path, sheets)
        res.output_path = out_path
        return
    out_dir = ensure_dir(os.path.join(spec.output_dir, f"{analysis.plancode}_Workup"))
    for name, (headers, rows) in tables.items():
        write_csv(os.path.join(out_dir, f"{name}.csv"), headers, rows)
    write_summary(os.path.join(out_dir, "WORKUP_SUMMARY.txt"), summary_lines)
    res.output_path = out_dir


def _index_ranges(spec: WorkupSpec, tables) -> "OrderedDict[str, str]":
    """Human-readable index range per rate table (from the actual rows)."""
    ranges: "OrderedDict[str, str]" = OrderedDict()
    for name in ("RATE_COI", "RATE_TRGPREM", "RATE_SCR", "RATE_EPU",
                 "RATE_BENCOI", "RATE_BENTRG"):
        rows = tables[name][1]
        indexes = {r[0] for r in rows if r and r[0] != ""}
        if indexes:
            lo, hi = min(indexes), max(indexes)
            ranges[name] = f"{lo}–{hi}  ({len(indexes)} index(es))"
        else:
            ranges[name] = "—"
    return ranges


def _summary_lines(
    spec: WorkupSpec,
    analysis: WorkupAnalysis,
    res: WorkupResult,
    warnings: List[str],
) -> List[str]:
    lines = [
        f"RATE WORKUP — {analysis.plancode}  (IssueVersion {analysis.issue_version})",
        "=" * 64,
        "",
        "Sources:",
        f"  IAF:      {spec.iaf_path or '—'}",
        f"  MPF:      {spec.mpf_path or '—'}",
        f"  CKULTB04: {spec.scr_path or '—'}"
        + (f"   (plan '{spec.scr_plan}')" if spec.scr_plan else ""),
        f"  CKULTB01: {spec.epu_path or '—'}"
        + (f"   (plan '{spec.epu_plan}', freq '{spec.epu_freq}', rule '{spec.epu_rule}')"
           if spec.epu_plan else ""),
        "",
        f"Rate space:  {analysis.rate_space_summary()}",
        f"Maturity age: {spec.maturity_age}   Pay age: {analysis.pay_age}   "
        f"Base index: {spec.base_index}",
        "Output codes:  Sex 1→M, 2→F (unisex unchanged)   Bands "
        + (", ".join(
            f"{k}→{v}" for k, v in
            sorted(_band_out_map(analysis.combos).items(),
                   key=lambda kv: kv[1]) if k != "0") or "(unbanded)"),
        "",
        "Benefits included:",
    ]
    lines.extend(_summary_benefit_lines(spec))
    lines.extend(["", "Tables written:"])
    lines.extend(_summary_table_lines(res))
    lines.extend(_summary_warning_lines(warnings))
    return lines


def _summary_benefit_lines(spec: WorkupSpec) -> List[str]:
    if spec.benefits:
        return [
            (
                f"  {b.code:<4} ({src})  "
                f"{'renewable' if b.renewable else 'level':<10}  "
                f"start index {start if start else '—'}"
                + (f"  cease age {b.cease_age}"
                   if b.cease_age is not None else "")
            )
            for b in spec.benefits
            for src, start in [(
                f"COI from MPF {b.mpf_code}" if b.mpf_code else "IAF",
                b.start_index or benefit_start_index(spec.base_index, b.code),
            )]
        ]
    return ["  (none)"]


def _summary_table_lines(res: WorkupResult) -> List[str]:
    lines: List[str] = []
    for name, count in res.table_counts.items():
        rng = res.index_ranges.get(name, "")
        lines.append(f"  {name:<15} {count:>10,} rows"
                     + (f"   indexes {rng}" if rng and rng != '—' else ""))
    return lines


def _summary_warning_lines(warnings: List[str]) -> List[str]:
    lines = ["", f"Warnings ({len(warnings)}):"]
    if warnings:
        lines.extend(f"  ⚠ {w}" for w in warnings)
    else:
        lines.append("  (none)")
    return lines
