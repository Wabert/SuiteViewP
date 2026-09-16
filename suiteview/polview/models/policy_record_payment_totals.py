"""Live Payment Accumulation (60), verified against the UL045809 capture."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from .policy_record_builder import (
    _append_screen_footer, _date_display, _decimal_display, _example,
    _policy_display, _sep, _tok, _wrap_record_groups,
)


def _value_token(row, spec):
    field, column = spec["name"], spec["db2"].split(".")[1]
    if column not in row:
        raise ValueError(f"Segment 60 source column is missing: {spec['db2']}")
    value = row[column]
    kind = spec["kind"]
    note = f"Live source: {spec['db2']}."
    if value is None:
        return {
            **_tok("**/**/****" if kind == "date" else (".00" if kind == "amount" else "?"), field),
            "dim": True,
            "note": note + " DB2 NULL, not a stored zero; displayed in CyberLife's null-slot format.",
        }
    if kind == "date":
        if isinstance(value, datetime):
            value = value.date()
        elif not isinstance(value, date):
            value = date.fromisoformat(str(value).strip())
        text = "**/**/****" if value.year in (1900, 9999) else _date_display(value)
    else:
        try:
            number = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"Invalid Segment 60 {column}: {value!r}") from exc
        precision = Decimal("1") if kind == "integer" else Decimal("0.01")
        if not number.is_finite() or number != number.quantize(precision):
            raise ValueError(f"Invalid Segment 60 {column} precision: {value!r}")
        text = str(int(number)) if kind == "integer" else _decimal_display(number, 2)
    return {**_tok(text, field), "note": note}


def build_segment_60(pi, screen):
    sources = {}
    for table in ("LH_POL_TOTALS", "LH_MO_ADD_PMT"):
        sources[table] = pi.fetch_table(table)
        error = pi.table_error(table)
        if error:
            raise ValueError(f"Segment 60 {table}: {error}")
    rows = sources["LH_POL_TOTALS"]
    if not rows:
        if sources["LH_MO_ADD_PMT"]:
            raise ValueError("Segment 60 monthly payments have no policy totals row")
        return None
    if len(rows) != 1:
        raise ValueError("Segment 60 requires exactly one LH_POL_TOTALS row")
    row = rows[0]
    if "MO_ADD_PMT_QTY" not in row or row["MO_ADD_PMT_QTY"] is None:
        raise ValueError("Segment 60 monthly accumulator count is unavailable")
    if Decimal(str(row["MO_ADD_PMT_QTY"])) != 0 or sources["LH_MO_ADD_PMT"]:
        raise ValueError(
            "Segment 60 monthly additional-payment extension is not yet verified; "
            "cannot reconstruct its used-accumulator counter and 12-month layout"
        )
    tokens = []
    for spec in screen["field_specs"]:
        name, kind = spec["name"], spec["kind"]
        if kind in ("reserved", "monthly"):
            continue
        if kind == "header":
            tokens.append(_tok("60" if name == "Segment Identification" else "0139", name))
        elif kind == "flag":
            tokens.append(_example(
                "00000000", name,
                "Reserved byte with no complete DB2 source. The captured zero byte is illustrative.",
            ))
        else:
            tokens.append(_value_token(row, spec))
    lines = [[_sep("  "), _tok("6260,", "Screen Name"), _sep(" "),
              _tok(_policy_display(pi), "Policy Number")]]
    lines.extend(_wrap_record_groups([[token] for token in tokens]))
    _append_screen_footer(lines, pi, min_lines=18)
    return lines
