import os
from datetime import date, datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QItemSelectionModel
from PyQt6.QtWidgets import QApplication, QMessageBox

from suiteview.illustration.core.regression_runner import (
    BasisResult,
    DiffRecord,
    RegressionCaseResult,
    RegressionRun,
    STATUS_FAIL,
    STATUS_NO_BASELINE,
)
from suiteview.illustration.core.summary_results import ALL_COLUMNS
from suiteview.illustration.models.case_store import SavedCase
from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.illustration.models.regression_suite import create_suite, save_suite
from suiteview.illustration.ui.regression_tab import IllustrationRegressionTab

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _saved_case(name):
    return SavedCase(
        name=name, policy_number=f"P-{name}", region="CKPR", company_code="01",
        saved_at=datetime(2026, 8, 5, 12, 0), app_version="2.8",
        schema_version=2, inputs={"grids": {}, "controls": {}, "dynamic": {}},
        path=Path(f"{name}.case.json"),
        policy_snapshot=IllustrationPolicyData(
            policy_number=f"P-{name}", issue_date=date(2020, 1, 1)),
    )


def _row(value):
    row = {column: 0.0 for column in ALL_COLUMNS}
    row.update({
        "Date": "2026-08-05", "Year": 1, "Month": 1,
        "Attained Age": 50, "DBO": "A", "EAV": value,
    })
    return row


def _run(suite):
    cases = []
    for index, entry in enumerate(suite.cases, start=1):
        current = [_row(index * 100.0)]
        guaranteed = [_row(index * 90.0)]
        diff = DiffRecord(
            entry.case_id, entry.case.name, "current", "2026-08-05", 1, 1,
            "EAV", index * 90.0, index * 100.0, index * 10.0, 0.005)
        cases.append(RegressionCaseResult(
            entry.case_id, entry.case.name, entry.case.policy_number,
            BasisResult(STATUS_FAIL, current, [diff]),
            BasisResult(STATUS_NO_BASELINE, guaranteed),
        ))
    return RegressionRun(
        "2026-08-05T10:00:00", "2026-08-05T10:01:00", "2.8",
        {"source": "test"}, cases)


def test_tab_populates_run_and_updates_selected_case_baseline(tmp_path, monkeypatch):
    _app()
    suite = create_suite("UI", [_saved_case("A"), _saved_case("B")])
    save_suite(suite, tmp_path / "ui.svreg")
    tab = IllustrationRegressionTab()
    tab.set_suite(suite)
    tab._on_finished(_run(suite))

    assert list(tab.case_grid.df["Case"]) == ["A", "B"]
    assert len(tab.diff_grid.df) == 2
    assert tab.update_btn.isEnabled()

    index = tab.case_grid.model.index(0, 0)
    tab.case_grid.table_view.selectionModel().select(
        index,
        QItemSelectionModel.SelectionFlag.Select
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    tab._on_update_baseline()

    first_id, second_id = [entry.case_id for entry in suite.cases]
    assert tab._suite.active.revision == 1
    assert first_id in tab._suite.active.rows
    assert second_id not in tab._suite.active.rows
    assert tab._run.cases[0].current.status == "PASS"
    assert tab._run.cases[1].current.status == "NO BASELINE"
    assert tab.undo_btn.isEnabled() is False


def test_tab_full_update_then_undo_recompares_without_rerun(tmp_path, monkeypatch):
    _app()
    suite = create_suite("Undo UI", [_saved_case("A")])
    save_suite(suite, tmp_path / "undo-ui.svreg")
    tab = IllustrationRegressionTab()
    tab.set_suite(suite)
    tab._on_finished(_run(suite))
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    tab._on_update_baseline()
    assert tab._run.cases[0].current.status == "PASS"

    changed_run = _run(tab._suite)
    changed_run.cases[0].current.rows[0]["EAV"] = 777.0
    tab._on_finished(changed_run)
    tab._on_update_baseline()
    assert tab._suite.active.revision == 2
    assert tab.undo_btn.isEnabled()

    tab._on_undo_baseline()
    assert tab._suite.active.revision == 1
    assert tab._run.cases[0].current.status == "FAIL"
