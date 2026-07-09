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
COI_HEADERS = ["Index", "Scale", "IssueAge", "Duration", "Rate"]
TRGPREM_HEADERS = [
    "Index(TRGPREM)", "IssueAge", "Rate(MTP)", "Rate(CTP)",
    "Rate(TBL4PREM)", "Rate(TBL1MTP)", "Rate(TBL1CTP)",
]
SCR_HEADERS = ["Index", "IssueAge", "Duration", "Rate"]
EPU_HEADERS = ["Index", "Scale", "IssueAge", "Duration", "Rate"]
POINT_BENEFIT_HEADERS = [
    "Plancode", "BenefitType", "Benefit", "IssueVersion",
    "Sex", "Rateclass", "Band", "Index(BENCOI)", "Index(BENTRG)",
]
BENCOI_HEADERS = ["Index", "Scale", "IssueAge", "Duration", "Rate"]
BENTRG_HEADERS = ["Index", "IssueAge", "MTP", "CTP"]

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
    # raw[(sex, cls, band)] = {(monthdur, highage): (eff_date, charge, guar)}
    raw: Dict[tuple, Dict[Tuple[int, int], Tuple[str, float, float]]] = defaultdict(dict)
    eff_dates: set = set()
    nonsentinel_max = 0
    state_skipped = 0

    for rec in ckultb01_parser.iter_records(spec.epu_path, progress_cb=progress_cb):
        if (rec["PLAN_CODE"], rec["FREQ_TYPE"], rec["RULE_CODE"]) != (
                spec.epu_plan, spec.epu_freq, spec.epu_rule):
            continue
        if rec["STATE_CODE"].strip() not in ("**", "AA", ""):
            state_skipped += 1
            continue
        key = (rec["SEX_CODE"], rec["RATE_CLASS"], rec["BAND_CODE"])
        bracket = (rec["MONTH_DUR"], rec["HIGH_AGE"])
        eff = rec["EFFECTIVE_DATE"]
        eff_dates.add(eff)
        prev = raw[key].get(bracket)
        # Multiple effective-date vintages: the most recent wins.
        if prev is None or _mdY(eff) > _mdY(prev[0]):
            raw[key][bracket] = (eff, rec["CHARGE"], rec["GUAR_CHARGE"])
        if rec["MAXIMUM"] < 9_999_999.0 or rec["GUAR_MAX"] < 9_999_999.0:
            nonsentinel_max += 1

    if state_skipped:
        warnings.append(
            f"EPU: {state_skipped:,} CKULTB01 rows with a specific state were "
            "ignored (only '**' all-state rows are loaded).")
    if nonsentinel_max:
        warnings.append(
            f"EPU: {nonsentinel_max:,} rows carry a real MAXIMUM/GUAR MAX cap "
            "(not 9,999,999) — caps are NOT loaded into RATE_EPU.")
    if len(eff_dates) > 1:
        warnings.append(
            "EPU: multiple effective dates present "
            f"({', '.join(sorted(eff_dates))}) — most recent kept per bracket.")

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
        brackets = [
            (md, ha, charge, guar)
            for (md, ha), (_eff, charge, guar) in raw[rk].items()
        ]

        # Expand brackets: year `dur` (months (dur-1)*12+1..dur*12) for issue
        # age `ia` uses the row with the smallest MONTHDUR >= dur*12 and the
        # smallest HIGH AGE >= ia. No covering bracket → charge 0.
        content: List[Tuple[int, int, float, float]] = []
        for ia in range(ia_min, ia_max + 1):
            max_dur = max_att_age - ia + 1
            if max_dur < 1:
                continue
            for dur in range(1, max_dur + 1):
                months = dur * 12
                best = None
                for md, ha, charge, guar in brackets:
                    if md >= months and ha >= ia:
                        cand = (md, ha, charge, guar)
                        if best is None or (cand[0], cand[1]) < (best[0], best[1]):
                            best = cand
                if best is None:
                    content.append((ia, dur, 0.0, 0.0))
                else:
                    content.append((ia, dur, best[2], best[3]))

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

    return combo_index, epu_rows, len(groups)


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

def _mpf_items_for_code(grouped, premcode: str) -> Dict[tuple, dict]:
    """``{(sex, cls, band): age_table}`` for one MPF premium code."""
    items: Dict[tuple, dict] = {}
    for (_company, _benefit, sex, cls, band, pc), table in grouped.items():
        if pc == premcode:
            items[(sex, cls, band)] = table
    return items


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
    )

    # ── BENCOI from the MPF premium code ────────────────────────────
    bencoi_rows: List[list] = []
    coi_groups: "OrderedDict[tuple, int]" = OrderedDict()
    coi_index: Dict[ComboKey, int] = {}
    missing: List[str] = []
    pct_converted = 0
    for combo in combos:
        rk = _match_raw(combo, mpf_items.keys())
        if rk is None:
            missing.append("/".join(combo))
            continue
        # Percent premiums load as decimals (5.64% → 0.0564).
        conv: Dict[int, float] = {}
        for age, (val, _s, is_pct) in mpf_items[rk].items():
            conv[age] = val / 100.0 if is_pct else val
            pct_converted += 1 if is_pct else 0
        sig = (tuple(sorted(conv.items())), sel.renewable)
        idx = coi_groups.get(sig)
        if idx is None:
            idx = start_index + len(coi_groups)
            coi_groups[sig] = idx
            for scale in (0, 1):
                for ia, dur, rate in _expand_attained_table(conv, sel.renewable):
                    bencoi_rows.append([idx, scale, ia, dur, rate])
        coi_index[combo] = idx

    # ── BENTRG from the IAF benefit code ────────────────────────────
    ctp = _benefit_rates_by_combo(result, sel.code, "T")
    mtp = _benefit_rates_by_combo(result, sel.code, "M")
    trg_bands = {b for (_s, _c, b) in set(ctp) | set(mtp)}
    bentrg_rows: List[list] = []
    trg_groups: "OrderedDict[tuple, int]" = OrderedDict()
    trg_index: Dict[ComboKey, int] = {}
    for combo in combos:
        key = _map_key(combo, trg_bands)
        c_rates = ctp.get(key, {}) if key else {}
        m_rates = mtp.get(key, {}) if key else {}
        if not c_rates and not m_rates:
            continue
        sig = (tuple(sorted(m_rates.items())), tuple(sorted(c_rates.items())))
        idx = trg_groups.get(sig)
        if idx is None:
            idx = start_index + len(trg_groups)
            trg_groups[sig] = idx
            bentrg_rows.extend(_bentrg_rows(idx, m_rates, c_rates))
        trg_index[combo] = idx

    # ── Pointer rows: Benefit column carries the MPF premium code ───
    pointer_rows: List[list] = []
    for combo in combos:
        ci = coi_index.get(combo)
        ti = trg_index.get(combo)
        if ci is None and ti is None:
            continue
        pointer_rows.append([
            plancode, sel.code, sel.mpf_code, issue_version,
            combo[0], combo[1], combo[2],
            ci if ci is not None else "",
            ti if ti is not None else "",
        ])

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

    block = max(len(coi_groups), len(trg_groups))
    return pointer_rows, bencoi_rows, bentrg_rows, block


def _expand_attained_table(table: Dict[int, float], renewable: bool):
    """Expand an attained-age table into ``(issue_age, duration, rate)`` rows.

    Mirrors the MPF Supplemental renewal logic: renewable → the rate at
    attained age issue+d-1; non-renewable → the issue-age rate held level.
    """
    ages = sorted(table)
    if not ages:
        return []
    max_age = ages[-1]
    rows = []
    for ia in ages:
        for dur in range(1, max_age - ia + 2):
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
    def _p(frac: float, msg: str = "") -> None:
        if progress_cb:
            progress_cb(frac, msg)

    res = WorkupResult()
    warnings: List[str] = list(analysis.warnings)

    try:
        result = analysis.iaf_result
        plancode = analysis.plancode
        issue_version = analysis.issue_version or "1"

        # ── 1. Base COI + targets from the IAF ─────────────────────────
        _p(0.0, "Building base COI and target tables…")
        reformatter = RateReformatter(
            result,
            starting_index=spec.base_index,
            trg_starting_index=spec.base_index,
        )
        computed = reformatter.compute()
        combos: List[ComboKey] = computed["combos"]
        coi_map, coi_reps = computed["coi_index"], computed["coi_reps"]
        trg_map, trg_reps = computed["trg_index"], computed["trg_reps"]
        ia_min, ia_max = computed["ia_min"], computed["ia_max"]
        select_period = computed["select_period"]
        max_att_age = reformatter.max_att_age

        # Series whose first duration > 1 are IAF pre-fill artifacts for
        # issue ages outside the product's true issue range — dropped.
        removed: set = set()
        coi_rows: List[list] = []
        for idx, scale, ia, dur, rate in reformatter.filter_artifact_issue_ages(
                reformatter.guaranteed_coi_rows(coi_reps, ia_min, ia_max),
                removed):
            coi_rows.append([idx, scale, ia, dur, fmt_rate(rate)])
        for idx, scale, ia, dur, rate in reformatter.filter_artifact_issue_ages(
                reformatter.current_coi_rows(
                    coi_reps, select_period, ia_min, ia_max),
                removed):
            coi_rows.append([idx, scale, ia, dur, fmt_rate(rate)])
        if removed:
            dropped_ages = sorted({ia for (_i, _s, ia) in removed})
            warnings.append(
                f"COI: dropped {len(removed)} artifact issue-age series "
                f"(first duration > 1) — issue ages {_condense(dropped_ages)} "
                "lie outside the product's true issue range.")

        trg_rows: List[list] = []
        for idx, ia, ctp, tbl1ctp, mtp, tbl1mtp in reformatter.target_rows(
                trg_reps, ia_min, ia_max):
            trg_rows.append([
                idx, ia, fmt_rate(mtp), fmt_rate(ctp),
                "",                       # Rate(TBL4PREM) — not used
                fmt_rate(tbl1mtp), fmt_rate(tbl1ctp),
            ])
        _p(0.2, f"Base: {len(coi_rows):,} COI rows, {len(trg_rows):,} target rows")

        # ── 2 & 3. Benefits — IAF riders, some with MPF-linked charges ─
        # Each benefit's index block follows the convention: base index with
        # the 2-digit type code inserted and two zeros appended (13400 +
        # benefit 12 → 1341200). A benefit with an mpf_code takes BENCOI
        # from that MPF premium code and BENTRG from the IAF; otherwise
        # everything comes from the IAF.
        point_benefit_rows: List[list] = []
        bencoi_rows: List[list] = []
        bentrg_rows: List[list] = []

        mpf_grouped = None
        if any(b.mpf_code for b in spec.benefits):
            if spec.mpf_path and os.path.isfile(spec.mpf_path):
                _p(0.2, "Reading MPF for linked benefit charges…")
                mpf_grouped = mpf_parser.group_by_combo(
                    mpf_parser.iter_records(
                        spec.mpf_path,
                        progress_cb=lambda f: _p(0.2 + f * 0.15, "")))
            else:
                warnings.append(
                    "Benefits are linked to MPF codes but no MPF file was "
                    "supplied — their BENCOI rates were NOT loaded.")

        if spec.benefits:
            _p(0.35, f"Building {len(spec.benefits)} benefit(s)…")
        for b in spec.benefits:
            start = b.start_index or benefit_start_index(
                spec.base_index, b.code)
            if not start:
                warnings.append(
                    f"Benefit {b.code}: no start index — the type code has "
                    "no numeric mapping; set the index manually. Skipped.")
                continue
            if b.mpf_code and mpf_grouped is not None:
                p_rows, c_rows, t_rows, _block = _build_linked_benefit(
                    result, b, _mpf_items_for_code(mpf_grouped, b.mpf_code),
                    combos, start, plancode, issue_version, warnings)
            else:
                db_spec = BenefitDBSpec(
                    code=b.code, renewable=b.renewable, start_index=start)
                p_rows, c_rows, t_rows, _counts = build_benefit_rows(
                    result, [db_spec])
            point_benefit_rows.extend(p_rows)
            for idx, scale, ia, dur, rate in c_rows:
                bencoi_rows.append([idx, scale, ia, dur, fmt_rate(rate)])
            for idx, ia, mtp, ctp in t_rows:
                bentrg_rows.append([
                    idx, ia,
                    fmt_rate(mtp) if mtp != "" else "",
                    fmt_rate(ctp) if ctp != "" else "",
                ])
        _p(0.55, "")

        # ── 4. Surrender charges (CKULTB04) ────────────────────────────
        scr_state_index: Dict[ComboKey, Dict[str, int]] = {}
        scr_rows: List[list] = []
        if spec.scr_path and os.path.isfile(spec.scr_path) and spec.scr_plan:
            _p(0.55, f"Building SCR from CKULTB04 plan '{spec.scr_plan}'…")
            scr_state_index, raw_scr_rows, _groups = _build_scr(
                spec, combos, warnings,
                progress_cb=lambda f: _p(0.55 + f * 0.2, ""))
            scr_rows = [[i, ia, dur, fmt_rate(r)] for i, ia, dur, r in raw_scr_rows]
        _p(0.75, "")

        # ── 5. Expense per unit (CKULTB01) ─────────────────────────────
        epu_index: Dict[ComboKey, int] = {}
        epu_rows: List[list] = []
        if spec.epu_path and os.path.isfile(spec.epu_path) and spec.epu_plan:
            _p(0.75, f"Building EPU from CKULTB01 plan '{spec.epu_plan}' "
                     f"rule '{spec.epu_rule}'…")
            epu_index, raw_epu_rows, _groups = _build_epu(
                spec, combos, ia_min, ia_max, max_att_age, warnings,
                progress_cb=lambda f: _p(0.75 + f * 0.15, ""))
            epu_rows = [[i, s, ia, dur, fmt_rate(r)] for i, s, ia, dur, r in raw_epu_rows]
        _p(0.9, "")

        # ── 6. POINT_PVSRB — AA rows + SCR exception states ────────────
        # Output code conversion: sex 1/2 → M/F (unisex codes unchanged),
        # band letters → 1, 2, 3, … (X and Y first when present).
        band_map = _band_out_map(combos)
        pvsrb_rows: List[list] = []
        for combo in combos:
            s, c, b = combo
            coi_idx = coi_map.get(combo, "")
            trg_idx = trg_map.get(combo, "")
            epu_idx = epu_index.get(combo, "")
            state_map = scr_state_index.get(combo, {"AA": ""})
            states = ["AA"] + sorted(st for st in state_map if st != "AA")
            for state in states:
                scr_idx = state_map.get(state, "")
                pvsrb_rows.append([
                    plancode, issue_version,
                    _sex_out(s), c, band_map.get(b, b), state,
                    "",            # Index(PREMLOAD)
                    trg_idx if trg_idx != "" else "",
                    "",            # Index(MFEE)
                    scr_idx,
                    coi_idx,
                    epu_idx,
                    "", "", "", "",   # Index(GLP), MORTID, Index(SHDINT), Index(TRAD_CV)
                ])

        # POINT_BENEFIT rows carry the same converted codes.
        for row in point_benefit_rows:
            row[4] = _sex_out(row[4])
            row[6] = band_map.get(row[6], row[6])

        # ── 7. Write output ────────────────────────────────────────────
        tables = OrderedDict([
            ("POINT_PVSRB", (PVSRB_HEADERS, pvsrb_rows)),
            ("RATE_COI", (COI_HEADERS, coi_rows)),
            ("RATE_TRGPREM", (TRGPREM_HEADERS, trg_rows)),
            ("RATE_SCR", (SCR_HEADERS, scr_rows)),
            ("RATE_EPU", (EPU_HEADERS, epu_rows)),
            ("POINT_BENEFIT", (POINT_BENEFIT_HEADERS, point_benefit_rows)),
            ("RATE_BENCOI", (BENCOI_HEADERS, bencoi_rows)),
            ("RATE_BENTRG", (BENTRG_HEADERS, bentrg_rows)),
        ])

        for name, (_h, rows) in tables.items():
            res.table_counts[name] = len(rows)

        res.index_ranges = _index_ranges(spec, tables)

        summary_lines = _summary_lines(spec, analysis, res, warnings)

        _p(0.9, "Writing output…")
        if spec.fmt == "excel":
            ensure_dir(spec.output_dir)
            out_path = os.path.join(
                spec.output_dir, f"{plancode} - Workup DB.xlsx")
            sheets = OrderedDict(tables)
            sheets["WORKUP_SUMMARY"] = (["Summary"], [[l] for l in summary_lines])
            write_workbook(out_path, sheets)
            res.output_path = out_path
        else:
            out_dir = ensure_dir(os.path.join(
                spec.output_dir, f"{plancode}_Workup"))
            for name, (headers, rows) in tables.items():
                write_csv(os.path.join(out_dir, f"{name}.csv"), headers, rows)
            write_summary(
                os.path.join(out_dir, "WORKUP_SUMMARY.txt"), summary_lines)
            res.output_path = out_dir

        res.warnings = warnings
        _p(1.0, "Workup complete.")

    except Exception as exc:      # surface, never swallow
        import traceback
        res.error = f"{exc}\n{traceback.format_exc()}"

    return res


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
    if spec.benefits:
        for b in spec.benefits:
            src = f"COI from MPF {b.mpf_code}" if b.mpf_code else "IAF"
            start = b.start_index or benefit_start_index(
                spec.base_index, b.code)
            lines.append(
                f"  {b.code:<4} ({src})  "
                f"{'renewable' if b.renewable else 'level':<10}  "
                f"start index {start if start else '—'}")
    else:
        lines.append("  (none)")
    lines += ["", "Tables written:"]
    for name, count in res.table_counts.items():
        rng = res.index_ranges.get(name, "")
        lines.append(f"  {name:<15} {count:>10,} rows"
                     + (f"   indexes {rng}" if rng and rng != '—' else ""))
    lines += ["", f"Warnings ({len(warnings)}):"]
    if warnings:
        lines.extend(f"  ⚠ {w}" for w in warnings)
    else:
        lines.append("  (none)")
    return lines
