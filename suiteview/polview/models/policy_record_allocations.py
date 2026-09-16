"""Live allocation segment 57 (CyberDoc D202, printed pages 90-96/602)."""

from datetime import date, datetime

from .policy_record_builder import (
    _append_screen_footer, _date_display, _decimal_display, _example,
    _packed_decimal, _policy_display, _sep, _tok, _wrap_record_groups,
)


HEADER_TABLE = "LH_FND_TRS_ALC_SET"
ENTRY_TABLE = "LH_FND_ALC"
FLAG_COLUMNS = ("ALC_SRC_CD", "AUTOCLOS_PROC_IND", "MTHLVRSY_PROC_IND")
VALUE_FIELDS = {
    "P": ("Fund Allocation Percent", "FND_ALC_PCT", "FALALPER-FUND-ALLOC-PCT", 5, 2),
    "D": ("Fund Allocation Dollars", "FND_ALC_AMT", "FALALDOL-FUND-ALLOC-DOL", 11, 2),
    "U": ("Fund Allocation Units", "FND_ALC_UNT_QTY", "FALALUNI-FUND-ALLOC-UNITS", 13, 4),
}


def _value(row, column):
    if column not in row:
        raise ValueError(f"Segment 57 source column is missing: {column}")
    return row[column]


def _integer(row, column, maximum=999):
    packed = _packed_decimal(_value(row, column), 3)
    number = int(packed[:-1])
    if packed.endswith("D") or number > maximum:
        raise ValueError(f"Invalid Segment 57 {column}: {row[column]!r}")
    return number


def _key_text(row, column, width=1):
    value = _value(row, column)
    text = "" if value is None else str(value).strip()
    if not text or len(text) > width or any(ord(char) < 32 for char in text):
        raise ValueError(f"Invalid Segment 57 {column}: {value!r}")
    return text


def _source_token(text, field, table, column, note=""):
    return {
        **_tok(text, field),
        "note": f"Live source: {table}.{column}. {note}".strip(),
    }


def _character_token(row, column, field, table, width=1):
    value = _value(row, column)
    if value is None:
        return {
            **_source_token(" " * width, field, table, column, "DB2 NULL, not a stored blank."),
            "dim": True,
        }
    text = str(value).rstrip(" ")
    if len(text) > width or any(ord(char) < 32 and char != "\x00" for char in text):
        raise ValueError(f"Invalid Segment 57 {column}: {value!r}")
    low_values = "\x00" in text
    token = _source_token(
        text.replace("\x00", " ").ljust(width), field, table, column,
        "DB2 low-values shown as blank character slots." if low_values else "",
    )
    if low_values:
        token["dim"] = True
    return token


def _date_token(row, segment_type):
    # The charge-deduction redefine stores the same record date separately.
    column = "CRG_DED_ALC_EFF_DT" if segment_type == "C" else "LST_ALC_CHG_DT"
    value = _value(row, column)
    if value is None:
        return {
            **_source_token("**/**/****", "Last Allocation Change Date", HEADER_TABLE,
                            column, "DB2 NULL date; no date has been inferred."),
            "dim": True,
        }
    if isinstance(value, datetime):
        value = value.date()
    elif not isinstance(value, date):
        value = date.fromisoformat(str(value).strip())
    text = "**/**/****" if value.year in (1, 1900, 9999) else _date_display(value)
    return _source_token(text, "Last Allocation Change Date", HEADER_TABLE, column)


def _flag_groups(row):
    bits = []
    for index, column in enumerate(FLAG_COLUMNS):
        value = _value(row, column)
        if value is None:
            bits.append({
                **_source_token("?", "Flag Byte A", HEADER_TABLE, column,
                                f"Bit {index}: DB2 NULL, not zero."),
                "dim": True,
            })
        else:
            bit = str(value).strip()
            if bit not in ("0", "1"):
                raise ValueError(f"Invalid Segment 57 flag {column}: {value!r}")
            bits.append(_source_token(bit, "Flag Byte A", HEADER_TABLE, column, f"Bit {index}."))
    bits.append(_example(
        "00000", "Flag Byte A",
        "Bits 3-6 are reserved; bit 7 (group-control generation) has no verified "
        "DB2 source. Captured zeros are illustrative, not live data.",
    ))
    return [bits, [_example(
        "00000000", "Flag Byte U",
        "User-reserved flag byte has no verified DB2 source. Captured zeros are illustrative.",
    )]]


def _entry_groups(row):
    direction = _character_token(row, "FND_ALC_DIR_CD", "Allocation From/To Indicator", ENTRY_TABLE)
    exclusion = _character_token(row, "FND_XCL_IND", "Allocation Exclusion Indicator", ENTRY_TABLE)
    if direction["text"] not in (" ", "F", "T") or exclusion["text"] not in (" ", "0", "1"):
        raise ValueError("Unsupported Segment 57 allocation direction/exclusion indicator")
    phase = _integer(row, "COV_PHA_NBR", maximum=255)
    fund = _key_text(row, "FND_ID_CD", 2)
    value_type = _key_text(row, "ALC_VAL_TYP_CD")
    if value_type not in VALUE_FIELDS:
        raise ValueError(f"Unsupported Segment 57 allocation value type: {value_type!r}")
    field, column, _, digits, decimals = VALUE_FIELDS[value_type]
    value = _value(row, column)
    if value is None:
        amount = {
            **_source_token("?" * (decimals + 2), field, ENTRY_TABLE, column,
                            "DB2 NULL: allocation amount is unavailable, not zero."),
            "dim": True,
        }
    else:
        _packed_decimal(value, digits, decimals)
        amount = _source_token(_decimal_display(value, decimals), field, ENTRY_TABLE, column)
    return [[token] for token in (
        direction, exclusion,
        _source_token(str(phase), "Allocation Coverage Phase", ENTRY_TABLE, "COV_PHA_NBR"),
        _source_token(fund.ljust(2), "Allocation Fund Identification", ENTRY_TABLE, "FND_ID_CD"),
        _source_token(value_type, "Allocation Value Type", ENTRY_TABLE, "ALC_VAL_TYP_CD"),
        amount,
    )]


def build_segment_57(pi):
    """Show all allocation sets, joining actual set sequence and entry index."""
    sources = {}
    for table in (HEADER_TABLE, ENTRY_TABLE):
        sources[table] = pi.fetch_table(table)
        error = pi.table_error(table)
        if error:
            raise ValueError(f"Segment 57 {table}: {error}")
    sets = {}
    for row in sources[HEADER_TABLE]:
        key = (_key_text(row, "FND_TRS_TYP_CD"), _integer(row, "FND_ALC_SEQ_NBR"))
        if key in sets:
            raise ValueError(f"Duplicate Segment 57 allocation set: {key}")
        sets[key] = row
    entries = {key: {} for key in sets}
    for row in sources[ENTRY_TABLE]:
        # The workbook swapped these descriptions: both tables use
        # FND_ALC_SEQ_NBR for the set; SEG_IDX_NBR orders the member entries.
        key = (_key_text(row, "FND_ALC_TYP_CD"), _integer(row, "FND_ALC_SEQ_NBR"))
        if key not in entries:
            raise ValueError(f"Segment 57 allocation entry has no matching set: {key}")
        index = _integer(row, "SEG_IDX_NBR", maximum=99)
        if index in entries[key]:
            raise ValueError(f"Duplicate Segment 57 entry index {index} in set {key}")
        entries[key][index] = row
    if not sets:
        return None
    lines = [[_sep("  "), _tok("6257,", "Screen Name"), _sep(" "),
              _tok(_policy_display(pi), "Policy Number")]]
    for key, row in sorted(sets.items()):
        allocations = entries[key]
        count = len(allocations)
        if sorted(allocations) != list(range(1, count + 1)):
            raise ValueError(f"Non-contiguous Segment 57 allocation indexes in set {key}")
        groups = [[_tok("57", "Segment Identification")],
                  [_tok(f"{30 + 16 * count:04d}", "Segment Length")]]
        groups.extend(_flag_groups(row))
        groups.extend([token] for token in (
            _source_token(key[0], "Segment Type", HEADER_TABLE, "FND_TRS_TYP_CD"),
            _source_token(str(key[1]), "Type Sequence", HEADER_TABLE, "FND_ALC_SEQ_NBR"),
            _date_token(row, key[0]),
            _character_token(row, "ALC_MTH_CD", "Allocation Method", HEADER_TABLE),
            _character_token(row, "SWP_FROM_FUND", "Sweep From Fund", HEADER_TABLE, 2),
            {**_tok(str(count), "Number of Allocations"),
             "note": "Count of LH_FND_ALC entries for this type/sequence; not the sequence value."},
        ))
        for index in sorted(allocations):
            groups.extend(_entry_groups(allocations[index]))
        lines.extend(_wrap_record_groups(groups))
    _append_screen_footer(lines, pi, min_lines=18)
    return lines
