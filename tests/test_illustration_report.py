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
        ending_sv=4000.0 + duration,
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


def test_seven_pay_restart_marks_ledger_and_footnotes():
    """A TAMRA material change restarts the 7-pay window: the ledger year is
    marked '+', the footnote legend states the new start date, and the change
    section's estimated limits show the new period start."""
    rows = [MonthlyState(policy_year=7, policy_month=6, duration=78,
                         gsp=31311.48, glp=2880.24, accumulated_glp=20162.31,
                         tamra_year=7, tamra_7pay_start_date=date(2019, 11, 9))]
    for month in range(1, 13):
        rows.append(_month(8, month, tamra_7pay_start_date=date(2019, 11, 9)))
    for month in range(1, 13):
        rows.append(_month(9, month, tamra_year=1,
                           tamra_7pay_start_date=date(2027, 11, 9),
                           tamra_7pay_level=5407.11))
    inputs = IllustrationInputSet(policy_changes=[
        PolicyChangeEvent(kind=PolicyChangeKind.FACE_AMOUNT,
                          effective_date=date(2027, 11, 9), value=150000.0),
    ])
    report = build_ul_report(_policy(), rows, future_inputs=inputs,
                             run_date=date(2026, 7, 3))

    assert report.seven_pay_restarts == [(9, date(2027, 11, 9))]
    year9 = next(row for row in report.ledger if row.year == 9)
    assert "+" in year9.markers
    year8 = next(row for row in report.ledger if row.year == 8)
    assert "+" not in year8.markers
    legend = next(l for l in report.footnote_legends if l.startswith("+"))
    assert "11/09/2027" in legend
    section = report.change_sections[0]
    assert any("7-PAY PREMIUM = $5,407.11" in line for line in section.limit_lines)
    assert any("NEW 7-PAY PERIOD STARTS = 11/09/2027" in line
               for line in section.limit_lines)

    # Both surface on the rendered pages: the ledger footnote and the
    # riders/regulatory page's estimated-limits block.
    from suiteview.illustration.ui.report_tab import format_report_pages
    flat = "\n".join(line for page in format_report_pages(report) for line in page)
    assert "+ A NEW 7-PAY PREMIUM TEST PERIOD STARTS ON 11/09/2027" in flat
    assert "NEW 7-PAY PERIOD STARTS = 11/09/2027" in flat


def test_report_dates_all_use_slash_mm_dd_yyyy():
    """Every numeric date in the report renders mm/dd/yyyy. The regulatory
    page's 7-PAY START DATE and the cover's premiums-paid AS OF date were
    formerly dash-formatted (mm-dd-yyyy)."""
    report = build_ul_report(_policy(), _results(), run_date=date(2026, 6, 10))

    # Riders/regulatory page: 7-pay start date (was 11-09-2019).
    assert any("7-PAY START DATE = 11/09/2019" in line
               for line in report.regulatory_lines)
    # Cover block: premiums-paid AS OF valuation date (was 05-09-2026).
    as_of_line = next(right for _left, right in report.policy_block
                      if "AS OF" in right)
    assert "(AS OF 05/09/2026)" in as_of_line

    # No dash-formatted date survives anywhere on the rendered pages.
    import re
    from suiteview.illustration.ui.report_tab import format_report_pages
    flat = "\n".join(line for page in format_report_pages(report) for line in page)
    assert not re.search(r"\d{2}-\d{2}-\d{4}", flat)


def test_no_seven_pay_restart_without_material_change():
    """An unchanged 7-pay start date produces no '+' marker or legend."""
    report = build_ul_report(_policy(), _results(), run_date=date(2026, 7, 3))
    assert report.seven_pay_restarts == []
    assert not any("+" in row.markers for row in report.ledger)
    assert not any(legend.startswith("+") for legend in report.footnote_legends)


def test_request_lines_fold_partial_years_into_runs():
    """Partial first/last years join their runs instead of annualized artifacts.

    $75 monthly requested from mid-year 12 (dated payments under a zero-amount
    silencing schedule) through year 19, then $50 monthly until the policy
    terminates 7 months into year 53 — two lines, no 'ANNUAL PREMIUM OF
    $150.00 IN POLICY YEAR 12' and no 'MONTHLY PREMIUM OF $29.17 IN YEAR 53'.
    """
    rows = [MonthlyState(policy_year=12, policy_month=10, duration=142)]
    for month in (11, 12):                      # remaining months of year 12
        rows.append(_month(12, month, requested_premium=75.0, gross_premium=75.0))
    for year in range(13, 53):
        for month in range(1, 13):
            amount = 75.0 if year <= 19 else 50.0
            rows.append(_month(year, month, requested_premium=amount, gross_premium=amount))
    for month in range(1, 8):                   # lapse-truncated final year
        rows.append(_month(53, month, requested_premium=50.0, gross_premium=50.0))

    inputs = IllustrationInputSet(scheduled_transactions=[
        ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=12, amount=0.0, mode="A"),
        ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=13, amount=75.0, mode="M"),
        ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=20, amount=50.0, mode="M"),
    ])
    report = build_ul_report(_policy(), rows, future_inputs=inputs,
                             run_date=date(2026, 7, 3))

    premium_lines = [line for line in report.request_lines if "PREMIUM OF" in line]
    assert premium_lines == [
        "MONTHLY PREMIUM OF $75.00 FOR POLICY YEARS 12 THROUGH 19",
        "MONTHLY PREMIUM OF $50.00 FOR POLICY YEARS 20 THROUGH 53",
    ]


def test_monthly_deduction_premium_renders_without_amount():
    """A Monthly-Deduction premium range gets its own no-amount sentence.

    The MD premium is solved in-engine (grossed-up monthly deduction, varying
    monthly), marked per-month by ``md_premium_mode`` — never inferred from
    amounts. Fixed $75 monthly for years 12-19, then MD premiums for years
    20-25: the fixed line is unchanged and the MD range renders as
    'PREMIUMS TO COVER MONTHLY DEDUCTIONS FOR POLICY YEARS 20 THROUGH 25'
    with no dollar amount, in schedule order after the fixed line.
    """
    rows = [MonthlyState(policy_year=11, policy_month=12, duration=132)]
    for year in range(12, 20):
        for month in range(1, 13):
            rows.append(_month(year, month, requested_premium=75.0, gross_premium=75.0))
    for year in range(20, 26):
        for month in range(1, 13):
            rows.append(_month(year, month, requested_premium=0.0, gross_premium=0.0,
                               md_premium_mode=True, md_premium=60.0 + month))

    inputs = IllustrationInputSet(scheduled_transactions=[
        ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=12, amount=0.0, mode="A"),
        ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=12, amount=75.0, mode="M"),
    ])
    report = build_ul_report(_policy(), rows, future_inputs=inputs,
                             run_date=date(2026, 7, 18))

    premium_lines = [line for line in report.request_lines
                     if "PREMIUM OF" in line or "MONTHLY DEDUCTIONS" in line]
    assert premium_lines == [
        "MONTHLY PREMIUM OF $75.00 FOR POLICY YEARS 12 THROUGH 19",
        "PREMIUMS TO COVER MONTHLY DEDUCTIONS FOR POLICY YEARS 20 THROUGH 25",
    ]
    assert "$" not in premium_lines[1]

    # A single MD year renders the singular span, still amount-free.
    short_rows = rows[:1 + 8 * 12] + [
        _month(20, month, requested_premium=0.0, gross_premium=0.0,
               md_premium_mode=True, md_premium=61.0)
        for month in range(1, 13)
    ]
    short = build_ul_report(_policy(), short_rows, future_inputs=inputs,
                            run_date=date(2026, 7, 18))
    assert "PREMIUMS TO COVER MONTHLY DEDUCTIONS IN POLICY YEAR 20" in short.request_lines


def test_monthly_deduction_window_ends_and_later_premium_resumes():
    """A bounded MD window renders its own range, and a premium AFTER the
    window still lists — the MD run ends where ``md_premium_mode`` stops.

    Fixed $75 monthly years 12-13, Monthly Deduction years 14-15, then fixed
    $200 monthly years 16-17. The cover shows all three, in schedule order,
    and the MD range is bounded to 14-15 (not open-ended).
    """
    rows = [MonthlyState(policy_year=11, policy_month=12, duration=132)]
    for year in range(12, 14):
        for month in range(1, 13):
            rows.append(_month(year, month, requested_premium=75.0, gross_premium=75.0))
    for year in range(14, 16):
        for month in range(1, 13):
            rows.append(_month(year, month, requested_premium=0.0, gross_premium=0.0,
                               md_premium_mode=True, md_premium=60.0 + month))
    for year in range(16, 18):
        for month in range(1, 13):
            rows.append(_month(year, month, requested_premium=200.0, gross_premium=200.0))

    inputs = IllustrationInputSet(scheduled_transactions=[
        ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=12, amount=0.0, mode="A"),
        ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=12, amount=75.0, mode="M"),
        ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=14, amount=0.0, mode="M"),
        ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=16, amount=200.0, mode="M"),
    ])
    report = build_ul_report(_policy(), rows, future_inputs=inputs,
                             run_date=date(2026, 7, 18))

    premium_lines = [line for line in report.request_lines
                     if "PREMIUM OF" in line or "MONTHLY DEDUCTIONS" in line]
    assert premium_lines == [
        "MONTHLY PREMIUM OF $75.00 FOR POLICY YEARS 12 THROUGH 13",
        "PREMIUMS TO COVER MONTHLY DEDUCTIONS FOR POLICY YEARS 14 THROUGH 15",
        "MONTHLY PREMIUM OF $200.00 FOR POLICY YEARS 16 THROUGH 17",
    ]


def test_values_at_maturity_strip_when_policy_endows():
    """A projection that reaches maturity gets a VALUES AT MATURITY strip —
    and the engine's post-maturity stub year gets NO ledger/expense row and
    no '%' legend (removed 2026-07-19: with EOY ages shown, a row past the
    maturity age reads as a phantom extra year, and the after-maturity DB
    wording is contract-specific)."""
    policy = _policy()
    policy.maturity_age = 58                    # year 9 begins at attained 58
    report = build_ul_report(policy, _results(), run_date=date(2026, 7, 3),
                             guaranteed_results=_guaranteed_results())

    # Year 9 (begins at the maturity age) is the stub: ledger and expense
    # report both end at year 8, and no maturity legend renders.
    assert [r.year for r in report.ledger] == [8]
    assert [r.year for r in report.expense_rows] == [8]
    assert not any(legend.startswith("%") for legend in report.footnote_legends)
    from suiteview.illustration.ui.report_tab import format_report_pages
    flat = "\n".join(line for page in format_report_pages(report) for line in page)
    assert "AFTER MATURITY" not in flat

    row = report.maturity_row
    assert row is not None
    final = _results()[-1]
    assert row.accum_value == final.av_end_of_month
    assert row.surr_value == final.ending_sv
    assert row.death_benefit == final.ending_db
    # Guaranteed run lapsed before maturity -> guaranteed columns show zero.
    assert row.guar_accum == 0.0 and row.guar_surr == 0.0 and row.guar_death == 0.0

    from suiteview.illustration.ui.report_tab import PAGE_WIDTH, format_report_pages
    ledger_page = format_report_pages(report)[1]
    strip = ledger_page.index(next(l for l in ledger_page if "VALUES AT MATURITY" in l))
    assert ledger_page[strip - 1] == "-" * PAGE_WIDTH
    assert ledger_page[strip + 1] == "-" * PAGE_WIDTH
    assert f"{final.av_end_of_month:,.0f}" in ledger_page[strip]


def test_no_maturity_strip_before_maturity_or_on_lapse():
    from suiteview.illustration.ui.report_tab import format_report_pages

    # Default policy matures at 121 — the age-58 projection shows no strip.
    report = build_ul_report(_policy(), _results(), run_date=date(2026, 7, 3))
    assert report.maturity_row is None
    assert not any("VALUES AT MATURITY" in line
                   for page in format_report_pages(report) for line in page)

    # Lapsing in the maturity year does not count as reaching maturity.
    policy = _policy()
    policy.maturity_age = 58
    rows = _results()
    rows[-1].lapsed = True
    report = build_ul_report(policy, rows, run_date=date(2026, 7, 3))
    assert report.maturity_row is None


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
                ending_sv=-50.0 if lapsed else 800.0,
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


# ── Expense Report supplemental page ────────────────────────────────────────

def _expense_results():
    """Two full projected years with distinct charge/credit values per month."""
    rows = [MonthlyState(policy_year=7, policy_month=6, duration=78)]
    for year in (8, 9):
        for month in range(1, 13):
            kw = dict(
                total_premium_load=5.0,
                total_coi_charge=10.0,
                epu_charge=3.0,
                mfee_charge=2.0,
                asset_charge=1.0,
                av_charge=0.5,
                benefit_charges=0.75,
                rider_charges=0.25,
                interest_credited=20.0,
                surrender_charge=400.0,
                policy_debt=250.0,
            )
            if year == 8 and month == 3:
                kw.update(applied_net_withdrawal=500.0, applied_regular_loan=200.0,
                          wd_partial_sc=75.0)
            if year == 9 and month == 1:
                kw.update(guideline_forceout=1000.0)
            rows.append(_month(year, month, **kw))
    return rows


def test_expense_rows_annualize_j_to_y_columns():
    """One hand-computed value per column family: charges/credits are annual
    sums, policy values are end-of-year, distributions include withdrawals,
    loans, and force-outs (RERUN vDistributionFromPolicy)."""
    report = build_ul_report(_policy(), _expense_results(), run_date=date(2026, 7, 3))

    assert [r.year for r in report.expense_rows] == [8, 9]
    year8, year9 = report.expense_rows
    assert year8.eoy_age == 58                          # K — age at END of year (50 + 8)
    assert year8.premium_outlay == 1200.0               # L — 12 x 100
    assert year8.distributions == 700.0                 # M — 500 WD + 200 loan
    assert year9.distributions == 1000.0                # M — force-out counts
    assert year8.premium_charge == 60.0                 # N — 12 x 5
    assert year8.coi_charge == 120.0                    # O — 12 x 10 (base COI only)
    assert year8.per_unit_charge == 36.0                # P — 12 x 3
    assert year8.monthly_fee == 24.0                    # Q — 12 x 2
    assert year8.asset_charge == 12.0                   # R — 12 x 1
    assert year8.av_charge == 6.0                       # S — 12 x 0.5
    assert year8.rider_charges == 12.0                  # T — 12 x (0.75 + 0.25)
    # Partial SC assessed on the March withdrawal lands in Expenses/Fees.
    assert year8.partial_surrender_charges == 75.0
    # Combined page column: P + Q + R + S + partial SC = 36 + 24 + 12 + 6 + 75
    # (premium charge is its own column and is NOT folded in).
    assert year8.expenses == 153.0
    assert year8.interest_credited == 240.0             # U — 12 x 20
    assert year8.accum_value == 5000.0 + 96             # V — EOY AV (duration 96)
    assert year8.surrender_charges == 400.0             # W — EOY full SC
    assert year8.net_surrender_value == 4000.0 + 96     # X — EOY SV
    assert year8.policy_debt == 250.0                   # EOY ledger loan balance
    assert year8.net_death_benefit == 100000.0          # Y — EOY DB


def test_expense_rows_zero_at_and_after_termination():
    """RERUN's inforce flag (year < sTerminationYear) zeroes the termination
    year's row — values render zero, year/age stay."""
    rows = _expense_results()
    for state in rows:
        if state.policy_year == 9 and state.policy_month >= 6:
            state.lapsed = True
    report = build_ul_report(_policy(), rows, run_date=date(2026, 7, 3))

    assert report.termination_year == 9
    year8, year9 = report.expense_rows
    assert year8.premium_outlay == 1200.0
    assert year9.year == 9 and year9.eoy_age == 59
    assert year9.premium_outlay == 0.0
    assert year9.coi_charge == 0.0
    assert year9.expenses == 0.0
    assert year9.interest_credited == 0.0
    assert year9.accum_value == 0.0
    assert year9.policy_debt == 0.0
    assert year9.net_death_benefit == 0.0


def test_expense_page_appended_only_when_enabled():
    from suiteview.illustration.ui.report_tab import (
        _EXPENSE_COLUMNS,
        PAGE_WIDTH,
        format_report_pages,
    )

    report = build_ul_report(_policy(), _expense_results(), run_date=date(2026, 7, 3))

    # Off by default — no expense page anywhere.
    default_pages = format_report_pages(report)
    assert not any("EXPENSE REPORT" in line for page in default_pages for line in page)

    pages = format_report_pages(report, include_expense_report=True)
    assert len(pages) == len(default_pages) + 1
    expense_page = pages[-1]                            # appended at the end
    flat = "\n".join(expense_page)
    assert "EXPENSE REPORT" in flat
    assert "WHERE EACH PREMIUM DOLLAR GOES" in flat     # intro verbiage
    assert all(len(line) <= PAGE_WIDTH for line in expense_page), max(expense_page, key=len)

    # Column widths span the full page; the locators lead with EOY age then
    # year (matching the illustration ledger), followed by the J:Y order with
    # Premium Charge left of COI, the combined EXPENSES/FEES column, and
    # POLICY DEBT before Net Surr Value.
    assert sum(width for width, *_ in _EXPENSE_COLUMNS) == PAGE_WIDTH
    bottom_header = next(line for line in expense_page
                         if line.strip().startswith("EOY") and "BENEFIT" in line)
    labels = bottom_header.split()
    assert labels == ["EOY", "YEAR", "OUTLAY", "BUTIONS", "CHARGE", "CHARGE",
                      "CHG", "EXPENSES/FEES", "CREDITED", "VALUE", "CHGS",
                      "DEBT", "VALUE", "BENEFIT"]

    # Data row: year 8 — EOY age 58, then premium charge (60), COI (120),
    # rider (12), combined expenses/fees (36+24+12+6+75=153), and EOY policy
    # values with debt before net surrender value.
    year8_line = next(line for line in expense_page
                      if line.split()[:2] == ["58", "8"])
    assert year8_line.split() == [
        "58", "8", "1,200", "700", "60", "120", "12", "153",
        "240", "5,096", "400", "250", "4,096", "100,000"]

    # Intro names the partial-surrender-charge component (normalize the
    # word-wrap so the phrase can span lines).
    assert "PARTIAL SURRENDER CHARGES ASSESSED ON WITHDRAWALS" in " ".join(flat.split())

    # A separate exhibit: its own heading and page numbering, no company
    # header, and the illustration's own numbering still excludes it.
    assert "SUPPLEMENTAL EXHIBIT FOR POLICY U0688012" in expense_page[1]
    assert "AMERICAN NATIONAL" not in flat
    assert "Page 1 of 1" in expense_page[0]
    illustration_total = len(default_pages)
    assert any(f"Page {illustration_total} of {illustration_total}" in line
               for line in pages[illustration_total - 1])


def test_expense_checkbox_rerenders_held_report(tmp_path, monkeypatch):
    from suiteview.illustration.ui import report_tab as report_tab_module
    from suiteview.illustration.ui.report_tab import IllustrationReportTab
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])  # noqa: F841
    monkeypatch.setattr(report_tab_module, "_SETTINGS_FILE", tmp_path / "settings.json")

    tab = IllustrationReportTab()
    assert not tab.expense_report_check.isChecked()     # off by default
    report = build_ul_report(_policy(), _expense_results(), run_date=date(2026, 7, 3))
    tab.display_report(report)
    base_sheets = tab._sheet_layout.count()

    # Checking the box re-renders from the held report — one extra sheet.
    tab.expense_report_check.setChecked(True)
    assert tab._sheet_layout.count() == base_sheets + 1
    last_sheet = tab._sheet_layout.itemAt(tab._sheet_layout.count() - 1).widget()
    assert "EXPENSE REPORT" in last_sheet.text()
    # Choice persisted to the settings file.
    import json
    settings = json.loads((tmp_path / "settings.json").read_text())
    assert settings["report_add_expense_page"] is True

    # Unchecking removes the page again.
    tab.expense_report_check.setChecked(False)
    assert tab._sheet_layout.count() == base_sheets


def test_expense_report_checkbox_uses_shared_run_controls_style():
    from suiteview.illustration.ui.report_tab import IllustrationReportTab
    from suiteview.illustration.ui.styles import INPUT_CHECKBOX_STYLE
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])  # noqa: F841

    tab = IllustrationReportTab()
    # "Add Expense Report" must render as the same purple, filled-checkmark
    # style as the Illustration Control tab's Run Controls checkboxes — not
    # a one-off plain-text checkbox.
    assert tab.expense_report_check.styleSheet() == INPUT_CHECKBOX_STYLE


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
