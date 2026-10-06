"""Soft-launch report safeguards: no printable illustration when the
guaranteed projection failed (M6, report half)."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from suiteview.illustration.core import run_service
from suiteview.illustration.core.report_builder import IllustrationReport
from suiteview.illustration.ui.report_tab import (
    IllustrationReportTab,
    ReportNotPrintableError,
    print_blocked_reason,
)

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _report(**kwargs) -> IllustrationReport:
    return IllustrationReport(
        company_name="AMERICAN NATIONAL INSURANCE COMPANY",
        prepared_for="PREPARED FOR JOHN DOE",
        run_date=date(2026, 10, 6),
        policy_number="U0000001",
        **kwargs,
    )


def test_print_blocked_reason_only_when_guaranteed_side_failed():
    assert print_blocked_reason(None) == ""
    assert print_blocked_reason(_report()) == ""
    assert print_blocked_reason(_report(has_guaranteed_values=True)) == ""
    reason = print_blocked_reason(_report(), guaranteed_error="no GCOI rates")
    assert "guaranteed projection failed" in reason
    assert "no GCOI rates" in reason
    # The failure carried on the report itself (session restore, write_pdf).
    assert "boom" in print_blocked_reason(_report(guaranteed_error="boom"))


def test_report_tab_disables_print_when_guaranteed_projection_failed():
    _app()
    tab = IllustrationReportTab()
    tab.display_report(_report(), guaranteed_error="lock values failed")

    assert not tab.print_pdf_btn.isEnabled()
    assert "lock values failed" in tab.print_pdf_btn.toolTip()
    assert tab.guaranteed_warning.isVisibleTo(tab)
    assert "Print to PDF is disabled" in tab.guaranteed_warning.text()
    assert "not printable" in tab.status_label.text()

    tab.display_report(_report(has_guaranteed_values=True))
    assert tab.print_pdf_btn.isEnabled()
    assert tab.print_pdf_btn.toolTip() == "Save the illustration report as a PDF file."
    assert not tab.guaranteed_warning.isVisibleTo(tab)


def test_report_tab_blocks_print_from_the_report_fact_alone():
    """A restored or re-rendered report keeps the block without the separate error arg."""
    _app()
    tab = IllustrationReportTab()
    tab.display_report(_report(guaranteed_error="rate table missing"))
    assert not tab.print_pdf_btn.isEnabled()

    state = tab.capture_session_state()
    restored = IllustrationReportTab()
    assert restored.restore_session_state(state)
    assert not restored.print_pdf_btn.isEnabled()


def test_print_click_on_blocked_report_refuses_without_file_dialog(monkeypatch):
    _app()
    tab = IllustrationReportTab()
    tab.display_report(_report(), guaranteed_error="lock values failed")
    warnings = []

    def no_dialog(*_args, **_kwargs):
        raise AssertionError("the save dialog must not open for an unprintable report")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", no_dialog)
    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, title, text: warnings.append((title, text)))

    tab._on_print_pdf()

    assert warnings and "lock values failed" in warnings[0][1]
    assert "refused" in tab.status_label.text()


def test_write_pdf_refuses_an_unprintable_report(tmp_path: Path):
    _app()
    target = tmp_path / "blocked.pdf"
    with pytest.raises(ReportNotPrintableError, match="guaranteed projection failed"):
        IllustrationReportTab.write_pdf(_report(guaranteed_error="boom"), str(target))
    assert not target.exists()


def test_run_service_carries_guaranteed_error_onto_the_report():
    built = _report()
    services = SimpleNamespace(report_builder=lambda *_args, **_kwargs: built)
    request = SimpleNamespace(controls=SimpleNamespace(run_date=date(2026, 10, 6)))
    scenario = SimpleNamespace(scenario=SimpleNamespace(projectable_policy=object()))
    resolved = SimpleNamespace(options=None, future_inputs=None)

    result = run_service.build_report_result(
        request, scenario, [], resolved, None, "guaranteed failed", services)

    assert result.guaranteed_error == "guaranteed failed"
    assert result.report.guaranteed_error == "guaranteed failed"
    assert print_blocked_reason(result.report)
