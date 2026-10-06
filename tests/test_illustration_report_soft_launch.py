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
    values = dict(
        company_name="AMERICAN NATIONAL INSURANCE COMPANY",
        prepared_for="PREPARED FOR JOHN DOE",
        run_date=date(2026, 10, 6),
        policy_number="U0000001",
    )
    values.update(kwargs)
    return IllustrationReport(**values)


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


def _all_blocks_report(monkeypatch):
    """A cover carrying every new block at once: stale values, suspended, MEC,
    shadow nullified by a loan, loan rates (all three loan types) and every
    non-default setting, plus the trace footer."""
    from suiteview.illustration.core.report_builder import ReportRunContext
    from suiteview.illustration.models.input_set import IllustrationOptions
    from suiteview.illustration.models.plancode_config import PlancodeConfig

    settings = IllustrationOptions(
        conform_to_tefra=False, conform_to_tamra=False, allow_exception_prems=True,
        switch_to_option_a_in_exception=True, exact_days_interest=True,
        levelizing_premium=True, guideline_by_search=True, apply_prem_to_loan=True,
        apply_excess_repayment_as_premium=True, loan_repay_principal_first=True,
        restrict_loans_to_sv=False, no_lapse=True)
    policy = _sd1_policy(
        valuation_date=date(2026, 6, 1), suspense_code="2", is_mec=True,
        ccv_active=True, shadow_account_value=14418.29,
        regular_loan_principal=3700.0, preferred_loan_principal=500.0,
        variable_loan_principal=250.0, variable_loan_charge_rate=0.0525)
    return _sd1_build(
        policy, config=PlancodeConfig(shadow_loan_impact="Nullify", loan_charge_rate_guar=0.06),
        monkeypatch=monkeypatch,
        run_context=ReportRunContext(
            app_build="SUITEVIEW 5.2 BUILD abc1234",
            run_timestamp=datetime(2026, 10, 6, 10, 15, 32),
            settings=settings, stop_on_lapse=False))


@pytest.mark.parametrize("variant", ["long_ledger", "all_new_cover_blocks"])
def test_footer_pages_still_fit_one_pdf_page_each(tmp_path: Path, monkeypatch, variant):
    import re

    from suiteview.illustration.ui.report_pages import pages_document, pdf_printer
    from suiteview.illustration.ui.report_tab import (
        REPORT_PAGE_MAX_LINES,
        format_report_pages,
        trace_footer,
    )

    _app()
    report = _traced_report() if variant == "long_ledger" else _all_blocks_report(monkeypatch)
    footer = trace_footer(report)
    pages = format_report_pages(report, include_expense_report=True)
    printer = pdf_printer(str(tmp_path / "fit.pdf"))
    assert pages_document(pages, printer).pageCount() == len(pages)
    illustration = [p for p in pages if report.company_name in p[0]]
    for number, page in enumerate(illustration, start=1):
        assert len(page) <= REPORT_PAGE_MAX_LINES
        assert page[-2:] == ["", footer]
        assert re.search(rf"Page {number} of {len(illustration)}$", page[0])
    if variant == "all_new_cover_blocks":
        # The stuffed cover continues on page 2 under the same header.
        text = ["\n".join(page) for page in illustration]
        assert "POLICY STATUS AS OF 06/01/2026:" in text[0] + text[1]
        assert "THIS ILLUSTRATION WAS RUN WITH THE FOLLOWING NON-DEFAULT SETTINGS:" in text[1]
        assert "+- GUARANTEED VALUES -+" in text[2]


def test_split_body_breaks_at_blank_lines():
    from suiteview.illustration.ui.report_tab import _split_body

    body = ["a", "b", "", "c", "d", "e", "", "f"]
    assert _split_body(body, 6) == [["a", "b", "", "c", "d", "e"], ["f"]]
    assert _split_body(body, 4) == [["a", "b"], ["c", "d", "e"], ["f"]]
    assert _split_body(["x"] * 5, 2) == [["x", "x"], ["x", "x"], ["x"]]
    assert _split_body(body, 20) == [body]


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

# ── Should-do 1: in-force report content ────────────────────────────────────

def _sd1_policy(**overrides):
    from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData

    values = dict(
        policy_number="U0586555", company_code="01", insured_name="JANE DOE",
        plancode="1U143800", form_number="IMUL", issue_date=date(2007, 10, 24),
        issue_age=40, attained_age=58, policy_year=20, rate_sex="F", rate_class="N",
        face_amount=100000.0, db_option="A", account_value=4338.32, modal_premium=60.0,
        billing_frequency=1, valuation_date=date(2026, 9, 24), guaranteed_interest_rate=0.03,
        segments=[CoverageSegment(face_amount=100000.0, issue_age=40, rate_sex="F", rate_class="N")],
    )
    values.update(overrides)
    return IllustrationPolicyData(**values)


def _sd1_states(inforce=None, **month_kw):
    from suiteview.illustration.models.calc_state import MonthlyState

    states = [inforce or MonthlyState(policy_year=20, policy_month=12, duration=240)]
    for duration in range(241, 241 + 24):
        year = (duration - 1) // 12 + 1
        kw = dict(date=date(2026, 10, 24), policy_year=year,
                  policy_month=(duration - 1) % 12 + 1, duration=duration,
                  attained_age=40 + year - 1, gross_premium=60.0, av_end_of_month=4500.0,
                  ending_sv=500.0, ending_db=100000.0, annual_interest_rate=0.03)
        kw.update(month_kw)
        states.append(MonthlyState(**kw))
    return states


def _sd1_build(policy, states=None, *, config=None, monkeypatch=None, run_date=date(2026, 10, 6),
               run_context=None):
    from suiteview.illustration.core import report_builder
    from suiteview.illustration.models.plancode_config import PlancodeConfig

    if monkeypatch is not None:
        monkeypatch.setattr(report_builder, "load_plancode", lambda _code: config or PlancodeConfig())
    return report_builder.build_ul_report(
        policy, states or _sd1_states(), run_date=run_date, run_context=run_context)


def _cover_text(report):
    from suiteview.illustration.ui.report_tab import format_report_pages

    return "\n".join(format_report_pages(report)[0])


def test_already_mec_is_stated_and_never_reported_as_becoming_one():
    from suiteview.illustration.models.calc_state import MonthlyState

    policy = _sd1_policy(is_mec=True)
    # Contributions over the 7-pay limit would otherwise flag a future MEC year.
    states = _sd1_states(tamra_year=3, tamra_7pay_level=10.0, accumulated_7pay=5000.0)
    report = _sd1_build(policy, states)

    assert report.already_mec
    assert "THIS POLICY IS A MODIFIED ENDOWMENT CONTRACT (MEC)." in report.policy_status_lines
    assert report.year_of_mec is None and report.mec_line == ""
    assert not any("&" in row.markers for row in report.ledger)
    assert "POLICY STATUS AS OF 09/24/2026:" in _cover_text(report)

    # A loaded non-MEC still gets the future-MEC sentence.
    future = _sd1_build(_sd1_policy(), states)
    assert not future.already_mec and future.mec_line.startswith("THIS ILLUSTRATION SHOWS")
    # The inforce row's latched MEC status counts too.
    inforce_mec = _sd1_build(_sd1_policy(), _sd1_states(
        inforce=MonthlyState(policy_year=20, policy_month=12, duration=240, is_mec=True)))
    assert inforce_mec.already_mec


def test_suspended_notice_reads_the_policy_record_suspense_code():
    suspended = _sd1_build(_sd1_policy(suspense_code="2"))
    assert ("THE POLICY RECORD SHOWS THIS POLICY AS SUSPENDED (SUSPENSE CODE 2)."
            in suspended.policy_status_lines)
    for code in ("", "0", "3"):
        report = _sd1_build(_sd1_policy(suspense_code=code))
        assert not any("SUSPENDED" in line for line in report.policy_status_lines)


@pytest.mark.parametrize(("valuation", "stale"), [
    (date(2026, 8, 22), None),   # 45 days: at the threshold, not flagged
    (date(2026, 8, 21), 46),
])
def test_stale_valuation_warning_beyond_45_days(valuation, stale):
    report = _sd1_build(_sd1_policy(valuation_date=valuation))
    assert report.stale_valuation_days == stale
    flagged = [line for line in report.policy_status_lines if "DAYS BEFORE THE RUN DATE" in line]
    if stale is None:
        assert flagged == []
    else:
        assert flagged == [
            "THE POLICY VALUES USED IN THIS ILLUSTRATION ARE AS OF 08/21/2026, 46 DAYS BEFORE "
            "THE RUN DATE OF 10/06/2026. CURRENT POLICY VALUES MAY DIFFER."]


def test_stale_warning_skipped_for_rollback_and_issue_runs():
    from suiteview.illustration.core.report_builder import stale_valuation_days

    old = date(2025, 1, 1)
    assert stale_valuation_days(_sd1_policy(valuation_date=old), date(2026, 10, 6)) == 643
    assert stale_valuation_days(_sd1_policy(valuation_date=old, rollback_date=old),
                                date(2026, 10, 6)) is None
    assert stale_valuation_days(_sd1_policy(valuation_date=old, run_from_issue=True),
                                date(2026, 10, 6)) is None
    assert stale_valuation_days(_sd1_policy(valuation_date=old), None) is None


def _shadow_config(impact="Reduce"):
    from suiteview.illustration.models.plancode_config import PlancodeConfig

    return PlancodeConfig(shadow_loan_impact=impact, snet_by_issue_age={40: 5},
                          loan_charge_rate_guar=0.06, loan_charge_rate_curr=0.03)


def test_shadow_guarantee_nullified_by_loan_on_nullify_plans(monkeypatch):
    policy = _sd1_policy(ccv_active=True, shadow_account_value=14418.29,
                         regular_loan_principal=3700.0, regular_loan_accrued=89.98)
    report = _sd1_build(policy, config=_shadow_config("Nullify"), monkeypatch=monkeypatch)
    assert report.policy_status_lines == [
        "SHADOW ACCOUNT (NO-LAPSE GUARANTEE) VALUE: $14,418.29.",
        "THIS PLAN'S NO-LAPSE GUARANTEE DOES NOT PROTECT THE POLICY WHILE THERE IS ANY POLICY "
        "DEBT. WITH POLICY DEBT OF $3,789.98, THE GUARANTEE IS NULLIFIED AND IS NOT PROTECTING "
        "THE POLICY.",
    ]


@pytest.mark.parametrize(("protection", "positive_sv", "expected"), [
    (True, False, "THE NO-LAPSE GUARANTEE IS CURRENTLY KEEPING THE POLICY IN FORCE"),
    (True, True, "THE NO-LAPSE GUARANTEE IS IN EFFECT BUT IS NOT CURRENTLY NEEDED"),
    (False, True, "THE NO-LAPSE GUARANTEE IS NOT CURRENTLY PROTECTING THE POLICY"),
])
def test_shadow_guarantee_status_follows_the_inforce_row(monkeypatch, protection, positive_sv, expected):
    from suiteview.illustration.models.calc_state import MonthlyState

    inforce = MonthlyState(policy_year=20, policy_month=12, duration=240,
                           shadow_protection=protection, positive_sv=positive_sv)
    report = _sd1_build(_sd1_policy(ccv_active=True, shadow_account_value=100.0),
                        _sd1_states(inforce=inforce), config=_shadow_config(),
                        monkeypatch=monkeypatch)
    assert report.policy_status_lines[1].startswith(expected)


def test_shadow_status_within_safety_net_and_ceased(monkeypatch):
    early = _sd1_build(_sd1_policy(ccv_active=True, policy_year=3), config=_shadow_config(),
                       monkeypatch=monkeypatch)
    assert "SAFETY NET" in early.policy_status_lines[1]
    ceased = _sd1_build(_sd1_policy(ccv_ceased=True), config=_shadow_config(),
                        monkeypatch=monkeypatch)
    assert ceased.policy_status_lines == [
        "THE SHADOW ACCOUNT (NO-LAPSE GUARANTEE) HAS CEASED AND NO LONGER PROTECTS THE "
        "POLICY FROM LAPSE."]
    assert _sd1_build(_sd1_policy()).policy_status_lines == []


def test_loan_interest_rates_printed_with_the_loan_balance(monkeypatch):
    policy = _sd1_policy(regular_loan_principal=3700.0, regular_loan_accrued=89.98)
    report = _sd1_build(policy, _sd1_states(reg_loan_credit_rate=0.03),
                        config=_shadow_config(), monkeypatch=monkeypatch)
    assert report.loan_interest_lines == [
        "REGULAR LOAN INTEREST IS CHARGED AT 6.00% A YEAR, IN ARREARS; THE LOANED PORTION OF "
        "THE ACCUMULATION VALUE IS CREDITED 3.00% A YEAR."]
    cover = _cover_text(report)
    assert "WITH A LOAN BALANCE OF 3,789.98" in cover
    assert "REGULAR LOAN INTEREST IS CHARGED AT 6.00% A YEAR" in cover

    # No loan, no new loans: no rate lines (and no plancode lookup needed).
    assert _sd1_build(_sd1_policy()).loan_interest_lines == []


def test_loan_interest_uses_edit_record_override_advance_and_other_loan_types(monkeypatch):
    from suiteview.illustration.models.plancode_config import PlancodeConfig

    config = PlancodeConfig(loan_type="Advance", loan_charge_rate_guar=0.08,
                            pref_loan_charge_rate_guar=0.06, pref_loan_charge_rate_curr=0.055)
    policy = _sd1_policy(
        regular_loan_principal=1000.0, regular_loan_charge_rate=0.074,
        starting_record_fields=["regular_loan_charge_rate"],
        preferred_loan_principal=500.0, variable_loan_principal=250.0,
        variable_loan_charge_rate=0.0525)
    lines = _sd1_build(policy, config=config, monkeypatch=monkeypatch).loan_interest_lines
    assert lines == [
        "REGULAR LOAN INTEREST IS CHARGED AT 7.40% A YEAR, IN ADVANCE.",
        "PREFERRED LOAN INTEREST IS CHARGED AT 6.00% A YEAR, IN ADVANCE; THE LOANED PORTION "
        "OF THE ACCUMULATION VALUE IS CREDITED 5.50% A YEAR.",
        "VARIABLE LOAN INTEREST IS CHARGED AT THE CURRENT VARIABLE RATE OF 5.25% A YEAR.",
    ]


def test_non_default_settings_are_disclosed_and_defaults_are_silent():
    from suiteview.illustration.core.report_builder import (
        ReportRunContext,
        non_default_settings_lines,
    )
    from suiteview.illustration.models.input_set import IllustrationOptions

    assert non_default_settings_lines(IllustrationOptions()) == []
    assert non_default_settings_lines(IllustrationOptions(exact_days_interest=False)) == []
    # IUL-only options are not disclosed (or printed) on a UL report.
    assert non_default_settings_lines(IllustrationOptions(iul_wair_crediting=True)) == []

    settings = IllustrationOptions(conform_to_tefra=False, exact_days_interest=True,
                                   loan_repay_principal_first=True)
    assert non_default_settings_lines(settings, stop_on_lapse=False) == [
        "GUIDELINE PREMIUM (TEFRA/DEFRA) LIMITS NOT ENFORCED",
        "EXACT DAYS INTEREST",
        "LOAN REPAYMENTS PAY PRINCIPAL BEFORE ACCRUED INTEREST",
        "PROJECTION CONTINUES AFTER LAPSE",
    ]
    report = _sd1_build(_sd1_policy(), run_context=ReportRunContext(
        app_build="SUITEVIEW TEST", settings=settings, stop_on_lapse=False))
    cover = _cover_text(report)
    assert "THIS ILLUSTRATION WAS RUN WITH THE FOLLOWING NON-DEFAULT SETTINGS:" in cover
    assert "    GUIDELINE PREMIUM (TEFRA/DEFRA) LIMITS NOT ENFORCED" in cover

    plain = _sd1_build(_sd1_policy(), run_context=ReportRunContext(
        settings=IllustrationOptions()))
    assert plain.settings_lines == []
    assert "NON-DEFAULT SETTINGS" not in _cover_text(plain)


def test_ul_report_carries_no_iul_or_ag49_text():
    from suiteview.illustration.core.report_builder import ReportRunContext
    from suiteview.illustration.models.input_set import IllustrationOptions
    from suiteview.illustration.ui.report_tab import format_report_pages

    report = _sd1_build(_sd1_policy(), run_context=ReportRunContext(
        app_build="SUITEVIEW TEST", settings=IllustrationOptions(use_policy_ag49_regime=True)))
    assert not report.is_iul
    text = "\n".join("\n".join(page) for page in format_report_pages(report, True)).upper()
    for term in ("INDEXED", "AG49", "AG 49", "BENCHMARK", "WAIR", "S&P", "PARTICIPATION"):
        assert term not in text, term


def test_status_lines_not_printed_for_issue_runs():
    report = _sd1_build(_sd1_policy(run_from_issue=True, is_mec=True, suspense_code="2"))
    assert report.policy_status_lines == []

# ── M8: Export case for support ─────────────────────────────────────────────

def test_execute_run_carries_run_messages_onto_the_report():
    from suiteview.illustration.core.run_service import (
        EngineServices, PolicyBasis, RunControls, RunRequest, SolveRequestSet, execute_run,
    )
    from suiteview.illustration.models.calc_state import MonthlyState
    from suiteview.illustration.models.input_set import IllustrationInputSet, IllustrationOptions

    policy = _sd1_policy()
    states = [MonthlyState(), MonthlyState(policy_year=21)]
    services = EngineServices(
        scenario_builder=lambda data, **kw: SimpleNamespace(
            projectable_policy=data, future_inputs=kw["future_inputs"]),
        engine_factory=lambda: object(),
        project=lambda *_a, **_kw: SimpleNamespace(states=states),
        guaranteed_runner=lambda *_a, **_kw: states,
        report_builder=lambda *_a, **_kw: _report(policy_number="U0586555"),
    )
    request = RunRequest(
        basis=PolicyBasis("U0586555", policy_data=policy),
        inputs=IllustrationInputSet(),
        controls=RunControls(options=IllustrationOptions(), projection_months=1,
                             duration_label="1 month", stop_on_lapse=True),
        solves=SolveRequestSet(),
    )
    result = execute_run(request, services)
    assert result.report.report.run_messages == result.messages
    assert result.messages[-1].startswith("Values ready for U0586555")


def _export(tmp_path, *, report=None, policy=None, **kw):
    from suiteview.illustration.core.support_export import write_support_export

    return write_support_export(
        tmp_path, policy_number="U0586555", region="CKPR", company_code="01",
        inputs={"premium_rows": [{"amount": 60.0}]},
        policy=policy or _sd1_policy(), report=report,
        now=datetime(2026, 10, 6, 11, 2, 33), **kw)


def test_support_export_writes_a_case_bundle_and_info_file(tmp_path, monkeypatch):
    import json

    from suiteview.illustration.core import support_export
    from suiteview.illustration.models.case_bundle import read_bundle

    monkeypatch.setattr(support_export, "app_build_label", lambda: "SUITEVIEW 5.2 BUILD abc1234")
    report = _report(
        policy_number="U0586555", guaranteed_error="no GCOI rates",
        run_timestamp=datetime(2026, 10, 6, 10, 59, 1), app_build="SUITEVIEW 5.2 BUILD abc1234",
        run_messages=["Solved premium $60.00", "Values ready for U0586555"],
        policy_status_lines=["THIS POLICY IS A MODIFIED ENDOWMENT CONTRACT (MEC)."],
        settings_lines=["EXACT DAYS INTEREST"])
    paths = _export(tmp_path, report=report, load_warnings=["Monthly deduction check mismatch"])

    stem = "SUPPORT - U0586555 - 1U143800 - 2026-10-06 11-02"
    assert paths.case_bundle == tmp_path / f"{stem}.cases.json"
    assert paths.info == tmp_path / f"{stem}.support.json"

    bundle = read_bundle(paths.case_bundle)
    assert not bundle.errors and len(bundle.cases) == 1
    case = bundle.cases[0]
    assert case.policy_number == "U0586555" and case.company_code == "01"
    assert case.inputs == {"premium_rows": [{"amount": 60.0}]}
    assert case.policy_snapshot == _sd1_policy()

    info = json.loads(paths.info.read_text(encoding="utf-8"))
    assert info["kind"] == "suiteview.illustration.support_export"
    assert info["app_build"] == "SUITEVIEW 5.2 BUILD abc1234"
    assert info["case_file"] == f"{stem}.cases.json"
    assert info["plancode"] == "1U143800" and info["valuation_date"] == "2026-09-24"
    assert len(info["plancode_config_sha256"]) == 64
    assert info["warnings"] == [
        "Monthly deduction check mismatch", "Guaranteed projection failed: no GCOI rates"]
    run = info["last_run"]
    assert run["run_timestamp"] == "2026-10-06T10:59:01"
    assert run["run_messages"] == ["Solved premium $60.00", "Values ready for U0586555"]
    assert run["policy_status_lines"] == ["THIS POLICY IS A MODIFIED ENDOWMENT CONTRACT (MEC)."]
    assert run["non_default_settings"] == ["EXACT DAYS INTEREST"]


def test_support_export_without_a_matching_run_says_so(tmp_path):
    import json

    paths = _export(tmp_path, report=_report(policy_number="U9999999"))
    info = json.loads(paths.info.read_text(encoding="utf-8"))
    assert info["last_run"] is None
    assert "No Run Values result" in info["last_run_note"]


def test_support_export_unknown_plancode_still_exports_with_a_warning(tmp_path, monkeypatch):
    import json

    from suiteview.illustration.core import support_export

    def boom(_code):
        raise KeyError("ZZZ not in plancode table")

    monkeypatch.setattr(support_export, "load_plancode", boom)
    paths = _export(tmp_path)
    info = json.loads(paths.info.read_text(encoding="utf-8"))
    assert info["plancode_config_sha256"] == ""
    assert any("fingerprint unavailable" in w for w in info["warnings"])


def test_support_export_refuses_without_policy_or_folder(tmp_path):
    from suiteview.illustration.core.support_export import SupportExportError, write_support_export

    with pytest.raises(SupportExportError, match="No illustration policy data"):
        write_support_export(tmp_path, policy_number="U1", region="CKPR", company_code="01",
                             inputs={}, policy=None)
    with pytest.raises(SupportExportError, match="Folder does not exist"):
        _export(tmp_path / "missing")


def test_window_menu_exports_case_for_support(tmp_path, monkeypatch):
    from suiteview.illustration.ui import support_export_controls
    from suiteview.illustration.ui.main_window import IllustrationWindow

    _app()
    infos, warnings = [], []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, t, text: infos.append(text))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, t, text: warnings.append(text))
    window = IllustrationWindow()
    try:
        texts = [a.text() for a in window.hamburger_btn.menu().actions()]
        assert support_export_controls.EXPORT_FOR_SUPPORT_TEXT in texts

        # Nothing loaded: a clear message, no dialog, no files.
        monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                            lambda *_a, **_kw: pytest.fail("no folder prompt without a policy"))
        window._support_export_action.trigger()
        assert infos and "Load a UL policy" in infos[-1]

        window._current_key = ("U0586555", "CKPR", "01")
        window._illustration_data = _sd1_policy()
        window._live_policy_checks = (None, ["Rate warning A"], None)
        monkeypatch.setattr(window.policy_tab, "has_pending_record_changes", lambda: False)
        prompts = []

        def choose(_parent, _title, start):
            prompts.append(start)
            return str(tmp_path)

        monkeypatch.setattr(QFileDialog, "getExistingDirectory", choose)
        window._support_export_action.trigger()

        assert prompts == [support_export_controls.documents_folder()]
        written = sorted(p.name for p in tmp_path.iterdir())
        assert len(written) == 2
        assert written[0].startswith("SUPPORT - U0586555 - 1U143800 - ")
        assert written[0].endswith(".cases.json") and written[1].endswith(".support.json")
        assert "Saved for support" in infos[-1] and not warnings
    finally:
        window.close()
