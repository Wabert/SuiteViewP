"""Build live CyberLife policy-record screens from real DB2 policy data.

This turns a :class:`PolicyInformation` into the exact ``lines`` token structure
that :mod:`suiteview.polview.ui.policy_record_viewer` renders on the green
screen -- so the viewer can show the *currently loaded* policy as it would look
on the CyberLife mainframe, not just the bundled sample.

Each screen is a list of *lines*; each line is a list of *runs*::

    {"text": "987.00", "field": "Amount"}   # a hover-aware value
    {"text": "  ",       "field": None}      # inert spacing

The ``field`` names match the keys in the segment's static ``fields`` map
(loaded from ``seg_<n>.json``) so tooltips and the Record Layout reference keep
working unchanged.

Segment 58 (screen 6258 -- "Target Premiums")
---------------------------------------------
The segment is the union of three DB2 target tables, laid out in the order given
by ``SEG_IDX_NBR`` (verified live against a real policy):

======================  ===============  ==================  =========================
Table                   Phase column     Rule column         Typical codes
======================  ===============  ==================  =========================
``LH_COM_TARGET``       AGT_COM_PHA_NBR  TAR_DT_RLE_CD       CA, CP, CT, VC
``LH_COV_TARGET``       COV_PHA_NBR      PRM_RLE_CD          ST
``LH_POL_TARGET``       (none -> 0)      PRM_RLE_CD          IX, MA, MT, TA, TS
======================  ===============  ==================  =========================

Each entry is a fixed sequence of fields::

    code(2)  flag(8)  phase(1)  rule(1)  date(MM/DD/YYYY)  amount(2dp)

and the 6-byte header carries the segment id (``58``), the segment length
(``6 + 15 * N`` as a 4-digit number) and the entry count ``N``.
"""

from __future__ import annotations

import getpass
import json
import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple

# Field-name constants (must match the keys in seg_58.json's "fields" map).
_F_SCREEN = "Screen Name"
_F_POLICY = "Policy Number"
_F_SEG_ID = "Segment Identification"
_F_SEG_LEN = "Segment Length"
_F_NUM_ENTRIES = "Number of Entries"
_F_CODE = "Target Premium Code"

# Segment 58 target codes (TAR_TYP_CD); meanings taken from how SuiteView reads
# each target. None of these are described in the CyberDoc field entry itself.
_TARGET_CODE_MEANINGS = {
    "CT": "Commission Target Premium",
    "MT": "Monthly Minimum Target Premium",
    "MA": "Accumulated Minimum Target Premium (MAP)",
    "TA": "Accumulated Guideline Level Premium target (GLP)",
    "LT": "Premium Limit Target",
    "NS": "NSP Base target",
    "NT": "NSP Other target",
    "VS": "Short-pay premium",
    "XP": "Shadow account value target",
    "ST": "Surrender Target",
    "SU": "Surrender Target",
    "CV": "CCV (Coverage Continuation Value) target",
}
_TARGET_CODE_UNCONFIRMED = "meaning not documented in CyberDoc or SuiteView"

# Segment 67 rate type codes (PRM_RT_TYP_CD).
_RATE_TYPE_MEANINGS = {
    "A": "Guideline Level Premium (GLP)",
    "B": "Benefit renewal rate",
    "C": "Current rate",
    "G": "Guaranteed rate",
    "M": "Minimum premium rate (MTP)",
    "S": "Guideline Single Premium (GSP)",
    "T": "Commission target premium rate (CTP)",
    "W": "Surrender target rate (not used by SuiteView)",
}


def _target_code_note(code: str) -> str:
    meaning = _TARGET_CODE_MEANINGS.get(code.strip())
    return f"{code.strip()} = {meaning}" if meaning else (
        f"{code.strip()}: {_TARGET_CODE_UNCONFIRMED}")
_F_FLAG = "Flag Byte A"
_F_PHASE = "Phase Code"
_F_RULE = "Rule"
_F_DATE = "Date"
_F_AMOUNT = "Amount"
_F_CUR_DATE = "Current Date"
_F_USER = "Part of the user ID?"
_F_REGION = "Region and Company"

_SEP = "  "               # standard 2-space gap between fields
_INDENT = " " * 12        # continuation-line indent (matches the sample screen)
_ENTRIES_PER_LINE = 2
_FLAG_PLACEHOLDER = "00000000"  # byte 9 has no DB2 source; the sample shows this

# Warnings surfaced in tooltips for values that are not real DB2 policy data.
_EXAMPLE_NOTE = ("EXAMPLE DATA \u2014 this value is not stored in DB2 for this "
                 "policy; it is shown for illustration only.")


# ---------------------------------------------------------------------------
# CyberDoc field-format index (authoritative display formats)
# ---------------------------------------------------------------------------
# The official CyberLife documentation records each field's storage/display
# format.  ``tools/policyrecord/build_cyberdoc_index.py`` distils that into a COBOL-name ->
# ``kind`` map so the builder can format each value exactly like the mainframe.
# The single case this settles that the archive sample cannot: some date fields
# are stored as a packed ``MMDDYY`` integer and shown *unslashed* (e.g. 71026),
# while ordinary calendar dates show slashed (07/10/2026).
_CYBERDOC_INDEX_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "policy_record_screens", "cyberdoc_field_formats.json",
)

# Date ``kind`` values (from the CyberDoc index) that the mainframe renders as a
# packed MMDDYY integer rather than a slashed calendar date.
_PACKED_DATE_KINDS = frozenset({"date_packed", "packed_num", "int"})

# Segment 02 (Coverage) coverage-field mapping -- an ordered list of
# {name, role, db2, kind, line_break, ...} generated by tools/policyrecord/gen_seg02_fields.py
# from seg_02.json's record layout, cross-checked against the Translation sheet.
_SEG02_FIELDS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "policy_record_screens", "seg_02_coverage_fields.json",
)

_cyberdoc_index_cache: Optional[dict] = None


def _cyberdoc_index() -> dict:
    """Load (and cache) the COBOL-name -> format-kind index; ``{}`` if absent."""
    global _cyberdoc_index_cache
    if _cyberdoc_index_cache is None:
        try:
            with open(_CYBERDOC_INDEX_PATH, "r", encoding="utf-8") as fh:
                _cyberdoc_index_cache = json.load(fh)
        except (OSError, ValueError):
            _cyberdoc_index_cache = {}
    return _cyberdoc_index_cache


def _field_kind_map(screen: dict) -> dict:
    """Map each field name -> CyberDoc display ``kind`` via its COBOL name.

    Uses the segment's ``field_specs`` (which carry the ``cobol`` name for every
    field) joined to the CyberDoc index.  Fields without a COBOL name or index
    entry are simply absent, so formatting falls back to sample inference.
    """
    index = _cyberdoc_index()
    if not index:
        return {}
    out: dict = {}
    for spec in screen.get("field_specs", []) or []:
        cobol = spec.get("cobol")
        name = spec.get("name")
        if not cobol or not name:
            continue
        meta = index.get(cobol)
        if meta and meta.get("kind"):
            out[name] = meta["kind"]
    return out


def build_segment_lines(segment: str, pi, screen: Optional[dict] = None) -> Optional[List[list]]:
    """Return the ``lines`` for *segment* built from live policy data.

    Returns ``None`` when this segment/data variant has no live rendering.
    The viewer omits absent/unsupported records and identifies errors, never
    substituting a captured screen. *screen* is the bundled
    ``seg_<n>.json`` dict.  A ``template`` screen (e.g. Segment 01) carries the
    authentic mainframe layout as annotated ``lines``; each value token is
    filled live from its ``db2`` source (or shown as clearly-labelled example
    data when no DB2 source exists).
    """
    if segment == "58":
        return _build_segment_58(pi)
    if segment == "53":
        return _build_segment_53(pi)
    if segment == "55":
        from .policy_record_fund_control import build_segment_55

        return build_segment_55(pi)
    if segment == "56" and screen:
        return _build_segment_56(pi, screen)
    if segment == "57":
        from .policy_record_allocations import build_segment_57

        return build_segment_57(pi)
    if segment == "59":
        return _build_segment_59(pi)
    if segment == "60" and screen:
        from .policy_record_payment_totals import build_segment_60

        return build_segment_60(pi, screen)
    if segment in ("63", "64"):
        from .policy_record_annual_totals import build_segment_63, build_segment_64

        return build_segment_63(pi) if segment == "63" else build_segment_64(pi)
    if segment == "02":
        return _build_segment_02(pi)
    if segment == "04":
        from .policy_record_benefits import build_segment_04

        return build_segment_04(pi)
    if segment == "66":
        return _build_segment_66(pi)
    if segment == "67":
        return _build_segment_67(pi)
    if screen and screen.get("template") and screen.get("lines"):
        return _build_templated_segment(pi, segment, screen)
    return None


# ---------------------------------------------------------------------------
# Segment 67 -- Renewal Rates (D202, printed pages 193-202 and 612)
# ---------------------------------------------------------------------------

_SEG67_PERIOD_TABLE = "LH_COV_INS_RNL_PER"
_SEG67_ENTRY_TABLES = (
    "LH_COV_INS_RNL_RT", "LH_BNF_INS_RNL_RT", "LH_SST_XTR_RNL_RT",
    "LH_COV_INS_GDL_PRM", "LH_BNF_INS_GDL_PRM",
)


def _seg67_value(row: dict, column: str):
    if column not in row:
        raise ValueError(f"Segment 67 source column is missing: {column}")
    return row[column]


def _seg67_text(row: dict, column: str, width: int) -> str:
    value = _seg67_value(row, column)
    if value is None:
        raise ValueError(f"Segment 67 requires {column}; DB2 returned NULL")
    text = str(value).strip()
    if len(text) > width or any(ord(c) < 32 for c in text):
        raise ValueError(f"Invalid Segment 67 {column}: {value!r}")
    return text.ljust(width)


def _seg67_integer(row: dict, column: str) -> int:
    value = _seg67_value(row, column)
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid Segment 67 {column}: {value!r}") from exc
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        raise ValueError(f"Invalid Segment 67 {column}: {value!r}")
    return int(number)


def _seg67_key(row: dict) -> tuple:
    return (
        _seg67_integer(row, "COV_PHA_NBR"),
        _seg67_text(row, "PRS_CD", 2),
        _seg67_integer(row, "PRS_SEQ_NBR"),
    )


def _seg67_token(text: str, field: str, table: str, column: str, note="") -> dict:
    return {
        **_tok(text, field),
        "note": f"Live source: {table}.{column}. {note}".strip(),
    }


def _seg67_amount(row: dict, table: str, column: str, field: str,
                  digits: int, decimals: int = 0) -> dict:
    value = _seg67_value(row, column)
    if value is None:
        return {
            **_seg67_token("?" * (digits + 1), field, table, column,
                          "DB2 NULL: unavailable, not zero."),
            "dim": True,
        }
    return _seg67_token(
        _packed_decimal(value, digits, decimals), field, table, column,
        "Packed decimal digits; C = positive/zero, D = negative.",
    )


def _seg67_extra_key_groups(table: str, row: dict) -> tuple[list, str]:
    percent = _seg67_text(row, "SST_XTR_PCT_IND", 1)
    if percent not in ("0", "1"):
        raise ValueError(f"Unsupported Segment 67 extra percentage flag: {percent!r}")
    return [[_seg67_token(
        _seg67_text(row, "SST_XTR_RT_TBL_CD", 2),
        "Table Rating Code", table, "SST_XTR_RT_TBL_CD",
    )]], percent


def _seg67_benefit_key(table: str, row: dict) -> tuple[str, str, str, str, str]:
    if table.startswith("LH_BNF_"):
        return (
            _seg67_text(row, "SPM_BNF_TYP_CD", 1),
            _seg67_text(row, "SPM_BNF_SBY_CD", 1),
            "SPM_BNF_TYP_CD",
            "SPM_BNF_SBY_CD",
            "0",
        )
    option = _seg67_value(row, "DTH_BNF_PLN_OPT_CD")
    option = "" if option is None else str(option).strip()
    if len(option) > 1 or (option and ord(option) < 32):
        raise ValueError(f"Invalid Segment 67 death benefit option: {option!r}")
    if table.endswith("_GDL_PRM"):
        btype, subtype, bcolumn, system_calc = _seg67_guideline_benefit_key(row, option)
        return btype, subtype, bcolumn, "DTH_BNF_PLN_OPT_CD", system_calc
    btype, subtype, bcolumn, scolumn = _seg67_coverage_benefit_key(row, option)
    return btype, subtype, bcolumn, scolumn, "0"


def _seg67_guideline_benefit_key(row: dict, option: str) -> tuple[str, str, str, str]:
    system_calc = _seg67_text(row, "SYS_CLC_PRM_IND", 1)
    if system_calc not in ("0", "1"):
        raise ValueError(f"Invalid Segment 67 guideline flag: {system_calc!r}")
    rate_type = _seg67_text(row, "PRM_RT_TYP_CD", 1)
    if system_calc == "1":
        if rate_type not in ("A", "S"):
            raise ValueError("Segment 67 system-calculated guidelines require type A or S")
        return " ", option or " ", "SYS_CLC_PRM_IND", system_calc
    if not option:
        raise ValueError("Segment 67 rate-file guideline plan option is unavailable")
    return "*", option, "SYS_CLC_PRM_IND", system_calc


def _seg67_coverage_benefit_key(row: dict, option: str) -> tuple[str, str, str, str]:
    rate_type = _seg67_text(row, "PRM_RT_TYP_CD", 1)
    if rate_type not in ("C", "T", "W", "L", "F", "M"):
        raise ValueError(f"Unsupported Segment 67 coverage rate type: {rate_type!r}")
    joint = _seg67_text(row, "JT_INS_IND", 1)
    if joint not in ("0", "1"):
        raise ValueError(f"Invalid Segment 67 joint-insured flag: {joint!r}")
    if joint == "1" and rate_type != "C":
        raise ValueError("Segment 67 joint-insured markers are verified only for C rates")
    subtype = "J" if joint == "1" else (option or "*")
    if rate_type == "C" and joint == "0":
        subtype = "*"
    scolumn = "JT_INS_IND" if joint == "1" else "DTH_BNF_PLN_OPT_CD"
    return "*", subtype, "PRM_RT_TYP_CD", scolumn


def _seg67_guideline_groups(table: str, row: dict, rate_type: str,
                            system_calc: str, benefit: bool) -> list:
    if rate_type not in ("A", "S", "1", "2", "3"):
        raise ValueError(f"Unsupported Segment 67 guideline type: {rate_type!r}")
    if not benefit and system_calc == "1":
        key = "  "
    else:
        key = "".join(_seg67_text(row, column, 1) for column in ("RT_SEX_CD", "RT_CLS_CD"))
        if not key.strip():
            raise ValueError("Segment 67 rate-file guideline key is unavailable")
    units = rate_type in ("1", "2")
    return [
        [_seg67_token(
            key, "Guideline Rate Key", table, "RT_SEX_CD / RT_CLS_CD",
            "System-calculated guideline premiums have a blank key.",
        )],
        [_seg67_amount(
            row, table, "GDL_PRM_UNT_QTY" if units else "GDL_PRM_AMT",
            "GLP/GSP Units" if units else "GLP/GSP Premium", 11, 3 if units else 2,
        )],
    ]


def _seg67_rate_key_group(table: str, row: dict) -> list:
    return [[
        _seg67_token(_seg67_text(row, column, 1), field, table, column)
        for column, field in (
            ("RT_SEX_CD", "Rate Sex"), ("RT_CLS_CD", "Rate Class"),
            ("RT_BAN_CD", "Rate Band"),
        )
    ]]


def _seg67_extra_amount_group(table: str, row: dict, percent: str) -> list:
    if percent == "0":
        amount = _seg67_value(row, "SST_XTR_UNT_AMT")
        if amount is not None and Decimal(str(amount)) != 0:
            raise ValueError(
                "Segment 67 nonzero dollar extra: packed precision is not "
                "verified for this coverage (fixed versus flexible premium)"
            )
    return [[_seg67_amount(
        row, table, "SST_XTR_PCT" if percent == "1" else "SST_XTR_UNT_AMT",
        "Extra Percentage" if percent == "1" else "Extra Unit Amount",
        9, 5 if percent == "1" else 0,
    )]]


def _seg67_entry_groups(table: str, row: dict) -> list:
    """Keep rate-key bytes together while allowing entries to span lines."""
    rate_type = _seg67_text(row, "PRM_RT_TYP_CD", 1)
    meaning = _RATE_TYPE_MEANINGS.get(rate_type.strip())
    type_note = f"{rate_type.strip()} = {meaning}." if meaning else ""
    groups = [[_seg67_token(rate_type, "Rate Type Code", table, "PRM_RT_TYP_CD", type_note)]]
    guideline = table.endswith("_GDL_PRM")
    benefit = table.startswith("LH_BNF_")
    system_calc = "0"
    percent = "0"

    if table == "LH_SST_XTR_RNL_RT":
        extra_groups, percent = _seg67_extra_key_groups(table, row)
        groups.extend(extra_groups)
    else:
        btype, subtype, bcolumn, scolumn, system_calc = _seg67_benefit_key(table, row)
        groups.extend([
            [_seg67_token(btype, "Benefit Type", table, bcolumn)],
            [_seg67_token(subtype, "Benefit Subtype", table, scolumn)],
        ])

    if guideline:
        groups.extend(_seg67_guideline_groups(table, row, rate_type, system_calc, benefit))
    else:
        groups.extend(_seg67_rate_key_group(table, row))
        if table == "LH_SST_XTR_RNL_RT":
            groups.extend(_seg67_extra_amount_group(table, row, percent))
        else:
            # RNL_RT already contains the unscaled nine packed digits in DB2.
            groups.append([_seg67_amount(row, table, "RNL_RT", "Rate", 9)])
    return groups


def _build_segment_67(pi) -> Optional[List[list]]:
    """Union the five entry sources by period and original segment index."""
    sources = {}
    for table in (_SEG67_PERIOD_TABLE, *_SEG67_ENTRY_TABLES):
        sources[table] = pi.fetch_table(table)
        error = pi.table_error(table)
        if error:
            raise ValueError(f"Segment 67 {table}: {error}")

    periods = {}
    for row in sources[_SEG67_PERIOD_TABLE]:
        key = _seg67_key(row)
        if key in periods:
            raise ValueError(f"Duplicate Segment 67 renewal period: {key}")
        periods[key] = row
    entries = {key: {} for key in periods}
    for table in _SEG67_ENTRY_TABLES:
        for row in sources[table]:
            key = _seg67_key(row)
            if key not in entries:
                raise ValueError(f"Segment 67 {table} has no renewal period: {key}")
            index = _seg67_integer(row, "SEG_IDX_NBR")
            if index in entries[key]:
                raise ValueError(f"Duplicate Segment 67 entry index {index} for {key}")
            entries[key][index] = (table, row)
    if not periods:
        return None

    lines = [[_sep(_SEP), _tok("6267,", _F_SCREEN), _sep(" "),
              _tok(_policy_display(pi), _F_POLICY)]]
    for key, period in sorted(periods.items()):
        period_entries = entries[key]
        count = len(period_entries)
        if sorted(period_entries) != list(range(1, count + 1)):
            raise ValueError(f"Non-contiguous Segment 67 entry indexes for {key}")
        length = 22 + 11 * count
        if length > 9999 or count > 999:
            raise ValueError(f"Segment 67 exceeds its display capacity for {key}")
        groups = [
            [_tok("67", _F_SEG_ID)], [_tok(f"{length:04d}", _F_SEG_LEN)],
            [_tok(str(key[0]), _F_PHASE)],
            [_seg67_token(
                _seg67_text(period, "PLN_DES_SER_CD", 11),
                "Plan Description Search Key", _SEG67_PERIOD_TABLE, "PLN_DES_SER_CD",
            )],
            [_seg67_token(
                _seg67_text(period, "RENEWABLE_PRM_CD", 1),
                "Renewal Class", _SEG67_PERIOD_TABLE, "RENEWABLE_PRM_CD",
            )],
            [_tok(key[1], "Person Code")], [_tok(str(key[2]), "Person Sequence")],
            [_tok(str(count), "Number of Rate Segments")],
        ]
        for index in sorted(period_entries):
            groups.extend(_seg67_entry_groups(*period_entries[index]))

        lines.extend(_wrap_record_groups(groups))
    _append_screen_footer(lines, pi, min_lines=18)
    return lines


# ---------------------------------------------------------------------------
# Segment 53 -- Automatic Transaction Control (Sweep Fund)
# ---------------------------------------------------------------------------

_SEG53_ATM_TABLE = "LH_ATM_TRS_SCH"
_SEG53_SWEEP_TABLE = "LH_SWF_SCH"
_SEG53_INDENT = " " * 12
_SEG53_SWEEP_TYPE = "B"
_SEG53_FLAGS = (
    "Flag Byte A", "Flag Byte B", "Flag Byte C",
    "Flag Byte D", "Flag Byte E", "Flag Byte U",
)
_SEG53_FLAG_NOTE = (
    "EXAMPLE DATA - DB2 exposes selected indicator bits, not every bit needed "
    "to reconstruct this complete CyberLife flag byte."
)
_SEG53_CHARGE_NOTE = (
    "EXAMPLE DATA - no verified DB2 mapping exists for this field. The value "
    "shown is from the UE142109 CyberLife capture, not this policy's live data."
)
_SEG53_SWEEP_NOTE = (
    "EXAMPLE DATA - no matching LH_SWF_SCH row was available. The current DB2 "
    "user may lack SELECT access; this UE142109 captured value is not live "
    "policy data."
)


def _seg53_moyr(value) -> str:
    """Decode CyberLife's one-based month count from January 1900."""
    month_number = _as_int(value)
    if month_number <= 0:
        return "00/1900"
    year = 1900 + (month_number - 1) // 12
    month = (month_number - 1) % 12 + 1
    return f"{month:02d}/{year:04d}"


def _seg53_date(value) -> str:
    parts = _date_parts(value)
    if parts is None:
        return "00/00/1900"
    month, day, year = parts
    if year >= 9999:
        return "00/00/1900"
    return f"{month:02d}/{day:02d}/{year:04d}"


def _seg53_fixed_text(value, width: int) -> str:
    """Preserve blank fixed-width character fields and their screen columns."""
    text = "" if value is None else str(value)
    return text[:width].ljust(width)


def _seg53_line(tokens: list[dict], *, indent: bool = False) -> list[dict]:
    line = [_sep(_SEG53_INDENT if indent else _SEP)]
    for index, token in enumerate(tokens):
        if index:
            line.append(_sep(_SEP))
        line.append(token)
    line.append(_sep(_SEP))
    return line


def _seg53_sweep_row(rows: List[dict], atm_row: dict) -> Optional[dict]:
    wanted_type = str(atm_row.get("ATM_TRS_TYP_CD") or "").strip()
    wanted_sequence = _as_int(atm_row.get("ATM_TRS_SEQ_NBR"))
    for row in rows:
        if (
            str(row.get("ATM_TRS_TYP_CD") or "").strip() == wanted_type
            and _as_int(row.get("ATM_TRS_SEQ_NBR")) == wanted_sequence
        ):
            return row
    return None


def _seg53_sweep_tokens(
    row: Optional[dict],
    missing_note: str = _SEG53_SWEEP_NOTE,
) -> list[dict]:
    fields = (
        ("Sweep Fund Minimum Balance", "SWEEP_MIN_BALANCE", "199.80", "dec2"),
        ("Sweep Frequency", "SWEEP_FREQUENCY", "M", "code"),
        ("Sweep Day", "SWEEP_DAY", "1", "int"),
        ("Sweep Month", "SWEEP_MONTH", "0", "int"),
    )
    if row is None:
        return [
            _example(sample, field, missing_note)
            for field, _, sample, _ in fields
        ]

    tokens = []
    for field, column, _, fmt in fields:
        value = row.get(column)
        if fmt == "dec2":
            text = _decimal_display(value, 2)
        elif fmt == "int":
            text = _seg66_int(value)
        else:
            text = _seg66_code(value)
        tokens.append(_tok(text, field))
    return tokens


def _build_segment_53(pi) -> Optional[List[list]]:
    """Render the verified Sweep Fund (type B) Segment 53 layout.

    Other Segment 53 transaction types redefine the variable area differently.
    Until each has a real terminal capture, a policy containing one falls back
    to the captured reference instead of receiving a speculative live layout.
    """
    rows = _safe_rows(pi, _SEG53_ATM_TABLE)
    if not rows:
        return None
    if any(
        str(row.get("ATM_TRS_TYP_CD") or "").strip() != _SEG53_SWEEP_TYPE
        for row in rows
    ):
        return None

    rows.sort(key=lambda row: (
        str(row.get("ATM_TRS_TYP_CD") or "").strip(),
        _as_int(row.get("ATM_TRS_SEQ_NBR")),
    ))
    sweep_rows = _safe_rows(pi, _SEG53_SWEEP_TABLE)
    sweep_note = _SEG53_SWEEP_NOTE
    table_error = getattr(pi, "table_error", None)
    if callable(table_error):
        error = table_error(_SEG53_SWEEP_TABLE)
        if error:
            sweep_note = (
                f"EXAMPLE DATA - {_SEG53_SWEEP_TABLE} could not be read from "
                f"DB2 ({error}). This UE142109 captured value is not live "
                "policy data."
            )

    lines: List[list] = [[
        _sep(_SEP),
        _tok("6253,", _F_SCREEN),
        _sep(_SEP),
        _tok(_policy_display(pi), _F_POLICY),
        _sep(_SEP),
    ]]

    for row in rows:
        flag_tokens = [
            _example("00000000", field, _SEG53_FLAG_NOTE)
            for field in _SEG53_FLAGS
        ]
        lines.append(_seg53_line([
            _tok("53", _F_SEG_ID),
            _tok("0089", _F_SEG_LEN),
            _tok(_SEG53_SWEEP_TYPE, "Automatic Transaction Type"),
            _tok(
                _seg66_int(row.get("ATM_TRS_SEQ_NBR")),
                "Automatic Transaction Sequence",
            ),
            *flag_tokens,
            _tok(_seg53_moyr(row.get("ATM_TRS_STR_MY_NBR")), "Start Date"),
        ]))
        lines.append(_seg53_line([
            _tok(_seg53_moyr(row.get("ATM_TRS_SUS_MY_NBR")), "Suspend Date"),
            _tok(_seg53_moyr(row.get("ATM_TRS_RST_MY_NBR")), "Restart Date"),
            _tok(_seg53_date(row.get("ATM_TRS_CEA_DT")), "Cease Date"),
            _tok(_seg53_moyr(row.get("LST_ACY_MY_NBR")), "Last Activity Date"),
            _tok(
                _seg53_moyr(row.get("NXT_SCH_ACY_MY_NBR")),
                "Next Scheduled Activity Date",
            ),
            _tok(_seg66_int(row.get("ACY_DAY_NBR")), "Activity Day"),
            _tok(
                _seg53_date(row.get("ATM_TRS_PRE_MNT_DT")),
                "Previous Maintenance Date",
            ),
            _tok(
                _seg53_fixed_text(row.get("DPT_DESK_CD"), 8),
                "Transaction Origin",
            ),
            _tok(_seg66_code(row.get("ATM_TRS_STA_CD")), "Status Code"),
        ], indent=True))
        lines.append(_seg53_line([
            _tok(_seg53_fixed_text(row.get("COS_EVT_CD"), 5), "Event Code"),
            _tok(
                _seg53_fixed_text(row.get("COS_ERR_CD"), 2),
                "Error Condition",
            ),
            _tok(_seg66_int(row.get("ATM_TRS_FQY_PER")), "Frequency"),
            _example("1", "Charge Override", _SEG53_CHARGE_NOTE),
            _example(".00", "Charge Amount", _SEG53_CHARGE_NOTE),
            *_seg53_sweep_tokens(
                _seg53_sweep_row(sweep_rows, row),
                sweep_note,
            ),
        ], indent=True))

    _append_screen_footer(lines, pi, min_lines=18)
    return lines


# ---------------------------------------------------------------------------
# Segment 56 -- Multiple Fund Control
# ---------------------------------------------------------------------------

_SEG56_GEN_TABLE = "LH_GEN_FND_RLE"
_SEG56_MVA_TABLE = "LH_MKT_VAL_ADJ_RLE"
_SEG56_FLAG_FIELDS = frozenset({
    "Flag Byte A", "Flag Byte B", "Flag Byte C", "User Flag Byte",
})
_SEG56_FLAG_NOTE = (
    "EXAMPLE DATA \u2014 this is a bit-packed flag byte. DB2 exposes selected "
    "bits, not the complete CyberLife byte shown here."
)
_SEG56_MISSING_MVA_NOTE = (
    "EXAMPLE DATA \u2014 no LH_MKT_VAL_ADJ_RLE row exists for this policy. "
    "This captured UE142109 value is not live DB2 policy data."
)


def _build_segment_56(pi, screen: dict) -> Optional[List[list]]:
    """Render the Multiple Fund Control segment from its two DB2 rule tables.

    ``LH_GEN_FND_RLE`` is the required plan-level row.  The optional
    ``LH_MKT_VAL_ADJ_RLE`` row supplies the MVA fields.  When the optional row
    is absent, the captured defaults remain visible in amber so they cannot be
    mistaken for policy data.
    """
    general_rows = _safe_rows(pi, _SEG56_GEN_TABLE)
    if not general_rows:
        return None

    general = general_rows[0]
    mva_rows = _safe_rows(pi, _SEG56_MVA_TABLE)
    mva = mva_rows[0] if mva_rows else None
    specs = {
        spec.get("name"): spec
        for spec in screen.get("field_specs", [])
        if spec.get("name")
    }
    kinds = _field_kind_map(screen)

    lines: List[list] = []
    # The captured terminal has four data lines; footer chrome is rebuilt with
    # today's date, current user, and the loaded policy's region/company.
    for template_line in screen.get("lines", [])[:4]:
        lines.append([
            _resolve_segment_56_run(
                pi, run, specs, kinds, general, mva,
            )
            for run in template_line
        ])

    _append_screen_footer(lines, pi, min_lines=18)
    return lines


def _resolve_segment_56_run(
    pi,
    run: dict,
    specs: dict,
    kinds: dict,
    general: dict,
    mva: Optional[dict],
) -> dict:
    field = run.get("field")
    sample = run.get("text", "")
    if not field:
        return _sep(sample)

    if field == _F_SCREEN:
        return _tok("6256,", field)
    if field == _F_POLICY:
        return _tok(_policy_display(pi), field)
    if field == _F_SEG_ID:
        return _tok("56", field)
    if field == _F_SEG_LEN:
        return _tok("0098", field)
    if field in _SEG56_FLAG_FIELDS:
        return _example(sample, field, _SEG56_FLAG_NOTE)

    spec = specs.get(field) or {}
    db2 = spec.get("db2")
    if not db2 or "." not in db2:
        return _example(_example_text(sample), field)

    table, column = db2.split(".", 1)
    if table == _SEG56_GEN_TABLE:
        row = general
    elif table == _SEG56_MVA_TABLE:
        row = mva
    else:
        row = None

    if row is None:
        note = (
            _SEG56_MISSING_MVA_NOTE
            if table == _SEG56_MVA_TABLE
            else _EXAMPLE_NOTE
        )
        return _example(_example_text(sample), field, note)

    value = row.get(column)
    text = _format_like(sample, value, kinds.get(field))
    if (value is None or str(value).strip() == "") and sample and not sample.strip():
        text = sample
    return _tok(text, field)


# ---------------------------------------------------------------------------
# Segment 59 -- TAMRA, Type 1
# ---------------------------------------------------------------------------

_SEG59_PERIOD_TABLE = "LH_TAMRA_7_PY_PER"
_SEG59_YEAR_TABLE = "LH_TAMRA_7_PY_YR"
_SEG59_INDENT = " " * 12
_SEG59_FLAG_A_COLUMNS = (
    "GDF_SVPY_TES_IND",
    "GDF_GDL_PRM_IND",
    "MAT_CHG_IND",
    "SVPY_PRM_CLC_IND",
    "REVERSE_TO_ISS_IND",
    "OVR_MEC_IND",
)
_SEG59_FLAG_NOTE = (
    "EXAMPLE DATA \u2014 this reserved flag byte has no DB2 source for this "
    "policy."
)
_SEG59_MISSING_YEAR_NOTE = (
    "EXAMPLE DATA \u2014 the expected TAMRA year row is missing from DB2 for "
    "this policy."
)


def _seg59_flag_a(row: dict) -> str:
    """Rebuild documented Flag Byte A bits 0-5; bits 6-7 are reserved zeros."""
    bits = [
        "1" if str(row.get(column) or "").strip() == "1" else "0"
        for column in _SEG59_FLAG_A_COLUMNS
    ]
    return "".join(bits) + "00"


def _seg59_line(tokens: list[dict], *, indent: bool = False) -> list[dict]:
    line = [_sep(_SEG59_INDENT if indent else _SEP)]
    for index, token in enumerate(tokens):
        if index:
            line.append(_sep(_SEP))
        line.append(token)
    line.append(_sep(_SEP))
    return line


def _seg59_value(row: dict, column: str, field: str, fmt: str) -> dict:
    value = row.get(column)
    if fmt == "date":
        text = _seg66_date(value)
    elif fmt == "dec2":
        text = _decimal_display(value, 2)
    elif fmt == "dec3":
        text = _decimal_display(value, 3)
    elif fmt == "int":
        text = _seg66_int(value)
    else:
        text = _seg66_code(value)
    return _tok(text, field)


def _build_segment_59(pi) -> Optional[List[list]]:
    """Render the live Type 1 TAMRA record and its seven accumulation years.

    CyberDoc defines a separate Type 2 redefine for special issue-age search
    keys. That variant is not emitted without verified live data; a policy with
    no Type 1 row falls back to the clearly labelled captured reference.
    """
    period_rows = _safe_rows(pi, _SEG59_PERIOD_TABLE)
    if not period_rows:
        return None
    period = period_rows[0]

    year_rows = {
        _as_int(row.get("SVPY_YR_SEQ_NBR")): row
        for row in _safe_rows(pi, _SEG59_YEAR_TABLE)
        if 1 <= _as_int(row.get("SVPY_YR_SEQ_NBR")) <= 7
    }

    lines: List[list] = [[
        _sep(_SEP),
        _tok("6259,", _F_SCREEN),
        _sep(_SEP),
        _tok(_policy_display(pi), _F_POLICY),
        _sep(_SEP),
    ]]

    lines.append(_seg59_line([
        _tok("59", _F_SEG_ID),
        _tok("0191", _F_SEG_LEN),
        _tok(_seg59_flag_a(period), "Flag Byte A"),
        _example("00000000", "Flag Byte B", _SEG59_FLAG_NOTE),
        _example("00000000", "Flag Byte U", _SEG59_FLAG_NOTE),
        _tok("1", "Segment Type"),
        _seg59_value(period, "MEC_STA_CD", "MEC Indicator", "code"),
        _seg59_value(
            period, "TAMRA_SST_RT_CD", "Rated Rates Indicator", "code",
        ),
        _seg59_value(period, "TAMRA_MEC_EFF_DT", "MEC Date", "date"),
        _seg59_value(
            period, "SVPY_PER_STR_DT", "7-Pay Period Start Date", "date",
        ),
        _seg59_value(
            period, "SVPY_NXT_CHG_DT", "7-Pay Next Change Date", "date",
        ),
    ]))

    period_tokens = [
        _seg59_value(
            period, "SVPY_LVL_PRM_AMT", "7-Pay Level Premium", "dec2",
        ),
        _seg59_value(
            period, "SVPY_WDW_PRM_AMT", "7-Pay Window Premiums", "dec2",
        ),
        _seg59_value(
            period, "TAMRA_ITS_RT", "7-Pay Current Interest Rate", "dec3",
        ),
        _seg59_value(
            period, "TAMRA_GUA_PER", "7-Pay Guaranteed Period", "int",
        ),
        _seg59_value(
            period,
            "SVPY_BEG_FCE_AMT",
            "7-Pay Beginning Specified or Face Amount",
            "dec2",
        ),
        _seg59_value(
            period, "SVPY_BEG_CSV_AMT", "7-Pay Beginning Cash Value", "dec2",
        ),
        _seg59_value(
            period,
            "GDF_DTH_BNF_1_AMT",
            "Death Benefit as of June 20, 1988",
            "dec2",
        ),
        _seg59_value(
            period,
            "GDF_DTH_BNF_2_AMT",
            "Death Benefit as of October 20, 1988",
            "dec2",
        ),
    ]

    accumulation_tokens: list[dict] = []
    for year in range(1, 8):
        row = year_rows.get(year)
        paid_field = f"7-Pay Premiums Paid [{year}]"
        withdrawal_field = f"7-Pay Withdrawals [{year}]"
        if row is None:
            accumulation_tokens.extend([
                _example(".00", paid_field, _SEG59_MISSING_YEAR_NOTE),
                _example(".00", withdrawal_field, _SEG59_MISSING_YEAR_NOTE),
            ])
        else:
            accumulation_tokens.extend([
                _seg59_value(row, "SVPY_PRM_PAY_AMT", paid_field, "dec2"),
                _seg59_value(row, "SVPY_WTD_AMT", withdrawal_field, "dec2"),
            ])

    # The U0633187 terminal capture places years 1-2 after the period fields,
    # then wraps years 3-7 and the 1035 counter to the final data line.
    lines.append(_seg59_line([
        *period_tokens,
        *accumulation_tokens[:4],
    ], indent=True))
    lines.append(_seg59_line([
        *accumulation_tokens[4:],
        _seg59_value(
            period,
            "XCG_1035_PMT_QTY",
            "1035 Exchange Information",
            "int",
        ),
    ], indent=True))

    _append_screen_footer(lines, pi, min_lines=18)
    return lines


# ---------------------------------------------------------------------------
# Segment 58 -- Target Premiums
# ---------------------------------------------------------------------------

def _build_segment_58(pi) -> List[list]:
    entries = _collect_target_entries(pi)
    n = len(entries)
    seg_len = 6 + 15 * n

    lines: List[list] = []

    # Line 1: screen name + policy number.
    lines.append([
        _sep(_SEP),
        _tok("6258,", _F_SCREEN),
        _sep(_SEP),
        _tok(_policy_display(pi), _F_POLICY),
        _sep(_SEP),
    ])

    # Line 2: the 6-byte header, then entries begin flowing after it.
    header = [
        _sep(_SEP),
        _tok("58", _F_SEG_ID),
        _sep(_SEP),
        _tok(f"{seg_len:04d}", _F_SEG_LEN),
        _sep(_SEP),
        _tok(str(n), _F_NUM_ENTRIES),
        _sep(_SEP),
    ]
    lines.extend(_layout_entries(entries, header))

    _append_screen_footer(lines, pi)
    return lines


def _append_screen_footer(lines: List[list], pi, min_lines: int = 20) -> None:
    """Pad to a full terminal and append the CK620 completion footer.

    Shared by every segment so live screens end exactly like the mainframe:
    a current date + user line and a ``CK620 DISPLAY COMPLETE`` region line.
    """
    used = len(lines)
    for _ in range(max(1, min_lines - used)):
        lines.append([_sep(" ")])

    lines.append([
        _sep(_SEP),
        _sep(" " * 66),
        _tok(_today_mmddyy(), _F_CUR_DATE),
        _sep(_SEP),
        _tok(_user_id(), _F_USER),
        _sep(" "),
    ])
    lines.append([
        _sep(_SEP),
        _sep("CK620 DISPLAY COMPLETE".ljust(58)),
        _tok(_region_company(pi), _F_REGION),
        _sep(_SEP),
    ])
    lines.append([_sep(" ")])


def _collect_target_entries(pi) -> List[dict]:
    """Gather + normalize the three target tables into ordered entries."""
    entries: List[dict] = []

    for row in _safe_rows(pi, "LH_COM_TARGET"):
        entries.append(_entry(row, phase_field="AGT_COM_PHA_NBR",
                              rule_field="TAR_DT_RLE_CD"))
    for row in _safe_rows(pi, "LH_COV_TARGET"):
        entries.append(_entry(row, phase_field="COV_PHA_NBR",
                              rule_field="PRM_RLE_CD"))
    for row in _safe_rows(pi, "LH_POL_TARGET"):
        entries.append(_entry(row, phase_field=None, rule_field="PRM_RLE_CD"))

    # CyberLife lays the segment out by SEG_IDX_NBR across all three sources.
    entries.sort(key=lambda e: e["idx"])
    return entries


def _entry(row: dict, phase_field: Optional[str], rule_field: str) -> dict:
    return {
        "idx": _as_int(row.get("SEG_IDX_NBR"), default=0),
        "code": str(row.get("TAR_TYP_CD") or "").strip(),
        "phase": "0" if phase_field is None
                 else str(_as_int(row.get(phase_field), default=0)),
        "rule": _rule_display(row.get(rule_field)),
        "date": _date_display(row.get("TAR_DT")),
        "amount": _amount_display(row.get("TAR_PRM_AMT")),
    }


def _layout_entries(entries: List[dict], header: list) -> List[list]:
    """Flow entries two-per-line; the first line starts after *header*."""
    lines: List[list] = []
    current = list(header)
    per_line = 0
    for entry in entries:
        current.extend(_entry_runs(entry))
        per_line += 1
        if per_line >= _ENTRIES_PER_LINE:
            lines.append(current)
            current = [_sep(_INDENT)]
            per_line = 0
    # Flush a partial trailing line, or the header line when there are no
    # entries at all.
    if per_line > 0 or not lines:
        lines.append(current)
    return lines


def _entry_runs(entry: dict) -> list:
    return [
        {**_tok(entry["code"].ljust(2), _F_CODE), "note": _target_code_note(entry["code"])},
        _sep(_SEP),
        _example(_FLAG_PLACEHOLDER, _F_FLAG),
        _sep(_SEP),
        _tok(entry["phase"], _F_PHASE),
        _sep(_SEP),
        _tok(entry["rule"], _F_RULE),
        _sep(_SEP),
        _tok(entry["date"], _F_DATE),
        _sep(_SEP),
        _tok(entry["amount"], _F_AMOUNT),
        _sep(_SEP),
    ]


# ---------------------------------------------------------------------------
# Segment 66 -- Advanced Product (screen 6266)
# ---------------------------------------------------------------------------
# Segment 66 is present only for non-traditional products (UL / IUL / VUL) and
# maps almost 1:1 onto a single ``LH_NON_TRD_POL`` row.  A handful of adjacent
# byte-fields are shown by the mainframe as one concatenated display token (e.g.
# the six Full-Surrender subfields render as ``0N15601``); those are modelled as
# consecutive runs with no separator between them (``group_start=False``).
#
# Each entry is ``(field_name, db2_column | None, fmt, group_start, line_break,
# example_text)``:
#   * ``db2_column``  -- read from the LH_NON_TRD_POL row; ``None`` => the value
#                        is not stored in DB2, so *example_text* is shown amber.
#   * ``fmt``         -- code (raw, keep leading zeros) / int (drop trailing .00)
#                        / dec2 / dec3 / date (MM/DD/YYYY; year>=9999 or blank ->
#                        ``**/**/****``).
#   * ``group_start`` -- ``True`` => a 2-space gap precedes this token;
#                        ``False`` => it abuts the previous token (display group).
#   * ``line_break``  -- ``True`` => this token starts a new (indented) line.
# The mapping is value-verified token-by-token against the real 6266 screen for
# U0361148 (see ``tools/policyrecord/probe_segment66.py``).

_SEG66_TABLE = "LH_NON_TRD_POL"
_SEG66_NULL_DATE = "**/**/****"
_SEG66_INDENT = " " * 8
_SEG66_FLAG_NOTE = (
    "EXAMPLE DATA \u2014 this is a bit-packed flag byte with no single DB2 "
    "column; it is shown as zero bytes for illustration only."
)
_SEG66_FLAG_BYTES = (
    "Flag Byte A", "Flag Byte B", "Flag Byte C",
    "Flag Byte D", "Flag Byte E", "User Flag Byte",
)

# (name, db2_column | None, fmt, group_start, line_break, example_text)
_SEG66_FIELDS: List[Tuple[str, Optional[str], str, bool, bool, str]] = [
    # --- Header line tail (follows the seg id/len + 6 flag bytes) ---
    ("TEFRA/DEFRA Code", "TFDF_CD", "code", True, False, ""),
    ("Death Benefit Plan Option", "DTH_BNF_PLN_OPT_CD", "code", True, False, ""),
    ("Decrease. LIFO/FIFO", "DCA_ORD_RLE_CD", "code", True, False, ""),
    ("Decrease. Plan Option Rule", "DCA_PLN_OPT_RLE_CD", "code", False, False, ""),
    ("Increase. LIFO/FIFO", "ICE_ORD_RLE_CD", "code", True, False, ""),
    ("Increase. Plan Option Rule", "ICE_PLN_OPT_RLE_CD", "code", False, False, ""),

    # --- Line: Maturity Date ... Late Pay Acceptance Period ---
    ("Maturity Date", "MT_DT", "date", True, True, ""),
    ("Minimum Cash Value Balance. Amount", "MIN_CSV_BAL_AMT", "int", True, False, ""),
    ("Minimum Cash Value Balance. Interest Rate", "MIN_CSV_BAL_ITS_RT", "dec3", True, False, ""),
    ("Policy Guaranteed Interest Rate", "POL_GUA_ITS_RT", "dec3", True, False, ""),
    ("Cash Value Expense Charges. Frequency", "CSV_XPN_FQY_CD", "code", True, False, ""),
    ("Cash Value Expense Charges. Basis", "CSV_XPN_BSS_CD", "code", True, False, ""),
    ("Cash Value Expense Charges. Table", "CSV_XPN_TBL_CD", "code", True, False, ""),
    ("Cash Value Expense Charges. Rule 1", "CSV_XPN_RLE_1_CD", "code", True, False, ""),
    ("Cash Value Expense Charges. Rule 2", "CSV_XPN_RLE_2_CD", "code", False, False, ""),
    ("Cash Value Expense Charges. Rule 3", "CSV_XPN_RLE_3_CD", "code", False, False, ""),
    ("Cost of Insurance. Net Amount at Risk Rule", "CINS_NAR_RLE_CD", "code", True, False, ""),
    ("Cost of Insurance. Guarantee. Rate Period Code", "CINS_GUA_RT_PER_CD", "code", True, False, ""),
    ("Cost of Insurance. Guarantee. Rate Period", "CINS_GUA_RT_PER", "int", True, False, ""),
    ("Cost of Insurance. Guarantee. End Date", "CINS_GUA_END_DT", "date", True, False, ""),
    ("Cost of Insurance. Charge Frequency", "CINS_CRG_FQY_PER", "int", True, False, ""),
    ("Cost of Insurance. Rate Calculation Rule", "CINS_RT_CLC_RLE_CD", "code", True, False, ""),
    ("Cost of Insurance. Charged Through Date", "CINS_CRG_THRU_DT", "date", True, False, ""),
    ("Premiums. Received Interest Rule", "PRM_REC_ITS_RLE_CD", "code", True, False, ""),
    ("Premiums. Late Pay Acceptance Period", "PRM_GRA_PER", "int", True, False, ""),

    # --- Line: Payment Freeze Period ... Minimum Sum Insured ---
    ("Premiums. Payment Freeze Period", "PRM_FREEZE_PER", "int", True, True, ""),
    ("Premiums. Loads. Table", "PRM_LD_TBL_CD", "code", True, False, ""),
    ("Premiums. Loads. Rule 1", "PRM_LD_RLE_1_CD", "code", True, False, ""),
    ("Premiums. Loads. Rule 2", "PRM_LD_RLE_2_CD", "code", False, False, ""),
    ("Premiums. Loads. Rule 3", "PRM_LD_RLE_3_CD", "code", False, False, ""),
    ("Premiums. Additional Payments. Number in One Year", "MAX_ADD_PMT_NBR", "int", True, False, ""),
    ("Premiums. Additional Payments. Debit", "ADD_PMT_DBT_CD", "code", True, False, ""),
    ("Premiums. Additional Payments. Minimum Amount", "ADD_PMT_MIN_AMT", "int", True, False, ""),
    ("Premiums. Additional Payments. Maximum Amount", "ADD_PMT_MAX_AMT", "int", True, False, ""),
    ("Premiums. Additional Payments. Maximum Rule", "ADD_PMT_MAX_CD", "code", True, False, ""),
    ("Premiums. Premium Tax Indicator", "PRM_TAX_CD", "code", True, False, ""),
    ("Billing. Plan Option", "BIL_PLN_OPT_CD", "code", True, False, ""),
    ("Billing. Status", "BIL_STA_CD", "code", True, False, ""),
    ("Billing. Commence Date", "BIL_COMMENCE_DT", "date", True, False, ""),
    ("Reinstatement Rule", "REN_RLE_CD", "code", True, False, ""),
    ("Commissions Rule", "COM_RLE_CD", "code", True, False, ""),
    ("Corridor. Rule", "CDR_RLE_CD", "code", True, False, ""),
    ("Corridor. Amount", "CDR_AMT", "int", True, False, ""),
    ("Corridor. Percent", "CDR_PCT", "dec3", True, False, ""),
    ("Minimum Sum Insured Amount", "MIN_SUM_ISU_AMT", "int", True, False, ""),

    # --- Line: Net Amount at Risk ... Preferred Policy Year Available ---
    ("Net Amount at Risk", "NAR_AMT", "dec2", True, True, ""),
    ("Death Benefit Amount", "DEATH_BEN_AMT", "dec2", True, False, ""),
    ("Annual Statement Frequency", "ANN_STT_FQY_PER", "int", True, False, ""),
    ("Confirmation Frequency", "CNFM_FQY_PER", "int", True, False, ""),
    ("Full Surrender. Allow", "FUL_SRD_ALW_CD", "code", True, False, ""),
    ("Full Surrender. Pro Rata Indicator", "FUL_SRD_PTA_IND", "code", False, False, ""),
    ("Full Surrender. Charge Table", "FUL_SRD_CRG_TBL_CD", "code", False, False, ""),
    ("Full Surrender. First Charge", "FUL_SRD_FST_CRG_CD", "code", False, False, ""),
    ("Full Surrender. Second Charge", "FUL_SRD_2ND_CRG_CD", "code", False, False, ""),
    ("Full Surrender. Free Look Rule", "FRE_LK_SRD_RLE_CD", "code", False, False, ""),
    ("Partial Surrender. Allow", "PAT_SRD_ALW_CD", "code", True, False, ""),
    ("Partial Surrender. Charge Table", "PAT_SRD_CRG_TBL_CD", "code", True, False, ""),
    ("Partial Surrender. First Charge", "PAT_SRD_FST_CRG_CD", "code", False, False, ""),
    ("Partial Surrender. Second Charge", "PAT_SRD_2ND_CRG_CD", "code", False, False, ""),
    ("Partial Surrender. Minimum Amount", "MIN_PAT_SRD_AMT", "int", True, False, ""),
    ("Partial Surrender. Number in One Year", "PAT_SRD_MAX_NBR", "int", True, False, ""),
    ("Partial Surrender. Balance Rule", "PAT_SRD_MIN_RLE_CD", "code", True, False, ""),
    ("Partial Surrender. Balance Months", "PAT_SRD_MIN_MO_NBR", "int", True, False, ""),
    ("Partial Surrender. Balance Amount", "PAT_SRD_BAL_AMT", "int", True, False, ""),
    ("Loans. Interest Disbursement Rule", "LN_ITS_DSB_RLE_CD", "code", True, False, ""),
    ("Loans. Credit Interest Rate Code", "LN_CRE_ITS_RT_CD", "code", True, False, ""),
    ("Loans. Credit Interest Rate", "LN_CRE_ITS_RT", "dec3", True, False, ""),
    ("Loans. Minimum Balance Table", "LN_MIN_BAL_TBL_CD", "code", True, False, ""),
    ("Loans. Minimum Balance Rule", "LN_MIN_BAL_RLE_CD", "code", False, False, ""),
    ("Loans. Minimum Duration", "LN_MIN_DUR", "int", True, False, ""),
    ("Loans. Minimum Amount", "LN_MIN_AMT", "int", True, False, ""),
    ("Loans. Preferred Loan Option", "PRF_LN_OPT_CD", "code", True, False, ""),
    ("Loans. Preferred Amount Percent", "PRF_LN_AMT_PCT", "int", True, False, ""),
    ("Loans. Preferred Policy Year Available", "PRF_LN_YR_AVA_NBR", "int", True, False, ""),

    # --- Line: Preferred Interest Charge Rate ... Archive History Durations ---
    ("Loans. Preferred Interest Charge Rate", "PRF_LN_ITS_CRG_RT", "dec3", True, True, ""),
    ("Loans. Preferred Interest Credit Code", "PRF_LN_ITS_CRE_CD", "code", True, False, ""),
    ("Loans. Preferred Interest Credit Rate", "PRF_LN_ITS_CRE_RT", "dec3", True, False, ""),
    ("Last Monthly Duration Processed", "LST_MO_DUR_PRC_NBR", "int", True, False, ""),
    ("Grace Period. Days", "GRA_PER_DAY_NBR", "int", True, False, ""),
    ("Grace Period. Interest Rate Code", "GRA_PER_ITS_RT_CD", "code", True, False, ""),
    ("Grace Period. Credit Rate", "GRA_PER_CRE_RT", "dec3", True, False, ""),
    ("Grace Period. Threshold Rule", "GRA_THD_RLE_CD", "code", True, False, ""),
    ("Grace Period. Expiration Date", "GRA_PER_EXP_DT", "date", True, False, ""),
    ("Last Statement Date", "LST_STT_DT", "date", True, False, ""),
    ("Last Statement Type", "LST_STT_TYP_CD", "code", True, False, ""),
    ("Process Back Date", "PRC_BACK_DT", "date", True, False, ""),
    ("Last Monthly Duration Number", "LST_MO_DUR_NBR", "int", True, False, ""),
    ("Archive History Durations", "ARCH_HST_DUR_NBR", "int", True, False, ""),

    # --- Line: Reward Type ... Reserved ---
    ("Policyowner Rewards. Reward Type", "REWARD_TYP_CD", "code", True, True, ""),
    ("Policyowner Rewards. Table Argument", "REWARD_TBL_AGU_CD", "code", True, False, ""),
    ("Prospective Bonus. Restriction Code", "PRO_BNS_RS_CD", "code", True, False, ""),
    ("Prospective Bonus. Restriction Date", "PRO_BNS_RS_DT", "date", True, False, ""),
    ("Retrospective Bonus. Restriction Code", "RETRO_BNS_RS_CD", "code", True, False, ""),
    ("Retrospective Bonus. Restriction Date", "RETRO_BNS_RS_DT", "date", True, False, ""),
    ("Current Rates Rule", "GLP_CUR_RT_RLE_CD", "code", True, False, ""),
    ("Threshold Amount", "THD_AMT", "dec2", True, False, ""),
    ("SC Free Window. Withdrawal Rule", None, "code", True, False, "0"),
    ("SC Free Window. Number of Days", None, "int", True, False, "0"),
    ("Freeze Net Amount at Risk", None, "code", True, False, "0"),
    ("Reduction Free Partial Surrender Calc", None, "code", True, False, "0"),
    ("Guaranteed Accumulation Value Rule", "GAV_RULE_CODE", "code", True, False, ""),
    ("Reserved Decrease Rule Code", None, "code", True, False, "1"),
]


def _seg66_date(value) -> str:
    """MM/DD/YYYY, with blank/null and the high-date sentinel shown ``**/**/****``."""
    parts = _date_parts(value)
    if parts is None:
        return _SEG66_NULL_DATE
    month, day, year = parts
    if year >= 9999 or year <= 1:
        return _SEG66_NULL_DATE
    return f"{month:02d}/{day:02d}/{year}"


def _seg66_int(value) -> str:
    """Integer display -- strips a trailing ``.00`` (blank/null -> ``0``)."""
    if value is None or str(value).strip() == "":
        return "0"
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value).strip()
    if d == d.to_integral_value():
        return str(int(d))
    return f"{d}"


def _seg66_code(value) -> str:
    """Raw code -- trimmed but leading zeros preserved (``09``, ``L0``, ``00``)."""
    return "" if value is None else str(value).strip()


def _seg66_format(value, fmt: str) -> str:
    if fmt == "date":
        return _seg66_date(value)
    if fmt == "int":
        return _seg66_int(value)
    if fmt == "dec2":
        return _decimal_display(value, 2)
    if fmt == "dec3":
        return _decimal_display(value, 3)
    return _seg66_code(value)


def _build_segment_66(pi) -> Optional[List[list]]:
    """Render Segment 66 live from ``LH_NON_TRD_POL``.

    Returns ``None`` for policies with no advanced-product record (traditional
    products), so the viewer falls back to the captured-reference screen.
    """
    rows = _safe_rows(pi, _SEG66_TABLE)
    if not rows:
        return None
    row = rows[0]

    lines: List[list] = []

    # Line 1: screen name + policy number.
    lines.append([
        _sep(_SEP),
        _tok("6266,", _F_SCREEN),
        _sep(_SEP),
        _tok(_policy_display(pi), _F_POLICY),
        _sep(_SEP),
    ])

    # Line 2 begins with the header (seg id/length + six bit-packed flag bytes),
    # then the body fields flow on from there.
    line = [
        _sep(_SEP),
        _tok("66", _F_SEG_ID),
        _sep(_SEP),
        _tok("0247", _F_SEG_LEN),
    ]
    for flag in _SEG66_FLAG_BYTES:
        line.append(_sep(_SEP))
        line.append(_example("00000000", flag, note=_SEG66_FLAG_NOTE))

    for name, col, fmt, group_start, line_break, ex in _SEG66_FIELDS:
        if line_break:
            lines.append(line)
            line = [_sep(_SEG66_INDENT)]
        elif group_start:
            line.append(_sep(_SEP))
        if col is None:
            line.append(_example(ex, name))
        else:
            line.append(_tok(_seg66_format(row.get(col), fmt), name))
    lines.append(line)

    _append_screen_footer(lines, pi)
    return lines


# ---------------------------------------------------------------------------
# Segment 02 -- Coverage (screen 6202)
# ---------------------------------------------------------------------------
# Unlike the single-record segments, screen 6202 REPEATS once per coverage phase
# (a row of ``LH_COV_PHA``): a base coverage plus any riders.  Each block is the
# header (``02 0220`` + four bit-packed flag bytes) followed by ~95 coverage
# fields flowing across five terminal lines.
#
# The field order/mapping lives in ``seg_02_coverage_fields.json`` (generated by
# ``tools/policyrecord/gen_seg02_fields.py`` from the record layout, with every COBOL->DB2
# resolved through the authoritative Translation sheet).  Each entry carries a
# ``role``:
#   * ``chrome``   -- the constant segment id / length.
#   * ``flag``     -- a bit-packed flag byte (no single DB2 column) -> amber example.
#   * ``data``     -- a live ``LH_COV_PHA`` column, formatted by its CyberDoc kind.
#   * ``example``  -- a display-only field with no DB2 source (Participation Type,
#                     Guarantee Option, filler); skipped so we never fabricate a
#                     specific value in the middle of real data.
#
# Every emitted token carries its own field name, so a value always hovers to the
# right field even where the mainframe collapses blank fields.  The base plan's
# ``Valuation Code: Subseries`` abuts the ``Valuation Code: Base`` token (the
# mainframe shows e.g. ``35D`` + ``MP`` as one visual ``35DMP``).

_SEG02_TABLE = "LH_COV_PHA"
_SEG02_INDENT = " " * 12  # continuation-line indent (matches the sample screen)
_SEG02_CONCAT_FIELDS = frozenset({"Valuation Code: Subseries"})
_SEG02_FLAG_NOTE = (
    "EXAMPLE DATA \u2014 this is a bit-packed flag byte with no single DB2 "
    "column; it is shown as zero bytes for illustration only."
)

_seg02_fields_cache: Optional[list] = None


def _seg02_fields() -> list:
    """Load (and cache) the ordered Segment 02 coverage-field mapping."""
    global _seg02_fields_cache
    if _seg02_fields_cache is None:
        try:
            with open(_SEG02_FIELDS_PATH, "r", encoding="utf-8") as fh:
                _seg02_fields_cache = json.load(fh)
        except (OSError, ValueError):
            _seg02_fields_cache = []
    return _seg02_fields_cache


def _seg02_format(value, kind: Optional[str]) -> str:
    """Format a coverage value by its CyberDoc *kind* (decimal:N / date / int / char)."""
    k = kind or "char"
    if k.startswith("decimal:"):
        try:
            decimals = int(k.split(":", 1)[1])
        except ValueError:
            decimals = 2
        return _decimal_display(value, decimals)
    if k == "date":
        return _seg66_date(value)
    if k in ("int", "packed_num"):
        return _seg66_int(value)
    return _seg66_code(value)


def _build_segment_02(pi) -> Optional[List[list]]:
    """Render Segment 02 (Coverage) live -- one block per ``LH_COV_PHA`` phase.

    Returns ``None`` when the policy has no coverage rows, so the viewer falls
    back to the captured-reference screen.
    """
    rows = _safe_rows(pi, _SEG02_TABLE)
    if not rows:
        return None
    fields = _seg02_fields()
    if not fields:
        return None

    lines: List[list] = []

    # Top line (once): screen name + policy number.
    lines.append([
        _sep(_SEP),
        _tok("6202,", _F_SCREEN),
        _sep(_SEP),
        _tok(_policy_display(pi), _F_POLICY),
        _sep(_SEP),
    ])

    for row in rows:
        line: list = [_sep(_SEP)]
        prev_emitted = False   # a value was placed since the last line break
        last_name = None       # name of the most recently emitted token
        for field in fields:
            name = field["name"]
            role = field.get("role")

            if field.get("line_break"):
                lines.append(line)
                line = [_sep(_SEG02_INDENT)]
                prev_emitted = False
                last_name = None

            if role == "chrome":
                run = _tok(field.get("const", ""), name)
            elif role == "flag":
                run = _example(field.get("const", "00000000"), name,
                               note=_SEG02_FLAG_NOTE)
            elif role == "data":
                col = field["db2"].split(".", 1)[1]
                text = _seg02_format(row.get(col), field.get("kind"))
                if text == "":
                    # Blank char field -- the mainframe collapses it.
                    continue
                if field.get("blank_if_zero") and text.strip("0.") == "":
                    # A zero here means "not applicable" -- shown blank on screen.
                    continue
                run = _tok(text, name)
            else:
                # Display-only field with no DB2 source -- skip (never fabricate).
                continue

            # The base plan's subseries abuts its base token (e.g. 35D + MP).
            concat = (name in _SEG02_CONCAT_FIELDS
                      and last_name == "Valuation Code: Base")
            if prev_emitted and not concat:
                line.append(_sep(_SEP))
            line.append(run)
            prev_emitted = True
            last_name = name
        lines.append(line)

    _append_screen_footer(lines, pi)
    return lines


# ---------------------------------------------------------------------------
# Templated segment (e.g. Segment 01 -- Basic Policy)
# ---------------------------------------------------------------------------

def _build_templated_segment(pi, segment: str, screen: dict) -> List[list]:
    """Render a ``template`` screen live from DB2.

    The screen's ``lines`` carry the authentic mainframe layout: chrome tokens
    (screen name, policy number, segment id/length, footer) tagged with a
    ``role``; value tokens carrying a ``db2`` source and a sample ``text``; and
    inert spacing runs.  We walk the template verbatim -- preserving its exact
    line breaks and spacing -- and substitute each token:

    * **chrome**   -- filled from the live policy (screen name ``62<seg>,``,
                      policy number, region/company, today's date, user id) or
                      kept as-is (segment id/length).
    * **real**     -- the token's ``db2`` source is read via
                      ``pi.data_item(table, column)`` and formatted like the
                      sample value (date / decimal / code), rendered in green.
    * **example**  -- the token has no ``db2`` source (packed flag bytes, extract
                      date, etc.); the sample value is shown in amber with a
                      "not real data" tooltip warning.
    """
    lines: List[list] = []
    kinds = _field_kind_map(screen)
    for tmpl_line in screen["lines"]:
        lines.append([_resolve_template_run(pi, segment, run, kinds) for run in tmpl_line])
    return lines


def _resolve_template_run(pi, segment: str, run: dict, kinds: dict) -> dict:
    field = run.get("field")
    if not field:
        return _sep(run.get("text", ""))

    role = run.get("role")
    if role:
        return _resolve_chrome(pi, segment, role, run)

    db2 = run.get("db2")
    if db2:
        kind = kinds.get(field)
        return _tok(_live_formatted(pi, db2, run.get("text", ""), kind), field)
    # No DB2 source -> illustrative example data (amber + warning tooltip).
    return _example(_example_text(run.get("text", "")), field)


def _resolve_chrome(pi, segment: str, role: str, run: dict) -> dict:
    field = run.get("field")
    if role == "screen_name":
        return _tok(f"62{segment},", field)
    if role == "policy":
        return _tok(_policy_display(pi), field)
    if role == "seg_id":
        return _tok(segment, field)
    if role == "current_date":
        return _tok(_today_mmddyy(), field)
    if role == "user":
        return _tok(_user_id(), field)
    if role == "region":
        return _tok(_region_company(pi), field)
    # seg_len (and any other structural chrome) keeps the template text.
    return _tok(run.get("text", ""), field)


def _live_formatted(pi, db2: str, sample: str, kind: Optional[str] = None) -> str:
    """Read *db2* (``TABLE.COLUMN``) live and format it.

    *kind* is the field's CyberDoc display class (e.g. ``date`` vs
    ``date_packed``); when omitted the format is inferred from *sample*.
    """
    table, _, column = db2.partition(".")
    value = None
    if column:
        try:
            value = pi.data_item(table.strip(), column.strip())
        except Exception:
            value = None
    return _format_like(sample, value, kind)


def _example_text(sample: str) -> str:
    """A tidy example value for a no-DB2 field, based on the sample token.

    Dates are normalised to the mainframe's null date so a stray archive value
    never looks like a real one; other samples (flag-byte bit patterns, codes)
    pass through unchanged.
    """
    fmt, _ = _infer_fmt(sample)
    if fmt == "date":
        return "00/00/1900"
    return sample


# ---------------------------------------------------------------------------
# Value formatting helpers
# ---------------------------------------------------------------------------

def _packed_decimal(value, digits: int, decimals: int = 0) -> str:
    """Render COMP-3 digits and the C/D sign nibble without rounding data."""
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid packed decimal: {value!r}") from exc
    if not number.is_finite():
        raise ValueError(f"Non-finite packed decimal: {value!r}")
    scaled = abs(number) * (10 ** decimals)
    if scaled != scaled.to_integral_value() or scaled >= 10 ** digits:
        raise ValueError(
            f"{value!r} does not fit {digits} packed digits with {decimals} decimals"
        )
    sign = "D" if number < 0 else "C"
    return f"{int(scaled):0{digits}d}{sign}"


_DATE_RE = re.compile(r"^(?:\d{2}/\d{2}/\d{4}|\*+/\*+/\*+)$")
_DECIMAL_RE = re.compile(r"^\d*\.(\d+)$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T].*)?$")


def _looks_like_iso_date(value) -> bool:
    """True when *value* is an ISO ``YYYY-MM-DD`` date string from DB2."""
    return isinstance(value, str) and bool(_ISO_DATE_RE.match(value.strip()))


def _norm_null_date(text: str) -> str:
    """Show the mainframe's null date for the ``12/31/9999`` high-date sentinel.

    CyberLife screen 6201 renders the "no scheduled date" sentinel that DB2
    stores as ``12/31/9999`` using its null-date form ``00/00/1900``.
    """
    return "00/00/1900" if text == "12/31/9999" else text


def _infer_fmt(sample: str):
    """Infer a value's display format from its sample text.

    Returns ``(kind, decimals)`` where *kind* is ``"date"``, ``"decimal"`` or
    ``"code"`` and *decimals* is the fractional-digit count for decimals.
    """
    s = (sample or "").strip()
    if _DATE_RE.match(s):
        return "date", 0
    m = _DECIMAL_RE.match(s)
    if m:
        return "decimal", len(m.group(1))
    return "code", 0


def _format_like(sample: str, value, kind: Optional[str] = None) -> str:
    """Format a live DB2 *value* using the format implied by *sample*.

    *kind* is the field's authoritative CyberDoc display class.  It only alters
    date rendering: most dates show slashed ``MM/DD/YYYY``, but a handful of
    "activity" dates are stored as a packed ``MMDDYY`` integer and shown
    unslashed on the mainframe (e.g. Accounting/Billing Date -> ``71026``).
    Non-date values keep the sample-inferred format.
    """
    # A real date value always renders as a date, even when the sample token was
    # null in the archive (so format inference couldn't tell it was a date).
    if isinstance(value, (datetime, date)) or _looks_like_iso_date(value):
        if kind in _PACKED_DATE_KINDS:
            return _packed_mmddyy(value)
        return _norm_null_date(_date_display(value))

    kind_s, decimals = _infer_fmt(sample)
    if kind_s == "date":
        text = _date_display(value)
        return _norm_null_date(text) if text else "00/00/1900"
    if kind_s == "decimal":
        return _decimal_display(value, decimals)
    # Code / char field.
    text = "" if value is None else str(value).strip()
    if not text:
        # Blank char fields stay blank; numeric codes show a zero.
        return " " if (sample or "").strip() == "" else "0"
    # Some DB2 code columns are wider than the 1-2 byte record field (e.g. a
    # company code stored "01" but shown "1").  Drop only *surplus leading
    # zeros* to match the sample's display width -- never a significant digit.
    s = (sample or "").strip()
    if text.isdigit() and s.isdigit() and len(text) > len(s) and text[0] == "0":
        trimmed = text.lstrip("0") or "0"
        if len(trimmed) < len(s):
            trimmed = trimmed.rjust(len(s), "0")
        text = trimmed
    return text


def _tok(text: str, field: str) -> dict:
    return {"text": text, "field": field}


def _example(text: str, field: str, note: str = _EXAMPLE_NOTE) -> dict:
    """A hover-aware value that is *illustrative*, not real DB2 policy data."""
    return {"text": text, "field": field, "example": True, "note": note}


def _sep(text: str) -> dict:
    return {"text": text, "field": None}


def _wrap_record_groups(groups: List[list], columns: int = 80) -> List[list]:
    """Wrap terminal fields, retaining concatenated keys as indivisible groups."""
    lines = []
    line, width = [_sep("  ")], 2
    for group in groups:
        size = sum(len(run["text"]) for run in group)
        gap = 1 if len(line) > 1 else 0
        if width + gap + size > columns:
            lines.append(line)
            line, width, gap = [_sep(" " * 10)], 10, 0
        if width + gap + size > columns:
            raise ValueError(f"Policy-record field exceeds {columns}-column terminal width")
        if gap:
            line.append(_sep(" "))
        line.extend(group)
        width += gap + size
    if len(line) > 1:
        lines.append(line)
    return lines


def _policy_display(pi) -> str:
    return str(getattr(pi, "policy_number", "") or "").strip()


def _region_company(pi) -> str:
    region = str(getattr(pi, "region", "") or "").strip()
    company = str(getattr(pi, "company_name", "") or "").strip()
    return f"{region}-{company}" if company else region


def _user_id() -> str:
    try:
        return (getpass.getuser() or "").upper()
    except Exception:
        return ""


def _today_mmddyy() -> str:
    return datetime.now().strftime("%m/%d/%y")


def _rule_display(value) -> str:
    text = str(value if value is not None else "").strip()
    return text if text else " "


def _date_display(value) -> str:
    """Format a DB2 date value as MM/DD/YYYY (blank stays blank)."""
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%m/%d/%Y")
    text = str(value).strip()
    if not text:
        return ""
    # ISO 'YYYY-MM-DD' (optionally with a time component).
    core = text.split(" ")[0].split("T")[0]
    parts = core.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        y, m, d = parts
        if y.isdigit() and m.isdigit() and d.isdigit():
            return f"{int(m):02d}/{int(d):02d}/{y}"
    return text


def _date_parts(value) -> Optional[Tuple[int, int, int]]:
    """Return ``(month, day, year)`` for a DB2 date value, else ``None``."""
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.month, value.day, value.year
    core = str(value).strip().split(" ")[0].split("T")[0]
    parts = core.split("-")
    if len(parts) == 3 and len(parts[0]) == 4 and all(p.isdigit() for p in parts):
        y, m, d = parts
        return int(m), int(d), int(y)
    return None


def _packed_mmddyy(value) -> str:
    """Render a date as the mainframe's packed ``MMDDYY`` integer.

    A handful of activity dates (Accounting/Financial/Change/Billing Date) are
    stored as a packed number and shown *unslashed* -- e.g. 07/10/2026 -> ``71026``
    (month has no leading zero; day and 2-digit year are zero-padded).  Null and
    the high-date sentinel render as ``0`` (matching the archive screens).
    """
    parts = _date_parts(value)
    if parts is None:
        return "0"
    month, day, year = parts
    if year <= 1900 or year >= 9999:
        return "0"
    return f"{month}{day:02d}{year % 100:02d}"


def _amount_display(value) -> str:
    if value is None or str(value).strip() == "":
        return "0.00"
    try:
        return f"{Decimal(str(value)):.2f}"
    except (InvalidOperation, ValueError):
        return str(value).strip()


def _decimal_display(value, decimals: int) -> str:
    """Format *value* to *decimals* places, dropping a leading zero.

    Matches the mainframe convention where fractional amounts/factors show no
    integer zero (e.g. ``.00000``, ``.08640``) while values >= 1 keep it
    (e.g. ``8.000``, ``107.00``).
    """
    try:
        d = Decimal(str(value)) if value not in (None, "") else Decimal(0)
    except (InvalidOperation, ValueError):
        return str(value).strip()
    text = f"{d:.{decimals}f}"
    if text.startswith("0."):
        return text[1:]
    if text.startswith("-0."):
        return "-" + text[2:]
    return text


def _as_int(value, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default


def _safe_rows(pi, table: str) -> List[dict]:
    """Fetch a table's rows, tolerating a missing/empty table."""
    try:
        rows = pi.fetch_table(table)
    except Exception:
        return []
    return list(rows or [])
