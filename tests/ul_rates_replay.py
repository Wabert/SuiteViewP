"""Recorded replay of the UL_Rates queries made by the unit-test suite.

Unit tests must not reach the live UL_Rates SQL Server. Rate lookups that tests
do not fake themselves (mostly band-spec lookups made by the illustration
engine) are answered from ``tests/golden/ul_rates_replay.json`` by a
connection-shaped stand-in, so the real ``Rates`` query code still runs.

A query that is not in the recording fails loudly. To (re)record after adding a
test that needs new rate queries, run the suite once with live read access::

    $env:SUITEVIEW_RECORD_UL_RATES = "1"
    venv\\Scripts\\python.exe -m pytest -q -p no:cacheprovider <tests>

Recording only executes the SELECTs the tests already issue and merges the
results into the replay file; review the diff before committing it.
"""
from __future__ import annotations

import datetime
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

REPLAY_PATH = Path(__file__).parent / "golden" / "ul_rates_replay.json"
RECORD_ENV = "SUITEVIEW_RECORD_UL_RATES"


def recording_enabled() -> bool:
    return os.environ.get(RECORD_ENV) == "1"


def _encode(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {"decimal": str(value)}
    if isinstance(value, datetime.datetime):
        return {"datetime": value.isoformat()}
    if isinstance(value, datetime.date):
        return {"date": value.isoformat()}
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict):
        if "decimal" in value:
            return Decimal(value["decimal"])
        if "datetime" in value:
            return datetime.datetime.fromisoformat(value["datetime"])
        if "date" in value:
            return datetime.date.fromisoformat(value["date"])
    return value


def _key(sql: str, params) -> str:
    return json.dumps([" ".join(sql.split()), [_encode(p) for p in (params or [])]])


def load_replay() -> dict[str, list[list[Any]]]:
    if not REPLAY_PATH.exists():
        return {}
    data = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
    return {entry["key"]: entry["rows"] for entry in data["queries"]}


def save_replay(recorded: dict[str, list[list[Any]]]) -> None:
    merged = load_replay()
    merged.update(recorded)
    payload = {
        "about": "Recorded UL_Rates query results for hermetic unit tests; see tests/ul_rates_replay.py.",
        "queries": [{"key": key, "rows": merged[key]} for key in sorted(merged)],
    }
    REPLAY_PATH.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")


class UnrecordedRateQuery(Exception):
    """A unit test issued a UL_Rates query that is not in the replay file."""


class _ReplayCursor:
    def __init__(self, replay: dict, recorded: dict | None, real_cursor=None):
        self._replay = replay
        self._recorded = recorded
        self._real = real_cursor
        self._rows: list[tuple] = []

    def execute(self, sql: str, params=None):
        key = _key(sql, params)
        if self._real is not None:
            self._real.execute(sql, params or [])
            rows = [tuple(row) for row in self._real.fetchall()]
            self._recorded[key] = [[_encode(v) for v in row] for row in rows]
            self._rows = rows
            return self
        if key not in self._replay:
            raise UnrecordedRateQuery(
                f"Unit test issued an unrecorded UL_Rates query: {key}. "
                f"Fake it in the test or re-record with {RECORD_ENV}=1 (see tests/ul_rates_replay.py)."
            )
        self._rows = [tuple(_decode(v) for v in row) for row in self._replay[key]]
        return self

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        if self._real is not None:
            self._real.close()


class ReplayConnection:
    """Connection-shaped stand-in for UL_Rates (replay, or record-through)."""

    def __init__(self, replay: dict, recorded: dict | None = None, real_connection=None):
        self._replay = replay
        self._recorded = recorded
        self._real = real_connection

    def cursor(self):
        return _ReplayCursor(self._replay, self._recorded,
                             self._real.cursor() if self._real is not None else None)

    def execute(self, sql: str, params=None):
        if " ".join(sql.split()).upper() == "SELECT 1":
            return self
        return self.cursor().execute(sql, params)

    def close(self):
        if self._real is not None:
            self._real.close()
