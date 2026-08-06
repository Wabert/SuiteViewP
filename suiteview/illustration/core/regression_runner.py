"""Headless execution and comparison for illustration regression suites."""
from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from suiteview import __version__ as APP_VERSION
from suiteview.illustration.core.compare_runner import run_scenario
from suiteview.illustration.core.guaranteed_projection import run_guaranteed_projection
from suiteview.illustration.core.summary_results import (
    ALL_COLUMNS,
    LEAD_COLUMNS,
    json_safe_rows,
    project_summary_rows,
)

MONEY_TOLERANCE = 0.005
RATE_TOLERANCE = 1e-8
STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_ERROR = "ERROR"
STATUS_NO_BASELINE = "NO BASELINE"


@dataclass
class PreparedRegressionCase:
    case_id: str
    name: str
    policy_number: str
    spec: object = None
    preparation_error: str = ""


@dataclass
class DiffRecord:
    case_id: str
    case_name: str
    basis: str
    date: object
    year: object
    month: object
    field: str
    expected: object
    actual: object
    delta: Optional[float] = None
    tolerance: Optional[float] = None
    kind: str = "value"


@dataclass
class BasisResult:
    status: str
    rows: list[dict] = field(default_factory=list)
    diffs: list[DiffRecord] = field(default_factory=list)
    error: str = ""


@dataclass
class RegressionCaseResult:
    case_id: str
    name: str
    policy_number: str
    current: BasisResult
    guaranteed: BasisResult

    @property
    def error(self) -> str:
        return self.current.error or self.guaranteed.error

    @property
    def diffs(self) -> list[DiffRecord]:
        return self.current.diffs + self.guaranteed.diffs

    @property
    def candidate_rows(self) -> Optional[dict]:
        if self.current.error or self.guaranteed.error:
            return None
        if not self.current.rows or not self.guaranteed.rows:
            return None
        return {
            "current": self.current.rows,
            "guaranteed": self.guaranteed.rows,
        }


@dataclass
class RegressionRun:
    started_at: str
    completed_at: str
    app_version: str
    provenance: dict
    cases: list[RegressionCaseResult]
    cancelled: bool = False
    baseline_revision: Optional[int] = None
    baseline_approved_at: Optional[str] = None

    @property
    def candidate_rows(self) -> dict:
        return {
            result.case_id: result.candidate_rows
            for result in self.cases
            if result.candidate_rows is not None
        }

    @property
    def diffs(self) -> list[DiffRecord]:
        return [diff for result in self.cases for diff in result.diffs]


def _numeric(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _row_key(row: dict) -> tuple:
    return row.get("Date"), row.get("Year"), row.get("Month")


def compare_rows(
    case_id: str,
    case_name: str,
    basis: str,
    actual: list[dict],
    expected: Optional[list[dict]],
) -> BasisResult:
    if expected is None:
        return BasisResult(status=STATUS_NO_BASELINE, rows=actual)

    diffs = []
    expected_by_key = {_row_key(row): row for row in expected}
    actual_by_key = {_row_key(row): row for row in actual}
    if len(expected_by_key) != len(expected):
        raise ValueError(f"{case_name} {basis} baseline has duplicate row keys.")
    if len(actual_by_key) != len(actual):
        raise ValueError(f"{case_name} {basis} result has duplicate row keys.")

    keys = list(dict.fromkeys([*expected_by_key, *actual_by_key]))
    for key in keys:
        expected_row = expected_by_key.get(key)
        actual_row = actual_by_key.get(key)
        if expected_row is None or actual_row is None:
            diffs.append(DiffRecord(
                case_id, case_name, basis, key[0], key[1], key[2],
                "<row>", "present" if expected_row else "missing",
                "present" if actual_row else "missing", kind="row",
            ))
            continue
        if tuple(expected_row.keys()) != ALL_COLUMNS or tuple(actual_row.keys()) != ALL_COLUMNS:
            diffs.append(DiffRecord(
                case_id, case_name, basis, key[0], key[1], key[2],
                "<schema>", list(expected_row), list(actual_row), kind="schema",
            ))
            continue
        for column in ALL_COLUMNS:
            expected_value = expected_row[column]
            actual_value = actual_row[column]
            if column in LEAD_COLUMNS or not (
                _numeric(expected_value) and _numeric(actual_value)
            ):
                equal = type(expected_value) is type(actual_value) and expected_value == actual_value
                tolerance = None
                delta = None
            else:
                tolerance = RATE_TOLERANCE if column == "Interest Rate" else MONEY_TOLERANCE
                delta = float(actual_value) - float(expected_value)
                boundary = tolerance + max(
                    math.ulp(float(actual_value)),
                    math.ulp(float(expected_value)),
                )
                equal = abs(delta) <= boundary
            if not equal:
                diffs.append(DiffRecord(
                    case_id, case_name, basis, key[0], key[1], key[2],
                    column, expected_value, actual_value, delta, tolerance,
                ))
    return BasisResult(
        status=STATUS_FAIL if diffs else STATUS_PASS,
        rows=actual,
        diffs=diffs,
    )


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_provenance() -> dict:
    plancode_dir = Path(__file__).resolve().parent.parent / "plancodes"
    files = {}
    for path in sorted(plancode_dir.glob("*.json")):
        files[path.name] = _file_hash(path)
    return {
        "app_version": APP_VERSION,
        "local_data": os.environ.get("SUITEVIEW_LOCAL_DATA") == "1",
        "plancode_json_sha256": files,
    }


def _baseline_rows(active_baseline, case_id: str, basis: str):
    if active_baseline is None:
        return None
    return (active_baseline.rows.get(case_id) or {}).get(basis)


def recompare_run(run: RegressionRun, active_baseline) -> RegressionRun:
    """Recompare retained actual rows after baseline update/undo, without rerun."""
    cases = []
    for result in run.cases:
        current = result.current
        guaranteed = result.guaranteed
        if not current.error:
            current = compare_rows(
                result.case_id, result.name, "current", current.rows,
                _baseline_rows(active_baseline, result.case_id, "current"),
            )
        if not guaranteed.error:
            guaranteed = compare_rows(
                result.case_id, result.name, "guaranteed", guaranteed.rows,
                _baseline_rows(active_baseline, result.case_id, "guaranteed"),
            )
        cases.append(RegressionCaseResult(
            result.case_id, result.name, result.policy_number,
            current, guaranteed,
        ))
    return RegressionRun(
        started_at=run.started_at,
        completed_at=run.completed_at,
        app_version=run.app_version,
        provenance=run.provenance,
        cases=cases,
        cancelled=run.cancelled,
        baseline_revision=(
            active_baseline.revision if active_baseline is not None else None),
        baseline_approved_at=(
            active_baseline.approved_at if active_baseline is not None else None),
    )


def run_regression(
    prepared_cases: list[PreparedRegressionCase],
    active_baseline=None,
    *,
    progress: Optional[Callable[[int, int, str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    run_fn=run_scenario,
    guaranteed_fn=run_guaranteed_projection,
) -> RegressionRun:
    started = datetime.now().isoformat(timespec="seconds")
    results = []
    cancelled = False
    total = len(prepared_cases)
    for index, prepared in enumerate(prepared_cases, start=1):
        if should_cancel and should_cancel():
            cancelled = True
            break
        if progress:
            progress(index, total, prepared.name)
        if prepared.preparation_error:
            results.append(RegressionCaseResult(
                prepared.case_id, prepared.name, prepared.policy_number,
                BasisResult(STATUS_ERROR, error=prepared.preparation_error),
                BasisResult(STATUS_ERROR, error="Case preparation failed."),
            ))
            continue
        try:
            outcome = run_fn(prepared.spec)
            current_rows = json_safe_rows(project_summary_rows(
                outcome.policy, outcome.results or []))
            current = compare_rows(
                prepared.case_id, prepared.name, "current", current_rows,
                _baseline_rows(active_baseline, prepared.case_id, "current"),
            )
        except Exception as exc:
            message = str(exc) or type(exc).__name__
            results.append(RegressionCaseResult(
                prepared.case_id, prepared.name, prepared.policy_number,
                BasisResult(STATUS_ERROR, error=message),
                BasisResult(STATUS_ERROR, error="Current projection failed."),
            ))
            continue

        try:
            guaranteed_results = guaranteed_fn(
                outcome.policy,
                outcome.results,
                base_options=outcome.options,
                base_future_inputs=outcome.future_inputs,
            )
            guaranteed_rows = json_safe_rows(project_summary_rows(
                outcome.policy, guaranteed_results))
            if not guaranteed_rows:
                raise ValueError("Guaranteed projection returned no rows.")
            guaranteed = compare_rows(
                prepared.case_id, prepared.name, "guaranteed", guaranteed_rows,
                _baseline_rows(active_baseline, prepared.case_id, "guaranteed"),
            )
        except Exception as exc:
            guaranteed = BasisResult(
                STATUS_ERROR, error=str(exc) or type(exc).__name__)
        results.append(RegressionCaseResult(
            prepared.case_id, prepared.name, prepared.policy_number,
            current, guaranteed,
        ))

    return RegressionRun(
        started_at=started,
        completed_at=datetime.now().isoformat(timespec="seconds"),
        app_version=APP_VERSION,
        provenance=collect_provenance(),
        cases=results,
        cancelled=cancelled,
        baseline_revision=(
            active_baseline.revision if active_baseline is not None else None),
        baseline_approved_at=(
            active_baseline.approved_at if active_baseline is not None else None),
    )
