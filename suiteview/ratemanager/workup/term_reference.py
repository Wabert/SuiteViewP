"""Read-only UL_Rates lookups that seed the Term workup screen.

The Term DB Manager workbook used to hold this knowledge — which modal-factor
and band-structure indexes exist, and which base index is free next. That is
now read straight from the database so there is one source of truth.

Every lookup degrades gracefully: when the DSN is unreachable the caller gets
an empty result plus an error string, and the user can still type the values
by hand.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from suiteview.ratemanager.workup.term_spec import BandSpecRow, MODEFACT_FIELDS

logger = logging.getLogger(__name__)

DEFAULT_DSN = "UL_Rates"

# Base indexes are allocated as free multiples of this, leaving room for up to
# BASE_INDEX_STEP - 1 rate combos per plancode.
BASE_INDEX_STEP = 1000


@dataclass
class TermReferenceData:
    """Existing shared reference rows, keyed by index."""

    modefact: "OrderedDict[str, Dict[str, float]]" = field(
        default_factory=OrderedDict)
    bandspecs: "OrderedDict[str, List[BandSpecRow]]" = field(
        default_factory=OrderedDict)
    used_base_indexes: List[int] = field(default_factory=list)
    error: str = ""

    @property
    def available(self) -> bool:
        return not self.error

    def next_base_index(self) -> int:
        """The next free multiple of BASE_INDEX_STEP."""
        highest = max(self.used_base_indexes, default=0)
        return (highest // BASE_INDEX_STEP + 1) * BASE_INDEX_STEP

    def next_index(self, existing) -> str:
        """The next unused whole-number index for a reference table."""
        numeric = []
        for key in existing:
            try:
                numeric.append(int(str(key).strip()))
            except ValueError:
                continue
        return str(max(numeric, default=-1) + 1)


def _connect(dsn: str):
    import pyodbc

    return pyodbc.connect(f"DSN={dsn}", autocommit=True, timeout=10)


def _base_index_of(index_value: str) -> Optional[int]:
    """Recover a plancode's base index from one of its rate indexes.

    '1001_PL' was allocated from base 1000, so rounding down to the nearest
    BASE_INDEX_STEP recovers it.
    """
    text = str(index_value or "").strip()
    number, _, _suffix = text.partition("_")
    try:
        return (int(number) // BASE_INDEX_STEP) * BASE_INDEX_STEP
    except ValueError:
        return None


def load_reference_data(dsn: str = DEFAULT_DSN) -> TermReferenceData:
    """Read the shared Term reference tables and the allocated base indexes."""
    data = TermReferenceData()
    try:
        connection = _connect(dsn)
    except Exception as exc:
        logger.warning("Term reference lookup unavailable: %s", exc)
        data.error = str(exc)
        return data

    try:
        cursor = connection.cursor()

        columns = ", ".join(f"[{name}]" for name in MODEFACT_FIELDS)
        cursor.execute(
            f"SELECT [Index(MODEFACT)], {columns} FROM [TERM_RATE_MODEFACT] "
            "ORDER BY [Index(MODEFACT)]"
        )
        for row in cursor.fetchall():
            index = str(row[0]).strip()
            data.modefact[index] = {
                name: float(value if value is not None else 0.0)
                for name, value in zip(MODEFACT_FIELDS, row[1:])
            }

        cursor.execute(
            "SELECT [Index(BANDSPEC)], [Issue_Date], [SpecifiedAmount], "
            "[Band], [BandCode] FROM [TERM_RATE_BANDSPECS] "
            "ORDER BY [Index(BANDSPEC)], [Issue_Date], [Band]"
        )
        for index_value, issue_date, amount, band, band_code in cursor.fetchall():
            index = str(index_value).strip()
            data.bandspecs.setdefault(index, []).append(BandSpecRow(
                issue_date=str(issue_date)[:10],
                specified_amount=float(amount if amount is not None else 0.0),
                band=int(band) if band is not None else 0,
                band_code=str(band_code or "").strip(),
            ))

        cursor.execute("SELECT DISTINCT [Index(PREM)] FROM [TERM_POINT_PVSRB]")
        bases = set()
        for (index_value,) in cursor.fetchall():
            base = _base_index_of(index_value)
            if base is not None:
                bases.add(base)
        data.used_base_indexes = sorted(bases)

        cursor.close()
    except Exception as exc:
        logger.warning("Term reference lookup failed: %s", exc)
        data.error = str(exc)
    finally:
        connection.close()

    return data


def describe_modefact(index: str, values: Dict[str, float]) -> str:
    """One-line summary of a modal-factor row for a picker."""
    return (f"{index}   PAC {values.get('PACS', 0):g}/"
            f"{values.get('PACQ', 0):g}/{values.get('PACM', 0):g}   "
            f"DIR {values.get('DIRS', 0):g}/"
            f"{values.get('DIRQ', 0):g}/{values.get('DIRM', 0):g}")


def describe_bandspec(index: str, rows: List[BandSpecRow]) -> str:
    """One-line summary of a band structure for a picker."""
    if not rows:
        return f"{index}   (no bands)"
    latest = max(row.issue_date for row in rows)
    current = [row for row in rows if row.issue_date == latest]
    breaks = ", ".join(
        f"{row.band_code}:{row.specified_amount:,.0f}"
        for row in sorted(current, key=lambda r: r.band)
    )
    return f"{index}   {len(current)} band(s)   {breaks}"


def modefact_choices(data: TermReferenceData) -> List[Tuple[str, str]]:
    return [(describe_modefact(index, values), index)
            for index, values in data.modefact.items()]


def bandspec_choices(data: TermReferenceData) -> List[Tuple[str, str]]:
    return [(describe_bandspec(index, rows), index)
            for index, rows in data.bandspecs.items()]
