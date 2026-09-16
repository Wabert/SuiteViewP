"""Live annual Policy Record totals; D202 printed pages 129–138, 608–609.

DB2 mappings are verified against COBOLDB2translation.xls and live UL045809.
The builder imports this module lazily, so shared terminal helpers are safe.
"""

from datetime import date, datetime

from .policy_record_builder import (
    _append_screen_footer, _date_display, _decimal_display, _example,
    _packed_decimal, _policy_display, _sep, _tok, _wrap_record_groups,
)

# name, DB2 column, COBOL name, packed digits, decimal places (None = date).
FIELDS_63 = (
    ("Year", "POL_YR_DUR", "FUYYEAR-YEAR", 3, 0),
    ("Cash Value Accumulation", "POL_TOT_CSV_AMT", "FUYCSHV-CASH-VALUE", 11, 2),
    ("Total Payments this Year", "YTD_TOT_PMT_AMT", "FUYTOTPM-TOTAL-PMT", 11, 2),
    ("Total Additional Payments this Year", "YTD_ADD_PRM_AMT", "FUYADLPM-ADDL-PMT", 11, 2),
    ("Number Additional Payments this Year", "YTD_ADD_PRM_QTY", "FUYADNUM-ADDL-NUM", 3, 0),
    ("Total Premium Tax Payments this Year", "YTD_PRM_TAX_AMT", "FUYPRMTX-PREM-TAX", 9, 2),
    ("Interest Credited this Year", "YTD_CRE_ITS_AMT", "FUYINCRD-INT-CREDITED", 11, 2),
    ("Interest Earned at Guaranteed Rate this Year", "YTD_GUA_RT_ITS_AMT", "FUYINGRT-INT-GUAR", 11, 2),
    ("Number of Withdrawals this Year", "YTD_WTD_NBR", "FUYWDNUM-WITHDRAWAL-NUM", 3, 0),
    ("Yearly Cash Value Accumulation", "YTD_CSV_AMT", "FUYCHSYR-YEARLY-CV", 11, 2),
    ("Number Transfers This Year", "YTD_TRF_QTY", "FUYTRNUM-TRANSFERS-NUM", 3, 0),
    ("Number Allocation Changes This Year", "YTD_ALC_CHG_QTY", "FUYACNUM-ALLOC-CHANGES-NUM", 3, 0),
    ("Year-To-Date Charge Free Withdrawal", "YTD_FRE_WTD_AMT", "FUYFWAMT-CHG-FREE-WDWL-AMT", 11, 2),
    ("Year-To-Date Charge Free Withdrawal Percentage", "CHG_FREE_WDWL_PCT", "FUYFWPCT-CHG-FREE-WDWL-PCT", 5, 2),
    ("Year-To-Date MVA Free Withdrawal", "YTD_MVA_FRE_AMT", "FUYFMAMT-MVA-FREE-WDWL-AMT", 11, 2),
    ("Adjusted Beginning of Year Accumulation Value", "POL_YR_MVA_CSV_AMT", "FUYACSHV-ADJ-CASH-VALUE", 11, 2),
    ("Fixed Fund Beginning Year Balance", "FND_BEG_YR_BAL_AMT", "FUYFBYBA-FIX-ACT-BEG-YEAR-BAL", 13, 2),
    ("Total Transfer Amount", "FND_TRS_AMT", "FUYTDTRN-YTD-FIX-ACT-TRNSFR", 13, 2),
    ("Number of Transfers", "FND_TRS_CNT_QTY", "FUYTDFNT-YTD-FIX-ACT-TRNSFERS", 3, 0),
    ("Beginning of Year Variable Account Balance", "BEG_YR_VAR_ACT_BAL", "FUYBYVBL-BEG-YR-VAR-ACCT-BAL", 11, 2),
    ("Carry Forward Charge Free Withdrawal Amount", "CRY_FWD_FRE_WD_AMT", "FUYCFFWA-CARRY-FWD-FREE-WD-AMT", 11, 2),
    ("Carry Forward Charge Free Withdrawal Percent", "CRY_FWD_FRE_WD_PCT", "FUYCFFWP-CARRY-FWD-FREE-WD-PCT", 5, 2),
)
FIELDS_64 = (
    ("Calender Year-End Date", "CAL_YR_END_DT", "FCYYEDTE-CAL-YEAR-END-DATE", 0, None),
    ("Unloaned Cash Value", "UNLOANED_CSV_AMT", "FCYYEPCV-YE-UNLOANED-CASH-VAL", 11, 2),
    ("Loaned Cash Value", "LOANED_CSV_AMT", "FCYYELON-YE-LOANED-CASH-VAL", 11, 2),
    ("Required Minimum Distribution Amount", "RQR_MIN_DTB_AMT", "FCYRMDAM-REQR-MIN-DIST-AMOUNT", 11, 2),
    ("Regular Minimum Distribution Amount", "REG_MIN_DTB_AMT", "FCYREGMD-REG-MIN-DIST-AMOUNT", 11, 2),
    ("Regular Premium Accumulation", "CAL_YR_REG_PRM_AMT", "FCYRGPRM-CAL-REG-PREMS", 11, 2),
    ("Additional Premium Accumulation", "CAL_YR_ADD_PRM_AMT", "FCYADPRM-CAL-ADDL-PREMS", 11, 2),
    ("Net Withdrawal Accumulation", "CAL_YR_NET_WTD_AMT", "FCYNWDWL-CAL-NET-WDWL-ACCUM", 11, 2),
    ("Withdrawal Charge Accumulation", "CAL_YR_WTD_CRG_AMT", "FCYWDWLC-CAL-WITHDRAWAL-CHG", 11, 2),
    ("Initial Expectation of Life Factor", "INT_LIFE_FCT", "FCYIFACT-INITIAL-EXP-FACTOR", 3, 1),
    ("Non-Regular Contributions", "CAL_YR_NRG_PRM_AMT", "FCYNONRC-NON-REG-CONTRIBS", 11, 2),
    ("Actuarial Value of Additional Benefits", "PV_ADDL_BENS", "FCYPVADB-PV-ADDL-BENS", 11, 2),
)
FLAG_COLUMNS = {
    "63": ("REVS_PRC_GEN_IND",),
    "64": ("YR_END_ACT_BAL_IND", "RMD_NOT_IND", "RMD_REMINDER_IND",
           "RMD_CLC_IND", "RMD_DEFERRED_IND"),
}
TABLES = {"63": "LH_POL_YR_TOT", "64": "LH_POL_CAL_YR_TOT"}
_UNKNOWN_FLAG = (
    "EXAMPLE DATA — reserved/user bits have no DB2 source; the captured zeros "
    "are illustrative, not verified live bits."
)


def _value(row, column, segment):
    if column not in row:
        raise ValueError(f"Segment {segment} source column is missing: {TABLES[segment]}.{column}")
    return row[column]


def _calendar_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip())


def _field_token(row, spec, segment):
    name, column, _, digits, decimals = spec
    value = _value(row, column, segment)
    note = f"Live source: {TABLES[segment]}.{column}."
    if value is None:
        # Live DB2 NULL slots are zero-shaped on the captured mainframe screen.
        # Retain that layout, but never label the slot as a stored numeric zero.
        text = "**/**/****" if decimals is None else (
            "0" if decimals == 0 else "." + "0" * decimals
        )
        return {**_tok(text, name), "dim": True,
                "note": note + " DB2 NULL, not a stored zero; CyberLife null-slot display."}
    try:
        if decimals is None:
            text = _date_display(_calendar_date(value))
        else:
            packed = _packed_decimal(value, digits, decimals)
            if decimals == 0:
                text = ("-" if packed.endswith("D") else "") + str(int(packed[:-1]))
            else:
                text = _decimal_display(value, decimals)
    except (ValueError, ArithmeticError) as exc:
        raise ValueError(f"Invalid Segment {segment} {column}: {value!r}") from exc
    return {**_tok(text, name), "note": note}


def _flag_groups(row, segment):
    bits = []
    for column in FLAG_COLUMNS[segment]:
        value = _value(row, column, segment)
        if value is None:
            bits.append({**_tok("?", "Flag Byte A"), "dim": True,
                         "note": f"Live source: {TABLES[segment]}.{column}. DB2 NULL, not zero."})
            continue
        bit = str(value).strip()
        if bit not in ("0", "1"):
            raise ValueError(f"Invalid Segment {segment} flag {column}: {value!r}")
        bits.append({**_tok(bit, "Flag Byte A"),
                     "note": f"Live source: {TABLES[segment]}.{column}."})
    bits.append(_example("0" * (8 - len(bits)), "Flag Byte A", _UNKNOWN_FLAG))
    names = ("User Flag Byte",) if segment == "63" else ("Flag Byte B", "Flag Byte C", "Flag Byte U")
    return [bits] + [[_example("00000000", name, _UNKNOWN_FLAG)] for name in names]


def _build(pi, segment):
    table = TABLES[segment]
    rows = pi.fetch_table(table)
    error = pi.table_error(table)
    if error:
        raise ValueError(f"Segment {segment} {table}: {error}")
    if not rows:
        return None
    specs = FIELDS_63 if segment == "63" else FIELDS_64
    keyed = {}
    for row in rows:
        value = _value(row, specs[0][1], segment)
        if value is None:
            raise ValueError(f"Segment {segment} year key is DB2 NULL")
        try:
            if segment == "63":
                text = _field_token(row, specs[0], segment)["text"]
                key = int(text)
                if not 0 <= key <= 255:
                    raise ValueError("Policy year exceeds its binary byte")
            else:
                key = _calendar_date(value)
                if key.year in (1, 1900, 9999) or (key.month, key.day) != (12, 31):
                    raise ValueError("Calendar year key is not a valid year-end")
        except (ValueError, ArithmeticError) as exc:
            raise ValueError(f"Invalid Segment {segment} {specs[0][1]}: {value!r}") from exc
        if key in keyed:
            raise ValueError(f"Segment {segment} duplicate year key: {key}")
        keyed[key] = row
    lines = [[_sep("  "), _tok(f"62{segment},", "Screen Name"),
              _tok(_policy_display(pi), "Policy Number")]]
    for key in sorted(keyed):
        row = keyed[key]
        groups = [[_tok(segment, "Segment Identification")],
                  [_tok("0108" if segment == "63" else "0074", "Segment Length")]]
        groups.extend(_flag_groups(row, segment))
        groups.extend([_field_token(row, spec, segment)] for spec in specs)
        # Captures have 79 usable cells after the shared two-space left inset.
        lines.extend(_wrap_record_groups(groups, columns=81))
    _append_screen_footer(lines, pi)
    return lines


def build_segment_63(pi):
    """Render every stored policy-year row, including the prior-years bucket 0."""
    return _build(pi, "63")


def build_segment_64(pi):
    """Render every stored calendar-year row; flags come from DB2, not today's date."""
    return _build(pi, "64")
