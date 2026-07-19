"""Tests for the illustration batch runner and the Batch tab.

The runner tests mock the per-policy run function (no DB2 / engine): results
collected in order, per-policy errors isolated, progress callback fired,
cancellation honored. The tab tests construct the widget offscreen and populate
it with a stubbed runner's results, following the Qt patterns of
tests/test_illustration_values_tab.py.
"""
import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.core.batch_runner import (
    FMT_DATE,
    FMT_MONEY,
    FORECAST_TYPES,
    GLP_COLUMNS,
    MINLEVEL_COLUMNS,
    ForecastType,
    PolicyResult,
    parse_policy_list,
    results_dataframe,
    run_batch,
)
from suiteview.illustration.ui.batch_tab import IllustrationBatchTab, _BatchWorker


_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _fake_forecast(run):
    return ForecastType(
        key="fake",
        label="Fake Forecast",
        columns=(("run_status", "Run Status"),
                 ("premium", "Premium"),
                 ("lapse", "Lapse Date")),
        formats={"premium": FMT_MONEY, "lapse": FMT_DATE},
        run=run,
    )


def _ok_result(policy, company=None, premium=123.456):
    return PolicyResult(
        policy=policy, company=company, status="Complete",
        values={"run_status": "Complete", "premium": premium,
                "lapse": date(2030, 6, 1)})


# ── parse_policy_list ────────────────────────────────────────────────


def test_parse_policy_list_tolerates_whitespace_blanks_and_duplicates():
    text = "  ul054426  \n\n UL054426\nS0503261\n\tS0503261 \n"
    assert parse_policy_list(text) == [(None, "UL054426"), (None, "S0503261")]


def test_parse_policy_list_accepts_company_prefix_variants():
    text = "01 UL054426\n01,UL058426\n26\tE0213651\nU0532652"
    assert parse_policy_list(text) == [
        ("01", "UL054426"),
        ("01", "UL058426"),
        ("26", "E0213651"),
        (None, "U0532652"),
    ]


def test_parse_policy_list_dedupes_on_company_and_policy():
    text = "01 UL054426\n01 UL054426\n04 UL054426"
    assert parse_policy_list(text) == [("01", "UL054426"), ("04", "UL054426")]


# ── run_batch ────────────────────────────────────────────────────────


def test_run_batch_collects_results_in_order_with_company_fallback():
    calls = []

    def run(policy, *, company=None, region="CKPR", engine=None):
        calls.append((policy, company, region))
        return _ok_result(policy, company)

    results = run_batch(
        [("01", "AAA"), (None, "BBB")], _fake_forecast(run),
        region="CKMO", default_company="04", engine=object())

    assert calls == [("AAA", "01", "CKMO"), ("BBB", "04", "CKMO")]
    assert [r.policy for r in results] == ["AAA", "BBB"]
    assert all(r.status == "Complete" for r in results)


def test_run_batch_isolates_one_policy_error():
    def run(policy, *, company=None, region="CKPR", engine=None):
        if policy == "BAD":
            raise RuntimeError("engine exploded")
        return _ok_result(policy)

    results = run_batch(
        ["AAA", "BAD", "CCC"], _fake_forecast(run), engine=object())

    assert [r.policy for r in results] == ["AAA", "BAD", "CCC"]
    assert results[0].status == "Complete"
    assert results[1].status == "Error"
    assert "engine exploded" in results[1].error
    assert results[2].status == "Complete"


def test_run_batch_fires_progress_with_one_based_index_and_total():
    seen = []

    def run(policy, *, company=None, region="CKPR", engine=None):
        return _ok_result(policy)

    run_batch(["AAA", "BBB", "CCC"], _fake_forecast(run),
              progress=lambda i, n, p: seen.append((i, n, p)),
              engine=object())

    assert seen == [(1, 3, "AAA"), (2, 3, "BBB"), (3, 3, "CCC")]


def test_run_batch_cancellation_stops_after_in_flight_policy():
    ran = []
    cancel_after_first = {"flag": False}

    def run(policy, *, company=None, region="CKPR", engine=None):
        ran.append(policy)
        cancel_after_first["flag"] = True  # cancel requested mid-policy
        return _ok_result(policy)

    results = run_batch(["AAA", "BBB", "CCC"], _fake_forecast(run),
                        should_cancel=lambda: cancel_after_first["flag"],
                        engine=object())

    # The in-flight policy (AAA) finishes; nothing after it starts.
    assert ran == ["AAA"]
    assert [r.policy for r in results] == ["AAA"]


def test_run_batch_skips_blank_entries():
    def run(policy, *, company=None, region="CKPR", engine=None):
        return _ok_result(policy)

    results = run_batch(["AAA", "", "  "], _fake_forecast(run), engine=object())
    assert [r.policy for r in results] == ["AAA"]


# ── results_dataframe ────────────────────────────────────────────────


def test_results_dataframe_columns_and_loud_errors():
    forecast = _fake_forecast(lambda *a, **k: None)
    results = [
        _ok_result("AAA", "01"),
        PolicyResult(policy="BAD", company=None, status="Error",
                     error="policy not found"),
    ]

    df = results_dataframe(results, forecast)

    # Run Status is folded into Status; the rest keep the forecast's order.
    assert list(df.columns) == ["Policy", "Company", "Status", "Error",
                                "Premium", "Lapse Date"]
    assert df.iloc[0]["Policy"] == "AAA"
    assert df.iloc[0]["Status"] == "Complete"
    assert df.iloc[0]["Premium"] == "123.46"       # money → 2dp string
    assert df.iloc[0]["Lapse Date"] == "6/1/2030"  # date → m/d/yyyy
    assert df.iloc[1]["Status"] == "Error"
    assert df.iloc[1]["Error"] == "policy not found"  # loud, never blank
    assert df.iloc[1]["Premium"] == ""


def test_registry_exposes_both_cli_forecasts():
    assert set(FORECAST_TYPES) == {"glp_forecasts", "min_level_to_exception"}
    glp = FORECAST_TYPES["glp_forecasts"]
    minlevel = FORECAST_TYPES["min_level_to_exception"]
    assert glp.columns == GLP_COLUMNS
    assert minlevel.columns == MINLEVEL_COLUMNS
    # Column labels stay in lock-step with the CLI workbook headers.
    assert dict(GLP_COLUMNS)["run_status"] == "Run Status"
    assert dict(MINLEVEL_COLUMNS)["min_prem"] == "Min Level Prem"


# ── Batch tab ────────────────────────────────────────────────────────


def test_batch_tab_constructs_with_forecast_choices():
    _app()
    tab = IllustrationBatchTab(runner=lambda *a, **k: [])

    labels = [tab.forecast_combo.itemText(i)
              for i in range(tab.forecast_combo.count())]
    assert labels == [f.label for f in FORECAST_TYPES.values()]
    assert tab.region_input.text() == "CKPR"
    assert not tab.run_btn.text() == ""
    assert not tab.cancel_btn.isEnabled()
    assert not tab.excel_btn.isEnabled()


def test_batch_tab_populates_results_grid_with_loud_errors():
    _app()
    tab = IllustrationBatchTab(runner=lambda *a, **k: [])
    tab.forecast_combo.setCurrentIndex(0)  # glp_forecasts

    results = [
        PolicyResult(policy="UL054426", company="01", status="Complete",
                     values={"run_status": "Complete", "plancode": "1U130N2X",
                             "level_prem": 55.25,
                             "exc_date": date(2031, 2, 1)}),
        PolicyResult(policy="XX999999", company=None, status="bypass (load error)",
                     error="Policy XX999999 not found in region CKPR",
                     values={"run_status": "bypass (load error)"}),
    ]
    tab.populate_results(results)

    df = tab.results_view.df
    assert list(df["Policy"]) == ["UL054426", "XX999999"]
    assert df.iloc[0]["Status"] == "Complete"
    assert df.iloc[0]["Plancode"] == "1U130N2X"
    assert df.iloc[0]["Level Prem to Exception"] == "55.25"
    assert df.iloc[1]["Status"] == "bypass (load error)"
    assert "not found" in df.iloc[1]["Error"]
    assert tab.excel_btn.isEnabled()
    assert tab.run_btn.isEnabled()
    assert not tab.cancel_btn.isEnabled()
    assert "Done — 2 policies" in tab.progress_label.text()


def test_batch_worker_runs_stub_runner_and_emits_signals():
    _app()

    def stub_runner(entries, forecast_key, *, region, default_company,
                    progress, should_cancel):
        assert forecast_key == "glp_forecasts"
        assert region == "CKPR"
        assert default_company == "01"
        out = []
        for i, (company, policy) in enumerate(entries, start=1):
            if should_cancel():
                break
            progress(i, len(entries), policy)
            out.append(_ok_result(policy, company or default_company))
        return out

    worker = _BatchWorker([(None, "AAA"), (None, "BBB")], "glp_forecasts",
                          "CKPR", "01", runner=stub_runner)
    progress_seen = []
    finished = []
    failed = []
    worker.progress.connect(lambda i, n, p: progress_seen.append((i, n, p)))
    worker.finished_results.connect(finished.append)
    worker.failed.connect(failed.append)

    worker.run()  # synchronous: exercise the thread body directly

    assert failed == []
    assert progress_seen == [(1, 2, "AAA"), (2, 2, "BBB")]
    assert len(finished) == 1
    assert [r.policy for r in finished[0]] == ["AAA", "BBB"]


def test_batch_worker_cancel_short_circuits_stub_runner():
    _app()

    def stub_runner(entries, forecast_key, *, region, default_company,
                    progress, should_cancel):
        out = []
        for i, (company, policy) in enumerate(entries, start=1):
            if should_cancel():
                break
            progress(i, len(entries), policy)
            out.append(_ok_result(policy))
        return out

    worker = _BatchWorker([(None, "AAA"), (None, "BBB")], "glp_forecasts",
                          "CKPR", None, runner=stub_runner)
    finished = []
    worker.finished_results.connect(finished.append)
    worker.cancel()   # cancel before the run starts — nothing should execute
    worker.run()

    assert len(finished) == 1
    assert finished[0] == []
