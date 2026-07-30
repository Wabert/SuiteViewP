"""Local percent-of-account-value monthly charge schedules."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional


_TABLE_PATH = Path(__file__).resolve().parent.parent / "plancodes" / "tRates_PoAV.json"
_CACHE: Optional[List[dict]] = None


def _load_table() -> List[dict]:
    global _CACHE
    if _CACHE is None:
        with open(_TABLE_PATH, "r", encoding="utf-8") as file:
            _CACHE = json.load(file)
    return _CACHE


def load_poav_schedule(
    table_code: str,
    band: int,
    *,
    scale: int = 1,
    max_year: int = 121,
) -> List:
    """Return a 1-indexed, fill-forward PoAV schedule.

    Scale 1 selects current rates and scale 0 selects guaranteed rates. Rates
    are monthly decimal percentages, so 0.04% is stored and returned as 0.0004.
    """
    code = str(table_code).strip()
    if code == "0":
        return []
    if scale not in (0, 1):
        raise ValueError(f"PoAV scale must be 0 or 1, got {scale}")
    if max_year < 1:
        raise ValueError(f"PoAV max_year must be positive, got {max_year}")

    normalized_band = int(band)
    table_rows = [
        row for row in _load_table()
        if str(row.get("Table", "")).strip() == code
    ]
    if not table_rows:
        raise ValueError(f"Unknown PoAV table code {code!r}")

    band_rows = [
        row for row in table_rows
        if int(row.get("Band", 0)) == normalized_band
    ]
    if not band_rows:
        raise ValueError(
            f"PoAV table {code!r} has no rates for band {normalized_band}"
        )

    rate_field = "Curr" if scale == 1 else "Guar"
    breakpoints = {
        int(row["Year"]): float(row[rate_field])
        for row in band_rows
    }
    if 1 not in breakpoints:
        raise ValueError(
            f"PoAV table {code!r}, band {normalized_band} has no year-1 rate"
        )

    schedule = [None]
    active_rate = breakpoints[1]
    for year in range(1, max_year + 1):
        active_rate = breakpoints.get(year, active_rate)
        schedule.append(active_rate)
    return schedule
