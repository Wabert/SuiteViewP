import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from suiteview.illustration.core.report_builder import build_ul_report
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    PolicyChangeEvent,
    PolicyChangeKind,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.models.policy_data import (
    BenefitInfo,
    CoverageSegment,
    IllustrationPolicyData,
)


def _policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        policy_number="U0688012",
        company_code="01",
        insured_name="JOHN DOE",
        plancode="1U143900",
        form_number="EXEC-UL",
        issue_date=date(2019, 11, 9),
        issue_age=50,
        attained_age=56,
        rate_sex="M",
        rate_class="N",
        face_amount=100000.0,
        db_option="A",
        account_value=6311.09,
        modal_premium=153.56,
        billing_frequency=1,
        premiums_paid_to_date=12421.68,
        valuation_date=date(2026, 5, 9),
        guaranteed_interest_rate=0.03,
        tamra_7pay_level=6721.24,
        tamra_7pay_start_date=date(2019, 11, 9),
        segments=[CoverageSegment(face_amount=100000.0, issue_age=50, rate_sex="M", rate_class="N")],
        benefits=[BenefitInfo(benefit_type="3", benefit_subtype="9", is_active=True)],
    )


def _month(year: int, month_in_year: int, **kw) -> MonthlyState:
    duration = (year - 1) * 12 + month_in_year
    defaults = dict(
        date=date(2019, 11, 9).replace(year=2019 + (duration - 1) // 12),
        policy_year=year,
        policy_month=month_in_year,
        duration=duration,
        attained_age=50 + year - 1,
        gross_premium=100.0,
        requested_premium=100.0,
        av_end_of_month=5000.0 + duration,
        surrender_value=4000.0 + duration,
        ending_db=100000.0,
        policy_debt=0.0,
        annual_interest_rate=0.0635,
        gsp=31311.48,
        glp=2880.24,
        accumulated_glp=20162.31,
        tamra_year=year,
        tamra_7pay_level=6721.24,
        accumulated_7pay=min(year, 7) * 100.0,
    )
    defaults.update(kw)
    return MonthlyState(**defaults)


def _results():
    rows = [MonthlyState(policy_year=7, policy_month=6, duration=78,
                         gsp=31311.48, glp=2880.24, accumulated_glp=20162.31, tamra_year=7)]
    for year in (8, 9):
        for month in range(1, 13):
            kw = {}
            if year == 9 and month == 1:
                kw = dict(guideline_forceout=6266.37, premium_capped=True, gross_premium=0.0)
            rows.append(_month(year, month, **kw))
    return rows


def test_report_ledger_annualizes_and_marks():
    inputs = IllustrationInputSet(
        scheduled_transactions=[
            ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=1, amount=1200.0, mode="M"),
            ScheduledTransaction(kind=TransactionKind.LOAN, policy_year=12, amount=3000.0, mode="A"),
            ScheduledTransaction(kind=TransactionKind.LOAN, policy_year=16, amount=0.0, mode="A"),
        ],
        dated_transactions=[
            DatedTransaction(kind=TransactionKind.WITHDRAWAL,
                             effective_date=date(2029, 11, 9), amount=1000.0),
        ],
        policy_changes=[
            PolicyChangeEvent(kind=PolicyChangeKind.FACE_AMOUNT,
                              effective_date=date(2027, 11, 9), value=75000.0),
        ],
    )
    report = build_ul_report(_policy(), _results(), future_inputs=inputs,
                             run_date=date(2026, 6, 10))

    assert [row.year for row in report.ledger] == [8, 9]
    year8 = report.ledger[0]
    assert year8.premium_outlay == 1200.0          # 12 x 100
    assert year8.accum_value == report.ledger[0].accum_value
    year9 = report.ledger[1]
    assert "@" in year9.markers                     # force-out fired
    assert year9.cash_from_policy > 6000            # includes the force-out
    assert any(legend.startswith("@") for legend in report.footnote_legends)
    assert not any(legend.startswith("^") for legend in report.footnote_legends)

    # Guaranteed columns stay blank.
    assert year8.guar_accum is None and year8.guar_surr is None and year8.guar_death is None

    # Cover request lines: compressed premium + loan + withdrawal.
    joined = " | ".join(report.request_lines)
    assert "MONTHLY PREMIUM OF $100.00" in joined
    assert "ANNUAL FIXED LOAN OF $3,000.00 FOR POLICY YEARS 12 THROUGH 15" in joined
    assert "WITHDRAWAL OF $1,000.00 IN POLICY YEAR 11" in joined

    # Policy change section with estimated limits.
    assert len(report.change_sections) == 1
    section = report.change_sections[0]
    assert section.year == 9
    assert any("GUIDELINE SINGLE" in line for line in section.limit_lines)

    # Regulatory limits from the inforce snapshot.
    assert any("GUIDELINE SINGLE = $31,311.48" in line for line in report.regulatory_lines)
    assert any("PREMIUM WAIVER" in line for line in report.rider_lines)


def test_report_pages_render_fixed_width():
    from suiteview.illustration.ui.report_tab import PAGE_WIDTH, format_report_pages

    report = build_ul_report(_policy(), _results(), run_date=date(2026, 6, 10))
    pages = format_report_pages(report)
    assert len(pages) >= 3  # cover + ledger + notes
    for page in pages:
        assert all(len(line) <= PAGE_WIDTH for line in page), max(page, key=len)
    cover = "\n".join(pages[0])
    assert "PREPARED FOR JOHN DOE" in cover
    assert "ACCUMULATION VALUE OF $6,311.09" in cover
    # Two-column cover: CURRENT elements share rows with the identity block.
    policy_number_line = next(line for line in pages[0] if "POLICY NUMBER:" in line)
    assert "CURRENT SPECIFIED AMOUNT:" in policy_number_line
    issue_date_line = next(line for line in pages[0] if "ISSUE DATE:" in line)
    assert "November 9, 2019" in issue_date_line
    assert "CURRENT BILLING MODE:" in issue_date_line
    ledger_page = "\n".join(pages[1])
    assert "NON-GUARANTEED" in ledger_page


def _guaranteed_results():
    """Guaranteed run: same span but AV collapses and the policy lapses in yr 9."""
    rows = [MonthlyState(policy_year=7, policy_month=6, duration=78)]
    for year in (8, 9):
        for month in range(1, 13):
            lapsed = year == 9 and month >= 3
            rows.append(_month(
                year, month,
                av_end_of_month=0.0 if lapsed else 1000.0,
                surrender_value=-50.0 if lapsed else 800.0,
                ending_db=0.0 if lapsed else 100000.0,
                lapsed=lapsed,
            ))
            if lapsed:
                return rows
    return rows


def test_report_guaranteed_columns_fill_from_guaranteed_run():
    report = build_ul_report(
        _policy(), _results(), run_date=date(2026, 6, 10),
        guaranteed_results=_guaranteed_results())

    assert report.has_guaranteed_values
    assert report.guaranteed_termination_year == 9
    year8, year9 = report.ledger
    assert year8.guar_accum == 1000.0
    assert year8.guar_surr == 800.0
    assert year8.guar_death == 100000.0
    # Lapsed guaranteed year renders zero, not blank.
    assert year9.guar_accum == 0.0 and year9.guar_surr == 0.0 and year9.guar_death == 0.0
    notes = " ".join(" ".join(p) for p in report.note_paragraphs)
    assert "UNDER GUARANTEED ACCUMULATION VALUE, YOUR POLICY WILL TERMINATE IN POLICY YEAR 9" in notes
    assert "GUARANTEED VALUES ARE NOT PROJECTED" not in notes


def test_lock_values_locks_current_cash_flows():
    from dateutil.relativedelta import relativedelta

    from suiteview.illustration.core.guaranteed_projection import lock_values

    policy = _policy()
    results = [MonthlyState(policy_year=7, policy_month=6, duration=78)]
    results.append(_month(8, 1, gross_premium=100.0, gp_exception_prem=25.0))
    results.append(_month(8, 2, gross_premium=0.0, applied_net_withdrawal=500.0,
                          applied_regular_loan=200.0, applied_variable_loan=75.0,
                          applied_loan_repayment=40.0))

    locked = lock_values(policy, results)

    # Zero premium schedule keeps the modal-premium fallback from billing.
    assert len(locked.scheduled_transactions) == 1
    anchor = locked.scheduled_transactions[0]
    assert anchor.kind == TransactionKind.PREMIUM and anchor.amount == 0.0

    month1 = policy.issue_date + relativedelta(months=results[1].duration - 1)
    month2 = policy.issue_date + relativedelta(months=results[2].duration - 1)
    by_key = {(t.kind, t.effective_date): t.amount for t in locked.dated_transactions}
    assert by_key[(TransactionKind.PREMIUM, month1)] == 125.0  # premium + exception
    assert by_key[(TransactionKind.WITHDRAWAL, month2)] == 500.0
    assert by_key[(TransactionKind.LOAN_REPAYMENT, month2)] == 40.0
    loans = [t for t in locked.dated_transactions
             if t.kind == TransactionKind.LOAN and t.effective_date == month2]
    assert sorted(t.amount for t in loans) == [75.0, 200.0]
    assert any(t.subtype == "variable" and t.amount == 75.0 for t in loans)


def test_guaranteed_options_disable_limits():
    from suiteview.illustration.core.guaranteed_projection import guaranteed_options
    from suiteview.illustration.models.input_set import IllustrationOptions

    base = IllustrationOptions(conform_to_tefra=True, conform_to_tamra=True,
                               allow_exception_prems=True, apply_prem_to_loan=True)
    opts = guaranteed_options(base)
    assert not opts.conform_to_tefra
    assert not opts.conform_to_tamra
    assert not opts.allow_exception_prems
    assert not opts.apply_prem_to_loan
    assert not opts.restrict_loans_to_sv
    assert not opts.guideline_cap_enabled and not opts.force_out_enabled
