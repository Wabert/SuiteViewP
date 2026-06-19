from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


_PLANCODE_DIR = Path(__file__).resolve().parent.parent / "plancodes"
_RIDER_TABLE_PATH = _PLANCODE_DIR / "rider_table.json"
_RIDER_CACHE: Optional[Dict[str, RiderConfig]] = None


@dataclass(frozen=True)
class RiderConfig:
    plancode: str = ""
    cov_type: str = ""
    cease_age_dur: Optional[int] = None
    cease_use_code: str = ""


def load_rider_config(plancode: str) -> Optional[RiderConfig]:
    """Load rider metadata from rider_table.json, if present for the plancode."""
    if not plancode:
        return None
    return _load_rider_table().get(str(plancode).strip())


def _load_rider_table() -> Dict[str, RiderConfig]:
    global _RIDER_CACHE
    if _RIDER_CACHE is not None:
        return _RIDER_CACHE

    if not _RIDER_TABLE_PATH.exists():
        raise FileNotFoundError(f"No rider table found: {_RIDER_TABLE_PATH}")

    with open(_RIDER_TABLE_PATH, "r") as f:
        table_data = json.load(f)

    rows = table_data.get("Riders", [])
    _RIDER_CACHE = {}
    for row in rows:
        plancode = str(row.get("Plancode", "")).strip()
        if not plancode:
            continue
        _RIDER_CACHE[plancode] = RiderConfig(
            plancode=plancode,
            cov_type=str(row.get("CovType", "")).strip(),
            cease_age_dur=_int_or_none(row.get("CeaseAgeDur")),
            cease_use_code=str(row.get("CeaseUseCode", "")).strip(),
        )
    return _RIDER_CACHE


def _int_or_none(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None