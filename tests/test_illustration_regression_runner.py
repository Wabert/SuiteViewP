from datetime import date
from types import SimpleNamespace

from suiteview.illustration.core.regression_runner import (
    MONEY_TOLERANCE,
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_NO_BASELINE,
    STATUS_PASS,
    PreparedRegressionCase,
    RegressionRun,
    compare_rows,
    recompare_run,
    run_regression,
)
from suiteview.illustration.core.summary_results import ALL_COLUMNS
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.illustration.models.regression_suite import BaselineRevision


def _row(value=100.0, *, rate=0.04, date_text="2026-08-05"):
    row = {column: 0.0 for column in ALL_COLUMNS}
    row.update({
        "Date": date_text,
        "Year": 1,
        "Month": 1,
        "Attained Age": 50,
        "DBO": "A",
        "EAV": value,
        "Interest Rate": rate,
    })
    return row


def test_compare_rows_uses_field_tolerances_and_exact_text():
    expected = [_row()]
    within = [_row(100.0 + MONEY_TOLERANCE, rate=0.04000001)]
    assert compare_rows("a", "A", "current", within, expected).status == STATUS_PASS

    money_fail = compare_rows(
        "a", "A", "current", [_row(100.006)], expected)
    assert money_fail.status == STATUS_FAIL
    assert money_fail.diffs[0].field == "EAV"
    assert money_fail.diffs[0].delta == 0.006000000000000227

    text = _row()
    text["DBO"] = "B"
    text_fail = compare_rows("a", "A", "current", [text], expected)
    assert text_fail.status == STATUS_FAIL
    assert text_fail.diffs[0].field == "DBO"
    assert text_fail.diffs[0].tolerance is None


def test_compare_rows_reports_missing_month_as_structural_failure():
    result = compare_rows(
        "a", "A", "guaranteed", [_row()], [_row(), _row(date_text="2026-09-05")])
    assert result.status == STATUS_FAIL
    assert result.diffs[-1].field == "<row>"
    assert result.diffs[-1].kind == "row"


def _state(value):
    return MonthlyState(
        date=date(2026, 8, 5), policy_year=1, policy_month=1,
        attained_age=50, db_option="A", av_end_of_month=value,
    )


def test_run_regression_current_guaranteed_and_immediate_recompare():
    policy = IllustrationPolicyData(db_option="A", face_amount=100000.0)

    def current_run(spec):
        return SimpleNamespace(
            policy=policy, results=[_state(100.0)], options=object(),
            future_inputs=object())

    def guaranteed_run(policy, results, **kwargs):
        return [_state(90.0)]

    prepared = [PreparedRegressionCase("a", "Case A", "P1", object())]
    run = run_regression(
        prepared, run_fn=current_run, guaranteed_fn=guaranteed_run)
    assert run.cases[0].current.status == STATUS_NO_BASELINE
    assert run.cases[0].guaranteed.status == STATUS_NO_BASELINE
    assert set(run.candidate_rows["a"]) == {"current", "guaranteed"}

    baseline = BaselineRevision(
        revision=1, approved_at="now", app_version="2.8",
        rows=run.candidate_rows)
    compared = recompare_run(run, baseline)
    assert compared.cases[0].current.status == STATUS_PASS
    assert compared.cases[0].guaranteed.status == STATUS_PASS


def test_run_regression_isolates_current_and_guaranteed_errors():
    prepared = [
        PreparedRegressionCase("a", "Bad Current", "P1", "bad"),
        PreparedRegressionCase("b", "Bad Guaranteed", "P2", "good"),
    ]
    policy = IllustrationPolicyData(db_option="A")

    def current_run(spec):
        if spec == "bad":
            raise ValueError("current boom")
        return SimpleNamespace(
            policy=policy, results=[_state(100.0)], options=None,
            future_inputs=None)

    def guaranteed_run(policy, results, **kwargs):
        raise ValueError("guaranteed boom")

    run = run_regression(
        prepared, run_fn=current_run, guaranteed_fn=guaranteed_run)
    assert run.cases[0].current.status == STATUS_ERROR
    assert run.cases[0].guaranteed.status == STATUS_ERROR
    assert run.cases[1].current.status == STATUS_NO_BASELINE
    assert run.cases[1].guaranteed.status == STATUS_ERROR
    assert run.candidate_rows == {}


def test_run_regression_honors_cancellation_between_cases():
    prepared = [
        PreparedRegressionCase("a", "A", "P1", object()),
        PreparedRegressionCase("b", "B", "P2", object()),
    ]
    calls = []
    policy = IllustrationPolicyData(db_option="A")

    def current_run(spec):
        calls.append(spec)
        return SimpleNamespace(
            policy=policy, results=[_state(100.0)], options=None,
            future_inputs=None)

    run = run_regression(
        prepared,
        run_fn=current_run,
        guaranteed_fn=lambda *args, **kwargs: [_state(90.0)],
        should_cancel=lambda: bool(calls),
    )
    assert run.cancelled
    assert len(run.cases) == 1
