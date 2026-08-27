import os
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from suiteview.illustration.core.report_builder import build_ul_report
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
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


def _iul_policy() -> IllustrationPolicyData:
    policy = _policy()
    policy.plancode = "1U145500"
    policy.form_number = "IUL14"
    policy.illustration_date = date(2026, 7, 1)
    policy.account_value = 5395.01
    policy.fund_values = {
        "SW": 149.60,
        "IX": 2816.33,
        "IF": 2429.08,
    }
    policy.premium_allocations = {
        "U1": 0.0,
        "IX": 0.5,
        "IF": 0.5,
        "IS": 0.0,
        "IC": 0.0,
    }
    policy.index_illustration_rates = {
        "IX": 0.0623,
        "IF": 0.0623,
        "IS": 0.0556,
        "IC": 0.0599,
    }
    policy.index_strategy_parameters = {
        "IX": {
            "floor": 0.0, "cap": 0.0975, "participation": 1.0,
            "int_rate_spread": 0.0, "specified_rate": 0.0,
            "multiplier": 0.0, "asset_fee": 0.0,
        },
        "IF": {
            "floor": 0.0, "cap": 9.9999, "participation": 1.0,
            "int_rate_spread": 0.08, "specified_rate": 0.0,
            "multiplier": 0.0, "asset_fee": 0.0,
        },
        "IS": {
            "floor": 0.0, "cap": 9.9999, "participation": 1.0,
            "int_rate_spread": 0.0, "specified_rate": 0.075,
            "multiplier": 0.0, "asset_fee": 0.0,
        },
        "IC": {
            "floor": 0.015, "cap": 0.085, "participation": 1.0,
            "int_rate_spread": 0.0, "specified_rate": 0.0,
            "multiplier": 0.0, "asset_fee": 0.0,
        },
    }
    policy.index_benchmark_minimum = 0.0388
    policy.index_benchmark_maximum = 0.0756
    returns = [
        0.1362, 0.0353, -0.3849, 0.2345, 0.1278,
        0.0, 0.1341, 0.2960, 0.1139, -0.0073,
        0.0954, 0.1942, -0.0624, 0.2888, 0.1626,
        0.2689, -0.1944, 0.2423, 0.2331, 0.1639,
    ]
    policy.index_market_returns = {
        "SP500": [
            {"date": date(year, 12, 31), "return": annual_return}
            for year, annual_return in zip(range(2006, 2026), returns)
        ]
    }
    return policy


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
                kw = dict(
                    guideline_forceout=6266.37,
                    premium_capped=True,
                    premium_capped_by_guideline=True,
                    gross_premium=0.0,
                )
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

    # Cover activity is ordered as premiums, loans, then withdrawals.
    assert report.request_intro[0] == (
        "THE FOLLOWING ACTIVITY WAS REQUESTED IN PREPARING THIS ILLUSTRATION. "
        "HOWEVER, PREMIUMS MAY BE RESTRICTED BY GUIDELINE PREMIUM LIMITS."
    )


    assert report.request_lines == [
        "MONTHLY PREMIUM OF $100.00 FOR POLICY YEARS 8 THROUGH 9",
        "ANNUAL FIXED LOAN OF $3,000.00 FOR POLICY YEARS 12 THROUGH 15",
        "ANNUAL WITHDRAWAL OF $1,000.00 IN POLICY YEAR 11",
    ]

    # The proceeds/loan-balance qualifier leads the notes, while the broader
    # non-guaranteed warning belongs directly under that heading.
    assert report.note_paragraphs[0] == [
        "PREMIUM OUTLAY, PROCEEDS AND LOAN BALANCE VALUES ARE DETERMINED BY "
        "VALUES USING NON-GUARANTEED ASSUMPTIONS"
    ]
    non_guaranteed = report.note_paragraphs[2]
    assert non_guaranteed[2:4] == [
        "NON-GUARANTEED VALUES AND BENEFITS ARE BASED ON ASSUMPTIONS WHICH ARE SUBJECT TO "
        "CHANGE BY THE INSURER.",
        "ACTUAL RESULTS MAY BE MORE OR LESS FAVORABLE.",
    ]

    from suiteview.illustration.ui.report_tab import format_report_pages

    pages = format_report_pages(report)
    cover = "\n".join(pages[0])
    assert cover.index("THE FOLLOWING ACTIVITY WAS REQUESTED") < cover.index(
        "MONTHLY PREMIUM OF $100.00"
    ) < cover.index("ANNUAL FIXED LOAN OF $3,000.00") < cover.index(
        "ANNUAL WITHDRAWAL OF $1,000.00"
    )
    notes = "\n".join(next(
        page for page in pages
        if any("PREMIUM OUTLAY, PROCEEDS" in line for line in page)
    ))
    normalized_notes = " ".join(notes.split())
    assert normalized_notes.index("PREMIUM OUTLAY, PROCEEDS") < normalized_notes.index(
        "NON-GUARANTEED ASSUMPTIONS"
    ) < normalized_notes.index("NON-GUARANTEED VALUES AND BENEFITS")

    # Policy change section with estimated limits.
    assert len(report.change_sections) == 1
    section = report.change_sections[0]
    assert section.year == 9
    assert any("GUIDELINE SINGLE" in line for line in section.limit_lines)

    # Regulatory limits from the inforce snapshot.
    assert any("GUIDELINE SINGLE = $31,311.48" in line for line in report.regulatory_lines)
    assert any("PREMIUM WAIVER" in line for line in report.rider_lines)


def test_report_distinguishes_tamra_premium_restriction():
    results = _results()
    restricted = next(
        state for state in results
        if state.policy_year == 9 and state.policy_month == 1
    )
    restricted.premium_capped_by_guideline = False
    restricted.premium_capped_by_tamra = True

    report = build_ul_report(_policy(), results, run_date=date(2026, 6, 10))

    year9 = next(row for row in report.ledger if row.year == 9)
    assert "#" in year9.markers
    assert "*" not in year9.markers
    assert any(
        legend.startswith("#") and "PREVENT THE POLICY FROM BECOMING A MEC" in legend
        for legend in report.footnote_legends
    )
    assert not any(legend.startswith("*") for legend in report.footnote_legends)
    assert report.request_intro == [
        "THE FOLLOWING ACTIVITY WAS REQUESTED IN PREPARING THIS ILLUSTRATION. "
        "HOWEVER, PREMIUMS MAY BE RESTRICTED BY 7-PAY PREMIUM LIMITS."
    ]


def test_report_combines_guideline_and_tamra_restriction_intro():
    results = _results()
    restricted = next(
        state for state in results
        if state.policy_year == 9 and state.policy_month == 1
    )
    restricted.premium_capped_by_tamra = True

    report = build_ul_report(_policy(), results, run_date=date(2026, 6, 10))

    assert report.request_intro == [
        "THE FOLLOWING ACTIVITY WAS REQUESTED IN PREPARING THIS ILLUSTRATION. "
        "HOWEVER, PREMIUMS MAY BE RESTRICTED BY GUIDELINE OR 7-PAY PREMIUM LIMITS."
    ]


def test_report_plan_option_descriptions():
    expected = {
        "A": "A - Level Death Benefit",
        "B": "B - Increasing Death Benefit",
        "C": "C - Return of Premium DB",
    }

    for option, description in expected.items():
        policy = _policy()
        policy.db_option = option
        report = build_ul_report(policy, _results(), run_date=date(2026, 7, 22))
        plan_option = next(
            right for _left, right in report.policy_block
            if "CURRENT PLAN OPTION:" in right
        )
        assert plan_option.endswith(description)


def test_activity_section_shows_zero_premium_without_loans_or_withdrawals():
    rows = [MonthlyState(policy_year=7, policy_month=12, duration=84)]
    rows.extend(
        _month(8, month, requested_premium=0.0, gross_premium=0.0)
        for month in range(1, 13)
    )

    report = build_ul_report(_policy(), rows, run_date=date(2026, 7, 22))

    assert report.request_intro == [
        "THE FOLLOWING ACTIVITY WAS REQUESTED IN PREPARING THIS ILLUSTRATION."
    ]
    assert report.request_lines == [
        "MONTHLY PREMIUM OF $0.00 IN POLICY YEAR 8"
    ]


def test_activity_section_includes_current_year_dated_loan():
    inputs = IllustrationInputSet(
        scheduled_transactions=[
            ScheduledTransaction(
                kind=TransactionKind.LOAN,
                policy_year=8,
                amount=250.0,
                mode="M",
                metadata={"loan_type": "fixed"},
            ),
            ScheduledTransaction(
                kind=TransactionKind.LOAN,
                policy_year=9,
                amount=0.0,
                mode="A",
                metadata={"loan_type": "fixed"},
            ),
        ],
        dated_transactions=[
            DatedTransaction(
                kind=TransactionKind.LOAN,
                effective_date=date(2026, 5, 9),
                amount=250.0,
                metadata={"mode": "M", "loan_type": "fixed"},
            ),
            DatedTransaction(
                kind=TransactionKind.LOAN,
                effective_date=date(2026, 6, 9),
                amount=250.0,
                metadata={"mode": "M", "loan_type": "fixed"},
            ),
        ]
    )

    report = build_ul_report(
        _policy(), _results(), future_inputs=inputs, run_date=date(2026, 7, 22)
    )

    assert report.request_lines == [
        "MONTHLY PREMIUM OF $100.00 FOR POLICY YEARS 8 THROUGH 9",
        "MONTHLY FIXED LOAN OF $250.00 FOR POLICY YEARS 7 THROUGH 8",
    ]


def test_activity_section_lists_recurring_and_forecast_date_distributions():
    inputs = IllustrationInputSet(
        scheduled_transactions=[
            ScheduledTransaction(
                kind=TransactionKind.LOAN,
                policy_year=10,
                amount=500.0,
                mode="A",
                metadata={"loan_type": "fixed"},
            ),
            ScheduledTransaction(
                kind=TransactionKind.LOAN,
                policy_year=11,
                amount=0.0,
                mode="A",
                metadata={"loan_type": "fixed"},
            ),
        ],
        dated_transactions=[
            DatedTransaction(
                kind=TransactionKind.LOAN,
                effective_date=date(2026, 6, 9),
                amount=2500.0,
                metadata={
                    "loan_type": "fixed",
                    "forecast_date_transaction": True,
                },
            ),
            DatedTransaction(
                kind=TransactionKind.WITHDRAWAL,
                effective_date=date(2026, 6, 9),
                amount=750.0,
                subtype="net",
                metadata={"forecast_date_transaction": True},
            ),
            DatedTransaction(
                kind=TransactionKind.WITHDRAWAL,
                effective_date=date(2029, 11, 9),
                amount=1000.0,
                subtype="net",
                metadata={"mode": "A"},
            ),
        ],
    )

    report = build_ul_report(
        _policy(), _results(), future_inputs=inputs, run_date=date(2026, 6, 10))

    assert "ANNUAL FIXED LOAN OF $500.00 IN POLICY YEAR 10" in report.request_lines
    assert "ONE-TIME FIXED LOAN OF $2,500.00 ON 06/09/2026" in report.request_lines
    assert "ONE-TIME NET WITHDRAWAL OF $750.00 ON 06/09/2026" in report.request_lines
    assert "ANNUAL WITHDRAWAL OF $1,000.00 IN POLICY YEAR 11" in report.request_lines


def test_report_describes_loan_repayments_and_combines_them_with_ledger_outlay():
    rows = _results()
    rows[1].applied_loan_repayment = 1700.0
    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(
            kind=TransactionKind.LOAN_REPAYMENT,
            effective_date=date(year, 11, 9),
            amount=1700.0,
            metadata={"mode": "A"},
        )
        for year in range(2026, 2031)
    ])

    report = build_ul_report(
        _policy(), rows, future_inputs=inputs, run_date=date(2026, 7, 22)
    )

    assert report.loan_repayments_illustrated
    assert report.request_lines == [
        "MONTHLY PREMIUM OF $100.00 FOR POLICY YEARS 8 THROUGH 9",
        "ANNUAL LOAN REPAYMENT OF $1,700.00 FOR POLICY YEARS 8 THROUGH 12",
    ]
    assert report.ledger[0].premium_outlay == 2900.0

    from suiteview.illustration.ui.report_tab import format_report_pages

    pages = format_report_pages(report)
    cover = "\n".join(pages[0])
    ledger = "\n".join(pages[1])
    assert "ANNUAL LOAN REPAYMENT OF $1,700.00 FOR POLICY YEARS 8 THROUGH 12" in cover
    assert "PREMIUM +     " in ledger
    assert "LOAN REPAY" in ledger
    assert "    2,900" in ledger


def test_report_keeps_premium_outlay_heading_without_loan_repayments():
    from suiteview.illustration.ui.report_tab import format_report_pages

    report = build_ul_report(_policy(), _results(), run_date=date(2026, 7, 22))
    ledger = "\n".join(format_report_pages(report)[1])

    assert not report.loan_repayments_illustrated
    assert "PREMIUM" in ledger
    assert "LOAN REPAY" not in ledger


def test_cash_from_policy_includes_gross_withdrawals_loans_and_forceouts():
    rows = [MonthlyState(policy_year=7, policy_month=12, duration=84)]
    rows.extend(_month(8, month) for month in range(1, 13))
    rows[3].applied_net_withdrawal = 500.0
    rows[3].gross_withdrawal = 600.0
    rows[3].applied_regular_loan = 200.0
    rows[3].applied_preferred_loan = 25.0
    rows[3].applied_variable_loan = 75.0
    rows[3].guideline_forceout = 100.0

    report = build_ul_report(_policy(), rows, run_date=date(2026, 7, 22))

    assert report.ledger[0].cash_from_policy == 1000.0


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


def test_changes_on_same_date_group_into_one_section():
    """Multiple policy changes sharing an effective date collapse into a single
    section so the cover and regulatory pages show one block per date."""
    inputs = IllustrationInputSet(policy_changes=[
        PolicyChangeEvent(kind=PolicyChangeKind.FACE_AMOUNT,
                          effective_date=date(2027, 11, 9), value=75000.0),
        PolicyChangeEvent(kind=PolicyChangeKind.DB_OPTION,
                          effective_date=date(2027, 11, 9), value="B"),
    ])
    report = build_ul_report(_policy(), _results(), future_inputs=inputs,
                             run_date=date(2026, 6, 10))

    assert len(report.change_sections) == 1
    section = report.change_sections[0]
    assert any("SPECIFIED AMOUNT CHANGE TO $75,000.00" in line
               for line in section.summary_lines)
    assert any("DEATH BENEFIT OPTION CHANGE TO OPTION B" in line
               for line in section.summary_lines)

    from suiteview.illustration.ui.report_tab import format_report_pages
    flat = "\n".join(line for page in format_report_pages(report) for line in page)
    assert flat.count("THE FOLLOWING POLICY CHANGES WERE FORECASTED ON 11/09/2027") == 1
    assert flat.count(
        "ESTIMATED REGULATORY LIMITS FOR PREMIUMS AS OF 11/09/2027") == 1
    assert flat.count(
        "RIDERS AND BENEFITS ASSUMED IN THIS ILLUSTRATION AS OF 11/09/2027") == 1


def test_retroactive_mec_marks_discovery_year_and_suppresses_later_restart():
    rows = [MonthlyState(
        policy_year=3, policy_month=12, duration=36,
        tamra_7pay_start_date=date(2023, 7, 12),
    )]
    for year in range(4, 9):
        start = date(2030, 7, 12) if year == 8 else date(2023, 7, 12)
        for month in range(1, 13):
            rows.append(_month(
                year, month,
                tamra_7pay_start_date=start,
                is_mec=True,
                mec_year=4,
            ))

    report = build_ul_report(_policy(), rows, run_date=date(2026, 8, 3))

    assert report.year_of_mec == 4
    assert "&" in next(row.markers for row in report.ledger if row.year == 4)
    assert report.seven_pay_restarts == []
    assert not any("NEW 7-PAY" in line for line in report.footnote_legends)
    assert any(
        line == "& THE POLICY IS ILLUSTRATED TO BECOME A MEC IN THIS YEAR"
        for line in report.footnote_legends
    )


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


def test_cvat_policy_shows_seven_pay_but_no_guideline_limits():
    """CVAT policies have no GLP/GSP guideline limits, but while inside the
    7-pay period the regulatory section still shows the 7-PAY PREMIUM and its
    start date."""
    policy = _policy()
    policy.def_of_life_ins = "CVAT"

    # Inforce snapshot (results[0]) sits inside the 7-pay window (tamra_year 1-7).
    inforce = MonthlyState(
        policy_year=7, policy_month=6, duration=78,
        tamra_year=3,
        tamra_7pay_level=12602.03,
        tamra_7pay_start_date=date(2024, 7, 9),
    )
    rows = [inforce]
    for year in (8, 9):
        for month in range(1, 13):
            rows.append(_month(year, month,
                               tamra_7pay_level=12602.03,
                               tamra_7pay_start_date=date(2024, 7, 9)))
    policy.tamra_7pay_level = 12602.03
    policy.tamra_7pay_start_date = date(2024, 7, 9)

    report = build_ul_report(policy, rows, run_date=date(2026, 8, 14))

    assert any("7-PAY PREMIUM = $12,602.03" in line for line in report.regulatory_lines)
    assert any("7-PAY START DATE = 07/09/2024" in line for line in report.regulatory_lines)
    # No guideline lines for a CVAT policy.
    assert not any("GUIDELINE SINGLE" in line for line in report.regulatory_lines)
    assert not any("LEVEL PREMIUM" in line for line in report.regulatory_lines)


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


def test_nothing_extra_renders_at_maturity():
    """Nothing extra happens at maturity (removed 2026-07-19): the ledger ends
    at the maturity-age EOY row, with NO VALUES AT MATURITY strip, no
    post-maturity stub row, and no '%' after-maturity legend."""
    policy = _policy()
    policy.maturity_age = 58                    # year 9 begins at attained 58
    report = build_ul_report(policy, _results(), run_date=date(2026, 7, 3),
                             guaranteed_results=_guaranteed_results())

    # Year 9 (begins at the maturity age) is the stub — dropped everywhere.
    assert [r.year for r in report.ledger] == [8]
    assert [r.year for r in report.expense_rows] == [8]
    assert not any(legend.startswith("%") for legend in report.footnote_legends)

    from suiteview.illustration.ui.report_tab import format_report_pages
    flat = "\n".join(line for page in format_report_pages(report) for line in page)
    assert "VALUES AT MATURITY" not in flat
    assert "AFTER MATURITY" not in flat


def test_no_maturity_strip_before_maturity_or_on_lapse():
    from suiteview.illustration.ui.report_tab import format_report_pages

    # A pre-maturity projection shows no maturity strip.
    report = build_ul_report(_policy(), _results(), run_date=date(2026, 7, 3))
    assert not any("VALUES AT MATURITY" in line
                   for page in format_report_pages(report) for line in page)

    # Lapsing in the maturity year likewise renders no strip.
    policy = _policy()
    policy.maturity_age = 58
    rows = _results()
    rows[-1].lapsed = True
    report = build_ul_report(policy, rows, run_date=date(2026, 7, 3))
    assert not any("VALUES AT MATURITY" in line
                   for page in format_report_pages(report) for line in page)


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
    assert "PROCEEDS" in ledger_page
    assert "CASH FROM" not in ledger_page


def test_ledger_separates_large_policy_values():
    from suiteview.illustration.core.report_builder import LedgerRow
    from suiteview.illustration.ui.report_tab import (
        PAGE_WIDTH,
        _LEDGER_HEADER,
        _ledger_line,
    )

    line = _ledger_line(LedgerRow(
        eoy_age=64,
        year=95,
        premium_outlay=18_000.0,
        guar_accum=12_166_463.0,
        guar_surr=12_166_463.0,
        guar_death=13_395_971.0,
        accum_value=42_152_076.0,
        surr_value=42_152_076.0,
        death_benefit=43_381_584.0,
    ))

    assert "12,166,463 12,166,463 13,395,971" in line
    assert "42,152,076 42,152,076 43,381,584" in line
    assert len(line) <= PAGE_WIDTH
    assert all(len(header) <= PAGE_WIDTH for header in _LEDGER_HEADER)


def test_iul_report_builds_fund_allocation_rate_and_historical_sections():
    report = build_ul_report(
        _iul_policy(), _results(), run_date=date(2026, 7, 1)
    )

    assert report.is_iul
    assert report.subtitle == "WITH INDEXED INTEREST CREDITING OPTION"
    assert [(row.fund_id, row.value) for row in report.iul_fund_values] == [
        ("SW", 149.60),
        ("IX", 2816.33),
        ("IF", 2429.08),
    ]
    assert [row.fund_id for row in report.iul_allocations] == [
        "U1", "IX", "IF", "IS", "IC",
    ]
    assert {
        row.fund_id: row.allocation for row in report.iul_allocations
    }["IF"] == pytest.approx(0.5)
    assert [row.fund_id for row in report.iul_strategy_rates] == [
        "IX", "IF", "IS", "IC",
    ]
    assert report.iul_fixed_rate is None
    assert report.iul_benchmark_minimum == pytest.approx(0.0388)
    assert report.iul_benchmark_maximum == pytest.approx(0.0756)
    assert len(report.iul_historical_rows) == 20
    assert report.iul_historical_rows[0].credited_rates == pytest.approx({
        "IX": 0.0975,
        "IF": 0.0562,
        "IS": 0.075,
        "IC": 0.085,
    })
    assert report.iul_historical_rows[2].credited_rates == pytest.approx({
        "IX": 0.0, "IF": 0.0, "IS": 0.0, "IC": 0.0,
    })
    twenty_year = report.iul_compound_yields[-1]
    assert twenty_year.years == 20
    assert twenty_year.market_returns["SP500"] == pytest.approx(
        0.08881489183456481
    )


def test_iul_history_period_uses_illustration_date_not_valuation_date():
    policy = _iul_policy()
    policy.valuation_date = date(2024, 5, 9)

    report = build_ul_report(
        policy, _results(), run_date=policy.illustration_date)

    assert report.iul_historical_rows[0].date_eoy == date(2006, 12, 31)
    assert report.iul_historical_rows[-1].date_eoy == date(2025, 12, 31)


def test_iul_report_renders_new_sections_and_benchmark_rates():
    from suiteview.illustration.ui.report_tab import PAGE_WIDTH, format_report_pages

    report = build_ul_report(
        _iul_policy(), _results(), run_date=date(2026, 7, 1)
    )
    pages = format_report_pages(report)
    flat_pages = ["\n".join(page) for page in pages]

    assert "WITH INDEXED INTEREST CREDITING OPTION" in flat_pages[0]
    assert "THE ACCUMULATION VALUE OF $5,395.01 CONSISTS" in flat_pages[0]
    assert "THE ALLOCATION PERCENTAGES USED IN THIS ILLUSTRATION ARE" in flat_pages[0]
    assert (
        "[IX] - S&P 500 INDEX ONE YEAR POINT TO POINT WITH A CAP AND 0% FLOOR"
        in flat_pages[0]
    )
    assumptions = next(
        page for page in flat_pages
        if "ILLUSTRATED RATES BY INDEX STRATEGY" in page
    )
    assert "BENCHMARK INDEX STRATEGY" in assumptions
    benchmark_line = next(
        line for line in assumptions.splitlines()
        if "ONE YEAR POINT TO POINT WITH CURRENT CAP AND FLOOR" in line
    )
    assert "3.88%" in benchmark_line
    assert "7.56%" in benchmark_line
    history = flat_pages[-1]
    assert "HISTORICAL INDEX RATE LEDGER - CURRENT SCENARIO" in history
    assert "S&P 500" in history and "IX" in history and "IF" in history
    assert "12/31/2006" in history and "20-YR YIELD" in history
    assert all(len(line) <= PAGE_WIDTH for page in pages for line in page)


def test_iul_historical_table_right_aligns_headers_rows_and_yields():
    from suiteview.illustration.ui.report_tab import format_report_pages

    report = build_ul_report(
        _iul_policy(), _results(), run_date=date(2026, 7, 1)
    )
    history = format_report_pages(report)[-1]
    separator_index = next(
        index
        for index, line in enumerate(history)
        if set(line) == {"-"} and "YEAR ENDING" in history[index - 1]
    )
    header = history[separator_index - 3:separator_index]
    annual = history[separator_index + 1]
    yields = [
        line for line in history if line.strip().endswith("%") and "YR YIELD" in line
    ]

    assert "MARKET INDEX" in header[0]
    assert "S&P 500" in header[1]
    assert "YEAR ENDING" in header[2]
    assert "RETURNS" in header[2]

    def percent_ends(line: str) -> list:
        ends = []
        search_from = 0
        for token in line.split():
            if token.endswith("%"):
                pos = line.index(token, search_from)
                ends.append(pos + len(token))
                search_from = pos + len(token)
        return ends

    annual_rate_ends = percent_ends(annual)
    assert header[0].index("MARKET INDEX") + len("MARKET INDEX") == annual_rate_ends[0]
    assert header[1].index("S&P 500") + len("S&P 500") == annual_rate_ends[0]
    assert header[2].index("RETURNS") + len("RETURNS") == annual_rate_ends[0]
    assert header[2].index("YEAR ENDING") + len("YEAR ENDING") == annual.index(
        "12/31/2006"
    ) + len("12/31/2006")

    for line in yields:
        assert percent_ends(line) == annual_rate_ends


def test_terminal_policy_year_death_benefit_is_zero():
    rows = _results()
    rows[-4].lapsed = True
    rows[-4].ending_db = 25_000.0
    rows[-3].ending_db = 25_000.0
    rows[-2].ending_db = 25_000.0
    rows[-1].ending_db = 25_000.0

    report = build_ul_report(
        _policy(), rows, run_date=date(2026, 7, 1)
    )

    terminal = report.ledger[-1]
    assert terminal.lapsed
    assert terminal.death_benefit == 0.0


def test_iul_historical_header_shows_multiplier_asset_fees():
    from suiteview.illustration.ui.report_tab import format_report_pages

    policy = _iul_policy()
    policy.plancode = "1U146800"
    policy.premium_allocations = {"IX": 0.0, "IF": 0.0, "IP": 0.5, "IR": 0.5}
    policy.index_illustration_rates = {
        "IX": 0.0623, "IF": 0.0623, "IP": 0.0623, "IR": 0.0623,
    }
    policy.index_strategy_parameters = {
        "IX": {
            "floor": 0.0, "cap": 0.0975, "participation": 1.0,
            "int_rate_spread": 0.0, "specified_rate": 0.0,
            "multiplier": 0.0, "asset_fee": 0.0,
        },
        "IF": {
            "floor": 0.0, "cap": 9.9999, "participation": 1.0,
            "int_rate_spread": 0.08, "specified_rate": 0.0,
            "multiplier": 0.0, "asset_fee": 0.0,
        },
        "IP": {
            "floor": 0.0, "cap": 0.12, "participation": 1.0,
            "int_rate_spread": 0.0, "specified_rate": 0.0,
            "multiplier": 0.24, "asset_fee": 0.0215,
        },
        "IR": {
            "floor": 0.0, "cap": 0.12, "participation": 1.0,
            "int_rate_spread": 0.0, "specified_rate": 0.0,
            "multiplier": 0.60, "asset_fee": 0.0415,
        },
    }

    report = build_ul_report(policy, _results(), run_date=date(2026, 7, 1))
    history = "\n".join(format_report_pages(report)[-1])

    assert "FEE 2.15%" in history
    assert "FEE 4.15%" in history


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


def test_bonus_stated_inline_not_as_footnote():
    """The interest bonus is stated inline in the non-guaranteed assumptions
    sentence, not as a separate '*' footnote (changed 2026-07-19)."""
    rows = [MonthlyState(policy_year=7, policy_month=6, duration=78)]
    for year in (8, 9):
        for month in range(1, 13):
            rows.append(_month(year, month, bonus_interest_rate=0.009))
    report = build_ul_report(_policy(), rows, run_date=date(2026, 7, 3))

    notes = " ".join(" ".join(p) for p in report.note_paragraphs)
    assert ("PLUS A BONUS OF 0.900% WHICH IS ADDED TO THE ILLUSTRATED RATE "
            "STARTING IN POLICY YEAR 8") in notes
    # No asterisk marker and no separate footnote paragraph.
    assert "BONUS*" not in notes
    assert "CURRENTLY THIS PLAN HAS A BONUS" not in notes

    from suiteview.illustration.ui.report_tab import format_report_pages
    flat = "\n".join(line for page in format_report_pages(report) for line in page)
    assert "*CURRENTLY THIS PLAN HAS A BONUS" not in flat

    # No bonus → no bonus wording at all.
    plain = build_ul_report(_policy(), _results(), run_date=date(2026, 7, 3))
    plain_notes = " ".join(" ".join(p) for p in plain.note_paragraphs)
    assert "BONUS" not in plain_notes


def test_lock_values_locks_current_cash_flows():
    from dateutil.relativedelta import relativedelta

    from suiteview.illustration.core.guaranteed_projection import lock_values

    policy = _policy()
    results = [MonthlyState(policy_year=7, policy_month=6, duration=78)]
    results.append(_month(8, 1, gross_premium=100.0, gp_exception_prem=25.0))
    results.append(_month(8, 2, gross_premium=0.0, applied_net_withdrawal=500.0,
                          guideline_forceout=750.0,
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
    # Force-outs are recalculated independently by the guaranteed projection,
    # not folded into its locked requested withdrawal.
    assert by_key[(TransactionKind.WITHDRAWAL, month2)] == 500.0
    assert by_key[(TransactionKind.LOAN_REPAYMENT, month2)] == 40.0
    loans = [t for t in locked.dated_transactions
             if t.kind == TransactionKind.LOAN and t.effective_date == month2]
    assert sorted(t.amount for t in loans) == [75.0, 200.0]
    assert any(t.subtype == "variable" and t.amount == 75.0 for t in loans)


def test_guaranteed_options_respect_disabled_tefra_forceouts():
    from suiteview.illustration.core.guaranteed_projection import guaranteed_options

    options = guaranteed_options(IllustrationOptions(
        conform_to_tefra=False,
        conform_to_tamra=False,
    ))

    assert not options.force_out_enabled
    assert not options.guideline_cap_enabled
    assert not options.tamra_cap_enabled


def test_guaranteed_projection_blends_the_guaranteed_rate_for_iul():
    """IUL blended-rate run: the guaranteed side blends GINT the same way the
    current side blends its crediting rate (index strategies floor at 0%)."""
    from suiteview.illustration.core.guaranteed_projection import (
        _guaranteed_crediting_rate,
    )
    from suiteview.illustration.models.input_set import IllustrationOptions

    policy = _policy()
    policy.plancode = "1U145500"                 # IUL14 — a real IUL plancode
    policy.premium_allocations = {"U1": 0.25, "IX": 0.75}

    rate = _guaranteed_crediting_rate(
        policy, 0.025, IllustrationOptions(iul_wair_crediting=False))
    # 0.25 fixed × 0.025 GINT = 0.625% — not the full 2.5% plan GINT.
    assert rate == pytest.approx(0.00625)


def test_guaranteed_projection_keeps_full_gint_for_declared_rate_plan():
    """Non-IUL (declared-rate) plans credit the plan GINT directly."""
    from suiteview.illustration.core.guaranteed_projection import (
        _guaranteed_crediting_rate,
    )
    from suiteview.illustration.models.input_set import IllustrationOptions

    policy = _policy()                            # plancode 1U143900 — declared rate
    rate = _guaranteed_crediting_rate(policy, 0.03, IllustrationOptions())
    assert rate == pytest.approx(0.03)


def test_guaranteed_projection_uses_full_gint_for_iul_wair_run():
    """WAIR runs enforce the guaranteed basis via the WAIR cap (RERUN VK), so
    the free-AV declared rate stays the plan GINT — it is not blended here."""
    from suiteview.illustration.core.guaranteed_projection import (
        _guaranteed_crediting_rate,
    )
    from suiteview.illustration.models.input_set import IllustrationOptions

    policy = _policy()
    policy.plancode = "1U145500"                 # IUL14
    policy.premium_allocations = {"U1": 0.25, "IX": 0.75}

    rate = _guaranteed_crediting_rate(
        policy, 0.025, IllustrationOptions(iul_wair_crediting=True))
    assert rate == pytest.approx(0.025)


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
                kw.update(applied_net_withdrawal=500.0, gross_withdrawal=575.0,
                          applied_regular_loan=200.0, wd_partial_sc=75.0)
            if year == 9 and month == 1:
                kw.update(guideline_forceout=1000.0)
            rows.append(_month(year, month, **kw))
    return rows


def test_expense_rows_annualize_j_to_y_columns():
    """One hand-computed value per column family: charges/credits are annual
    sums, policy values are end-of-year, cash out includes gross withdrawals
    and force-outs but not loans."""
    report = build_ul_report(_policy(), _expense_results(), run_date=date(2026, 7, 3))

    assert [r.year for r in report.expense_rows] == [8, 9]
    year8, year9 = report.expense_rows
    assert year8.eoy_age == 58                          # K — age at END of year (50 + 8)
    assert year8.premium_outlay == 1200.0               # L — 12 x 100
    assert year8.distributions == 575.0                 # M — gross WD includes 75 PSC
    assert year9.distributions == 1000.0                # M — force-out counts
    assert year8.premium_charge == 60.0                 # N — 12 x 5
    assert year8.coi_charge == 120.0                    # O — 12 x 10 (base COI only)
    assert year8.per_unit_charge == 36.0                # P — 12 x 3
    assert year8.monthly_fee == 24.0                    # Q — 12 x 2
    assert year8.asset_charge == 12.0                   # R — 12 x 1
    assert year8.av_charge == 6.0                       # S — 12 x 0.5
    assert year8.rider_charges == 12.0                  # T — 12 x (0.75 + 0.25)
    # PSC is already included in gross withdrawal and is not counted again.
    # Combined page column: P + Q + R + S = 36 + 24 + 12 + 6.
    assert year8.expenses == 78.0
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
    assert "ANNUAL ACTIVITY INTO ITS EXPENSE" in flat   # intro verbiage
    assert "CASH" in flat and "OUT" in flat
    assert "DISTRI-" not in flat and "BUTIONS" not in flat
    assert all(len(line) <= PAGE_WIDTH for line in expense_page), max(expense_page, key=len)

    # Column widths span the full page; the locators lead with EOY age then
    # year (matching the illustration ledger), followed by the J:Y order with
    # Premium Charge left of COI, the combined EXPENSES/FEES column, and
    # POLICY DEBT before Net Surr Value.
    assert sum(width for width, *_ in _EXPENSE_COLUMNS) == PAGE_WIDTH
    bottom_header = next(line for line in expense_page
                         if line.strip().startswith("EOY") and "BENEFIT" in line)
    labels = bottom_header.split()
    assert labels == ["EOY", "YEAR", "OUTLAY", "OUT", "CHARGE", "CHARGE",
                      "CHG", "EXP/FEES", "CREDITED", "VALUE", "CHGS",
                      "DEBT", "VALUE", "BENEFIT"]

    # Data row: year 8 — EOY age 58, then premium charge (60), COI (120),
    # rider (12), combined expenses/fees (36+24+12+6=78), and EOY policy
    # values with debt before net surrender value.
    year8_line = next(line for line in expense_page
                      if line.split()[:2] == ["58", "8"])
    assert year8_line.split() == [
        "58", "8", "1,200.00", "575", "60", "120", "12", "78",
        "240", "5,096", "400", "250", "4,096", "100,000"]

    assert "CASH OUT (GROSS WITHDRAWALS AND FORCED-OUT PREMIUM)" in " ".join(flat.split())
    assert "PARTIAL SURRENDER CHARGES" not in flat

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


def test_guaranteed_options_preserve_regulatory_conformance():
    from suiteview.illustration.core.guaranteed_projection import guaranteed_options
    base = IllustrationOptions(conform_to_tefra=True, conform_to_tamra=True,
                               allow_exception_prems=True, apply_prem_to_loan=True)
    opts = guaranteed_options(base)
    assert opts.conform_to_tefra
    assert opts.conform_to_tamra
    assert not opts.allow_exception_prems
    assert not opts.apply_prem_to_loan
    assert not opts.restrict_loans_to_sv
    assert opts.guideline_cap_enabled and opts.force_out_enabled
    assert opts.tamra_cap_enabled


def test_guaranteed_options_preserve_explicit_acceptance_cap_override():
    from suiteview.illustration.core.guaranteed_projection import guaranteed_options

    opts = guaranteed_options(IllustrationOptions(
        conform_to_tefra=True,
        cap_premiums_at_acceptance=False,
    ))

    assert opts.force_out_enabled
    assert not opts.guideline_cap_enabled
