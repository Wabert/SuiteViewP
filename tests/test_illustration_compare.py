"""Tests for the scenario comparison runner and the Compare tab.

The runner tests stub the per-scenario run function (no DB2 / engine): KPI
extraction (lapse vs sustains, MEC, deltas and their signs/tones), one-side
failure isolation, and the side-by-side scenario-block ledger DataFrame —
Year | Age, then A's block, a separator column, then B's block, with NO Δ
columns (deltas live only in the KPI rows), plain measure display labels, and
scenario names carried by the grouped-header spans. The tab tests construct
the widget offscreen and populate it with a stubbed runner's result,
following the Qt patterns of tests/test_illustration_batch.py.
"""
import os
from datetime import date
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from PyQt6.QtWidgets import QApplication

from suiteview.illustration.core.compare_runner import (
    LEDGER_SEPARATOR,
    ComparisonResult,
    KpiRow,
    ScenarioOutcome,
    ScenarioSpec,
    annual_rows,
    build_comparison_ledger,
    build_kpi_rows,
    kpi_summary_frame,
    ledger_block_columns,
    ledger_column_groups,
    ledger_header_labels,
    run_comparison,
    run_scenario,
    scenario_kpi_values,
    separator_columns,
    side_tags,
)
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.ui.compare_tab import (
    CURRENT_INPUTS_LABEL,
    NO_SCENARIO_LABEL,
    _NO_SCENARIO,
    _SEPARATOR_COLOR,
    _SEPARATOR_WIDTH,
    IllustrationCompareTab,
    _CompareWorker,
    _ScenarioComboBox,
)
from suiteview.illustration.ui.saved_cases_panel import SAVED_CASE_MIME

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _policy(**kw):
    kw.setdefault("is_mec", False)
    return SimpleNamespace(**kw)


def _state(year, month, **kw):
    return MonthlyState(
        date=date(2026, 1, 1),
        policy_year=year,
        policy_month=month,
        attained_age=44 + year,
        **kw,
    )


def _run(years, *, lapse_year=None, matured=False, premium=1200.0,
         av=10_000.0, sv=9_000.0, db=100_000.0, wd_per_year=0.0,
         new_loan_per_year=0.0, repay_per_year=0.0):
    """A projection: the inforce row plus one December-ish row per year.

    One state per policy year keeps the annual aggregation obvious: annual
    premium == ``premium``, EOY AV grows by 1000/yr, etc.
    """
    results = [_state(0, 0)]   # inforce row
    wd_to_date = 0.0
    for year in range(1, years + 1):
        wd_to_date += wd_per_year
        state = _state(
            year, 12,
            gross_premium=premium,
            av_end_of_month=av + 1000.0 * year,
            ending_sv=sv + 1000.0 * year,
            ending_db=db,
            withdrawals_to_date=wd_to_date,
            applied_regular_loan=new_loan_per_year,
            applied_loan_repayment=repay_per_year,
        )
        if lapse_year is not None and year >= lapse_year:
            state.lapsed = True
        if matured and year == years:
            state.matured = True
        results.append(state)
        if lapse_year is not None and year >= lapse_year:
            break
    return results


def _outcome(label, results, policy=None, error=None):
    return ScenarioOutcome(
        label=label, results=results,
        policy=policy or _policy(), error=error)


def _dummy_spec(label):
    return ScenarioSpec(label=label, scenario=None, months=None, options=None)


# ── KPI extraction ───────────────────────────────────────────────────


def test_kpi_values_lapse_and_sustains():
    lapsing = scenario_kpi_values(_policy(), _run(6, lapse_year=3))
    assert lapsing["outcome"] == "Lapses Yr 3 · Age 47"
    assert lapsing["lapse_year"] == 3

    matured = scenario_kpi_values(_policy(), _run(40, matured=True))
    assert matured["outcome"] == "Sustains to maturity"
    assert matured["lapse_year"] is None

    horizon = scenario_kpi_values(_policy(), _run(10))
    assert horizon["outcome"] == "In force to Yr 10 (end of projection)"


def test_kpi_values_points_total_outlay_and_first_exception():
    results = _run(12, premium=1200.0)
    results[3].gp_exception_prem = 50.0   # policy year 3
    kpis = scenario_kpi_values(_policy(), results)

    assert kpis["total_outlay"] == 1200.0 * 12 + 50.0
    assert kpis["first_exception_year"] == 3
    assert kpis["points"][5]["av"] == 15_000.0
    assert kpis["points"][10]["sv"] == 19_000.0
    assert kpis["points"][20] is None            # projection stops at year 12
    assert kpis["points"]["end"]["av"] == 22_000.0


def test_mec_status_inforce_projected_and_clean():
    assert scenario_kpi_values(
        _policy(is_mec=True), _run(2))["mec"] == "MEC (inforce)"

    results = _run(3)
    results[2].tamra_year = 2
    results[2].tamra_7pay_level = 500.0
    results[2].accumulated_7pay = 1_500.0   # > 2 × 500
    assert scenario_kpi_values(_policy(), results)["mec"] == "Becomes MEC (Yr 2)"

    assert scenario_kpi_values(_policy(), _run(3))["mec"] == "Not a MEC"


# ── KPI rows / deltas ────────────────────────────────────────────────


def test_kpi_rows_delta_signs_and_tones():
    a = _outcome("Current Inputs", _run(10, premium=1000.0, av=10_000.0))
    b = _outcome("Solved Min", _run(10, premium=800.0, av=12_000.0))
    rows = {row.key: row for row in build_kpi_rows([a, b])}

    outlay = rows["total_outlay"]
    assert outlay.delta_value == -2000.0
    assert outlay.tone == "good"            # lower outlay is better
    assert outlay.delta_text == "-2,000"

    av_end = rows["av_end"]
    assert av_end.delta_value == 2000.0
    assert av_end.tone == "good"            # higher AV is better
    assert av_end.delta_text == "+2,000"


def test_kpi_rows_lapse_vs_sustains():
    lapser = _outcome("Current Inputs", _run(20, lapse_year=8))
    sustainer = _outcome("With Repay Plan", _run(40, matured=True))

    rows = {row.key: row for row in build_kpi_rows([lapser, sustainer])}
    assert rows["outcome"].values[0].startswith("Lapses Yr 8")
    assert rows["outcome"].values[1] == "Sustains to maturity"
    assert rows["outcome"].delta_text == "B sustains; A lapses"
    assert rows["outcome"].tone == "good"

    # Reversed: B lapsing earlier than A is bad and the year delta is signed.
    rows = {row.key: row
            for row in build_kpi_rows([
                _outcome("A", _run(20, lapse_year=8)),
                _outcome("B", _run(20, lapse_year=5))])}
    assert rows["outcome"].delta_value == -3.0
    assert rows["outcome"].delta_text == "-3 yrs"
    assert rows["outcome"].tone == "bad"


def test_kpi_rows_one_side_failure_keeps_survivor():
    a = _outcome("Current Inputs", _run(10))
    b = ScenarioOutcome(label="Broken Case", error="solver exploded")

    rows = build_kpi_rows([a, b])
    by_key = {row.key: row for row in rows}
    assert by_key["total_outlay"].values[0] == "12,000"   # 10 yrs × 1,200
    assert by_key["total_outlay"].values[1] == "—"
    assert by_key["total_outlay"].delta_text == "—"
    assert by_key["total_outlay"].tone == "neutral"
    assert by_key["outcome"].values[0] == "In force to Yr 10 (end of projection)"
    assert by_key["outcome"].values[1] == "—"


def test_run_comparison_isolates_one_scenario_error():
    ok_results = _run(5)

    def run_fn(spec, engine=None):
        if spec.label == "BAD":
            raise RuntimeError("engine exploded")
        return _outcome(spec.label, ok_results)

    result = run_comparison(
        [_dummy_spec("GOOD"), _dummy_spec("BAD")], run_fn=run_fn)

    a, b = result.outcomes
    assert a.ok
    assert not b.ok
    assert "engine exploded" in b.error
    assert result.kpis                       # survivor's KPIs still produced
    assert not result.ledger.empty
    assert "A: AV" in result.ledger.columns
    # The scenario names still title the blocks via the grouped header.
    groups = ledger_column_groups(result.ledger, a.label, b.label)
    assert [label for label, _cols in groups] == ["GOOD", "BAD"]
    # The failed side's cells are blank, never fabricated.
    assert result.ledger["B: AV"].isna().all()


# ── annual rows / ledger ─────────────────────────────────────────────


def test_annual_rows_sums_flows_and_takes_eoy_balances():
    rows = annual_rows(_run(3, premium=1200.0, wd_per_year=500.0,
                            new_loan_per_year=250.0, repay_per_year=100.0))
    # Rollups: Contributions = premium outlay + loan repay; Distributions =
    # withdrawals + force-outs + new loans.
    assert rows[2]["contributions"] == 1300.0        # 1,200 + 100
    assert rows[2]["distributions"] == 750.0          # 500 + 0 + 250
    assert sorted(rows) == [1, 2, 3]
    assert rows[2]["outlay"] == 1200.0
    assert rows[2]["wd"] == 500.0
    assert rows[2]["new_loan"] == 250.0
    assert rows[2]["loan_repay"] == 100.0
    assert rows[2]["av"] == 12_000.0        # EOY balance, not a sum
    assert rows[3]["db"] == 100_000.0
    assert annual_rows(None) == {}
    assert annual_rows([_state(0, 0)]) == {}


def test_ledger_is_two_scenario_blocks_with_separator():
    a = _outcome("Current Inputs", _run(3))
    b = _outcome("DB Opt A", _run(3, wd_per_year=500.0))

    ledger = build_comparison_ledger([a, b])

    # Every block carries the same five measures — cash flows rolled up into
    # Contributions / Distributions. Block A is contiguous, then the separator,
    # then block B.
    stems = ("Contributions", "Distributions", "AV", "SV", "DB")
    expected = (["Year", "Age"]
                + [f"A: {stem}" for stem in stems]
                + [LEDGER_SEPARATOR]
                + [f"B: {stem}" for stem in stems])
    assert list(ledger.columns) == expected
    # No Δ columns anywhere — deltas live only in the KPI summary.
    assert not any("Δ" in str(c) for c in ledger.columns)
    assert list(ledger.columns).index(LEDGER_SEPARATOR) == 2 + len(stems)
    assert len(ledger) == 3
    assert list(ledger["Year"]) == [1, 2, 3]
    assert list(ledger[LEDGER_SEPARATOR]) == ["", "", ""]
    # Only B withdraws → its Distributions carry the 500/yr; A's are zero.
    assert list(ledger["B: Distributions"]) == [500.0, 500.0, 500.0]
    assert list(ledger["A: Distributions"]) == [0.0, 0.0, 0.0]


def test_ledger_display_labels_and_grouped_scenario_headers():
    a = _outcome("Current Inputs", _run(3))
    b = _outcome("DB Opt A", _run(3))

    ledger = build_comparison_ledger([a, b])

    # Display labels are plain measure names (no scenario suffix); the
    # separator's header is blank.
    labels = ledger_header_labels(ledger)
    assert labels["A: Contributions"] == "Contributions"
    assert labels["B: AV"] == "AV"
    assert labels[LEDGER_SEPARATOR] == ""
    assert "Year" not in labels                # shared columns keep their names

    # Scenario identity rides the grouped-header spans, one per block.
    a_cols, b_cols = ledger_block_columns(ledger)
    assert ledger_column_groups(ledger, a.label, b.label) == [
        ("Current Inputs", a_cols), ("DB Opt A", b_cols)]
    # Identical labels still disambiguate via side_tags.
    groups = ledger_column_groups(ledger, "Same", "Same")
    assert [label for label, _cols in groups] == ["Same (A)", "Same (B)"]


def test_ledger_blanks_years_one_side_never_reaches():
    a = _outcome("Current Inputs", _run(5, lapse_year=2))
    b = _outcome("Funded", _run(4))

    ledger = build_comparison_ledger([a, b])

    assert list(ledger["Year"]) == [1, 2, 3, 4]
    assert pd.isna(ledger.loc[2, "A: AV"])     # year 3: A lapsed away
    assert ledger.loc[2, "B: AV"] == 13_000.0


def test_side_tags_disambiguate_identical_labels():
    assert side_tags("Case X", "Case Y") == ("Case X", "Case Y")
    assert side_tags("Case X", "Case X") == ("Case X (A)", "Case X (B)")
    assert side_tags("", "") == ("Scenario A", "Scenario B")


def test_kpi_summary_frame_carries_labels_in_headers():
    a = _outcome("Current Inputs", _run(3))
    b = _outcome("Solved Min", _run(3))
    result = ComparisonResult(outcomes=[a, b], kpis=build_kpi_rows([a, b]),
                              ledger=build_comparison_ledger([a, b]))

    frame = kpi_summary_frame(result)
    assert list(frame.columns) == [
        "KPI", "Current Inputs", "Solved Min", "Δ (B − A)"]
    assert "Outcome" in list(frame["KPI"])


# ── three-scenario comparison ────────────────────────────────────────


def test_three_scenario_ledger_has_three_blocks_and_two_solid_dividers():
    a = _outcome("Current Inputs", _run(3))
    b = _outcome("Opt A", _run(3))
    c = _outcome("Opt B", _run(3, wd_per_year=250.0))

    ledger = build_comparison_ledger([a, b, c])

    stems = ("Contributions", "Distributions", "AV", "SV", "DB")
    expected = (["Year", "Age"]
                + [f"A: {stem}" for stem in stems]
                + [LEDGER_SEPARATOR]
                + [f"B: {stem}" for stem in stems]
                + [f"{LEDGER_SEPARATOR}2"]
                + [f"C: {stem}" for stem in stems])
    assert list(ledger.columns) == expected
    assert separator_columns(ledger) == [LEDGER_SEPARATOR, f"{LEDGER_SEPARATOR}2"]
    a_cols, b_cols, c_cols = ledger_block_columns(ledger)
    assert c_cols == [f"C: {stem}" for stem in stems]
    # Grouped headers carry all three scenario names.
    groups = ledger_column_groups(ledger, a.label, b.label, c.label)
    assert [label for label, _cols in groups] == [
        "Current Inputs", "Opt A", "Opt B"]
    # Only C withdraws; its Distributions own the activity.
    assert list(ledger["C: Distributions"]) == [250.0, 250.0, 250.0]
    assert list(ledger["A: Distributions"]) == [0.0, 0.0, 0.0]
    labels = ledger_header_labels(ledger)
    assert labels["C: AV"] == "AV"
    assert labels[f"{LEDGER_SEPARATOR}2"] == ""


def test_three_scenario_kpis_show_all_values_and_deltas_vs_a():
    a = _outcome("Base", _run(10, premium=1000.0, av=10_000.0))
    b = _outcome("More", _run(10, premium=1200.0, av=12_000.0))
    c = _outcome("Less", _run(10, premium=800.0, av=9_000.0))

    rows = {row.key: row for row in build_kpi_rows([a, b, c])}

    outlay = rows["total_outlay"]
    assert outlay.values == ["10,000", "12,000", "8,000"]
    # Both deltas against A on one neutral line — two deltas can disagree,
    # so no single green/red applies.
    assert outlay.delta_text == "B +2,000 · C -2,000"
    assert outlay.tone == "neutral"
    assert outlay.delta_value is None

    av_end = rows["av_end"]
    assert av_end.values == ["20,000", "22,000", "19,000"]
    assert av_end.delta_text == "B +2,000 · C -1,000"


def test_three_scenario_one_failure_keeps_both_survivors():
    ok_results = _run(4)

    def run_fn(spec, engine=None):
        if spec.label == "BAD":
            raise RuntimeError("solver exploded")
        return _outcome(spec.label, ok_results)

    result = run_comparison(
        [_dummy_spec("GOOD1"), _dummy_spec("BAD"), _dummy_spec("GOOD2")],
        run_fn=run_fn)

    oks = [o.ok for o in result.outcomes]
    assert oks == [True, False, True]
    assert "solver exploded" in result.outcomes[1].error
    assert result.ledger["B: AV"].isna().all()      # failed middle block blank
    assert not result.ledger["A: AV"].isna().any()
    assert not result.ledger["C: AV"].isna().any()
    by_key = {row.key: row for row in result.kpis}
    assert by_key["total_outlay"].values[1] == "—"
    assert by_key["total_outlay"].values[2] == "4,800"   # 4 yrs × 1,200


def test_run_comparison_rejects_wrong_scenario_count():
    import pytest

    with pytest.raises(ValueError):
        run_comparison([_dummy_spec("only one")], run_fn=lambda s, engine=None: None)
    with pytest.raises(ValueError):
        run_comparison([_dummy_spec(str(i)) for i in range(4)],
                       run_fn=lambda s, engine=None: None)


def test_side_tags_three_way_disambiguation():
    assert side_tags("X", "Y", "Z") == ("X", "Y", "Z")
    assert side_tags("Same", "Same", "Other") == (
        "Same (A)", "Same (B)", "Other")
    assert side_tags("", "", "") == ("Scenario A", "Scenario B", "Scenario C")


def test_kpi_summary_frame_three_scenarios_delta_header():
    a = _outcome("One", _run(3))
    b = _outcome("Two", _run(3))
    c = _outcome("Three", _run(3))
    result = ComparisonResult(outcomes=[a, b, c],
                              kpis=build_kpi_rows([a, b, c]),
                              ledger=build_comparison_ledger([a, b, c]))

    frame = kpi_summary_frame(result)
    assert list(frame.columns) == ["KPI", "One", "Two", "Three", "Δ (vs A)"]


# ── Compare tab ──────────────────────────────────────────────────────


def _stub_runner(result):
    return lambda specs, **kw: result


def _saved_case_mime(name):
    """A drag payload identical to what the Saved Cases panel produces."""
    from PyQt6.QtCore import QByteArray, QMimeData

    mime = QMimeData()
    mime.setData(SAVED_CASE_MIME, QByteArray(name.encode("utf-8")))
    mime.setText(name)
    return mime


def test_compare_tab_constructs_with_defaults(tmp_path):
    _app()
    tab = IllustrationCompareTab(runner=_stub_runner(None),
                                 case_directory=tmp_path)

    assert tab.run_btn.text() == "Run Comparison"
    assert not tab.excel_btn.isEnabled()
    assert tab.banner_a.isHidden()
    assert tab.banner_b.isHidden()
    assert tab.banner_c.isHidden()
    tab.refresh_scenario_choices()

    # Every picker holds ONLY the fixed slots — Current Inputs + (none), never
    # an enumeration of saved cases. With no case dropped, that is two entries.
    for combo in tab.scenario_combos:
        assert combo.count() == 2
        assert combo.itemText(0) == CURRENT_INPUTS_LABEL
        assert combo.itemText(1) == NO_SCENARIO_LABEL
    # A leads on Current Inputs; B and C start skipped at (none).
    assert tab.scenario_a_combo.currentText() == CURRENT_INPUTS_LABEL
    assert tab.scenario_b_combo.currentText() == NO_SCENARIO_LABEL
    assert tab.scenario_c_combo.currentText() == NO_SCENARIO_LABEL
    assert not tab._third_scenario_active()


def test_compare_tab_never_enumerates_saved_cases(tmp_path):
    """Even with saved cases on disk (and the loaded policy owning some), the
    pickers stay at the three fixed slots — cases enter only by drag-drop."""
    _app()
    from suiteview.illustration.models import case_store

    for name in ("Case One", "Case Two", "Case Three"):
        case_store.save_case(
            name, policy_number="UL054426", region="CKPR", company_code="01",
            inputs={"grids": {}}, directory=tmp_path)
    window = SimpleNamespace(_current_key=("UL054426", "CKPR", "01"))
    tab = IllustrationCompareTab(window=window, runner=_stub_runner(None),
                                 case_directory=tmp_path)
    tab.refresh_scenario_choices()

    for combo in tab.scenario_combos:
        assert combo.count() == 2   # Current Inputs + (none) only
        assert [combo.itemText(i) for i in range(combo.count())] == [
            CURRENT_INPUTS_LABEL, NO_SCENARIO_LABEL]


def test_compare_tab_drop_populates_and_selects_case(tmp_path):
    _app()
    from suiteview.illustration.models import case_store

    case_store.save_case(
        "My Min Prem", policy_number="UL054426", region="CKPR",
        company_code="01", inputs={"grids": {}}, directory=tmp_path)
    tab = IllustrationCompareTab(runner=_stub_runner(None),
                                 case_directory=tmp_path)

    combo = tab.scenario_b_combo
    assert combo.currentText() == NO_SCENARIO_LABEL
    # Dropping resolves the case from the store and loads it into the picker.
    tab._on_case_dropped(combo, "My Min Prem")

    # Now exactly three slots: Current Inputs, the dropped case (selected), (none).
    assert combo.count() == 3
    assert [combo.itemText(i) for i in range(3)] == [
        CURRENT_INPUTS_LABEL, "My Min Prem", NO_SCENARIO_LABEL]
    assert combo.currentIndex() == 1
    assert combo.currentText() == "My Min Prem"
    assert tab._selected_case(combo) is combo.dropped_case()
    assert combo.dropped_case().name == "My Min Prem"


def test_scenario_combo_drop_emits_dropped_case_name():
    """The picker parses the custom MIME and emits the dropped case name;
    a foreign payload is ignored. Exercised through the drop-handling seam
    with a constructed QMimeData (no live QDropEvent)."""
    _app()
    from PyQt6.QtCore import QMimeData

    combo = _ScenarioComboBox()
    received: list = []
    combo.case_drop_requested.connect(received.append)

    assert combo.handle_dropped_mime(_saved_case_mime("Dropped Case")) is True
    assert received == ["Dropped Case"]

    # A drag that is not a saved-case row is not handled and emits nothing.
    plain = QMimeData()
    plain.setText("just text")
    assert combo.handle_dropped_mime(plain) is False
    assert received == ["Dropped Case"]


def test_compare_tab_none_clears_comparison_source(tmp_path):
    _app()
    from suiteview.illustration.models import case_store

    case_store.save_case(
        "Case Z", policy_number="UL054426", region="CKPR", company_code="01",
        inputs={"grids": {}}, directory=tmp_path)
    tab = IllustrationCompareTab(runner=_stub_runner(None),
                                 case_directory=tmp_path)
    combo = tab.scenario_b_combo
    tab._on_case_dropped(combo, "Case Z")
    assert tab._selected_case(combo) is not None

    # Selecting (none) clears the source — the side carries no case.
    combo.select_none()
    assert combo.currentText() == NO_SCENARIO_LABEL
    assert combo.currentData() == _NO_SCENARIO
    assert tab._selected_case(combo) is None
    # The dropped case stays in its slot, ready to re-select without re-dropping.
    assert combo.itemText(1) == "Case Z"


def _made_case(name, policy="UL054426", snapshot="SNAP"):
    """A real SavedCase (isinstance checks matter to _selected_case) carrying
    a stand-in frozen snapshot."""
    from datetime import datetime
    from pathlib import Path

    from suiteview.illustration.models.case_store import SavedCase

    return SavedCase(
        name=name, policy_number=policy, region="CKPR", company_code="01",
        saved_at=datetime(2026, 7, 1), app_version="test", schema_version=2,
        inputs={}, path=Path(f"{name}.json"),
        policy_snapshot=SimpleNamespace(marker=snapshot))


def _capture_info_boxes(monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    seen: list = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda _parent, _title, text, *a, **k: seen.append(text)))
    return seen


def test_run_two_dropped_cases_needs_no_loaded_policy(monkeypatch):
    """A comparison built purely from dropped saved cases runs with NO policy
    loaded — each side projects from its own frozen snapshot."""
    _app()
    infos = _capture_info_boxes(monkeypatch)

    a = _outcome("Case One", _run(3))
    b = _outcome("Case Two", _run(3, premium=800.0))
    result = ComparisonResult(outcomes=[a, b], kpis=build_kpi_rows([a, b]),
                              ledger=build_comparison_ledger([a, b]))
    tab = IllustrationCompareTab(window=None, runner=_stub_runner(result))

    built: list = []

    def fake_build_spec(self, case, key, side):
        built.append((side, case, key))
        return ScenarioSpec(label=case.name, scenario=None, months=None,
                            options=None)

    monkeypatch.setattr(IllustrationCompareTab, "_build_spec", fake_build_spec)
    # Run the worker body synchronously so the result lands in-test.
    monkeypatch.setattr(_CompareWorker, "start", lambda self: self.run())

    tab.scenario_a_combo.set_dropped_case(_made_case("Case One"))
    tab.scenario_b_combo.set_dropped_case(_made_case("Case Two"))
    tab._on_run()

    # No gate fired; both sides were built from their own saved case (key is
    # None — there is no live policy) and the comparison rendered.
    assert infos == []
    assert [(side, case.name, key) for side, case, key in built] == [
        ("A", "Case One", None), ("B", "Case Two", None)]
    assert tab.status_label.text() == "Comparison ready."
    assert "A: AV" in tab.ledger_view.df.columns


def test_run_current_inputs_without_policy_shows_reworded_gate(monkeypatch):
    """Current Inputs on an active side still requires a loaded policy — the
    message box names that, and nothing runs."""
    _app()
    infos = _capture_info_boxes(monkeypatch)
    tab = IllustrationCompareTab(window=None, runner=_stub_runner(None))

    # A stays on Current Inputs; B gets a dropped case. No policy loaded.
    tab.scenario_b_combo.set_dropped_case(_made_case("Case Two"))
    tab._on_run()

    assert len(infos) == 1
    assert infos[0].startswith("Load a policy to compare Current Inputs")
    assert tab._worker is None
    assert tab.run_btn.isEnabled()


def test_saved_cases_view_rows_are_draggable(tmp_path):
    """The Saved Cases panel produces the custom drag payload for a case row."""
    _app()
    from PyQt6.QtWidgets import QAbstractItemView

    from suiteview.illustration.models import case_store
    from suiteview.illustration.ui.saved_cases_panel import SavedCasesView

    case_store.save_case(
        "Draggable Case", policy_number="UL054426", region="CKPR",
        company_code="01", inputs={"grids": {}}, directory=tmp_path)
    view = SavedCasesView()
    view.cases_directory = tmp_path
    view.refresh_cases()

    assert view.case_tree.dragEnabled()
    assert (view.case_tree.dragDropMode()
            == QAbstractItemView.DragDropMode.DragOnly)
    item = view.case_tree.topLevelItem(0)
    mime = view.case_tree.mimeData([item])
    assert mime.hasFormat(SAVED_CASE_MIME)
    assert bytes(mime.data(SAVED_CASE_MIME)).decode("utf-8") == "Draggable Case"


def test_compare_tab_populates_ledger_and_status_without_kpi_strip():
    _app()
    a = _outcome("Current Inputs", _run(5))
    b = _outcome("Solved Min", _run(5, premium=800.0))
    result = ComparisonResult(outcomes=[a, b], kpis=build_kpi_rows([a, b]),
                              ledger=build_comparison_ledger([a, b]))
    tab = IllustrationCompareTab(runner=_stub_runner(result))

    tab.populate_comparison(result)

    assert tab.excel_btn.isEnabled()
    assert tab.run_btn.isEnabled()
    assert tab.banner_a.isHidden()
    assert tab.banner_b.isHidden()
    # The on-screen KPI delta strip was removed — no such widget exists.
    assert not hasattr(tab, "kpi_grid")

    view = tab.ledger_view
    df = view.df
    assert "A: AV" in df.columns and "B: AV" in df.columns
    # Plain measure names in the column headers (scenario names ride the
    # grouped header band, which is now shown).
    b_av_index = list(df.columns).index("B: AV")
    from PyQt6.QtCore import Qt
    assert view.model.headerData(
        b_av_index, Qt.Orientation.Horizontal) == "AV"
    assert view._column_groups == ledger_column_groups(
        result.ledger, "Current Inputs", "Solved Min")
    assert not view.group_bar.isHidden()
    # The divider column is thin and SOLID-filled — a clear vertical rule.
    # The tint records intent on the model; a delegate does the actual paint
    # (the ledger-style stylesheet suppresses the model background brush).
    from PyQt6.QtGui import QColor
    sep_index = list(df.columns).index(LEDGER_SEPARATOR)
    assert view.table_view.columnWidth(sep_index) == _SEPARATOR_WIDTH
    assert _SEPARATOR_WIDTH >= 8          # a clear divider bar, not a hairline
    assert view.model._column_backgrounds[LEDGER_SEPARATOR] == QColor(
        _SEPARATOR_COLOR)
    divider_delegate = view.table_view.itemDelegateForColumn(sep_index)
    assert divider_delegate is not None
    assert divider_delegate is view._divider_delegate

    # Status is minimal — the ledger's grouped headers already name both sides.
    assert tab.status_label.text() == "Comparison ready."


def test_compare_tab_populates_three_scenarios_with_two_dividers():
    _app()
    a = _outcome("Current Inputs", _run(5))
    b = _outcome("Opt A", _run(5, premium=900.0))
    c = _outcome("Opt B", _run(5, premium=800.0))
    result = ComparisonResult(outcomes=[a, b, c],
                              kpis=build_kpi_rows([a, b, c]),
                              ledger=build_comparison_ledger([a, b, c]))
    tab = IllustrationCompareTab(runner=_stub_runner(result))

    tab.populate_comparison(result)

    view = tab.ledger_view
    assert "C: AV" in view.df.columns
    assert [label for label, _cols in view._column_groups] == [
        "Current Inputs", "Opt A", "Opt B"]
    from PyQt6.QtGui import QColor
    for sep in separator_columns(result.ledger):
        sep_index = list(view.df.columns).index(sep)
        assert view.table_view.columnWidth(sep_index) == _SEPARATOR_WIDTH
        assert view.model._column_backgrounds[sep] == QColor(_SEPARATOR_COLOR)
        # Both dividers are painted by the solid-fill delegate.
        assert view.table_view.itemDelegateForColumn(sep_index) is (
            view._divider_delegate)
    assert tab.banner_c.isHidden()
    assert tab.status_label.text() == "Comparison ready."


def test_compare_tab_shows_loud_failure_banner_for_failed_side():
    _app()
    a = _outcome("Current Inputs", _run(5))
    b = ScenarioOutcome(label="Broken Case", error="no level premium sustains")
    result = ComparisonResult(outcomes=[a, b], kpis=build_kpi_rows([a, b]),
                              ledger=build_comparison_ledger([a, b]))
    tab = IllustrationCompareTab(runner=_stub_runner(result))

    tab.populate_comparison(result)

    assert tab.banner_a.isHidden()
    assert not tab.banner_b.isHidden()
    assert "Broken Case" in tab.banner_b.text()
    assert "no level premium sustains" in tab.banner_b.text()
    assert "partially ready" in tab.status_label.text()
    # The survivor's results still render.
    assert tab.excel_btn.isEnabled()
    assert "A: AV" in tab.ledger_view.df.columns


def test_compare_tab_clear_results_wipes_everything():
    _app()
    a = _outcome("Current Inputs", _run(5))
    b = _outcome("Solved Min", _run(5, premium=800.0))
    result = ComparisonResult(outcomes=[a, b], kpis=build_kpi_rows([a, b]),
                              ledger=build_comparison_ledger([a, b]))
    tab = IllustrationCompareTab(runner=_stub_runner(result))
    tab.populate_comparison(result)
    tab.banner_b.setVisible(True)
    tab.apply_note.setVisible(True)

    tab.clear_results()

    assert tab._result is None
    assert not tab.excel_btn.isEnabled()
    assert tab.banner_a.isHidden() and tab.banner_b.isHidden()
    assert tab.banner_c.isHidden()
    assert tab.apply_note.isHidden()
    assert tab.ledger_view.df.empty
    # Dividers cleared with the ledger — no stale decorated columns remain.
    assert tab.ledger_view._divider_applied == []
    assert tab.status_label.text().startswith("Load a policy")


# ── _build_spec: each side owns its policy data ──────────────────────
#
# Regression for the "two different saved cases, identical values" bug: while
# viewing a saved case the window has no live policy (``_policy is None``), so
# materializing the case against live data loaded the throwaway tab from None,
# its PolicyContext stayed empty, every dated change row (a DBO change) dropped
# its effective date, and both cases collapsed onto the same base projection.
# A saved case must materialize against its OWN frozen snapshot.


class _FakeInputsTab:
    """Records what _build_spec loads/applies — no heavy real tab needed."""

    last = None

    def __init__(self):
        self.loaded = None
        self.load_kw = None
        self.applied = None
        _FakeInputsTab.last = self

    def load_data_from_policy(self, policy, **kw):
        self.loaded = policy
        self.load_kw = kw

    def apply_case_inputs(self, inputs):
        self.applied = inputs
        return ["landed rows"]

    def deleteLater(self):
        pass


def _boom(*_a, **_k):
    raise AssertionError("a live fetch happened where a snapshot should be used")


def _fake_spec_from_tab(captured):
    def _spec(label, inputs_tab, policy_data):
        captured.update(label=label, tab=inputs_tab, base=policy_data)
        return ScenarioSpec(label=label, scenario=None, months=None, options=None)
    return staticmethod(_spec)


def test_build_spec_saved_case_uses_its_snapshot_not_live_policy(monkeypatch):
    _app()
    import suiteview.illustration.ui.inputs_tab as inputs_tab_mod
    monkeypatch.setattr(inputs_tab_mod, "IllustrationInputsTab", _FakeInputsTab)
    captured: dict = {}
    monkeypatch.setattr(IllustrationCompareTab, "_spec_from_tab",
                        _fake_spec_from_tab(captured))
    # A snapshot-backed case must NEVER trigger a live DB2 fetch.
    monkeypatch.setattr(IllustrationCompareTab, "_fetch_live_policy_data",
                        staticmethod(_boom))

    snap = SimpleNamespace(marker="SNAP", has_shadow_account=True, ccv_ceased=False)
    case = SimpleNamespace(name="Opt A", policy_snapshot=snap, inputs={"x": 1})
    # Snapshot view: the window holds no live policy at all.
    window = SimpleNamespace(_policy=None, _illustration_data=None, inputs_tab=None)
    tab = IllustrationCompareTab(window=window)

    spec = tab._build_spec(case, ("U0351626", "CKPR", "01"), side="A")

    # The throwaway tab was loaded from the snapshot (deepcopy carries the
    # marker), and the scenario base is the snapshot too — never _policy (None).
    assert _FakeInputsTab.last.loaded.marker == "SNAP"
    assert captured["base"].marker == "SNAP"
    assert captured["tab"] is _FakeInputsTab.last
    assert _FakeInputsTab.last.applied == {"x": 1}
    # has_shadow / shadow_ceased are read from the snapshot, not the window.
    assert _FakeInputsTab.last.load_kw == {
        "has_shadow": True, "shadow_ceased": False}
    assert spec.apply_warnings == ["[A · Opt A] landed rows"]


def test_build_spec_current_inputs_uses_window_loaded_data(monkeypatch):
    _app()
    captured: dict = {}
    monkeypatch.setattr(IllustrationCompareTab, "_spec_from_tab",
                        _fake_spec_from_tab(captured))
    monkeypatch.setattr(IllustrationCompareTab, "_fetch_live_policy_data",
                        staticmethod(_boom))
    loaded = SimpleNamespace(marker="LOADED")
    live_tab = object()
    window = SimpleNamespace(
        _policy=None, _illustration_data=loaded, inputs_tab=live_tab)
    tab = IllustrationCompareTab(window=window)

    tab._build_spec(None, ("P", "CKPR", "01"), side="A")

    # Current Inputs runs on the window's already-loaded policy data (which is
    # the frozen snapshot in snapshot view) and the live inputs tab — no fetch.
    assert captured["label"] == CURRENT_INPUTS_LABEL
    assert captured["tab"] is live_tab
    assert captured["base"] is loaded


def test_build_spec_v1_case_without_snapshot_falls_back_to_live(monkeypatch):
    _app()
    import suiteview.illustration.ui.inputs_tab as inputs_tab_mod
    monkeypatch.setattr(inputs_tab_mod, "IllustrationInputsTab", _FakeInputsTab)
    captured: dict = {}
    monkeypatch.setattr(IllustrationCompareTab, "_spec_from_tab",
                        _fake_spec_from_tab(captured))
    live_data = SimpleNamespace(marker="LIVE")
    monkeypatch.setattr(IllustrationCompareTab, "_fetch_live_policy_data",
                        staticmethod(lambda key: live_data))
    live_policy = SimpleNamespace(marker="LIVEPOLICY")
    window = SimpleNamespace(
        _policy=live_policy,
        _illustration_data=SimpleNamespace(
            has_shadow_account=False, ccv_ceased=False),
        inputs_tab=None)
    tab = IllustrationCompareTab(window=window)
    case = SimpleNamespace(name="Legacy", policy_snapshot=None, inputs={})

    tab._build_spec(case, ("P", "CKPR", "01"), side="B")

    # No snapshot to freeze against → the legacy path fetches live data and
    # loads the tab from the window's live policy.
    assert captured["base"] is live_data
    assert _FakeInputsTab.last.loaded is live_policy


def test_run_scenario_carries_each_sides_own_schedule_to_engine():
    """Runner-level: two sides with different premium schedules produce
    different ledgers — no cross-side leakage."""
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet, ScheduledTransaction, TransactionKind,
    )

    class _EchoEngine:
        def project(self, policy, months, future_inputs, options, stop_on_lapse):
            total = sum(t.amount for t in future_inputs.scheduled_transactions)
            return [_state(0, 0),
                    _state(1, 12, av_end_of_month=total,
                           ending_sv=total, ending_db=total)]

    def spec(label, amount):
        fi = IllustrationInputSet(scheduled_transactions=[ScheduledTransaction(
            kind=TransactionKind.PREMIUM, policy_year=1, amount=amount, mode="A")])
        scenario = SimpleNamespace(projectable_policy=_policy(), future_inputs=fi)
        return ScenarioSpec(label=label, scenario=scenario, months=12, options=None)

    engine = _EchoEngine()
    a = run_scenario(spec("A", 1000.0), engine=engine)
    b = run_scenario(spec("B", 2500.0), engine=engine)

    assert a.results[-1].av_end_of_month == 1000.0
    assert b.results[-1].av_end_of_month == 2500.0
    ledger = build_comparison_ledger([a, b])
    assert list(ledger["A: AV"]) != list(ledger["B: AV"])


def test_compare_worker_emits_result_from_stub_runner():
    _app()
    a = _outcome("Current Inputs", _run(2))
    b = _outcome("Case", _run(2))
    expected = ComparisonResult(outcomes=[a, b], kpis=[], ledger=pd.DataFrame())

    worker = _CompareWorker([_dummy_spec("A"), _dummy_spec("B")],
                            runner=_stub_runner(expected))
    finished, failed = [], []
    worker.finished_result.connect(finished.append)
    worker.failed.connect(failed.append)

    worker.run()   # synchronous: exercise the thread body directly

    assert failed == []
    assert finished == [expected]


def test_compare_worker_emits_failed_on_runner_crash():
    _app()

    def broken(specs, **kw):
        raise RuntimeError("total meltdown")

    worker = _CompareWorker([_dummy_spec("A"), _dummy_spec("B")], runner=broken)
    finished, failed = [], []
    worker.finished_result.connect(finished.append)
    worker.failed.connect(failed.append)

    worker.run()

    assert finished == []
    assert failed == ["total meltdown"]
