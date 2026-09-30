"""Indeterminate premium term (IPT) in RERUN: premium periods, modal premiums, the
projection against CyberLife's illustration, the in-force checks, the report and the
workspace.

Fixture values are CyberLife's own, read from live records by
``tools/rerun/verify_term_inforce.py``:

* D0194819 (company 01, B15TG100 "ART12", male nicotine, issue age 62 on 01/18/2017,
  100 units, monthly direct bill 202.00, paid to 10/18/2026): PREM C/G from schema
  ``rates`` - 23.36 for the ten level years, then 130.63 / 139.92 at duration 11 ...
  843.06 at 33. CyberLife's illustration (TERM - D0194819.pdf) shows the current
  premiums 13,152 ... 79,512; the illustration team's review (8/27/2026) corrected the
  guaranteed column: the level-period guaranteed premium is the current premium, and
  year 11 is 14,076 at the monthly mode (CyberLife printed 14,052 at the annual mode).
* B15TD300 mode rule (E0000485: 500 x 0.67 + 60 at PAC monthly 0.0864 = 34.13 billed).
"""
from __future__ import annotations

import re
from datetime import date

import pytest

from suiteview.illustration.core.fixed_premium import ModeFactors
from suiteview.illustration.core.ledger_report import format_ledger_pages
from suiteview.illustration.core.term.engine import TermEngine, TermProjectionError
from suiteview.illustration.core.term.inforce_checks import inforce_checks
from suiteview.illustration.core.term.policy_loader import is_indeterminate_term
from suiteview.illustration.core.term.rates import PremiumSchedule, TermRates
from suiteview.illustration.core.term.report import TITLE, build_term_report
from suiteview.illustration.core.term.service import TermBasis
from suiteview.illustration.models.term import (
    ROLE_BASE,
    ROLE_RIDER,
    TermBenefit,
    TermCoverage,
    TermExtra,
    TermInputs,
    TermPolicy,
)

CURRENT = (23.36,) * 10 + (
    130.63, 143.92, 158.55, 174.96, 193.35, 213.36, 234.45, 257.67, 283.05, 310.02, 337.77, 367.35, 400.80,
    438.72, 479.85, 523.56, 569.13, 615.99, 661.26, 704.34, 748.56, 794.28, 843.06)
GUARANTEED = (23.36,) * 10 + (139.92, 151.83, 164.73, 179.07, 194.97) + CURRENT[15:]
# CyberLife's non-guaranteed contract premiums, years 11-32 (its year 33 repeats year 32).
CYBERLIFE_CURRENT = (13152, 14472, 15936, 17580, 19416, 21420, 23532, 25848, 28392, 31080, 33864, 36816, 40164,
                     43956, 48072, 52440, 57000, 61680, 66204, 70512, 74940, 79512)
DIR = (ModeFactors("DIR", "A", 1.0, 1.0, 60.0, "4", "2", "3"), ModeFactors("DIR", "S", 0.5, 0.5, 60.0, "4", "2", "3"),
       ModeFactors("DIR", "Q", 0.25, 0.25, 60.0, "4", "2", "3"),
       ModeFactors("DIR", "M", 0.08333, 0.11667, 60.0, "4", "2", "3"))


def base_coverage(**changes) -> TermCoverage:
    values = dict(
        phase=1, plancode="B15TG100", role=ROLE_BASE, form_number="ART12", description="10 YR FREEDOM TERM ENDORSED",
        product_line="N", issue_date=date(2017, 1, 18), issue_age=62, rate_sex="M", sex_description="Male",
        rate_class="S", band_code="0", units=100.0, value_per_unit=1000.0, annual_premium_per_unit=23.36,
        pay_up_date=date(2027, 1, 18), maturity_date=date(2050, 1, 18), renewable_code="E",
        initial_renewal_period=10, renewal_start_duration=10, renewal_period=1, next_renewal_rate=130.63,
        next_change_date=date(2027, 1, 18))
    values.update(changes)
    return TermCoverage(**values)


def make_policy(**changes) -> TermPolicy:
    values = dict(
        policy_number="D0194819", company_code="01", region="CKPR", insured_name="Kevin Grieve", issue_state="OH",
        issue_date=date(2017, 1, 18), valuation_date=date(2026, 9, 18), last_anniversary=date(2026, 1, 18),
        paid_to_date=date(2026, 10, 18), billing_frequency=1, bill_form="0", modal_premium=202.00,
        forced_premium=False, premium_status="22", premium_status_description="Premium Paying", indeterminate=True,
        coverages=(base_coverage(),),
        benefits=(TermBenefit(1, "#1", "#", "ACCELERATED BENEFIT RIDER FOR TERMINAL ILLNESS", "ABR11-TM", 100.0,
                              1000.0, 0.0, 1.0, date(2017, 1, 18), 62, date(2050, 1, 18)),),
    )
    values.update(changes)
    return TermPolicy(**values)


def make_rates(factors=DIR, benefits=None) -> TermRates:
    schedule = PremiumSchedule("B15TG100 PREM M/S/0", (None,) + CURRENT, (None,) + GUARANTEED)
    return TermRates({1: schedule}, benefits=benefits or {}, mode_factors=factors)


# -- premium periods and modal premiums ------------------------------------------------

@pytest.mark.parametrize("level, start, every, year, expected", [
    (10, 10, 1, 5, 1), (10, 10, 1, 10, 1), (10, 10, 1, 11, 11), (10, 10, 1, 12, 12),   # D0194819
    (20, 20, 1, 21, 21), (1, 1, 1, 5, 5),                                                # B15TD300, B75TL500
    (5, 10, 1, 7, 6), (5, 10, 1, 11, 11),                                                # CyberDoc D10 example 3
    (10, 10, 0, 15, 11), (0, 0, 0, 30, 1),                                               # non-renewable, level
])
def test_premium_period_start_year(level, start, every, year, expected):
    coverage = base_coverage(initial_renewal_period=level, renewal_start_duration=start, renewal_period=every)
    assert TermEngine.period_start_year(coverage, year) == expected


def test_modal_premium_reproduces_the_billed_premium():
    engine = TermEngine(make_policy(), make_rates())
    assert engine.modal_premium(date(2026, 10, 18)) == (202.00, 202.00)      # 100 x 1.95 + 7.00
    assert engine.modal_premium(date(2027, 1, 18)) == (1096.00, 1173.00)     # year 11: 100 x 10.89 / 11.66 + 7
    assert [c.status for c in inforce_checks(make_policy(), make_rates())] == ["match"] * 3


def test_fee_modalized_at_the_premium_factor_rounds_once():
    pac = (ModeFactors("PAC", "M", 0.0864, 0.0864, 60.0, "4", "1", "3"),)
    policy = make_policy(coverages=(base_coverage(plancode="B15TD300", units=500.0, annual_premium_per_unit=0.67,
                                                  initial_renewal_period=20, renewal_start_duration=20,
                                                  next_renewal_rate=1.97),),
                         bill_form="G", modal_premium=34.13, benefits=())
    parts = TermEngine(policy, make_rates(pac)).premium_parts(date(2026, 10, 18))
    assert [p.kind for p in parts] == ["coverage", "fee", "rounding"]
    assert round(sum(p.current for p in parts), 2) == 34.13                  # E0000485, not 28.94 + 5.18


# -- projection against CyberLife's illustration -----------------------------------

def test_projection_reproduces_cyberlife_current_and_corrects_the_guaranteed_premiums():
    result = TermEngine(make_policy(), make_rates()).run()
    years = {y.policy_year: y for y in result.years}
    # the first year holds only the premiums still due (10/18, 11/18, 12/18)
    assert (years[10].current_premium, years[10].guaranteed_premium) == (606.00, 606.00)
    for offset, cyberlife in enumerate(CYBERLIFE_CURRENT):
        assert years[11 + offset].current_premium == cyberlife
    assert years[11].guaranteed_premium == 14076.00                          # CyberLife printed 14,052 (annual)
    assert years[16].guaranteed_premium == years[16].current_premium        # the scales meet at duration 16
    assert years[33].current_premium == 84384.00                             # CyberLife repeated 79,512
    assert result.years[-1].age == 95 and all(y.death_benefit == 100000.0 for y in result.years)
    assert years[10].period == "level" and years[11].period == "ART"


def test_billed_premium_is_the_premium_due_at_the_paid_to_date():
    # 15044388 shape: annual, paid to the anniversary the next period starts on
    coverage = base_coverage(plancode="B15TD500", units=250.0, annual_premium_per_unit=23.36,
                             initial_renewal_period=1, renewal_start_duration=1, renewal_period=1,
                             next_renewal_rate=130.63)
    policy = make_policy(coverages=(coverage,), billing_frequency=12, paid_to_date=date(2027, 1, 18),
                         modal_premium=round(250 * 130.63 + 60, 2))
    engine = TermEngine(policy, make_rates())
    assert engine.record_premium_date() == date(2027, 1, 18)
    assert engine.premium_adjustment == 0.0
    assert inforce_checks(policy, make_rates())[-1].status == "match"


def test_a_renewal_not_yet_billed_is_checked_at_the_stored_rate():
    # E0096685 shape: paid to the renewal anniversary, still billed at the stored rate
    coverage = base_coverage(units=250.0, initial_renewal_period=1, renewal_start_duration=1, renewal_period=1)
    policy = make_policy(coverages=(coverage,), billing_frequency=12, paid_to_date=date(2027, 1, 18),
                         modal_premium=round(250 * 23.36 + 60, 2), benefits=())
    engine = TermEngine(policy, make_rates())
    parts, basis = engine.billed_parts()
    assert "stored rates" in basis and engine.premium_adjustment == 0.0
    check = inforce_checks(policy, make_rates())[-1]
    assert check.status == "match" and "renewal is not billed yet" in check.detail
    # the projection still charges the renewal rate from the anniversary
    year = {y.policy_year: y for y in engine.run().years}[11]
    assert year.current_premium == round(250 * 130.63 + 60, 2)


def test_premiums_in_arrears_are_skipped_and_the_stored_rate_is_the_last_anniversarys():
    # NLP00116 shape: the renewal anniversary passed unpaid; the record still stores the old rate
    policy = make_policy(paid_to_date=date(2026, 8, 18), valuation_date=date(2027, 2, 18),
                         last_anniversary=date(2026, 1, 18))
    engine = TermEngine(policy, make_rates())
    assert engine.record_year(policy.base) == 10
    result = engine.run()
    assert result.months[0].when == date(2027, 2, 18) and result.months[0].premium_due
    assert any("in arrears" in note for note in result.notes)


def test_table_extra_is_rerated_with_the_coverage_rate():
    coverage = base_coverage(table_rating=4, extras=(TermExtra("1", 23.36, 2.0, "D", None),))
    engine = TermEngine(make_policy(coverages=(coverage,), modal_premium=397.00), make_rates())
    level = [p for p in engine.premium_parts(date(2026, 10, 18)) if p.kind == "extra"][0]
    renewal = [p for p in engine.premium_parts(date(2027, 1, 18)) if p.kind == "extra"][0]
    assert level.rate == 23.36 and renewal.rate == 130.63                    # rate x (2.00 - 1)


def test_benefit_without_a_guaranteed_scale_uses_its_current_rates():
    waiver = TermBenefit(1, "30", "3", "PREMIUM WAIVER", "LPW84", 100.0, 1000.0, 0.17, 1.0, date(2017, 1, 18), 62,
                         date(2040, 1, 18), renews=True)
    schedule = PremiumSchedule("B15TG100 benefit 30 PREM", (None,) + (0.17,) * 10 + (0.91,) * 20, (None,))
    engine = TermEngine(make_policy(benefits=(waiver,), modal_premium=203.42), make_rates(benefits={(1, "30"): schedule}))
    part = [p for p in engine.premium_parts(date(2027, 1, 18)) if p.kind == "benefit"][0]
    assert part.current == part.guaranteed == round(100 * round(0.91 * 0.08333, 2), 2)
    assert any("only a current premium scale" in note for note in engine.notes)


def test_a_benefit_that_does_not_renew_keeps_its_stored_rate():
    # FF902782: ADB 0.77 (RNL_RT_IND 0) is level to its cease date though its schedule ends earlier
    adb = TermBenefit(1, "13", "1", "ACCIDENTAL DEATH BENEFIT", "ADBR", 100.0, 1000.0, 0.77, 1.0, date(2017, 1, 18), 62,
                      date(2045, 1, 18), renews=False)
    schedule = PremiumSchedule("B15TG100 benefit 13 PREM", (None,) + (0.77,) * 5, (None,))
    engine = TermEngine(make_policy(benefits=(adb,), modal_premium=202.64),
                        make_rates(benefits={(1, "13"): schedule}))
    part = [p for p in engine.premium_parts(date(2040, 1, 18)) if p.kind == "benefit"][0]
    assert part.rate == 0.77


def test_mode_factors_missing_from_schema_are_borrowed_only_when_they_reproduce_the_bill():
    # B15TI300 "SIGTERM" has no RATE_MODEFACT rows; the family's sets are tried against the bill
    table_355 = DIR
    table_352 = (ModeFactors("DIR", "M", 0.093, 0.093, 60.0, "4", "1", "3"),)
    candidates = (("B15TD100 (shared by 28 B15T plans)", table_352), ("B15TG100 (shared by 5 B15T plans)", table_355))
    rates = TermRates({1: make_rates().coverages[1]}, mode_factor_candidates=candidates)
    billed_352 = round((100 * 23.36 + 60) * 0.093, 2)
    engine = TermEngine(make_policy(modal_premium=billed_352), rates)
    assert engine.mode_factors_source.startswith("B15TD100") and engine.premium_adjustment == 0.0
    assert any("reproduce the billed premium" in note for note in engine.notes)
    assert TermEngine(make_policy(), rates).mode_factors_source.startswith("B15TG100")      # 202.00: table 355
    refused = make_policy(modal_premium=999.99)
    with pytest.raises(TermProjectionError, match="none of the B15T plans' factors reproduce"):
        TermEngine(refused, rates).run()
    checks = inforce_checks(refused, rates)                   # the other checks still run
    assert checks[-1].status == "differs" and "cannot be illustrated" in checks[-1].detail
    assert checks[0].status == "match"


def test_borrowed_mode_factor_candidates_try_the_bill_form_then_the_other():
    from decimal import Decimal

    from suiteview.core.rates_schema import ModeFactor
    from suiteview.illustration.core.term.rates import _shared_mode_factors

    def row(form, factor):
        return ModeFactor("", form, Decimal("0"), Decimal("0"), "M", Decimal(factor), Decimal(factor), Decimal("60"),
                          "4", "3", Decimal("0"), "0", "1", "1", "1")

    class _Plan:
        def __init__(self, plancode):
            self.plancode, self.company = plancode, "00"

    class _Reader:
        def modal_factor_plancodes(self, company, prefix):
            return ["B15TD100", "B15TD300"]

        def plan_defs(self, plancode):
            return [_Plan(plancode)]

        def modal_factors(self, company, plancode):
            return [row("DIR", "0.093"), row("PAC", "0.0864")]

    candidates = _shared_mode_factors(_Reader(), _Plan("B15TI300"), make_policy(bill_form="0"))
    assert [c[1][0].prem_factor for c in candidates] == [0.093, 0.0864]     # direct first, then PAC
    assert "PAC factors" in candidates[1][0] and "shared by 2 B15T plans" in candidates[0][0]


def test_inputs_change_the_mode_and_drop_riders():
    rider = base_coverage(phase=2, plancode="B1582000", role=ROLE_RIDER, form_number="CTR12M", units=10.0,
                          annual_premium_per_unit=7.5, initial_renewal_period=0, renewal_start_duration=0,
                          renewal_period=0, next_renewal_rate=None, maturity_date=date(2030, 1, 18))
    policy = make_policy(coverages=(base_coverage(), rider), modal_premium=208.00)
    kept = TermEngine(policy, make_rates()).run()
    assert kept.years[0].rider_death_benefit == 10000.0
    dropped = TermEngine(policy, make_rates(), TermInputs(drop_riders=[2])).run()
    assert dropped.years[0].rider_death_benefit == 0.0
    annual = TermEngine(make_policy(), make_rates(), TermInputs(billing_frequency=12)).run()
    assert {y.policy_year: y.guaranteed_premium for y in annual.years}[11] == 14052.00   # CyberLife's annual figure


# -- report and workspace -----------------------------------------------------------

def test_report_pages_follow_cyberlifes_term_illustration():
    result = TermEngine(make_policy(), make_rates()).run()
    report = build_term_report(result, date(2026, 9, 30))
    pages = format_ledger_pages(report)
    assert all(len(line) <= report.width for page in pages for line in page)
    assert pages[0][1].strip() == TITLE and "Page 1 of 3" in pages[0][0]
    cover = "\n".join(pages[0])
    assert "PLAN:  10 YR FREEDOM TERM ENDORSED (B15TG100)" in cover and "FORM:  ART12" in cover
    assert "PREMIUM CLASS:  STANDARD" in cover
    assert "PREMIUMS ARE LEVEL FOR THE FIRST 10 YEARS (TO 01/18/2027), THEN RENEW ANNUALLY" in cover
    ledger = "\n".join(pages[1])
    assert "GUARANTEED VALUES" in ledger and "NON-GUAR" in ledger
    rows = [line for line in pages[1] if re.match(r"^\s*\d{2}\s+\d{1,2}\s+[\d,]+\.\d\d", line)]
    assert len(rows) == len(result.years)
    assert rows[1].split()[:4] == ["73", "11", "13,152.00", "14,076.00"]
    assert "ACCELERATED BENEFIT RIDER FOR TERMINAL ILLNESS" in "\n".join(pages[-1])


def test_indeterminate_term_detection():
    class _Stub:
        def __init__(self, **attrs):
            self.__dict__.update(attrs)

    def pi(indicator="1", line="N", advanced=False):
        facts = _Stub(product_line_code=line)
        coverages = _Stub(get_base_coverage=lambda: _Stub(cov_pha_nbr=1), traditional_facts=lambda _p: facts)
        return _Stub(product=_Stub(is_advanced_product=advanced), coverages=coverages,
                     field_value=lambda name: indicator)

    assert is_indeterminate_term(pi())
    assert not is_indeterminate_term(pi(indicator="0"))
    assert not is_indeterminate_term(pi(line="0"))          # par whole life
    assert not is_indeterminate_term(pi(advanced=True))


def test_workspace_runs_and_shows_the_pages_values_and_checks(qtbot, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QPushButton

    from suiteview.illustration.ui import report_pages
    from suiteview.illustration.ui.term_workspace import COVERAGE_COLUMNS, TermWorkspace

    monkeypatch.setattr(report_pages, "report_settings_file", lambda: tmp_path / "settings.json")
    workspace = TermWorkspace()
    qtbot.addWidget(workspace)
    workspace.load(TermBasis(make_policy(), make_rates()))
    assert workspace.checks_view.summary.text().startswith("In-force check: 3 match, 0 differ")
    table = workspace.policy_view.coverages.table
    assert table.item(0, COVERAGE_COLUMNS.index("Level To")).text() == "01/18/2027"
    assert [b.text() for b in workspace.policy_view.benefit_group.findChildren(QPushButton)] == ["ABR11-TM"]
    workspace.inputs_tab.mode_combo.setCurrentIndex(1)                      # annual
    result = workspace.run()
    assert result.inputs.billing_frequency == 12
    assert workspace.tabs.currentWidget() is workspace.report_view and workspace.report_view.pages
    premiums = workspace.values_tab.premium_frame()
    assert len(premiums) == sum(1 for m in result.months if m.premium_due)
    assert len(workspace.values_tab.detail_frame()) >= len(premiums)
    path = tmp_path / "term.pdf"
    workspace.report_view.write_pdf(str(path))
    assert path.read_bytes().startswith(b"%PDF")
