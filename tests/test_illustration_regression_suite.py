import json
import zipfile
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from suiteview.core import json_store
from suiteview.illustration.core.summary_results import ALL_COLUMNS
from suiteview.illustration.core.regression_runner import (
    BasisResult,
    DiffRecord,
    RegressionCaseResult,
    RegressionRun,
    STATUS_PASS,
)
from suiteview.illustration.models.case_store import SavedCase
from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.illustration.models.regression_suite import (
    RegressionSuiteError,
    create_suite,
    load_suite,
    save_suite,
    save_run_result,
    undo_baseline_update,
    update_baseline,
)


def _case(name: str) -> SavedCase:
    return SavedCase(
        name=name,
        policy_number=f"P-{name}",
        region="CKPR",
        company_code="01",
        saved_at=datetime(2026, 8, 5, 12, 0, 0),
        app_version="2.8",
        schema_version=2,
        inputs={"grids": {}, "controls": {}, "dynamic": {}},
        path=Path(f"{name}.case.json"),
        policy_snapshot=IllustrationPolicyData(
            policy_number=f"P-{name}", issue_date=date(2020, 1, 1)),
    )


def _rows(value: float) -> list[dict]:
    row = {column: 0.0 for column in ALL_COLUMNS}
    row.update({
        "Date": "2026-08-05",
        "Year": 1,
        "Month": 1,
        "Attained Age": 50,
        "DBO": "A",
        "EAV": value,
    })
    return [row]


def _actual(case_id: str, value: float) -> dict:
    return {case_id: {"current": _rows(value), "guaranteed": _rows(value - 1)}}


def test_suite_round_trip_and_selected_update_preserves_other_cases(tmp_path):
    suite = create_suite("Core Regression", [_case("A"), _case("B")])
    path = tmp_path / "core.svreg"
    save_suite(suite, path)
    loaded = load_suite(path)
    first, second = [entry.case_id for entry in loaded.cases]

    all_actual = {
        **_actual(first, 100.0),
        **_actual(second, 200.0),
    }
    loaded = update_baseline(loaded, all_actual, provenance={"run": "one"})
    assert loaded.active.revision == 1
    assert loaded.previous is None

    changed = _actual(first, 150.0)
    loaded = update_baseline(loaded, changed, [first], provenance={"run": "two"})
    assert loaded.active.revision == 2
    assert loaded.active.rows[first]["current"][0]["EAV"] == 150.0
    assert loaded.active.rows[second]["current"][0]["EAV"] == 200.0
    assert loaded.previous.revision == 1
    assert loaded.previous.rows[first]["current"][0]["EAV"] == 100.0

    reopened = load_suite(path)
    assert reopened.active.rows == loaded.active.rows
    assert [entry.case.name for entry in reopened.cases] == ["A", "B"]


def test_undo_swaps_active_and_previous_and_second_update_replaces_history(tmp_path):
    suite = create_suite("Undo", [_case("A")])
    save_suite(suite, tmp_path / "undo.svreg")
    case_id = suite.cases[0].case_id
    suite = update_baseline(suite, _actual(case_id, 10.0))
    suite = update_baseline(suite, _actual(case_id, 20.0))
    suite = undo_baseline_update(suite)
    assert suite.active.rows[case_id]["current"][0]["EAV"] == 10.0
    assert suite.previous.rows[case_id]["current"][0]["EAV"] == 20.0

    suite = update_baseline(suite, _actual(case_id, 30.0))
    assert suite.active.rows[case_id]["current"][0]["EAV"] == 30.0
    assert suite.previous.rows[case_id]["current"][0]["EAV"] == 10.0


def test_suite_rejects_snapshotless_case():
    case = replace(_case("A"), policy_snapshot=None)
    with pytest.raises(RegressionSuiteError, match="frozen schema-v2"):
        create_suite("Bad", [case])


def test_suite_detects_checksum_tampering(tmp_path):
    suite = create_suite("Checksums", [_case("A")])
    path = tmp_path / "checksums.svreg"
    save_suite(suite, path)

    with zipfile.ZipFile(path, "r") as source:
        members = {name: source.read(name) for name in source.namelist()}
    case_member = next(name for name in members if name.startswith("cases/"))
    payload = json.loads(members[case_member])
    payload["name"] = "Tampered"
    members[case_member] = json.dumps(payload).encode("utf-8")
    with zipfile.ZipFile(path, "w") as target:
        for name, data in members.items():
            target.writestr(name, data)

    with pytest.raises(RegressionSuiteError, match="Checksum mismatch"):
        load_suite(path)


def test_failed_atomic_replace_leaves_original_suite(tmp_path, monkeypatch):
    suite = create_suite("Atomic", [_case("A")])
    path = tmp_path / "atomic.svreg"
    save_suite(suite, path)
    original = path.read_bytes()

    def fail_replace(source, target):
        raise OSError("replace failed")

    monkeypatch.setattr(json_store.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        update_baseline(suite, _actual(suite.cases[0].case_id, 10.0))
    assert path.read_bytes() == original


def test_result_package_contains_actual_rows_diffs_and_baseline_identity(tmp_path):
    suite = create_suite("Result", [_case("A")])
    save_suite(suite, tmp_path / "result.svreg")
    case_id = suite.cases[0].case_id
    suite = update_baseline(suite, _actual(case_id, 100.0))
    diff = DiffRecord(
        case_id, "A", "current", "2026-08-05", 1, 1,
        "EAV", 100.0, 101.0, 1.0, 0.005)
    run = RegressionRun(
        "2026-08-05T10:00:00", "2026-08-05T10:01:00", "2.8",
        {"source": "test"},
        [RegressionCaseResult(
            case_id, "A", "P-A",
            BasisResult(STATUS_PASS, _rows(101.0), [diff]),
            BasisResult(STATUS_PASS, _rows(99.0)),
        )],
        baseline_revision=1,
        baseline_approved_at=suite.active.approved_at,
    )

    result_path = save_run_result(suite, run, tmp_path / "audit")
    assert result_path.name == "audit.svreg-result"
    with zipfile.ZipFile(result_path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["suite_id"] == suite.suite_id
        assert manifest["baseline_revision"] == 1
        assert manifest["cases"][0]["current_status"] == STATUS_PASS
        assert json.loads(archive.read("differences.json"))[0]["field"] == "EAV"
        actual_member = manifest["cases"][0]["actual"]["current"]
        assert json.loads(archive.read(actual_member))[0]["EAV"] == 101.0
