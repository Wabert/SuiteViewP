"""ISWL on reduced paid-up: CyberLife's NSP roll-forward, the projection, checks, report and workspace.

Offline (no DB2): the stored values are hard-coded from the record (read-only, 10/9/2026):

* 11663262 81335100 issue 10/07/1988 age 21, 20.610 units, L4 (1980 CSO male composite ALB)
  5.5%, LOW_DUR_PER 38: 427.13, 440.77, 454.498282; PolView NSP cash value 8,803.15 at
  10/07/2026; maturity 10/07/2062.
* N8620833 FN2VN100 issue 03/17/1986 age 30, 1.230 units, N1 (1980 CSO female nonsmoker ANB)
  6%, LOW_DUR_PER 40: 465.91, 481.77, 497.616442; PolView 582.82 at 09/17/2026 (6 months).
"""
import math
import os
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from suiteview.illustration.core.iswl_rpu.engine import ISWLRPUEngine, ISWLRPUError, nsp_schedule
from suiteview.illustration.core.iswl_rpu.inforce_checks import inforce_checks
from suiteview.illustration.core.iswl_rpu.nsp_roll import (
    claims_factor,
    endowment_nsp,
    roll_step,
    stored_step_tolerance,
)
from suiteview.illustration.core.iswl_rpu.policy_loader import build_iswl_rpu_policy, is_iswl_rpu
from suiteview.illustration.core.iswl_rpu.report import build_iswl_rpu_report
from suiteview.illustration.core.iswl_rpu.service import ISWLRPUBasis
from suiteview.illustration.core.iswl_rpu.workup import roll_workup
from suiteview.illustration.core.ledger_report import format_ledger_pages
from suiteview.illustration.core.parwl.nsp import mortality_table
from suiteview.illustration.models.iswl_rpu import ISWLRPUInputs, ISWLRPULoan, ISWLRPUPolicy


def make_policy(**overrides) -> ISWLRPUPolicy:
    values = dict(
        policy_number="11663262", company_code="01", region="CKPR", insured_name="TEST INSURED",
        issue_state="TX", phase=1, plancode="81335100", form_number="ISWL88", description="",
        issue_date=date(1988, 10, 7), issue_age=21, rate_sex="M", sex_description="Male", rate_class="N",
        premium_status="45", premium_status_description="RPU", valuation_date=date(2026, 10, 7),
        last_anniversary=date(2026, 10, 7), paid_to_date=date(2022, 2, 7),
        last_account_value_date=date(2022, 1, 7), units=20.61, value_per_unit=1000.0,
        maturity_date=date(2062, 10, 7), nsp_table="L4", eti_table="L8", nsp_interest=0.055,
        rpu_benefit_code="6", low_duration=38, stored_nsp=(427.13, 440.77, 454.498282),
        polview_cash_value=8803.15, record_death_benefit=20610.0)
    values.update(overrides)
    return ISWLRPUPolicy(**values)


def anb_policy(**overrides) -> ISWLRPUPolicy:
    values = dict(policy_number="N8620833", plancode="FN2VN100", issue_date=date(1986, 3, 17), issue_age=30,
                  units=1.23, maturity_date=date(2051, 3, 17), nsp_table="N1", eti_table="NB", nsp_interest=0.06,
                  low_duration=40, stored_nsp=(465.91, 481.77, 497.616442), valuation_date=date(2026, 9, 17),
                  last_anniversary=date(2026, 3, 17), polview_cash_value=582.82, record_death_benefit=1230.0,
                  sex_description="Female", rate_sex="F")
    values.update(overrides)
    return make_policy(**values)


# -- the conversion basis -------------------------------------------------------

def test_endowment_nsp_reproduces_11663262_conversion():
    """02/07/2022 conversion (FH_FIXED TR net 7,518.57; LH_COV_TMN 25 original units): the cash
    buys a paid-up endowment at 95, face = cash / NSP rounded up to the next dollar (B20 p.498)."""
    at_54, at_55 = endowment_nsp("L4", 0.055, 54, 95), endowment_nsp("L4", 0.055, 55, 95)
    assert at_54 == pytest.approx(360.384160, abs=1e-6)
    conversion = (at_54 * 8 + at_55 * 4) / 12                    # 4 months past the 10/07/2021 anniversary
    per_unit = math.ceil(round(7518.57 / 25 / (conversion / 1000) * 100, 6)) / 100
    assert per_unit == 824.39                                   # WORK RPU AMT, rounded to the high cent
    assert math.ceil(per_unit * 25) == 20610                     # the record's 20.610 units
    # The third stored value at conversion, rolled forward four anniversaries, gives today's record.
    carry = round(endowment_nsp("L4", 0.055, 56, 95), 6)
    for duration in range(35, 39):
        carry = roll_step(carry, "L4", 0.055, 21, duration).carried
    assert round(carry, 2) == 440.77
    assert roll_step(carry, "L4", 0.055, 21, 39).carried == pytest.approx(454.498282, abs=0.001)


def test_endowment_nsp_is_one_thousand_at_maturity_and_matches_the_term_sum():
    assert endowment_nsp("L4", 0.055, 95, 95) == 1000.0
    table, i = mortality_table("L4"), 0.055
    c, v, alive, total = claims_factor(table, i), 1 / 1.055, 1.0, 0.0
    for t, age in enumerate(range(54, 95)):
        q = table.qx[age - table.first_age]
        total += alive * q * v ** (t + 1)
        alive *= 1 - q
    assert endowment_nsp("L4", i, 54, 95) == pytest.approx(1000 * (c * total + alive * v ** 41), abs=1e-9)


def test_comparison_is_the_paid_up_endowment():
    engine = ISWLRPUEngine(make_policy())
    first = engine.schedule[0]
    assert first.comparison == pytest.approx(endowment_nsp("L4", 0.055, 59, 95))
    assert engine.schedule[-1].comparison <= 1000.0


# -- the roll-forward step ------------------------------------------------------

def test_roll_reproduces_11663262_stored_values():
    first = roll_step(427.13, "L4", 0.055, 21, 38)
    assert first.q_age == 60                                    # issue age + d + 1
    assert abs(first.value - 440.77) <= 0.0115
    second = roll_step(440.77, "L4", 0.055, 21, 39)
    assert abs(second.value - 454.498282) <= 0.0058
    assert first.claims_factor == pytest.approx(0.055 / math.log(1.055))       # ALB: i / ln(1 + i)
    assert abs(roll_step(440.77, "L4", 0.055, 21, 39 - 1).value - 454.498282) > 0.5   # q one age younger misses


def test_roll_reproduces_an_age_nearest_birthday_table():
    table = mortality_table("N1")
    assert not table.age_last_birthday and claims_factor(table, 0.06) == 1.0
    first = roll_step(465.91, "N1", 0.06, 30, 40)
    second = roll_step(481.77, "N1", 0.06, 30, 41)
    assert abs(first.value - 481.77) <= stored_step_tolerance(first, 0)
    assert abs(second.value - 497.616442) <= stored_step_tolerance(second, 1)
    assert second.carried == round(second.value, 6)


# -- the schedule and projection ---------------------------------------------------

def test_schedule_rolls_from_the_third_stored_value_and_stops_at_the_first_negative():
    schedule = nsp_schedule(make_policy())
    by_duration = {v.duration: v for v in schedule}
    assert [v.source for v in schedule[:3]] == ["stored"] * 3
    assert by_duration[40].per_unit == 454.50 and by_duration[40].carry == 454.498282
    assert by_duration[41].carry == pytest.approx(468.248484, abs=1e-6)
    assert by_duration[56].per_unit == 623.76 and by_duration[56].age == 77                 # the peak
    negative = schedule[-1]
    assert (negative.duration, negative.age, negative.source) == (67, 88, "negative")
    assert negative.carry == pytest.approx(-21.816205, abs=1e-6)
    assert by_duration[66].per_unit == 177.73


def test_projection_ties_to_polview_then_freezes_after_the_negative_value():
    result = ISWLRPUEngine(make_policy()).run()
    start = result.months[0]
    assert (start.when, start.cash_value, start.death_benefit) == (date(2026, 10, 7), 8803.15, 20610.0)
    assert any("ties to PolView" in note for note in result.notes)
    assert result.peak.age == 77 and result.peak.per_unit == 623.76
    assert result.freeze_from == date(2054, 10, 7)
    years = {y.policy_year: y for y in result.years}
    assert years[39].cash_value == 9084.27 and not years[39].frozen
    assert years[66].cash_value == 3663.02 and not years[66].frozen
    assert years[67].frozen and years[67].cash_value == 3663.02 and years[74].cash_value == 3663.02
    assert result.years[-1].end_date == date(2062, 10, 7) and result.years[-1].age == 95
    assert any("turns negative at duration 67" in w for w in result.warnings)
    assert result.divergence_from == 51
    assert all(y.comparison_cash_value > y.cash_value for y in result.years)
    month = next(m for m in result.months if m.when == date(2055, 1, 7))
    assert month.frozen and month.cash_value == 3663.02


def test_monthly_interpolation_is_polviews():
    result = ISWLRPUEngine(anb_policy()).run()
    start = result.months[0]
    assert (start.duration, start.month_of_year) == (40, 6)
    assert start.cash_value == 582.82                       # 1.23 x (465.91 x 6 + 481.77 x 6) / 12
    later = ISWLRPUEngine(make_policy(valuation_date=date(2027, 2, 7))).run().months[0]
    assert later.cash_value == 8896.86                       # 20.61 x (427.13 x 8 + 440.77 x 4) / 12


def test_illustrate_to_age_and_refusals():
    result = ISWLRPUEngine(make_policy(), ISWLRPUInputs(end_age=70)).run()
    assert result.years[-1].age == 70 and result.years[-1].end_date == date(2037, 10, 7)
    with pytest.raises(ISWLRPUError, match="after the attained age"):
        ISWLRPUEngine(make_policy(), ISWLRPUInputs(end_age=59)).run()
    with pytest.raises(ISWLRPUError, match="loan of"):
        ISWLRPUEngine(make_policy(run_block="A policy loan of $1,000.00 ...")).run()
    with pytest.raises(ISWLRPUError, match="cover durations 38-40"):
        ISWLRPUEngine(make_policy(valuation_date=date(2028, 11, 7))).run()


# -- checks, workup and report -------------------------------------------------------

def test_inforce_checks_match_the_record():
    policy = make_policy()
    checks = inforce_checks(policy, ISWLRPUEngine(policy))
    status = {c.item.split(" (")[0] if c.area != "Cash value" else c.area: c.status for c in checks}
    assert status["LOW_DUR_1_NSP_AMT"] == "match" and status["LOW_DUR_2_NSP_AMT"] == "match"
    assert status["Cash value"] == "match"
    assert next(c for c in checks if c.area == "Death benefit").status == "match"
    differs = inforce_checks(make_policy(stored_nsp=(427.13, 441.77, 454.498282)), ISWLRPUEngine(make_policy()))
    assert differs[0].status == "differs" and "Differs by" in differs[0].detail


def test_workup_rebuilds_stored_rolled_and_negative_values():
    policy = make_policy()
    schedule = nsp_schedule(policy)
    stored = roll_workup(policy, schedule, 39)
    assert stored.matches and any(s.check.startswith("Matches LOW_DUR_1_NSP_AMT") for s in stored.steps)
    rolled = roll_workup(policy, schedule, 41)
    assert rolled.matches and rolled.step.q_age == 62
    assert any(s.check == "Matches the NSP schedule" for s in rolled.steps)
    negative = roll_workup(policy, schedule, 67)
    assert any(s.item == "Negative value" for s in negative.steps)
    with pytest.raises(ValueError):
        roll_workup(policy, schedule, 38)


def test_report_pages_show_both_bases_and_the_frozen_years():
    result = ISWLRPUEngine(make_policy()).run()
    pages = format_ledger_pages(build_iswl_rpu_report(result, date(2026, 10, 9)))
    text = "\n".join("\n".join(page) for page in pages)
    assert "REDUCED PAID-UP INSURANCE" in text and "PAID-UP FACE AMOUNT:  $20,610" in text
    assert "CYBERLIFE BASIS" in text and "ENDOWMENT NSP" in text
    assert "YEARS 67-74: CYBERLIFE'S NET SINGLE PREMIUM TURNS NEGATIVE AT AGE 88" in text
    assert "NOT VERIFIED" in text


# -- detection and loading -------------------------------------------------------------

class _Stub:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)


def _pi(advanced=True, status="45", line="I", trad_loans=(), loans=(), vpu=1000.0):
    base = _Stub(cov_pha_nbr=1, plancode="81335100", form_number="ISWL88", issue_date=date(1988, 10, 7),
                 issue_age=21, maturity_date=date(2062, 10, 7), units=20.61, vpu=vpu, sex_desc="Male",
                 rate_class="N")
    facts = _Stub(product_line_code=line, nsp_rpu_table="L4", nsp_extended_table="L8", nsp_interest_rate=5.5,
                  stored_low_duration=38, stored_nsp_values=(427.13, 440.77, 454.498282), rpu_benefit_code="6",
                  cease_reason_code="", mortality_function_code="2")
    coverages = _Stub(get_base_coverage=lambda: base, traditional_facts=lambda _p: facts,
                      get_coverages=lambda: [base], cov_index_for_phase=lambda _p: 1)
    rates = _Stub(guaranteed_cash_value=lambda: {"value": 8803.15, "as_of": date(2026, 10, 7), "reason": ""},
                  cov_rate_sex_code=lambda _i: "1", cov_cash_value_rates=lambda _i: {"basis": "NSP"})
    return _Stub(
        exists=True, policy_number="11663262", company_code="01",
        product=_Stub(is_advanced_product=advanced, issue_state="TX"),
        status=_Stub(premium_pay_status_code=status, premium_pay_status_description="RPU"),
        coverages=coverages, rates=rates, persons=_Stub(primary_insured_name="TEST INSURED"),
        activity=_Stub(last_anniversary=date(2026, 10, 7), paid_to_date=date(2022, 2, 7)),
        values=_Stub(valuation_date=date(2026, 10, 7), last_account_value_date=date(2022, 1, 7),
                     death_benefit=20610),
        benefits=_Stub(get_benefits=lambda: []),
        loans=_Stub(get_trad_loans=lambda: list(trad_loans), get_loans=lambda: list(loans)))


def _ul_loan(mv_date, principal, interest):
    return _Stub(principal=principal, accrued_interest=interest, interest_rate=8.0, raw_data={"MVRY_DT": mv_date})


def test_detection_needs_an_advanced_iswl_base_on_status_45():
    assert is_iswl_rpu(_pi())
    assert not is_iswl_rpu(_pi(status="22"))
    assert not is_iswl_rpu(_pi(line="0"))
    assert not is_iswl_rpu(_pi(advanced=False))


def test_loader_reads_the_basis_and_treats_pre_conversion_ul_loans_as_history():
    pi = _pi(loans=[_ul_loan("2022-01-07", 2248.56, 45.35), _ul_loan("2021-12-07", 2241.46, 29.97)])
    policy = build_iswl_rpu_policy(pi)
    assert policy.run_block == "" and policy.loan_balance == 0.0
    assert (policy.nsp_interest, policy.low_duration, policy.polview_cash_value) == (0.055, 38, 8803.15)
    assert any("predate the RPU conversion (balance $2,293.91 at 01/07/2022)" in n for n in policy.notes)
    assert ISWLRPUBasis(policy).run().months[0].cash_value == 8803.15


def test_loader_refuses_a_current_loan_naming_its_balance():
    trad = _Stub(principal=1000.0, accrued_interest=25.5, interest_rate=8.0, mv_date=date(9999, 12, 31))
    policy = build_iswl_rpu_policy(_pi(trad_loans=[trad]))
    assert "A policy loan of $1,025.50" in policy.run_block
    assert policy.current_loans == (ISWLRPULoan("LH_CSH_VAL_LOAN", date(9999, 12, 31), 1000.0, 25.5, 0.08, True),)
    current_ul = build_iswl_rpu_policy(_pi(loans=[
        _ul_loan("9999-12-31", 9703.20, 0.0), _ul_loan("2026-05-12", 8984.44, 0.0),    # 11051396's pattern
        _ul_loan("2021-12-07", 2241.46, 29.97)]))
    assert "A policy loan of $9,703.20 (principal $9,703.20" in current_ul.run_block
    assert [loan.principal for loan in current_ul.current_loans] == [9703.20]
    assert "value per unit is 949.11" in build_iswl_rpu_policy(_pi(vpu=949.11)).run_block


# -- the workspace -------------------------------------------------------------------------

def test_workspace_runs_and_shows_values_workup_report_and_checks(qtbot, tmp_path, monkeypatch):
    from suiteview.illustration.ui import report_pages
    from suiteview.illustration.ui.iswl_rpu_workspace import ISWLRPUInputError, ISWLRPUWorkspace

    monkeypatch.setattr(report_pages, "report_settings_file", lambda: tmp_path / "settings.json")
    workspace = ISWLRPUWorkspace()
    qtbot.addWidget(workspace)
    workspace.load(ISWLRPUBasis(make_policy()))
    assert workspace.checks_view.summary.text().startswith("In-force check: 4 match, 0 differ")
    assert workspace.policy_view.info.get_value("stored") == "427.13 / 440.77 / 454.498282"
    workspace.inputs_tab.end_age.setValue(80)
    result = workspace.run()
    assert result.years[-1].age == 80
    assert workspace.tabs.currentWidget() is workspace.report_view and workspace.report_view.pages
    assert len(workspace.values_tab.month_frame()) == len(result.months)
    assert len(workspace.values_tab.schedule_frame()) == len(result.schedule)
    workup = workspace.values_tab.workup_page
    assert workup.workup is not None and workup.workup.duration == 39
    workup.combo.setCurrentIndex(2)
    assert workup.workup.duration == 41 and len(workup.frame()) > 10
    path = tmp_path / "iswl_rpu.pdf"
    workspace.report_view.write_pdf(str(path))
    assert path.read_bytes().startswith(b"%PDF")

    workspace.load(ISWLRPUBasis(make_policy(run_block="A policy loan of $1,025.50 is on the record.")))
    assert "Run Values is refused" in workspace.policy_view.check_notice.text()
    with pytest.raises(ISWLRPUInputError, match="loan of"):
        workspace.run()
