"""
CKULTB04 surrender-charge table parser.

Parses the CyberLife "ONLINE TABLES LIST" report (table CKULTBC4) into flat
records. Each data record spans two printed lines:

  Line 1: PLAN CODE, RULE CODE, STATE CODE, SEX CODE, RATE CLASS, BAND CODE,
          EFFECTIVE DATE, HIGH DURATION, HIGH ISSUE AGE, GRACE PD DAYS,
          CHARGE AMOUNT, CHARGE PERCENTAGE [, ALLOW CODE]
  Line 2: FREE PERCENTAGE, MONTHS FREE CHARGE, AUDIT#, CHANGED (date)

Header / page-break lines use ASA carriage control in column 1 ('1' = new
page, '0' = control/section header). Records are streamed so the parser stays
memory-light on the very large (100 MB+) print files.
"""

from __future__ import annotations

import os
import re
from typing import Callable, Dict, Iterator, List, Optional, Tuple

# Ordered dict keys for a parsed record.
RAW_KEYS: List[str] = [
    "PLAN_CODE", "RULE_CODE", "STATE_CODE", "SEX_CODE", "RATE_CLASS",
    "BAND_CODE", "EFFECTIVE_DATE", "HIGH_DURATION", "HIGH_ISSUE_AGE",
    "GRACE_PD", "CHARGE_AMOUNT", "CHARGE_PCT", "ALLOW_CODE",
    "FREE_PCT", "MONTHS_FREE", "AUDIT_NUM", "CHANGED_DATE",
]

# Display headers for the "Excel Raw" output, matching the CKULTB04 report.
RAW_HEADERS: List[str] = [
    "PLAN CODE",
    "RULE CODE",
    "STATE CODE",
    "SEX CODE",
    "RATE CLASS",
    "BAND CODE",
    "EFFECTIVE DATE",
    "HIGH DURATION",
    "HIGH ISSUE AGE",
    "GRACE PD DAYS/MO EXCESS INT",
    "CHARGE AMOUNT/RATE/REQ PREMIUM",
    "CHARGE PERCENTAGE",
    "ALLOW CODE",
    "FREE PERCENTAGE",
    "MONTHS FREE CHARGE",
    "AUDIT#",
    "CHANGED",
]

_DATE_RE = re.compile(r"\d{2}/\d{2}/\d{4}$")
_DASHES_RE = re.compile(r"^[\s\-]+$")


def is_skip_line(line: str) -> bool:
    """Return True for a header, separator, or other non-data line."""
    if not line.strip():
        return True
    # ASA carriage control: '1' = page break, '0' = control/section header.
    if line[0] in ("1", "0"):
        return True
    # Separator lines (dashes and spaces only).
    if _DASHES_RE.match(line):
        return True
    # Field-description lines from the report metadata section.
    if re.search(r"\bCHAR\b|\bNUM\b(?!\s*\d)", line) and "DESCRIPTION" not in line:
        return True
    if "DESCRIPTION" in line and "TYPE" in line:
        return True
    # Table identifier line.
    if re.match(r"^\s*CKULTB", line):
        return True
    # Column header continuation line.
    stripped = line.strip()
    if stripped.startswith("CD PCTFREE") or stripped.startswith("CD  PCTFREE"):
        return True
    return False


def is_data_line1(parts: List[str]) -> bool:
    """Whether whitespace-split tokens look like a main data line (line 1)."""
    if len(parts) < 12:
        return False
    # Field index 6 is the effective date (MM/DD/YYYY).
    return bool(_DATE_RE.match(parts[6]))


def _record_from_line1(parts: List[str]) -> Dict:
    """Build a partial record from a parsed line-1 token list."""
    return {
        "PLAN_CODE": parts[0],
        "RULE_CODE": parts[1],
        "STATE_CODE": parts[2],
        "SEX_CODE": parts[3],
        "RATE_CLASS": parts[4],
        "BAND_CODE": parts[5],
        "EFFECTIVE_DATE": parts[6],
        "HIGH_DURATION": int(parts[7]),
        "HIGH_ISSUE_AGE": int(parts[8]),
        "GRACE_PD": int(parts[9]),
        "CHARGE_AMOUNT": float(parts[10]),
        "CHARGE_PCT": float(parts[11]),
        "ALLOW_CODE": parts[12] if len(parts) >= 13 else "",
        "FREE_PCT": 0.0,
        "MONTHS_FREE": 0,
        "AUDIT_NUM": "",
        "CHANGED_DATE": "",
    }


def _apply_line2(record: Dict, parts: List[str]) -> None:
    """Attach the continuation-line (line 2) fields to a record in place."""
    try:
        record["FREE_PCT"] = float(parts[0])
        record["MONTHS_FREE"] = int(parts[1])
    except (ValueError, IndexError):
        pass
    if len(parts) >= 3:
        record["AUDIT_NUM"] = parts[2]
    if len(parts) >= 4:
        record["CHANGED_DATE"] = parts[3]


def iter_records(
    input_path: str,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> Iterator[Dict]:
    """Stream parsed records from a CKULTB04 report file.

    Yields one dict per record (keys are ``RAW_KEYS``). ``progress_cb`` is
    called periodically with a 0.0-1.0 fraction of the file read.
    """
    size = os.path.getsize(input_path) or 1
    pending: Optional[Dict] = None
    lines_seen = 0

    with open(input_path, "r", encoding="utf-8", errors="replace") as fh:
        # NOTE: read via readline() rather than ``for line in fh`` — the file
        # iterator protocol disables fh.tell() ("telling position disabled by
        # next() call"), which we need for progress reporting.
        while True:
            line = fh.readline()
            if not line:
                break
            lines_seen += 1
            if progress_cb is not None and (lines_seen & 0x3FFF) == 0:
                progress_cb(min(fh.tell() / size, 1.0))

            if is_skip_line(line):
                continue

            parts = line.split()
            if is_data_line1(parts):
                # A new line-1 starts; flush any pending record without a
                # continuation line first.
                if pending is not None:
                    yield pending
                pending = _record_from_line1(parts)
            else:
                # Continuation line for the pending record.
                if pending is not None:
                    _apply_line2(pending, parts)
                    yield pending
                    pending = None

    if pending is not None:
        yield pending

    if progress_cb is not None:
        progress_cb(1.0)


def list_plan_codes(
    input_path: str,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> List[Tuple[str, int]]:
    """Return the distinct PLAN CODE values found in the report.

    Yields ``(plan_code, record_count)`` pairs sorted by plan code, so the UI
    can present them for selection.
    """
    counts: Dict[str, int] = {}
    for record in iter_records(input_path, progress_cb=progress_cb):
        code = record["PLAN_CODE"]
        counts[code] = counts.get(code, 0) + 1
    return sorted(counts.items())
