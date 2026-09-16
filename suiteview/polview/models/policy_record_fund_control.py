"""Live 6255 fixed-fund control; D202 pp.63–77/600 and verified DB2 sources.

LH_COV_IVM_FND_CTL is the common header, not a variable-fund alternative to
LH_COV_FXD_FND_CTL. Fixed records join both on the complete policy/fund key.
"""

from datetime import date, datetime
from decimal import Decimal

from .policy_record_builder import (
    _append_screen_footer, _date_display, _decimal_display, _example,
    _packed_decimal, _policy_display, _sep, _tok, _wrap_record_groups,
)

COMMON_TABLE = "LH_COV_IVM_FND_CTL"
FIXED_TABLE = "LH_COV_FXD_FND_CTL"
TIER_TABLES = ("LH_AMT_TIERED_ITS", "LH_DUR_TIERED_ITS")
TABLES = (COMMON_TABLE, FIXED_TABLE, *TIER_TABLES)
KEY_COLUMNS = ("TCH_POL_ID", "CK_CMP_CD", "CK_SYS_CD", "COV_PHA_NBR", "FND_ID_CD")
FLAG_COLUMNS = (
    "ICP_ACY_IND", "ACTING_VAL_SEG_IND", "IRL_GNR_IND", "DEL_IND",
    "RE_ADDED_IND", "IDX_ANU_IND", "MVA_APP_IND", "FND_VAL_STA_IND",
)

# Name, DB2 column, COBOL name, one-based bytes, format, display/packed width.
COMMON_FIELDS = (
    ("Coverage Phase", "COV_PHA_NBR", "FIFCOVPH-ASSOC-COV-PHASE", "8", "binary", 1),
    ("Fund Identification", "FND_ID_CD", "FIFFNDID-FUND-ID", "9-10", "text", 2),
    ("Fund Type", "FND_TYP_CD", "FIFFNDTY-FUND-TYPE", "11", "text", 1),
    ("Qualified/Nonqualified", "FND_TAX_STA_CD", "FIFFNDQL-FUND-QUALIFICATION", "12", "text", 1),
    ("Minimum Balance Table", "FND_MIN_BAL_TBL_CD", "FIFMBTBL-MIN-BAL-TBL-CODE", "13-14", "text", 2),
    ("Initial Minimum Balance Rule", "INT_MIN_BAL_RLE_CD", "FIFMBINL-INITIAL", "15", "text", 1),
    ("Remain Minimum Balance Rule", "RMD_MIN_BAL_RLE_CD", "FIFMBRMN-REMAIN", "16", "text", 1),
    ("Purchase Rule", "FND_PUR_RLE_CD", "FIFPURCH-PURCHASE-RULE", "17", "text", 1),
    ("Transfers", "TRF_RLE_CD", "FIFDTRNF-TRANSFERS", "18", "text", 1),
    ("Withdrawals", "WTD_RLE_CD", "FIFDWDRW-WITHDRAWALS", "19", "text", 1),
    ("Loans", "LN_RLE_CD", "FIFDLOAN-LOANS", "20", "text", 1),
    ("Loan Interest", "LN_ITS_RLE_CD", "FIFDLINT-LOAN-INTEREST", "21", "text", 1),
    ("Charges", "CRG_RLE_CD", "FIFDCHRG-CHARGES", "22", "text", 1),
    ("Minimum Duration", "MIN_DUR", "FIFDMDUR-MIN-DUR-PRIOR", "23-24", "integer", 3),
    ("Penalties Table", "PNY_TBL_CD", "FIFPTBLE-PENALTY-TABLE", "25-26", "text", 2),
    ("Penalties Rule 1", "PNY_RLE_1_CD", "FIFPRUL1-PENALTY-RULE-1", "27", "text", 1),
    ("Penalties Rule 2", "PNY_RLE_2_CD", "FIFPRUL2-PENALTY-RULE-2", "28", "text", 1),
    ("Last Transfer Date", "LST_TRF_DT", "FIFLTRDT-LAST-TRANSFER-DATE", "29-32", "date", 4),
    ("Last Transfer In/Out", "LST_TRF_TYP_CD", "FIFLTRTY-LAST-TRNSFR-TYPE", "33", "text", 1),
    ("Assumed Interest Rate", "ANU_ASM_ITS_RT", "FIFVAIRT-ASSUM-INT-RATE", "34-36", "rate", 5),
)
FIXED_FIELDS = (
    ("Investment Method", "IVM_MTH_TYP_CD", "FIFFIVMT-INVESTMENT-METHOD", "46", "text", 1),
    ("Investment Method Subtype", "IVM_MTH_SBY_CD", "FIFFISTP-INV-SUBTYPE", "47", "text", 1),
    ("Interest Accrual Frequency", "ITS_ACCR_FQY_PER", "FIFFIFRQ-INTEREST-FREQUENCY", "48-49", "integer", 3),
    ("Compound Rule", "ITS_CMPD_RLE_CD", "FIFFCMPD-INT-COMPOUND-RULE", "50", "text", 1),
    ("Guaranteed Interest Rate", "GUA_FND_ITS_RT", "FIFFGIRT-GUAR-INT-RATE", "51-53", "rate", 5),
    ("Guaranteed Rule", "GUA_ITS_PER_RLE_CD", "FIFFGRUL-INT-GUAR-RULE", "54", "text", 1),
    ("Guaranteed Interest Period", "GUA_ITS_PER", "FIFFGPRD-INIT-GUAR-PERIOD", "55-56", "integer", 3),
    ("User Rule for guaranteed calculation", "ADD_GUA_PER_RLE_CD", "FIFFGURL-USER-GUAR-RULE", "57", "text", 1),
    ("User months for guaranteed period", "ADD_GUA_PER", "FIFFGUPD-USER-GUAR-PERIOD", "58-59", "integer", 3),
    ("High Phase", "HI_FND_VAL_PHA_NBR", "FIFHIPHS-FUND-HIGH-PHASE-CODE", "60-61", "binary", 2),
    ("Current Interest Rates File Search Key", "CUR_ITS_RT_SER_NBR", "FIFFKEY-INT-RTE-FILE-SRCH-KY", "62-72", "text", 11),
    ("Initial Interest Rate", "CUR_ITS_RT", "FIFIDIR-ISS-DATA-INT-RATE", "73-75", "rate", 5),
    ("Initial Interest Rate End Date", "ITS_PER_END_DT", "FIFISEDT-ISS-DATA-END-DATE", "76-79", "date", 4),
)


def _value(row, table, column):
    if column not in row:
        raise ValueError(f"Segment 55 source column is missing: {table}.{column}")
    return row[column]


def _key(row, table):
    values = [_value(row, table, column) for column in KEY_COLUMNS]
    if any(value is None or not str(value).strip() for value in values):
        raise ValueError(f"Segment 55 {table} has an incomplete policy/fund key")
    try:
        phase = Decimal(str(values[3]))
        if not phase.is_finite() or phase != phase.to_integral_value() or not 1 <= phase <= 255:
            raise ValueError("coverage phase must be 1..255")
    except ArithmeticError as exc:
        raise ValueError(f"Segment 55 invalid coverage phase: {values[3]!r}") from exc
    fund = str(values[4]).strip()
    if len(fund) > 2:
        raise ValueError(f"Segment 55 invalid fund identifier: {fund!r}")
    return (*[str(value).strip() for value in values[:3]], int(phase), fund)


def _index(rows, table):
    indexed = {}
    for row in rows:
        key = _key(row, table)
        if key in indexed:
            raise ValueError(f"Segment 55 duplicate {table} policy/fund key: {key}")
        indexed[key] = row
    return indexed


def _field_token(row, table, spec):
    name, column, _, _, kind, width = spec
    value = _value(row, table, column)
    note = f"Live source: {table}.{column}."
    if value is None:
        text = {"date": "**/**/****", "rate": ".000", "text": "?" * width}.get(kind, "0")
        return {**_tok(text, name), "dim": True,
                "note": note + " DB2 NULL, not a stored zero; CyberLife null-slot display."}
    try:
        if kind == "text":
            text = str(value).strip()
            if len(text) > width or any(ord(char) < 32 for char in text):
                raise ValueError("text exceeds record field width or contains control characters")
            text = text.ljust(width)
        elif kind == "date":
            if isinstance(value, datetime):
                value = value.date()
            elif not isinstance(value, date):
                value = date.fromisoformat(str(value).strip())
            text = "**/**/****" if value.year in (1900, 9999) else _date_display(value)
        else:
            number = Decimal(str(value))
            if kind == "binary":
                if not number.is_finite() or number != number.to_integral_value() or not 0 <= number < 256 ** width:
                    raise ValueError("unsigned binary field is out of range")
            else:
                _packed_decimal(number, width, 3 if kind == "rate" else 0)
            text = _decimal_display(number, 3) if kind == "rate" else str(int(number))
    except (ValueError, ArithmeticError) as exc:
        raise ValueError(f"Invalid Segment 55 {table}.{column}: {value!r}") from exc
    return {**_tok(text, name), "note": note}


def _flags(row):
    bits = []
    for index, column in enumerate(FLAG_COLUMNS):
        value = _value(row, COMMON_TABLE, column)
        note = f"Live source: {COMMON_TABLE}.{column}; Flag A bit {index}."
        if value is None:
            bits.append({**_tok("?", "Flag Byte A"), "dim": True,
                         "note": note + " DB2 NULL, not zero."})
        elif str(value).strip() in ("0", "1"):
            bits.append({**_tok(str(value).strip(), "Flag Byte A"), "note": note})
        else:
            raise ValueError(f"Invalid Segment 55 flag {column}: {value!r}")
    return bits


def build_segment_55(pi):
    """Render verified fixed-fund records; fail loudly on incomplete/unknown bases."""
    sources = {}
    for table in TABLES:
        sources[table] = pi.fetch_table(table)
        if error := pi.table_error(table):
            raise ValueError(f"Segment 55 {table}: {error}")
        if sources[table] is None:
            raise ValueError(f"Segment 55 {table} returned no row collection")
    common = _index(sources[COMMON_TABLE], COMMON_TABLE)
    fixed = _index(sources[FIXED_TABLE], FIXED_TABLE)
    if not any(sources.values()):
        return None
    if not common:
        raise ValueError("Segment 55 has no LH_COV_IVM_FND_CTL fund-control rows")
    for table in (FIXED_TABLE, *TIER_TABLES):
        for row in sources[table]:
            key = _key(row, table)
            if key not in common:
                raise ValueError(f"Segment 55 orphan {table} policy/fund key: {key}")
    if any(sources[table] for table in TIER_TABLES):
        raise ValueError(
            "Segment 55 tiered/duration portfolio extension is not yet live-screen verified; "
            "cannot safely reconstruct its count, stored length and tier ordering"
        )
    lines = [[_sep("  "), _tok("6255,", "Screen Name"), _sep(" "),
              _tok(_policy_display(pi), "Policy Number")]]
    for key in sorted(common, key=lambda item: (item[3], item[4], *item[:3])):
        row = common[key]
        fund_type = _value(row, COMMON_TABLE, "FND_TYP_CD")
        if fund_type != "F":
            raise ValueError(
                f"Segment 55 fund {key[3:]} type {fund_type!r}: variable/unknown fund "
                "layout is not live-screen verified; fixed-fund data must not be fabricated"
            )
        if key not in fixed:
            raise ValueError(f"Segment 55 missing {FIXED_TABLE} row for policy/fund key: {key}")
        fixed_row = fixed[key]
        method = _value(fixed_row, FIXED_TABLE, "IVM_MTH_TYP_CD")
        subtype = _value(fixed_row, FIXED_TABLE, "IVM_MTH_SBY_CD")
        if method is None or subtype is None:
            raise ValueError(f"Segment 55 fund {key[3:]} investment method/subtype is unknown")
        method, subtype = str(method).strip(), str(subtype).strip()
        count = _value(fixed_row, FIXED_TABLE, "TIER_ITS_RT_NBR")
        if count is not None:
            try:
                count = Decimal(str(count))
                if not count.is_finite() or count != count.to_integral_value() or not 0 <= count <= 8:
                    raise ValueError("expected a tier count in 0..8")
            except (ValueError, ArithmeticError) as exc:
                raise ValueError(f"Segment 55 invalid {FIXED_TABLE}.TIER_ITS_RT_NBR: {count!r}") from exc
        if subtype in ("D", "T") or count not in (None, 0):
            raise ValueError("Segment 55 tiered/duration portfolio layout is not yet live-screen verified")
        if (method, subtype) not in {
            ("1", ""), ("1", "4"), *[("2", str(number)) for number in range(1, 7)],
        }:
            raise ValueError(f"Segment 55 unsupported investment method/subtype: {method!r}/{subtype!r}")
        groups = [
            [_tok("55", "Segment Identification")],
            [{**_tok("0079", "Segment Length"),
              "note": "Verified fixed, non-tiered record: 45-byte common area + 34-byte fixed area."}],
            _flags(row),
        ]
        groups.extend([_example(
            "00000000", name,
            "Reserved byte with no DB2 source; captured zeros are illustrative, not verified live bits.",
        )] for name in ("Flag Byte B", "Flag Byte U"))
        groups.extend([_field_token(row, COMMON_TABLE, spec)] for spec in COMMON_FIELDS)
        groups.extend([_field_token(fixed_row, FIXED_TABLE, spec)] for spec in FIXED_FIELDS)
        lines.extend(_wrap_record_groups(groups))
    _append_screen_footer(lines, pi, min_lines=18)
    return lines
