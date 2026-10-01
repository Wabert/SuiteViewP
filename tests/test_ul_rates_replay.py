"""The UL_Rates replay prune mode keeps only the queries a session replayed."""
from __future__ import annotations

import json

import pytest

from tests import ul_rates_replay


@pytest.fixture
def replay_file(tmp_path, monkeypatch):
    path = tmp_path / "ul_rates_replay.json"
    monkeypatch.setattr(ul_rates_replay, "REPLAY_PATH", path)
    ul_rates_replay.save_replay({
        ul_rates_replay._key("SELECT a FROM t WHERE x = ?", ["1"]): [[1]],
        ul_rates_replay._key("SELECT b FROM t", []): [[2]],
    })
    return path


def test_replayed_queries_are_tracked_and_unused_ones_pruned(replay_file):
    used: set = set()
    connection = ul_rates_replay.ReplayConnection(ul_rates_replay.load_replay(), used=used)

    rows = connection.cursor().execute("SELECT  a FROM t\n WHERE x = ?", ["1"]).fetchall()

    assert rows == [(1,)]
    assert ul_rates_replay.prune_replay(used) == 1
    kept = json.loads(replay_file.read_text(encoding="utf-8"))["queries"]
    assert [entry["key"] for entry in kept] == sorted(used)


def test_unrecorded_query_still_fails_loudly(replay_file):
    connection = ul_rates_replay.ReplayConnection(ul_rates_replay.load_replay(), used=set())

    with pytest.raises(ul_rates_replay.UnrecordedRateQuery):
        connection.cursor().execute("SELECT c FROM t", [])
