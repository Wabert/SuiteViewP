"""Strict, source-keyed CyberLife prints; no illustration-rate compilation.

D11 CKCRECCV (106–110) defines inclusive cash-value durations. CKARECPR
(57–71) defines the original premium identifiers and rate types. In particular,
an IAF age is not always an issue age, and identifier duration is not a year
that can safely be subtracted from that age.
"""

from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import re

from suiteview.ratemanager.database_loader import PackageValidationError
from suiteview.ratemanager.layouts import Field, LineRule, RepeatedGroup, ensure_padding_is_blank


CV_COLUMNS = (
    "USER_CODE", "RATE_KEY", "CLASS", "BASE_SERIES", "SUBSERIES", "USER_DEFINED",
    "ISSUE_AGE", "PREMIUM_YEARS", "BENEFIT_YEARS", "FIRST_DURATION",
    "LAST_DURATION", "DURATION_ZERO_VALUE", "DURATION", "RATE",
)
CV_KEYS = ("USER_CODE", "RATE_KEY", "USER_DEFINED", "ISSUE_AGE", "DURATION")
PUI_COLUMNS = (
    "USER_CODE", "PLANCODE", "SEX", "RATECLASS", "ATTAINED_AGE", "TABLE_RATING",
    "RATE", "AUDIT_NUMBER", "CHANGED_DATE",
)
PUI_KEYS = (
    "USER_CODE", "PLANCODE", "SEX", "RATECLASS", "ATTAINED_AGE", "TABLE_RATING",
)
IAF_COLUMNS = (
    "USER_CODE", "SOURCE_PLANCODE", "SOURCE_IAF_VERSION", "SOURCE_EFFECTIVE_DATE",
    "PLANCODE", "IAF_VERSION", "EFFECTIVE_DATE", "FIRST_AGE", "LAST_AGE", "IAR_USE",
    "PAY_AGE", "PAY_AGE_USE", "ME_AGE", "ME_AGE_USE", "VALUE_PER_UNIT",
    "PRODUCTION_CREDIT", "PRODUCTION_CREDIT_USE", "MDRT", "DEFICIENT",
    "SPECIAL_BENEFITS", "R", "LV", "DUR", "RATE_TYPE", "SCALE_START", "SCALE_STOP",
    "PREMIUM_IDENTIFIER", "DURATION_CODE", "SEX", "RATECLASS", "BAND",
    "PLAN_OPTION", "RATE",
)
IAF_KEYS = (
    "USER_CODE", "SOURCE_PLANCODE", "SOURCE_IAF_VERSION", "SOURCE_EFFECTIVE_DATE",
    "PLANCODE", "IAF_VERSION", "EFFECTIVE_DATE", "FIRST_AGE", "LAST_AGE", "IAR_USE",
    "RATE_TYPE", "SCALE_START", "PREMIUM_IDENTIFIER",
)
NSP_COLUMNS = (
    "USER_CODE", "RATE_KEY", "BASIS_ID", "BASIS_DESCRIPTION", "SEX", "RATECLASS",
    "ISSUE_AGE", "DURATION", "EFFECTIVE_DATE", "RATE_PER", "RATE",
)
NSP_KEYS = (
    "USER_CODE", "RATE_KEY", "BASIS_ID", "SEX", "RATECLASS",
    "ISSUE_AGE", "DURATION", "EFFECTIVE_DATE",
)

_NUMBER = re.compile(r"[+-]?(?:(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?|\.\d+)-?")
_CV_HEADER = re.compile(
    r"\s*(?P<user>\d{2})\s+(?P<class>[A-Z0-9])-(?P<base>[A-Z0-9 ]{3})-"
    r"(?P<sub>[A-Z0-9 ]{2})\s+(?P<defined>.{0,8}?)\s+"
    r"(?P<age>\d{2,3})\s+(?P<prem>\d{2,3})\s+(?P<ben>\d{2,3})\s+"
    r"(?P<first>\d{2,3})\s+(?P<last>\d{2,3})\s+(?P<zero>NO ZERO DUR|\S+)\s*"
)
_CV_LABELS = (
    "USER ID CLASS-BASE-SUB USER DEFINED AGE PREM YEARS BENF YEARS "
    "FIRST DUR LAST DUR DURATION ZERO VALUE"
)
CVF_INFERENCE_RULE = "negative-header-initial-decline-v1"


def _fail(path, line, message):
    raise PackageValidationError(f"{path}:{line}: {message}")


def _lines(path, *, null_padding=False):
    path = Path(path)
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("cp1252")
        except UnicodeDecodeError as exc:
            _fail(path, 1, f"Unsupported source encoding: {exc}")
    for number, line in enumerate(text.split("\n"), 1):
        line = line.rstrip("\r").lstrip("\f")
        if null_padding:
            if re.search(r"[^\s\x00]\x00+[^\s\x00]", line):
                _fail(path, number, "NUL inside a numeric field or identifier.")
            line = line.replace("\x00", "")
        if any(ord(char) < 32 for char in line):
            _fail(path, number, "Unsupported control character in source line.")
        yield number, line


def _decimal(token, path, line, *, scale=None):
    token = token.strip()
    if not _NUMBER.fullmatch(token) or (
        token.endswith("-") and token.startswith(("+", "-"))
    ):
        _fail(path, line, f"Invalid numeric value {token!r}.")
    value = Decimal(token.rstrip("-").replace(",", ""))
    if token.endswith("-"):
        value = -value
    if scale is not None and value.as_tuple().exponent < -scale:
        _fail(path, line, f"Value {token!r} exceeds {scale} decimal places.")
    return value


def _integer(token, path, line, *, maximum=999):
    if not re.fullmatch(r"\d+", token.strip()):
        _fail(path, line, f"Invalid integer {token!r}.")
    value = int(token)
    if value > maximum:
        _fail(path, line, f"Integer {token!r} exceeds {maximum}.")
    return value


def _date(token, path, line, *, optional=False):
    token = token.strip()
    if not token and optional:
        return None
    fmt = "%m%d%Y" if re.fullmatch(r"\d{8}", token) else "%m/%d/%Y"
    if not re.fullmatch(r"\d{8}|\d{2}/\d{2}/\d{4}", token):
        _fail(path, line, f"Invalid date {token!r}.")
    try:
        return datetime.strptime(token, fmt).date()
    except ValueError:
        _fail(path, line, f"Invalid calendar date {token!r}.")


def _ctx_path(context):
    return context["path"], context["line"]


def _text(token, _context):
    return token.strip()


def _ctx_integer(maximum=999):
    def convert(token, context):
        path, line = _ctx_path(context)
        return _integer(token, path, line, maximum=maximum)

    return convert


def _ctx_decimal(scale=None):
    def convert(token, context):
        path, line = _ctx_path(context)
        return _decimal(token, path, line, scale=scale)

    return convert


def _ctx_date(optional=False):
    def convert(token, context):
        path, line = _ctx_path(context)
        return _date(token, path, line, optional=optional)

    return convert


class _Rows:
    """Keep identical source occurrences; detect conflicting natural keys."""

    def __init__(self, path, keys):
        self.path = path
        self.keys = keys
        self.rows = []
        self.seen = {}

    def add(self, row, line):
        key = tuple(row[name] for name in self.keys)
        previous = self.seen.get(key)
        if previous is not None and previous[0] != row:
            _fail(self.path, line, f"Conflicting duplicate key {key!r}; first at line {previous[1]}.")
        if previous is None:
            self.seen[key] = (row, line)
        self.rows.append(row)

    def finish(self, line):
        if not self.rows:
            _fail(self.path, line, "No supported rate records found.")
        return self.rows


def _cvf_initial_minimum(values, last, signed_zero, explicit_positive):
    """Find a strict initial trough anchored by a known negative starting value."""
    previous = abs(signed_zero)
    for duration in range(1, last + 1):
        magnitude = abs(values[duration][0])
        if magnitude == previous:
            return None
        if magnitude > previous:
            minimum = duration - 1
            if any(0 < item < minimum for item in explicit_positive):
                return None
            return minimum
        previous = magnitude
    return None


def parse_cvf(
    path, *, infer_early_negatives: bool = False,
    inference_audit: list[dict] | None = None,
) -> list[dict[str, object]]:
    """Floor signed CVs, optionally inferring the strict decline before a minimum.

    Inference is an opt-in assumption, not recovered source signs. Audit records
    are emitted only after the complete raw source has passed validation.
    """
    if not isinstance(infer_early_negatives, bool):
        raise PackageValidationError("CVF sign inference must be true or false.")
    result = _Rows(path, CV_KEYS)
    current = None
    values = {}
    explicit_positive = set()
    inferred_records = {}
    seen_report = False
    header_pending = False
    grid_header = False
    line_number = 1

    def finish_record():
        nonlocal current, values, grid_header, explicit_positive
        if current is None:
            return
        first, last = current["FIRST_DURATION"], current["LAST_DURATION"]
        missing = set(range(first, last + 1)) - values.keys()
        if missing:
            _fail(path, line_number, f"Incomplete cash-value record; missing duration {min(missing)}.")
        zero = current["DURATION_ZERO_VALUE"]
        if zero is not None and 0 in values and abs(values[0][0]) != abs(zero):
            _fail(path, values[0][1], "Duration-zero header disagrees with grid magnitude.")
        for duration, (rate, source_line) in values.items():
            if first <= duration <= last:
                result.add({**current, "DURATION": duration, "RATE": zero if duration == 0 else rate}, source_line)
            elif rate != 0:
                _fail(path, source_line, f"Nonzero padding outside FIRST/LAST duration: {duration}.")
        if infer_early_negatives and first == 0 and zero is not None and zero < 0:
            minimum = _cvf_initial_minimum(values, last, zero, explicit_positive)
            inferred = {}
            if minimum is not None:
                for duration in range(1, minimum):
                    rate, source_line = values[duration]
                    if rate > 0:
                        inferred[duration] = {
                            **{key: current[key] for key in CV_KEYS if key != "DURATION"},
                            "DURATION": duration, "printed_rate": str(rate),
                            "loaded_rate": "0.00", "source_line": source_line,
                            "minimum_duration": minimum,
                            "minimum_rate": str(values[minimum][0]),
                            "header_zero": str(zero),
                        }
            record_key = tuple(current[key] for key in CV_KEYS if key != "DURATION")
            if record_key in inferred_records:
                # A repeated record with an explicit '+' must veto inference too.
                inferred = {
                    duration: audit for duration, audit in inferred_records[record_key].items()
                    if duration in inferred
                }
            inferred_records[record_key] = inferred
        current, values, grid_header, explicit_positive = None, {}, False, set()

    for line_number, line in _lines(path, null_padding=True):
        stripped = line.strip()
        if not stripped:
            continue
        if re.fullmatch(
            r"1CKCVDVPC\s+RUN DATE\s*=\s*\d{2}/\d{2}/\d{2,4}\s+"
            r"CASH VALUE RATES\s+PAGE\s+\d+", stripped,
        ):
            seen_report = True
            continue
        if " ".join(stripped.removeprefix("0").split()) == _CV_LABELS:
            if not seen_report:
                _fail(path, line_number, "Missing CKCVDVPC CASH VALUE RATES report heading.")
            if header_pending:
                _fail(path, line_number, "Cash-value header has no record.")
            finish_record()
            header_pending = True
            continue
        if header_pending:
            match = _CV_HEADER.fullmatch(line)
            if match is None:
                _fail(path, line_number, "Malformed cash-value record header.")
            data = match.groupdict()
            first, last = int(data["first"]), int(data["last"])
            if first > last:
                _fail(path, line_number, "FIRST DUR exceeds LAST DUR.")
            zero = (
                None if data["zero"] == "NO ZERO DUR"
                else _decimal(data["zero"], path, line_number, scale=2)
            )
            if zero is None and first == 0:
                _fail(path, line_number, "NO ZERO DUR requires a positive FIRST duration.")
            current = {
                "USER_CODE": data["user"],
                "RATE_KEY": data["class"] + data["base"] + data["sub"],
                "CLASS": data["class"], "BASE_SERIES": data["base"],
                "SUBSERIES": data["sub"], "USER_DEFINED": data["defined"].strip(),
                "ISSUE_AGE": int(data["age"]), "PREMIUM_YEARS": int(data["prem"]),
                "BENEFIT_YEARS": int(data["ben"]), "FIRST_DURATION": first,
                "LAST_DURATION": last,
                "DURATION_ZERO_VALUE": zero,
            }
            header_pending = False
            continue
        if re.fullmatch(r"-+", stripped):
            if current is None:
                _fail(path, line_number, "Grid separator outside a cash-value record.")
            continue
        if stripped.startswith("DURATION"):
            expected = "DURATION" + "".join(f"({i})" for i in range(1, 11))
            if re.sub(r"\s+", "", stripped) != expected or current is None:
                _fail(path, line_number, "Unsupported cash-value grid heading.")
            grid_header = True
            continue
        match = re.fullmatch(r"\s*(\d{3})-(\d{3})\s+(.+?)\s*", line)
        if match and current is not None and grid_header:
            start, end = int(match[1]), int(match[2])
            tokens = match[3].split()
            if end != start + 9 or len(tokens) != 10:
                _fail(path, line_number, "Expected ten values for the printed duration range.")
            # NO ZERO DUR starts at FIRST in the printed decade containing FIRST-1.
            first = current["FIRST_DURATION"]
            offset = first - ((first - 1) // 10) * 10 if current["DURATION_ZERO_VALUE"] is None else 0
            for duration, token in enumerate(tokens, start + offset):
                rate = _decimal(token, path, line_number, scale=2)
                if duration in values:
                    _fail(path, line_number, f"Repeated grid duration {duration}.")
                values[duration] = (rate, line_number)
                if token.startswith("+"):
                    explicit_positive.add(duration)
            continue
        _fail(path, line_number, f"Unsupported CVF section or layout: {stripped[:100]!r}.")
    if header_pending:
        _fail(path, line_number, "Cash-value header has no record.")
    finish_record()
    rows = result.finish(line_number)
    adjustments = [
        audit for record in inferred_records.values() for audit in record.values()
    ]
    inferred_keys = {tuple(audit[key] for key in CV_KEYS) for audit in adjustments}
    # Validate signed headers, padding and duplicate source keys before flooring.
    zero = Decimal("0.00")
    for row in rows:
        if inferred_keys and tuple(row[key] for key in CV_KEYS) in inferred_keys:
            row["RATE"] = zero
        for column in ("RATE", "DURATION_ZERO_VALUE"):
            if row[column] is not None and row[column] < 0:
                row[column] = zero
    if inference_audit is not None:
        inference_audit.extend(adjustments)
    return rows


def parse_nsp(path) -> list[dict[str, object]]:
    """Read explicitly supplied NSP values, never derive them from another rate.

    This is SuiteView's canonical CSV contract, not a claimed CyberLife print
    layout. BASIS_ID/DESCRIPTION identify the independently verified actuarial
    basis; RATE is premium for RATE_PER face amount in the same currency.
    """
    result = _Rows(path, NSP_KEYS)
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if tuple(reader.fieldnames or ()) != NSP_COLUMNS:
            _fail(
                path, 1, "NSP requires the canonical CSV header with explicit basis "
                "and RATE_PER units. CVF, PUI and IAF tax premiums are not NSP. "
                f"Expected: {','.join(NSP_COLUMNS)}",
            )
        try:
            for record in reader:
                line = reader.line_num
                if set(record) != set(NSP_COLUMNS) or any(v is None for v in record.values()):
                    _fail(path, line, "NSP CSV row has missing or extra columns.")
                row = {}
                for column, size in (
                    ("USER_CODE", 2), ("RATE_KEY", 32), ("BASIS_ID", 32),
                    ("BASIS_DESCRIPTION", 500), ("SEX", 1), ("RATECLASS", 1),
                ):
                    value = record[column].strip()
                    if column != "BASIS_DESCRIPTION":
                        value = value.upper()
                    if (
                        len(value) > size or not value.isascii()
                        or any(ord(char) < 32 for char in value)
                        or (not value and column not in ("SEX", "RATECLASS"))
                    ):
                        _fail(path, line, f"Invalid NSP {column}; explicit basis and identifiers are required.")
                    row[column] = value
                if not re.fullmatch(r"\d{2}", row["USER_CODE"]):
                    _fail(path, line, "NSP USER_CODE must contain exactly two digits.")
                for column in ("ISSUE_AGE", "DURATION"):
                    row[column] = _integer(record[column], path, line)
                token = record["EFFECTIVE_DATE"].strip()
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", token):
                    _fail(path, line, "NSP EFFECTIVE_DATE must be YYYY-MM-DD.")
                try:
                    row["EFFECTIVE_DATE"] = datetime.strptime(token, "%Y-%m-%d").date()
                except ValueError:
                    _fail(path, line, "NSP EFFECTIVE_DATE is not a valid calendar date.")
                for column in ("RATE_PER", "RATE"):
                    row[column] = _decimal(record[column], path, line, scale=8)
                if row["RATE_PER"] <= 0 or row["RATE"] < 0:
                    _fail(path, line, "NSP RATE_PER must be positive and RATE cannot be negative.")
                result.add({column: row[column] for column in NSP_COLUMNS}, line)
        except csv.Error as exc:
            _fail(path, reader.line_num, f"Invalid NSP CSV: {exc}")
    return result.finish(reader.line_num)


def _check_spaces(line, spans, path, number):
    if not ensure_padding_is_blank(line, spans):
        _fail(path, number, "Unexpected data outside documented fixed-width fields.")


_PUI_ROW_RULE = LineRule("pui-row", (
    Field("PLANCODE", 11, 22, _text),
    Field("SEX", 23, 31, _text),
    Field("RATECLASS", 32, 40, _text),
    Field("ATTAINED_AGE", 41, 49, _ctx_integer()),
    Field("TABLE_RATING", 50, 58, _text),
    Field("RATE", 59, 73, _ctx_decimal(scale=6)),
    Field("AUDIT_NUMBER", 74, 80, _text),
    Field("CHANGED_DATE", 81, 91, _ctx_date()),
))


def parse_pui(path) -> list[dict[str, object]]:
    """Read CJUDTPUI's printed natural key and six-decimal rate without remapping."""
    result = _Rows(path, PUI_KEYS)
    user = None
    table_seen = False
    columns_seen = False
    end_seen = False
    section_pending = False
    totals = None
    all_entries = False
    definitions = set()
    definition_lines = {
        "PLAN CD PLAN CODE CHAR 11 C1 PUI RATE PUI RATE NUM 11, 6 N2",
        "SEX PLAN SEX CODE CHAR 1 C2",
        "CLASS PLAN RATECLASS CHAR 1 C3",
        "ATT AGE PLAN ATTAINED AGE NUM 3, 0 N1",
        "TAB RATE PLAN TABLE RATING CHAR 2 C4",
    }
    line_number = 1
    for line_number, line in _lines(path):
        stripped = line.strip()
        words = " ".join(stripped.split())
        if not stripped or words == "0":
            continue
        if end_seen:
            _fail(path, line_number, "Unexpected content after END-OF-JOB.")
        if re.fullmatch(
            r"1DATE\s+\d{2}/\d{2}/\d{2,4}\s+CYBERLIFE ONLINE TABLES LIST\s+PAGE\s+\d+",
            stripped,
        ):
            continue
        if words == "0 CONTROL STATEMENTS FOLLOW:":
            continue
        if re.fullmatch(r"CJUDTPUI(?:\s+\d+)?", stripped) and not table_seen:
            continue
        if words.startswith("0TABLE:"):
            if not re.fullmatch(
                r"0TABLE: CJUDTPUI PROCESSING OPTIONS: USERID = (?:ALL|\d{2}) "
                r"AUDIT# = \S+ DELETED RECORDS = OMIT", words,
            ):
                _fail(path, line_number, "Unsupported table or processing options; expected CJUDTPUI.")
            table_seen = True
            all_entries = "USERID = ALL AUDIT# = ALL" in words
            continue
        if re.fullmatch(r"0?\s*USER \d{2} UNIQUE ENTRIES", stripped):
            if not table_seen:
                _fail(path, line_number, "Summary outside CJUDTPUI table.")
            continue
        match = re.fullmatch(
            r"0TABLE CONTAINS ([\d,]+) ENTRIES OF WHICH ([\d,]+) HAVE BEEN MARKED FOR DELETION\.",
            words,
        )
        if match:
            totals = (int(match[1].replace(",", "")), int(match[2].replace(",", "")))
            continue
        if words == "0*** END-OF-JOB ***":
            end_seen = True
            continue
        if words in definition_lines:
            definitions.add(words)
            continue
        if words in {
            "0 ARGUMENT DESCRIPTIONS FUNCTION DESCRIPTIONS",
            "NAME DESCRIPTION TYPE LENGTH KYWD NAME DESCRIPTION TYPE LENGTH KYWD",
        }:
            continue
        if re.fullmatch(r"[- ]+", stripped):
            continue
        match = re.fullmatch(r"0\s*ENTRIES FOR USER (\d{2})(?:\s+CONTINUED)?", stripped)
        if match:
            if not table_seen:
                _fail(path, line_number, "User section outside CJUDTPUI table.")
            if section_pending and user != match[1]:
                _fail(path, line_number, "PUI user section has no rate rows.")
            user = match[1]
            columns_seen = False
            section_pending = True
            continue
        if words == "0 PLAN CD SEX CLASS ATT AGE TAB RATE PUI RATE AUDIT# CHANGED":
            if user is None:
                _fail(path, line_number, "PUI columns have no user section.")
            columns_seen = True
            continue
        if not table_seen or not columns_seen or user is None:
            _fail(path, line_number, f"Unsupported PUI section or missing headers: {words[:100]!r}.")
        if definitions and definitions != definition_lines:
            _fail(path, line_number, "Incomplete or unsupported CJUDTPUI argument definitions.")
        _check_spaces(line, _PUI_ROW_RULE.spans, path, line_number)
        row = _PUI_ROW_RULE.parse(line, {"path": path, "line": line_number})
        plan = row["PLANCODE"]
        sex = row["SEX"]
        rateclass = row["RATECLASS"]
        table_rating = row["TABLE_RATING"]
        if not plan or len(sex) > 1 or len(rateclass) > 1 or len(table_rating) > 2:
            _fail(path, line_number, "Malformed PUI source key.")
        result.add({
            "USER_CODE": user, "PLANCODE": plan, "SEX": sex, "RATECLASS": rateclass,
            "ATTAINED_AGE": row["ATTAINED_AGE"], "TABLE_RATING": table_rating,
            "RATE": row["RATE"], "AUDIT_NUMBER": row["AUDIT_NUMBER"],
            "CHANGED_DATE": row["CHANGED_DATE"],
        }, line_number)
        section_pending = False
    if section_pending:
        _fail(path, line_number, "PUI user section has no rate rows.")
    if totals and all_entries and len(result.rows) != totals[0] - totals[1]:
        _fail(path, line_number, "Printed table totals do not match parsed nondeleted rows.")
    return result.finish(line_number)


_IAF_PLAN_LABELS = (
    "PLAN CODE V EFFDATE FST LST USE PAY-AGE USE ME-AGE USE VAL PER UNIT "
    "PROD CRED AMT USE MDRT DEF SPEC BENEFITS R LV DUR"
)
_IAF_RATE_LABELS = (
    "**PREMIUM RATES- TYP START STOP IDENT RATE IDENT RATE IDENT RATE IDENT RATE"
)
_IAF_PRODUCT_RULE = LineRule("whole-life-iaf-product", (
    Field("SOURCE_PLANCODE", 2, 13, _text),
    Field("SOURCE_IAF_VERSION", 13, 16, _text),
    Field("SOURCE_EFFECTIVE_DATE", 16, 24, _ctx_date()),
    Field("FIRST_AGE", 25, 28, _ctx_integer()),
    Field("LAST_AGE", 29, 32, _ctx_integer()),
    Field("IAR_USE", 34, 35, _ctx_integer(maximum=1)),
    Field("PAY_AGE", 41, 44, _ctx_integer()),
    Field("PAY_AGE_USE", 46, 47, _ctx_integer(maximum=1)),
    Field("ME_AGE", 53, 56, _ctx_integer()),
    Field("ME_AGE_USE", 58, 59, _ctx_integer(maximum=1)),
    Field("VALUE_PER_UNIT", 60, 74, _ctx_decimal()),
    Field("PRODUCTION_CREDIT", 75, 89, _ctx_decimal()),
    Field("PRODUCTION_CREDIT_USE", 91, 92, _ctx_integer()),
    Field("MDRT", 93, 97, _text),
    Field("DEFICIENT", 100, 101, _ctx_integer()),
    Field("SPECIAL_BENEFITS", 102, 117, _text),
    Field("R", 118, 119, _text),
    Field("LV", 120, 122, _text),
    Field("DUR", 123, 133, _text),
))

_IAF_RATE_HEADER_RULE = LineRule("whole-life-iaf-rate-header", (
    Field("RATE_TYPE", 19, 20, _text),
    Field("SCALE_START", 23, 31, _ctx_date()),
    Field("SCALE_STOP", 33, 41, _ctx_date(optional=True)),
))

_IAF_RATE_CELL_GROUP = RepeatedGroup("whole-life-iaf-rate-cells", (43, 65, 87, 109), (
    Field("PREMIUM_IDENTIFIER", 0, 7, _text),
    Field("RATE", 8, 20, _ctx_decimal()),
), required_field="PREMIUM_IDENTIFIER")


def _iaf_product(line, path, number):
    _check_spaces(line, _IAF_PRODUCT_RULE.spans, path, number)
    row = _IAF_PRODUCT_RULE.parse(line, {"path": path, "line": number})
    plan = row["SOURCE_PLANCODE"]
    if not re.fullmatch(r"\S{1,11}", plan):
        _fail(path, number, "Invalid IAF source plancode.")
    if row["FIRST_AGE"] > row["LAST_AGE"]:
        _fail(path, number, "IAF first age exceeds last age.")
    return row


def _iaf_aliases(line, path, number):
    text = line[31:].strip()
    alias = re.compile(r"(\S{1,11})\s+(?:(\S{1,3})\s+)?(\d{8})(?:\s+|$)")
    result = []
    while text:
        match = alias.match(text)
        if match is None:
            _fail(path, number, f"Unsupported IAF search-key layout: {text[:60]!r}.")
        result.append({
            "PLANCODE": match[1], "IAF_VERSION": match[2] or "",
            "EFFECTIVE_DATE": _date(match[3], path, number),
        })
        text = text[match.end():]
    if not result:
        _fail(path, number, "Empty IAF search-key section.")
    return result


def parse_iaf(path, user_code) -> list[dict[str, object]]:
    """Read uncompiled IAF premium cells, retaining source records and aliases.

    Uses the existing IAFParser's documented fixed-column mechanics, but every
    field and section is validated. Unsupported auxiliary sections fail closed.
    Rows expand search aliases, never age ranges or premium duration codes.
    """
    user_code = str(user_code).strip()
    if not re.fullmatch(r"\d{2}", user_code):
        _fail(path, 1, "IAF user/company code must be exactly two digits.")
    result = _Rows(path, IAF_KEYS)
    product = None
    aliases = []
    rates = []
    scale = None
    scale_count = 0
    rate_section = False
    aliases_section = False
    pending_product = False
    pending_rate = False
    page_header = False
    line_number = 1

    def finish_product():
        if product is None:
            return
        if pending_rate:
            _fail(path, line_number, "Truncated IAF premium section.")
        if not aliases or not rates:
            _fail(path, line_number, "Incomplete IAF record: search keys and premium rates are required.")
        expected = (product["SOURCE_PLANCODE"], product["SOURCE_IAF_VERSION"],
                    product["SOURCE_EFFECTIVE_DATE"])
        if expected not in {
            (a["PLANCODE"], a["IAF_VERSION"], a["EFFECTIVE_DATE"]) for a in aliases
        }:
            _fail(path, line_number, "IAF search keys omit the source record's own key.")
        for alias in aliases:
            for rate, source_line in rates:
                result.add({"USER_CODE": user_code, **product, **alias, **rate}, source_line)

    for line_number, line in _lines(path):
        stripped = line.strip()
        words = " ".join(stripped.split())
        if not stripped:
            continue
        if re.fullmatch(r"1 {40,}\S.*", line):
            continue
        if re.fullmatch(
            r"0DATE\s+\d{2}/\d{2}/\d{2,4}\s+PRINT ISSUE AGE DESCRIPTION FILE\s+PAGE\s+\d+",
            stripped,
        ):
            page_header = True
            continue
        if words == _IAF_PLAN_LABELS:
            if pending_product:
                _fail(path, line_number, "IAF plan heading has no record.")
            pending_product = True
            page_header = False
            continue
        if len(line) > 2 and line[:2] == "  " and not line[2].isspace() and line[2] != "*":
            finish_product()
            product = _iaf_product(line, path, line_number)
            aliases, rates, scale, scale_count = [], [], None, 0
            pending_product = False
            rate_section = aliases_section = pending_rate = False
            continue
        if pending_product:
            _fail(path, line_number, "Expected IAF plan record after heading.")
        if line.startswith(" *** PLAN SEARCH KEYS"):
            if product is None or rates:
                _fail(path, line_number, "Search-key section outside a new IAF record.")
            if line[21:31].strip():
                _fail(path, line_number, "Unexpected IAF search-key prefix.")
            aliases.extend(_iaf_aliases(line, path, line_number))
            aliases_section = True
            continue
        if words == _IAF_RATE_LABELS:
            if product is None or not aliases:
                _fail(path, line_number, "Premium section requires a plan and search keys.")
            rate_section = True
            aliases_section = False
            pending_rate = not (page_header and scale_count > 0)
            page_header = False
            continue
        if aliases_section and not line[:31].strip():
            aliases.extend(_iaf_aliases(line, path, line_number))
            continue
        if not rate_section or line[:19].strip() or len(line) <= 19:
            _fail(path, line_number, f"Unsupported IAF section or layout: {stripped[:100]!r}.")
        new_scale = bool(line[19:20].strip())
        if new_scale:
            if scale is not None and scale_count == 0:
                _fail(path, line_number, "Previous premium scale has no rate cells.")
            scale = _IAF_RATE_HEADER_RULE.parse(
                line, {"path": path, "line": line_number},
            )
            rate_type = scale["RATE_TYPE"]
            if rate_type not in "0ABCFGLMNSTWXY":
                _fail(path, line_number, f"Unknown IAF premium rate type {rate_type!r}.")
            start = scale["SCALE_START"]
            stop = scale["SCALE_STOP"]
            if stop is not None and stop < start:
                _fail(path, line_number, "Premium scale stop date precedes start date.")
            scale_count = 0
            pending_rate = True
        elif scale is None:
            _fail(path, line_number, "Premium cells have no rate type/start date.")
        spans = list(_IAF_RATE_HEADER_RULE.spans) if new_scale else []
        spans.extend(_IAF_RATE_CELL_GROUP.spans)
        count = 0
        for cell in _IAF_RATE_CELL_GROUP.parse(
            line, {"path": path, "line": line_number},
        ):
            ident = cell["PREMIUM_IDENTIFIER"]
            if not re.fullmatch(r"\d{2}\S{5}", ident):
                _fail(path, line_number, f"Malformed premium identifier {ident!r}.")
            rate = {
                **scale, "PREMIUM_IDENTIFIER": ident, "DURATION_CODE": ident[:2],
                "SEX": ident[2], "RATECLASS": ident[3], "BAND": ident[4],
                "PLAN_OPTION": ident[5:], "RATE": cell["RATE"],
            }
            rates.append((rate, line_number))
            count += 1
        _check_spaces(line, spans, path, line_number)
        if not count and not new_scale:
            _fail(path, line_number, "Empty premium-rate continuation.")
        if count:
            scale_count += count
            pending_rate = False
    if pending_product or pending_rate:
        _fail(path, line_number, "Truncated IAF record or premium section.")
    finish_product()
    return result.finish(line_number)
