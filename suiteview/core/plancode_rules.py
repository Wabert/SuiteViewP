"""Lightweight product rules needed by infrastructure-level rate lookups."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
import json
from pathlib import Path

_PLANCODE_TABLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "illustration"
    / "plancodes"
    / "plancode_table.json"
)


@lru_cache(maxsize=1)
def _band_table2_issue_dates() -> dict[str, date | None]:
    with _PLANCODE_TABLE_PATH.open("r", encoding="utf-8") as stream:
        rows = json.load(stream).get("Plancodes", [])
    dates: dict[str, date | None] = {}
    for row in rows:
        plancode = str(row.get("Plancode", "")).strip()
        if not plancode:
            continue
        raw = row.get("BandTable2IssueDate")
        dates[plancode] = date.fromisoformat(str(raw).strip()) if raw else None
    return dates


def band_table2_issue_date(plancode: str) -> date | None:
    """Return the issue-date cutoff for the legacy CZ banding rule."""

    return _band_table2_issue_dates().get(plancode)
