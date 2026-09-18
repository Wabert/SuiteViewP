"""Live Benefits (6204): D20 pp.159-175/374, verified against U0566833."""

from datetime import date, datetime
from decimal import Decimal

from .policy_record_builder import (
    _append_screen_footer, _date_display, _decimal_display, _packed_decimal,
    _policy_display, _sep, _tok, _wrap_record_groups,
)

TABLE = "LH_SPM_BNF"
EXTENSION_TABLE = "TH_SPM_BNF"
REQUEST_TABLE = "LH_ALL_COV_BNF_REQ"
TABLES = (REQUEST_TABLE, TABLE, EXTENSION_TABLE)
KEY_COLUMNS = (
    "TCH_POL_ID", "CK_CMP_CD", "CK_SYS_CD", "COV_PHA_NBR",
    "SPM_BNF_TYP_CD", "SPM_BNF_SBY_CD", "PRS_CD", "PRS_SEQ_NBR",
    "BNF_STA_CD", "BNF_ISS_DT",
)
FLAGS = {
    "Flag Byte A": (
        ("IF_POL_IND", "Derived from inforce record"),
        ("MAT_EXTN_IND", "Contract maturity extended"),
        ("CEA_DT_INP_IND", "Cease date explicitly input"),
        ("BNF_NBR_LIVES_CD", "Joint lives"),
        ("PW_PCT_IND", "Waiver premium is a percentage"),
        ("DCA_FCA_IND", "Requested decrease applied"),
        ("STP_BAN_IND", "Step-banded premium"),
        ("BNF_SEG_IVD_IND", "Invalid benefit"),
    ),
    "Flag Byte B": (
        ("UNT_REQ_IND", "Units explicitly requested"),
        ("BNF_REQ_MTH_IND", "Requested on all applicable coverages"),
        ("INP_FRM_NBR_IND", "Form number input override"),
        ("INP_BNF_PRM_IND", "Annual premium input override"),
        ("INT_TRM_IND", "Regular premium during initial term"),
        ("IHT_BNF_IND", "Inherent benefit"),
        ("BNF_VLD_IND", "Internal validation indicator"),
        ("BNF_DENIED_IND", "Underwriter denied benefit"),
    ),
}

# Name, column, COBOL name, bytes, kind, text/binary width or packed digits, decimals.
FIELDS = (
    ("Coverage Phase", "COV_PHA_NBR", "FSBBPHS-PHASE-CODE", "7", "binary", 1, 0),
    ("Benefit Type", "SPM_BNF_TYP_CD", "FSBBTYP-TYPE-CODE", "8", "text", 1, 0),
    ("Benefit Subtype", "SPM_BNF_SBY_CD", "FSBBSTYP-SUBTYPE-CODE", "9", "text", 1, 0),
    ("Person Code", "PRS_CD", "FSBPERSN-PERSON-CODE", "10-11", "text", 2, 0),
    ("Person Sequence", "PRS_SEQ_NBR", "FSBPSEQ-PERSON-SEQUENCE", "12", "binary", 1, 0),
    ("Cease Date", "BNF_CEA_DT", "FSBBCDDF-CEASE-DATE-FIELDS", "13-17", "date", 5, 0),
    ("Use Code", "BNF_STA_CD", "FSBBCUSE-USE-CODE", "18", "text", 1, 0),
    ("Commission Code", "BNF_COM_CD", "FSBBCOM-COMMISSION-CODE", "19", "text", 1, 0),
    ("Reserve Plan", "RES_MTH_PLN_CD", "FSBBPLN-RESERVE-PLAN", "20-22", "text", 3, 0),
    ("Issue Age", "BNF_ISS_AGE", "FSBBAGE-ISSUE-AGE", "23-24", "number", 3, 0),
    ("Age Admitted Code", "AGE_SRC_CD", "FSBAGADM-AGE-ADMITTED-CODE", "25", "text", 1, 0),
    ("Issue Date", "BNF_ISS_DT", "FSBBISDF-ISSUE-DATE-FIELDS", "26-30", "date", 5, 0),
    ("Pay-Up Date", "BNF_PAY_UP_DT", "FSBPUDAT-PAY-UP-DATE", "31-35", "date", 5, 0),
    ("Rating Factor", "BNF_RT_FCT", "FSBBRAT-RATING-FACTOR", "36-37", "number", 3, 2),
    ("Annual Premium per Unit", "BNF_ANN_PPU_AMT", "FSBBAP-ANNUAL-PREM-PER-UNIT", "38-42", "number", 9, 2),
    ("Premium Calculation Percent", "BNF_PRM_CLC_PCT", "FSBPRMCP-PREMIUM-CALC-PERCENT", "43-44", "number", 3, 0),
    ("Number of Units", "BNF_UNT_QTY", "FSBBUNT-NUMBER-OF-UNITS", "45-49", "number", 9, 3),
    ("Value per Unit", "BNF_VPU_AMT", "FSBBVPU-VALUE-PER-UNIT", "50-54", "number", 9, 2),
    ("Original Cease Date", "BNF_OGN_CEA_DT", "FSBOCSDF-ORIG-CSE-DATE-FIELDS", "55-59", "date", 5, 0),
    ("Renewable Rate Indicator", "RNL_RT_IND", "FSBRENRT-RENEWABLE-RATE-IND", "60", "renewal", 1, 0),
    ("Benefit Form Number", "BNF_FRM_NBR", "FSBFRMNO-BENEFIT-FORM-NUMBER", "61-69", "text", 9, 0),
)
PPA_FIELD = (
    "Policy Protection Interest Rate", "PRT_PCT", "FSBPPAP-POL-PROTECTION-PCT",
    "70-72", "number", 5, 3,
)
DENY_FIELD = (
    "Automatic Rate Deny", "AUTO_RATE_DENY", "FSBRDIND-RATE-DENY-IND",
    "76-77 (archived positions conflict)", "text", 1, 0,
)
FREQUENCY_FIELD = (
    "Benefit Frequency", "BENEFIT_FREQ", "FSBBFREQ-BENEFIT-FREQ",
    "76-77 (archived positions conflict)", "text", 1, 0,
)


def _value(row, table, column):
    if column not in row:
        raise ValueError(f"Segment 04 source column is missing: {table}.{column}")
    return row[column]


def _calendar_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip())


def _field_token(row, table, spec):
    name, column, _, _, kind, width, decimals = spec
    value = _value(row, table, column)
    note = f"Live source: {table}.{column}."
    if value is None:
        if kind == "date":
            text = "**/**/****"
        elif kind in ("text", "renewal"):
            text = "?" * width
        else:
            text = "." + "0" * decimals if decimals else "0"
        return {**_tok(text, name), "dim": True,
                "note": note + " DB2 NULL, not a stored zero or blank; CyberLife null-slot display."}
    try:
        if kind == "date":
            day = _calendar_date(value)
            text = "**/**/****" if day.year in (1900, 9999) else _date_display(day)
        elif kind == "renewal":
            code = str(value).strip()
            if code not in ("0", "1"):
                raise ValueError("expected 0 or 1")
            text = "X" if code == "0" else " "
            note += " 0 = X (not renewable); 1 = blank (renewable)."
        elif kind == "text":
            text = str(value).strip()
            if len(text) > width or any(ord(char) < 32 for char in text):
                raise ValueError("text exceeds field width or contains control characters")
            text = text.ljust(width)
        else:
            number = Decimal(str(value))
            if kind == "binary":
                if not number.is_finite() or number != number.to_integral_value() or not 0 <= number < 256 ** width:
                    raise ValueError("unsigned binary field out of range")
            else:
                _packed_decimal(number, width, decimals)
            text = _decimal_display(number, decimals) if decimals else str(int(number))
    except (ValueError, ArithmeticError) as exc:
        raise ValueError(f"Invalid Segment 04 {table}.{column}: {value!r}") from exc
    return {**_tok(text, name), "note": note}


def _key(row, table):
    values = []
    for column in KEY_COLUMNS:
        value = _value(row, table, column)
        if value is None or not str(value).strip():
            raise ValueError(f"Segment 04 {table} has an incomplete benefit key: {column}")
        try:
            if column == "BNF_ISS_DT":
                value = _calendar_date(value)
            elif column in ("COV_PHA_NBR", "PRS_SEQ_NBR"):
                number = Decimal(str(value))
                if not number.is_finite() or number != number.to_integral_value() or not 0 <= number <= 255:
                    raise ValueError("unsigned binary key out of range")
                value = int(number)
            else:
                value = str(value).strip()
        except (ValueError, ArithmeticError) as exc:
            raise ValueError(f"Invalid Segment 04 {table} benefit key {column}: {value!r}") from exc
        values.append(value)
    return tuple(values)


def _index(rows, table):
    indexed = {}
    for row in rows:
        key = _key(row, table)
        if key in indexed:
            raise ValueError(f"Segment 04 duplicate {table} benefit key: {key}")
        indexed[key] = row
    return indexed


def _flag_tokens(row, name):
    tokens = []
    for bit, (column, meaning) in enumerate(FLAGS[name]):
        value = _value(row, TABLE, column)
        note = f"Live source: {TABLE}.{column}; {name} bit {bit}: {meaning}."
        if value is None:
            tokens.append({**_tok("?", name), "dim": True, "note": note + " DB2 NULL, not zero."})
        elif str(value).strip() in ("0", "1"):
            tokens.append({**_tok(str(value).strip(), name), "note": note})
        else:
            raise ValueError(f"Invalid Segment 04 flag {column}: {value!r}")
    return tokens


def _check_variant(row, extension):
    for column in ("IFT_PCT", "CPI_ADJ_REJ_NBR", "OPT_DT"):
        value = _value(row, TABLE, column)
        if value is not None:
            raise ValueError(
                f"Segment 04 {column} option/inflation variant is not yet screen-verified; "
                "cannot substitute the ordinary benefit layout"
            )
    if str(_value(row, TABLE, "SPM_BNF_TYP_CD")).strip() != "A" and _value(row, TABLE, "PRT_PCT") is not None:
        raise ValueError("Segment 04 policy-protection rate exists on a non-PPA benefit")
    if extension is not None:
        for column in ("BENEFIT_FREQ", "ABR_QUAL_IND"):
            value = _value(extension, EXTENSION_TABLE, column)
            if value is not None and str(value).strip():
                raise ValueError(
                    f"Segment 04 {EXTENSION_TABLE}.{column} has an unverified user-area value; "
                    "a matching terminal capture is needed"
                )


def build_segment_04(pi):
    """Join benefit extensions by full identity, preserving source order per phase."""
    sources = {}
    for table in TABLES:
        sources[table] = pi.fetch_table(table)
        if error := pi.table_error(table):
            raise ValueError(f"Segment 04 {table}: {error}")
        if sources[table] is None:
            raise ValueError(f"Segment 04 {table} returned no row collection")
    if sources[REQUEST_TABLE]:
        raise ValueError("Segment 04 all-coverage benefit requests are not yet screen-verified")
    benefits = _index(sources[TABLE], TABLE)
    extensions = _index(sources[EXTENSION_TABLE], EXTENSION_TABLE)
    if extensions.keys() - benefits.keys():
        raise ValueError("Segment 04 orphan TH_SPM_BNF benefit extension")
    if not benefits:
        return None
    lines = [[_sep("  "), _tok("6204,", "Screen Name"), _sep(" "),
              _tok(_policy_display(pi), "Policy Number")]]
    for key, row in sorted(benefits.items(), key=lambda item: item[0][3]):
        extension = extensions.get(key)
        _check_variant(row, extension)
        groups = [[_tok("04", "Segment Identification")], [_tok("0081", "Segment Length")]]
        groups.extend(_flag_tokens(row, name) for name in FLAGS)
        for spec in FIELDS:
            if spec[1] == "BNF_STA_CD" and key[4] == "U":
                spec = (spec[0], "COL_ICE_FQY_CD", *spec[2:])
            groups.append([_field_token(row, TABLE, spec)])
        if key[4] == "A":
            groups.append([_field_token(row, TABLE, PPA_FIELD)])
        if extension is None:
            groups.append([{**_tok("?", DENY_FIELD[0]), "dim": True,
                            "note": "No matching TH_SPM_BNF row; automatic rate deny is unavailable."}])
        else:
            groups.append([_field_token(extension, EXTENSION_TABLE, DENY_FIELD)])
        lines.extend(_wrap_record_groups(groups))
    _append_screen_footer(lines, pi, min_lines=18)
    return lines
