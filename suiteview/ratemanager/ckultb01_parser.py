"""
CKULTB01 expense-per-unit (EPU) table parser.

Parses the CyberLife "ONLINE TABLES LIST" report for table CKULTB01 into flat
records. Each data record spans two printed lines:

  Line 1: PLANCODE, FREQTYPE, RULECODE, STATCODE, SEX CODE, RATECLAS, BAND,
          EFF DATE, MONTHDUR (high monthly duration), HIGH AGE (high issue
          age), CHARGE (current), MAXIMUM (may wrap — its final characters can
          spill onto line 2)
  Line 2: [wrapped tail of MAXIMUM,] GUAR CHG, GUAR MAX, AUDIT#, CHANGED

Wildcards: STATCODE ``**`` = all states; SEX/RATECLAS/BAND ``*`` = all values.
Sentinels: MONTHDUR ``99,999`` = all remaining durations; HIGH AGE ``999`` =
all issue ages. MONTHDUR is a high-duration bracket in months — e.g. 120
means the rate applies through month 120 (the first 10 policy years).
"""

from __future__ import annotations

import re
from typing import Callable, Dict, Iterator, List, Optional, Tuple

from suiteview.ratemanager.online_tables import DASHES_RE, DATE_RE, iter_report_lines

RAW_KEYS: List[str] = [
    "PLAN_CODE", "FREQ_TYPE", "RULE_CODE", "STATE_CODE", "SEX_CODE",
    "RATE_CLASS", "BAND_CODE", "EFFECTIVE_DATE", "MONTH_DUR", "HIGH_AGE",
    "CHARGE", "MAXIMUM", "GUAR_CHARGE", "GUAR_MAX", "AUDIT_NUM", "CHANGED_DATE",
]

RAW_HEADERS: List[str] = [
    "PLANCODE", "FREQTYPE", "RULECODE", "STATCODE", "SEX CODE", "RATECLAS",
    "BAND", "EFF DATE", "MONTHDUR", "HIGH AGE", "CHARGE", "MAXIMUM",
    "GUAR CHG", "GUAR MAX", "AUDIT#", "CHANGED",
]

# MONTHDUR at this value means "all remaining durations".
SENTINEL_MONTHDUR = 99999
# HIGH AGE at this value means "all issue ages".
SENTINEL_HIGH_AGE = 999


def _num(tok: str) -> float:
    return float(tok.replace(",", ""))


def _int(tok: str) -> int:
    return int(tok.replace(",", ""))


def is_skip_line(line: str) -> bool:
    """Return True for a header, separator, or other non-data line."""
    if not line.strip():
        return True
    # ASA carriage control: '1' = page break, '0' = control/section header.
    if line[0] in ("1", "0"):
        return True
    if DASHES_RE.match(line):
        return True
    # Argument/function dictionary lines (field TYPE descriptors).
    if re.search(r"\bCHAR\b|\bNUM\b\s+\d", line) and "DESCRIPTION" not in line:
        return True
    if "DESCRIPTION" in line and "TYPE" in line:
        return True
    # Table identifier line.
    if re.match(r"^\s*CKULTB", line):
        return True
    # Column-header continuation line ("GUAR CHG ... AUDIT# CHANGED").
    if "GUAR CHG" in line and "AUDIT#" in line:
        return True
    return False


def is_data_line1(parts: List[str]) -> bool:
    """Whether whitespace-split tokens look like a main data line (line 1)."""
    if len(parts) < 12:
        return False
    # Field index 7 is the effective date (MM/DD/YYYY).
    return bool(DATE_RE.match(parts[7]))


def _record_from_line1(parts: List[str]) -> Dict:
    """Build a partial record from a parsed line-1 token list."""
    return {
        "PLAN_CODE": parts[0],
        "FREQ_TYPE": parts[1],
        "RULE_CODE": parts[2],
        "STATE_CODE": parts[3],
        "SEX_CODE": parts[4],
        "RATE_CLASS": parts[5],
        "BAND_CODE": parts[6],
        "EFFECTIVE_DATE": parts[7],
        "MONTH_DUR": _int(parts[8]),
        "HIGH_AGE": _int(parts[9]),
        "CHARGE": _num(parts[10]),
        "_MAXIMUM_RAW": parts[11],   # may be truncated; completed on line 2
        "MAXIMUM": 0.0,
        "GUAR_CHARGE": 0.0,
        "GUAR_MAX": 0.0,
        "AUDIT_NUM": "",
        "CHANGED_DATE": "",
    }


def _apply_line2(record: Dict, parts: List[str]) -> None:
    """Attach the continuation-line fields, stitching the wrapped MAXIMUM.

    Line 2 is either ``[wrap, GUAR CHG, GUAR MAX, AUDIT#, CHANGED]`` (5 tokens,
    MAXIMUM's final characters wrapped from line 1) or
    ``[GUAR CHG, GUAR MAX, AUDIT#, CHANGED]`` (4 tokens, no wrap).
    """
    max_raw = record.pop("_MAXIMUM_RAW", "0")
    rest = parts
    if len(parts) >= 5:
        max_raw += parts[0]
        rest = parts[1:]
    try:
        record["MAXIMUM"] = _num(max_raw)
    except ValueError:
        record["MAXIMUM"] = 0.0
    try:
        record["GUAR_CHARGE"] = _num(rest[0])
        record["GUAR_MAX"] = _num(rest[1])
    except (ValueError, IndexError):
        pass
    if len(rest) >= 3:
        record["AUDIT_NUM"] = rest[2]
    if len(rest) >= 4:
        record["CHANGED_DATE"] = rest[3]


def iter_records(
    input_path: str,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> Iterator[Dict]:
    """Stream parsed records from a CKULTB01 report file.

    Yields one dict per record (keys are ``RAW_KEYS``).
    """
    pending: Optional[Dict] = None
    for line in iter_report_lines(input_path, progress_cb=progress_cb):
        if is_skip_line(line):
            continue
        parts = line.split()
        if is_data_line1(parts):
            # A new line-1 starts; flush any pending record that never got a
            # continuation line (shouldn't happen, but don't drop data).
            if pending is not None:
                _apply_line2(pending, [])
                yield pending
            pending = _record_from_line1(parts)
        elif pending is not None:
            _apply_line2(pending, parts)
            yield pending
            pending = None

    if pending is not None:
        _apply_line2(pending, [])
        yield pending


def list_plan_groups(
    input_path: str,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> List[Tuple[str, str, str, int]]:
    """Return the distinct (plancode, freqtype, rulecode) groups in the report.

    Yields ``(plan_code, freq_type, rule_code, record_count)`` sorted, so the
    UI can present them for selection.
    """
    counts: Dict[Tuple[str, str, str], int] = {}
    for rec in iter_records(input_path, progress_cb=progress_cb):
        key = (rec["PLAN_CODE"], rec["FREQ_TYPE"], rec["RULE_CODE"])
        counts[key] = counts.get(key, 0) + 1
    return sorted((pc, ft, rc, n) for (pc, ft, rc), n in counts.items())
