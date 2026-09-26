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

from suiteview.ratemanager.layouts import Field, LineRule, RepeatedGroup, ensure_padding_is_blank
from suiteview.ratemanager.schema import PackageValidationError


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


class _CvfParser:
    """State machine for CKCVDVPC cash-value report records."""

    def __init__(self, path, infer_early_negatives: bool):
        self.path = path
        self.infer_early_negatives = infer_early_negatives
        self.result = _Rows(path, CV_KEYS)
        self.current = None
        self.values = {}
        self.explicit_positive = set()
        self.inferred_records = {}
        self.seen_report = False
        self.header_pending = False
        self.grid_header = False
        self.line_number = 1

    def parse(self):
        for self.line_number, line in _lines(self.path, null_padding=True):
            self._parse_line(line)
        if self.header_pending:
            _fail(self.path, self.line_number, "Cash-value header has no record.")
        self._finish_record()
        rows = self.result.finish(self.line_number)
        adjustments = [
            audit for record in self.inferred_records.values() for audit in record.values()
        ]
        self._floor_signed_values(rows, adjustments)
        return rows, adjustments

    def _parse_line(self, line):
        stripped = line.strip()
        if not stripped:
            return
        if self._is_report_heading(stripped):
            self.seen_report = True
            return
        if " ".join(stripped.removeprefix("0").split()) == _CV_LABELS:
            self._handle_label_line()
            return
        if self.header_pending:
            self._start_record(line)
            return
        if re.fullmatch(r"-+", stripped):
            self._require_current("Grid separator outside a cash-value record.")
            return
        if stripped.startswith("DURATION"):
            self._handle_grid_heading(stripped)
            return
        if self._handle_duration_row(line):
            return
        _fail(self.path, self.line_number, f"Unsupported CVF section or layout: {stripped[:100]!r}.")

    @staticmethod
    def _is_report_heading(stripped):
        return re.fullmatch(
            r"1CKCVDVPC\s+RUN DATE\s*=\s*\d{2}/\d{2}/\d{2,4}\s+"
            r"CASH VALUE RATES\s+PAGE\s+\d+",
            stripped,
        )

    def _require_current(self, message):
        if self.current is None:
            _fail(self.path, self.line_number, message)

    def _handle_label_line(self):
        if not self.seen_report:
            _fail(self.path, self.line_number, "Missing CKCVDVPC CASH VALUE RATES report heading.")
        if self.header_pending:
            _fail(self.path, self.line_number, "Cash-value header has no record.")
        self._finish_record()
        self.header_pending = True

    def _start_record(self, line):
        match = _CV_HEADER.fullmatch(line)
        if match is None:
            _fail(self.path, self.line_number, "Malformed cash-value record header.")
        data = match.groupdict()
        first, last = int(data["first"]), int(data["last"])
        if first > last:
            _fail(self.path, self.line_number, "FIRST DUR exceeds LAST DUR.")
        zero = None if data["zero"] == "NO ZERO DUR" else _decimal(
            data["zero"], self.path, self.line_number, scale=2,
        )
        if zero is None and first == 0:
            _fail(self.path, self.line_number, "NO ZERO DUR requires a positive FIRST duration.")
        self.current = {
            "USER_CODE": data["user"], "RATE_KEY": data["class"] + data["base"] + data["sub"],
            "CLASS": data["class"], "BASE_SERIES": data["base"], "SUBSERIES": data["sub"],
            "USER_DEFINED": data["defined"].strip(), "ISSUE_AGE": int(data["age"]),
            "PREMIUM_YEARS": int(data["prem"]), "BENEFIT_YEARS": int(data["ben"]),
            "FIRST_DURATION": first, "LAST_DURATION": last, "DURATION_ZERO_VALUE": zero,
        }
        self.header_pending = False

    def _handle_grid_heading(self, stripped):
        expected = "DURATION" + "".join(f"({i})" for i in range(1, 11))
        if re.sub(r"\s+", "", stripped) != expected or self.current is None:
            _fail(self.path, self.line_number, "Unsupported cash-value grid heading.")
        self.grid_header = True

    def _handle_duration_row(self, line):
        match = re.fullmatch(r"\s*(\d{3})-(\d{3})\s+(.+?)\s*", line)
        if not (match and self.current is not None and self.grid_header):
            return False
        start, end = int(match[1]), int(match[2])
        tokens = match[3].split()
        if end != start + 9 or len(tokens) != 10:
            _fail(self.path, self.line_number, "Expected ten values for the printed duration range.")
        offset = self._duration_offset()
        for duration, token in enumerate(tokens, start + offset):
            self._add_duration_value(duration, token)
        return True

    def _duration_offset(self):
        first = self.current["FIRST_DURATION"]
        if self.current["DURATION_ZERO_VALUE"] is None:
            return first - ((first - 1) // 10) * 10
        return 0

    def _add_duration_value(self, duration, token):
        rate = _decimal(token, self.path, self.line_number, scale=2)
        if duration in self.values:
            _fail(self.path, self.line_number, f"Repeated grid duration {duration}.")
        self.values[duration] = (rate, self.line_number)
        if token.startswith("+"):
            self.explicit_positive.add(duration)

    def _finish_record(self):
        if self.current is None:
            return
        first, last = self.current["FIRST_DURATION"], self.current["LAST_DURATION"]
        self._validate_complete_range(first, last)
        zero = self.current["DURATION_ZERO_VALUE"]
        if zero is not None and 0 in self.values and abs(self.values[0][0]) != abs(zero):
            _fail(self.path, self.values[0][1], "Duration-zero header disagrees with grid magnitude.")
        for duration, (rate, source_line) in self.values.items():
            self._add_or_validate_padding(duration, rate, source_line, first, last, zero)
        self._record_inference(first, last, zero)
        self.current, self.values = None, {}
        self.grid_header, self.explicit_positive = False, set()

    def _validate_complete_range(self, first, last):
        missing = set(range(first, last + 1)) - self.values.keys()
        if missing:
            _fail(self.path, self.line_number, f"Incomplete cash-value record; missing duration {min(missing)}.")

    def _add_or_validate_padding(self, duration, rate, source_line, first, last, zero):
        if first <= duration <= last:
            value = zero if duration == 0 else rate
            self.result.add({**self.current, "DURATION": duration, "RATE": value}, source_line)
        elif rate != 0:
            _fail(self.path, source_line, f"Nonzero padding outside FIRST/LAST duration: {duration}.")

    def _record_inference(self, first, last, zero):
        if not (self.infer_early_negatives and first == 0 and zero is not None and zero < 0):
            return
        minimum = _cvf_initial_minimum(self.values, last, zero, self.explicit_positive)
        inferred = self._inferred_adjustments(minimum, zero) if minimum is not None else {}
        record_key = tuple(self.current[key] for key in CV_KEYS if key != "DURATION")
        if record_key in self.inferred_records:
            inferred = {
                duration: audit for duration, audit in self.inferred_records[record_key].items()
                if duration in inferred
            }
        self.inferred_records[record_key] = inferred

    def _inferred_adjustments(self, minimum, zero):
        inferred = {}
        for duration in range(1, minimum):
            rate, source_line = self.values[duration]
            if rate > 0:
                inferred[duration] = {
                    **{key: self.current[key] for key in CV_KEYS if key != "DURATION"},
                    "DURATION": duration, "printed_rate": str(rate),
                    "loaded_rate": "0.00", "source_line": source_line,
                    "minimum_duration": minimum, "minimum_rate": str(self.values[minimum][0]),
                    "header_zero": str(zero),
                }
        return inferred

    @staticmethod
    def _floor_signed_values(rows, adjustments):
        inferred_keys = {tuple(audit[key] for key in CV_KEYS) for audit in adjustments}
        zero = Decimal("0.00")
        for row in rows:
            if inferred_keys and tuple(row[key] for key in CV_KEYS) in inferred_keys:
                row["RATE"] = zero
            for column in ("RATE", "DURATION_ZERO_VALUE"):
                if row[column] is not None and row[column] < 0:
                    row[column] = zero


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
    rows, adjustments = _CvfParser(path, infer_early_negatives).parse()
    if inference_audit is not None:
        inference_audit.extend(adjustments)
    return rows


_NSP_TEXT_COLUMNS = (
    ("USER_CODE", 2),
    ("RATE_KEY", 32),
    ("BASIS_ID", 32),
    ("BASIS_DESCRIPTION", 500),
    ("SEX", 1),
    ("RATECLASS", 1),
)


def _nsp_validate_header(fieldnames, path) -> None:
    if tuple(fieldnames or ()) != NSP_COLUMNS:
        _fail(
            path, 1, "NSP requires the canonical CSV header with explicit basis "
            "and RATE_PER units. CVF, PUI and IAF tax premiums are not NSP. "
            f"Expected: {','.join(NSP_COLUMNS)}",
        )


def _nsp_text_value(record, column, size, path, line):
    value = record[column].strip()
    if column != "BASIS_DESCRIPTION":
        value = value.upper()
    invalid = (
        len(value) > size
        or not value.isascii()
        or any(ord(char) < 32 for char in value)
        or (not value and column not in ("SEX", "RATECLASS"))
    )
    if invalid:
        _fail(path, line, f"Invalid NSP {column}; explicit basis and identifiers are required.")
    return value


def _nsp_effective_date(token, path, line):
    token = token.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", token):
        _fail(path, line, "NSP EFFECTIVE_DATE must be YYYY-MM-DD.")
    try:
        return datetime.strptime(token, "%Y-%m-%d").date()
    except ValueError:
        _fail(path, line, "NSP EFFECTIVE_DATE is not a valid calendar date.")


def _nsp_row(record, path, line):
    if set(record) != set(NSP_COLUMNS) or any(v is None for v in record.values()):
        _fail(path, line, "NSP CSV row has missing or extra columns.")
    row = {
        column: _nsp_text_value(record, column, size, path, line)
        for column, size in _NSP_TEXT_COLUMNS
    }
    if not re.fullmatch(r"\d{2}", row["USER_CODE"]):
        _fail(path, line, "NSP USER_CODE must contain exactly two digits.")
    for column in ("ISSUE_AGE", "DURATION"):
        row[column] = _integer(record[column], path, line)
    row["EFFECTIVE_DATE"] = _nsp_effective_date(record["EFFECTIVE_DATE"], path, line)
    for column in ("RATE_PER", "RATE"):
        row[column] = _decimal(record[column], path, line, scale=8)
    if row["RATE_PER"] <= 0 or row["RATE"] < 0:
        _fail(path, line, "NSP RATE_PER must be positive and RATE cannot be negative.")
    return {column: row[column] for column in NSP_COLUMNS}


def parse_nsp(path) -> list[dict[str, object]]:
    """Read explicitly supplied NSP values, never derive them from another rate.

    This is SuiteView's canonical CSV contract, not a claimed CyberLife print
    layout. BASIS_ID/DESCRIPTION identify the independently verified actuarial
    basis; RATE is premium for RATE_PER face amount in the same currency.
    """
    result = _Rows(path, NSP_KEYS)
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        _nsp_validate_header(reader.fieldnames, path)
        try:
            for record in reader:
                line = reader.line_num
                result.add(_nsp_row(record, path, line), line)
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


_PUI_DEFINITION_LINES = {
    "PLAN CD PLAN CODE CHAR 11 C1 PUI RATE PUI RATE NUM 11, 6 N2",
    "SEX PLAN SEX CODE CHAR 1 C2",
    "CLASS PLAN RATECLASS CHAR 1 C3",
    "ATT AGE PLAN ATTAINED AGE NUM 3, 0 N1",
    "TAB RATE PLAN TABLE RATING CHAR 2 C4",
}
_PUI_IGNORED_WORDS = {
    "0 CONTROL STATEMENTS FOLLOW:",
    "0 ARGUMENT DESCRIPTIONS FUNCTION DESCRIPTIONS",
    "NAME DESCRIPTION TYPE LENGTH KYWD NAME DESCRIPTION TYPE LENGTH KYWD",
}


class _PuiParser:
    """State machine for CJUDTPUI rows and report control sections."""

    def __init__(self, path):
        self.path = path
        self.result = _Rows(path, PUI_KEYS)
        self.user = None
        self.table_seen = False
        self.columns_seen = False
        self.end_seen = False
        self.section_pending = False
        self.totals = None
        self.all_entries = False
        self.definitions = set()
        self.line_number = 1

    def parse(self):
        for self.line_number, line in _lines(self.path):
            self._parse_line(line)
        if self.section_pending:
            _fail(self.path, self.line_number, "PUI user section has no rate rows.")
        if self.totals and self.all_entries and len(self.result.rows) != self.totals[0] - self.totals[1]:
            _fail(self.path, self.line_number, "Printed table totals do not match parsed nondeleted rows.")
        return self.result.finish(self.line_number)

    def _parse_line(self, line):
        stripped = line.strip()
        words = " ".join(stripped.split())
        if not stripped or words == "0":
            return
        if self.end_seen:
            _fail(self.path, self.line_number, "Unexpected content after END-OF-JOB.")
        if self._is_page_heading(stripped):
            return
        if words in _PUI_IGNORED_WORDS:
            return
        if re.fullmatch(r"CJUDTPUI(?:\s+\d+)?", stripped) and not self.table_seen:
            return
        if words.startswith("0TABLE:"):
            self._handle_table_options(words)
            return
        if re.fullmatch(r"0?\s*USER \d{2} UNIQUE ENTRIES", stripped):
            self._require_table("Summary outside CJUDTPUI table.")
            return
        if self._handle_totals_or_end(words):
            return
        if words in _PUI_DEFINITION_LINES:
            self.definitions.add(words)
            return
        if re.fullmatch(r"[- ]+", stripped):
            return
        if self._handle_user_or_columns(stripped, words):
            return
        self._add_rate_row(line, words)

    @staticmethod
    def _is_page_heading(stripped):
        return re.fullmatch(
            r"1DATE\s+\d{2}/\d{2}/\d{2,4}\s+CYBERLIFE ONLINE TABLES LIST\s+PAGE\s+\d+",
            stripped,
        )

    def _require_table(self, message):
        if not self.table_seen:
            _fail(self.path, self.line_number, message)

    def _handle_table_options(self, words):
        if not re.fullmatch(
            r"0TABLE: CJUDTPUI PROCESSING OPTIONS: USERID = (?:ALL|\d{2}) "
            r"AUDIT# = \S+ DELETED RECORDS = OMIT",
            words,
        ):
            _fail(self.path, self.line_number, "Unsupported table or processing options; expected CJUDTPUI.")
        self.table_seen = True
        self.all_entries = "USERID = ALL AUDIT# = ALL" in words

    def _handle_totals_or_end(self, words):
        match = re.fullmatch(
            r"0TABLE CONTAINS ([\d,]+) ENTRIES OF WHICH ([\d,]+) HAVE BEEN MARKED FOR DELETION\.",
            words,
        )
        if match:
            self.totals = (int(match[1].replace(",", "")), int(match[2].replace(",", "")))
            return True
        if words == "0*** END-OF-JOB ***":
            self.end_seen = True
            return True
        return False

    def _handle_user_or_columns(self, stripped, words):
        match = re.fullmatch(r"0\s*ENTRIES FOR USER (\d{2})(?:\s+CONTINUED)?", stripped)
        if match:
            self._start_user_section(match[1])
            return True
        if words == "0 PLAN CD SEX CLASS ATT AGE TAB RATE PUI RATE AUDIT# CHANGED":
            if self.user is None:
                _fail(self.path, self.line_number, "PUI columns have no user section.")
            self.columns_seen = True
            return True
        return False

    def _start_user_section(self, user):
        self._require_table("User section outside CJUDTPUI table.")
        if self.section_pending and self.user != user:
            _fail(self.path, self.line_number, "PUI user section has no rate rows.")
        self.user = user
        self.columns_seen = False
        self.section_pending = True

    def _add_rate_row(self, line, words):
        if not self.table_seen or not self.columns_seen or self.user is None:
            _fail(self.path, self.line_number, f"Unsupported PUI section or missing headers: {words[:100]!r}.")
        if self.definitions and self.definitions != _PUI_DEFINITION_LINES:
            _fail(self.path, self.line_number, "Incomplete or unsupported CJUDTPUI argument definitions.")
        _check_spaces(line, _PUI_ROW_RULE.spans, self.path, self.line_number)
        row = _PUI_ROW_RULE.parse(line, {"path": self.path, "line": self.line_number})
        plan, sex = row["PLANCODE"], row["SEX"]
        rateclass, table_rating = row["RATECLASS"], row["TABLE_RATING"]
        if not plan or len(sex) > 1 or len(rateclass) > 1 or len(table_rating) > 2:
            _fail(self.path, self.line_number, "Malformed PUI source key.")
        self.result.add({
            "USER_CODE": self.user, "PLANCODE": plan, "SEX": sex,
            "RATECLASS": rateclass, "ATTAINED_AGE": row["ATTAINED_AGE"],
            "TABLE_RATING": table_rating, "RATE": row["RATE"],
            "AUDIT_NUMBER": row["AUDIT_NUMBER"],
            "CHANGED_DATE": row["CHANGED_DATE"],
        }, self.line_number)
        self.section_pending = False


def parse_pui(path) -> list[dict[str, object]]:
    """Read CJUDTPUI's printed natural key and six-decimal rate without remapping."""
    return _PuiParser(path).parse()


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


class _IafParser:
    """State machine for whole-life IAF plan/search-key/premium sections."""

    def __init__(self, path, user_code):
        self.path = path
        self.user_code = user_code
        self.result = _Rows(path, IAF_KEYS)
        self.product = None
        self.aliases = []
        self.rates = []
        self.scale = None
        self.scale_count = 0
        self.rate_section = False
        self.aliases_section = False
        self.pending_product = False
        self.pending_rate = False
        self.page_header = False
        self.line_number = 1

    def parse(self):
        for self.line_number, line in _lines(self.path):
            self._parse_line(line)
        if self.pending_product or self.pending_rate:
            _fail(self.path, self.line_number, "Truncated IAF record or premium section.")
        self._finish_product()
        return self.result.finish(self.line_number)

    def _parse_line(self, line):
        stripped = line.strip()
        words = " ".join(stripped.split())
        if not stripped:
            return
        if re.fullmatch(r"1 {40,}\S.*", line):
            return
        if self._is_page_header(stripped):
            self.page_header = True
            return
        if words == _IAF_PLAN_LABELS:
            self._handle_plan_heading()
            return
        if self._is_product_line(line):
            self._start_product(line)
            return
        if self.pending_product:
            _fail(self.path, self.line_number, "Expected IAF plan record after heading.")
        if line.startswith(" *** PLAN SEARCH KEYS"):
            self._add_search_keys(line)
            return
        if words == _IAF_RATE_LABELS:
            self._start_rate_section()
            return
        if self.aliases_section and not line[:31].strip():
            self.aliases.extend(_iaf_aliases(line, self.path, self.line_number))
            return
        self._add_rate_line(line, stripped)

    @staticmethod
    def _is_page_header(stripped):
        return re.fullmatch(
            r"0DATE\s+\d{2}/\d{2}/\d{2,4}\s+PRINT ISSUE AGE DESCRIPTION FILE\s+PAGE\s+\d+",
            stripped,
        )

    @staticmethod
    def _is_product_line(line):
        return len(line) > 2 and line[:2] == "  " and not line[2].isspace() and line[2] != "*"

    def _handle_plan_heading(self):
        if self.pending_product:
            _fail(self.path, self.line_number, "IAF plan heading has no record.")
        self.pending_product = True
        self.page_header = False

    def _start_product(self, line):
        self._finish_product()
        self.product = _iaf_product(line, self.path, self.line_number)
        self.aliases, self.rates, self.scale = [], [], None
        self.scale_count = 0
        self.pending_product = False
        self.rate_section = self.aliases_section = self.pending_rate = False

    def _add_search_keys(self, line):
        if self.product is None or self.rates:
            _fail(self.path, self.line_number, "Search-key section outside a new IAF record.")
        if line[21:31].strip():
            _fail(self.path, self.line_number, "Unexpected IAF search-key prefix.")
        self.aliases.extend(_iaf_aliases(line, self.path, self.line_number))
        self.aliases_section = True

    def _start_rate_section(self):
        if self.product is None or not self.aliases:
            _fail(self.path, self.line_number, "Premium section requires a plan and search keys.")
        self.rate_section = True
        self.aliases_section = False
        self.pending_rate = not (self.page_header and self.scale_count > 0)
        self.page_header = False

    def _add_rate_line(self, line, stripped):
        if not self.rate_section or line[:19].strip() or len(line) <= 19:
            _fail(self.path, self.line_number, f"Unsupported IAF section or layout: {stripped[:100]!r}.")
        new_scale = bool(line[19:20].strip())
        if new_scale:
            self._start_scale(line)
        elif self.scale is None:
            _fail(self.path, self.line_number, "Premium cells have no rate type/start date.")
        spans = list(_IAF_RATE_HEADER_RULE.spans) if new_scale else []
        count = self._add_rate_cells(line, spans)
        if not count and not new_scale:
            _fail(self.path, self.line_number, "Empty premium-rate continuation.")
        if count:
            self.scale_count += count
            self.pending_rate = False

    def _start_scale(self, line):
        if self.scale is not None and self.scale_count == 0:
            _fail(self.path, self.line_number, "Previous premium scale has no rate cells.")
        self.scale = _IAF_RATE_HEADER_RULE.parse(
            line, {"path": self.path, "line": self.line_number},
        )
        rate_type = self.scale["RATE_TYPE"]
        if rate_type not in "0ABCFGLMNSTWXY":
            _fail(self.path, self.line_number, f"Unknown IAF premium rate type {rate_type!r}.")
        start, stop = self.scale["SCALE_START"], self.scale["SCALE_STOP"]
        if stop is not None and stop < start:
            _fail(self.path, self.line_number, "Premium scale stop date precedes start date.")
        self.scale_count = 0
        self.pending_rate = True

    def _add_rate_cells(self, line, spans):
        spans.extend(_IAF_RATE_CELL_GROUP.spans)
        count = 0
        for cell in _IAF_RATE_CELL_GROUP.parse(line, {"path": self.path, "line": self.line_number}):
            self._add_rate_cell(cell)
            count += 1
        _check_spaces(line, spans, self.path, self.line_number)
        return count

    def _add_rate_cell(self, cell):
        ident = cell["PREMIUM_IDENTIFIER"]
        if not re.fullmatch(r"\d{2}\S{5}", ident):
            _fail(self.path, self.line_number, f"Malformed premium identifier {ident!r}.")
        rate = {
            **self.scale, "PREMIUM_IDENTIFIER": ident, "DURATION_CODE": ident[:2],
            "SEX": ident[2], "RATECLASS": ident[3], "BAND": ident[4],
            "PLAN_OPTION": ident[5:], "RATE": cell["RATE"],
        }
        self.rates.append((rate, self.line_number))

    def _finish_product(self):
        if self.product is None:
            return
        if self.pending_rate:
            _fail(self.path, self.line_number, "Truncated IAF premium section.")
        if not self.aliases or not self.rates:
            _fail(self.path, self.line_number, "Incomplete IAF record: search keys and premium rates are required.")
        expected = (
            self.product["SOURCE_PLANCODE"],
            self.product["SOURCE_IAF_VERSION"],
            self.product["SOURCE_EFFECTIVE_DATE"],
        )
        if expected not in {
            (a["PLANCODE"], a["IAF_VERSION"], a["EFFECTIVE_DATE"]) for a in self.aliases
        }:
            _fail(self.path, self.line_number, "IAF search keys omit the source record's own key.")
        for alias in self.aliases:
            for rate, source_line in self.rates:
                self.result.add({"USER_CODE": self.user_code, **self.product, **alias, **rate}, source_line)


def parse_iaf(path, user_code) -> list[dict[str, object]]:
    """Read uncompiled IAF premium cells, retaining source records and aliases.

    Uses the existing IAFParser's documented fixed-column mechanics, but every
    field and section is validated. Unsupported auxiliary sections fail closed.
    Rows expand search aliases, never age ranges or premium duration codes.
    """
    user_code = str(user_code).strip()
    if not re.fullmatch(r"\d{2}", user_code):
        _fail(path, 1, "IAF user/company code must be exactly two digits.")
    return _IafParser(path, user_code).parse()
