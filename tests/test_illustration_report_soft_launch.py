"""Soft-launch report safeguards: no printable illustration when the
guaranteed projection failed (M6, report half)."""
from __future__ import annotations

import os
from datetime import date, datetime
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
    request = SimpleNamespace(controls=SimpleNamespace(
        run_date=date(2026, 10, 6), run_timestamp=None, options=None, stop_on_lapse=True))
    scenario = SimpleNamespace(scenario=SimpleNamespace(projectable_policy=object()))
    resolved = SimpleNamespace(options=None, future_inputs=None)

    result = run_service.build_report_result(
        request, scenario, [], resolved, None, "guaranteed failed", services)

    assert result.guaranteed_error == "guaranteed failed"
    assert result.report.guaranteed_error == "guaranteed failed"
    assert print_blocked_reason(result.report)


# ── M8: support traceability footer ─────────────────────────────────────────

def test_build_info_label_uses_stamped_sha_then_version_alone(monkeypatch, tmp_path):
    from suiteview import __version__
    from suiteview.core import build_info

    (tmp_path / build_info.BUILD_SHA_FILENAME).write_text("abc1234\n", encoding="utf-8")
    assert build_info._stamped_sha(tmp_path) == "abc1234"
    assert build_info._stamped_sha(tmp_path / "missing") == ""
    assert build_info.git_sha(tmp_path) == ""  # not a checkout: no guessed commit

    monkeypatch.setattr(build_info, "build_sha", lambda: "abc1234")
    assert build_info.app_build_label() == f"SUITEVIEW {__version__} BUILD abc1234"
    monkeypatch.setattr(build_info, "build_sha", lambda: "")
    assert build_info.app_build_label() == f"SUITEVIEW {__version__}"


def _traced_report():
    from suiteview.illustration.core.report_builder import (
        ExpenseRow,
        LedgerRow,
        ReportRunContext,
        build_ul_report,
    )
    from suiteview.illustration.models.calc_state import MonthlyState
    from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData

    policy = IllustrationPolicyData(
        policy_number="U0688012", company_code="01", insured_name="JOHN DOE",
        plancode="1U143900", form_number="EXEC-UL", issue_date=date(2019, 11, 9),
        issue_age=50, attained_age=56, rate_sex="M", rate_class="N",
        face_amount=100000.0, db_option="A", account_value=6311.09, modal_premium=153.56,
        billing_frequency=1, valuation_date=date(2026, 9, 9), guaranteed_interest_rate=0.03,
        segments=[CoverageSegment(face_amount=100000.0, issue_age=50, rate_sex="M", rate_class="N")],
    )
    states = [MonthlyState(policy_year=7, policy_month=11, duration=83)]
    for month in range(84, 84 + 12 * 40):
        year = (month - 1) // 12 + 1
        states.append(MonthlyState(
            date=date(2019, 11, 9), policy_year=year, policy_month=(month - 1) % 12 + 1,
            duration=month, attained_age=50 + year - 1, gross_premium=153.56,
            av_end_of_month=7000.0, ending_sv=5000.0, ending_db=100000.0,
            annual_interest_rate=0.03))
    report = build_ul_report(
        policy, states, run_date=date(2026, 10, 6),
        run_context=ReportRunContext(
            app_build="SUITEVIEW 5.2 BUILD abc1234",
            run_timestamp=datetime(2026, 10, 6, 10, 15, 32)),
    )
    assert report.ledger and isinstance(report.ledger[0], LedgerRow)
    assert isinstance(report.expense_rows[0], ExpenseRow)
    return report


EXPECTED_FOOTER = (
    "SUITEVIEW 5.2 BUILD abc1234 | RUN 10/06/2026 10:15:32 | POLICY VALUES AS OF 09/09/2026")


def test_every_page_including_the_expense_exhibit_carries_the_trace_footer():
    from suiteview.illustration.ui.report_tab import format_report_pages, trace_footer

    report = _traced_report()
    assert trace_footer(report) == EXPECTED_FOOTER
    pages = format_report_pages(report, include_expense_report=True)
    assert len(pages) >= 5
    for page in pages:
        assert page[-2:] == ["", EXPECTED_FOOTER]


def test_reports_built_outside_run_values_have_no_footer():
    from suiteview.illustration.ui.report_tab import format_report_pages, trace_footer

    report = _report(valuation_date=date(2026, 9, 9))
    assert trace_footer(report) == ""
    assert all(EXPECTED_FOOTER not in "\n".join(page) for page in format_report_pages(report))


def test_footer_pages_still_fit_one_pdf_page_each(tmp_path: Path):
    from suiteview.illustration.ui.report_pages import pages_document, pdf_printer
    from suiteview.illustration.ui.report_tab import format_report_pages

    _app()
    pages = format_report_pages(_traced_report(), include_expense_report=True)
    printer = pdf_printer(str(tmp_path / "fit.pdf"))
    assert pages_document(pages, printer).pageCount() == len(pages)


def test_run_service_stamps_build_label_run_time_and_settings(monkeypatch):
    from suiteview.illustration.models.input_set import IllustrationOptions

    captured = {}

    def builder(*_args, **kwargs):
        captured.update(kwargs)
        return _report()

    monkeypatch.setattr(run_service, "app_build_label", lambda: "SUITEVIEW 9.9 BUILD feed123")
    settings = IllustrationOptions(conform_to_tefra=False)
    request = SimpleNamespace(controls=SimpleNamespace(
        run_date=date(2026, 10, 6), run_timestamp=datetime(2026, 10, 6, 8, 0, 1),
        options=settings, stop_on_lapse=False))
    scenario = SimpleNamespace(scenario=SimpleNamespace(projectable_policy=object()))
    resolved = SimpleNamespace(options=IllustrationOptions(), future_inputs=None)

    run_service.build_report_result(
        request, scenario, [], resolved, None, None, SimpleNamespace(report_builder=builder))

    context = captured["run_context"]
    assert context.app_build == "SUITEVIEW 9.9 BUILD feed123"
    assert context.run_timestamp == datetime(2026, 10, 6, 8, 0, 1)
    assert context.settings is settings
    assert context.stop_on_lapse is False


def test_run_service_stamps_now_when_no_run_time_is_given(monkeypatch):
    captured = {}
    monkeypatch.setattr(run_service, "app_build_label", lambda: "X")
    request = SimpleNamespace(controls=SimpleNamespace(
        run_date=date(2026, 10, 6), run_timestamp=None, options=None, stop_on_lapse=True))
    run_service.build_report_result(
        request, SimpleNamespace(scenario=SimpleNamespace(projectable_policy=object())), [],
        SimpleNamespace(options=None, future_inputs=None), None, None,
        SimpleNamespace(report_builder=lambda *_a, **kw: captured.update(kw) or _report()))
    stamp = captured["run_context"].run_timestamp
    assert isinstance(stamp, datetime) and stamp.microsecond == 0
