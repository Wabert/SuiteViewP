"""Participating whole life (par WL) in RERUN: rates arithmetic, the monthly engine,
the in-force checks and the par WL workspace.

Fixture values are CyberLife's own, read from live records by
``tools/rerun/verify_parwl_inforce.py``:

* 000282131 (company 26, NB1XSL00 age 49, 100 units, option 4, PUA rider NB1PU300,
  advance loan at 7.4%): the 02/13/2026 dividend was 100 x 24.22 on the coverage and
  38.038 x 15.60 on its additions (38,037.86 held going in); the rider paid 7.881 x
  10.11 and 0.853 x 10.11, the 0.853 including the 117.82 its premium additions bought
  that day. The additions became 42,409.06 and 8,746.92, and the loan
  58,771.65 / (1 - 0.074) = 63,468.30 with 4,696.65 of advance interest.
* Modal premiums 14739485 (11.43), 12864500 (49.10) and E0112582 (90.41); RPU NSPs of
  10150100 (722.75) and B111A100 14766291 (180.42).
"""
from __future__ import annotations

import re
from datetime import date

import pytest

from suiteview.illustration.core.fixed_premium import BILL_FORM_FAMILY, ModeFactors
from suiteview.illustration.core.parwl.engine import ParWLEngine, ParWLProjectionError
from suiteview.illustration.core.parwl.inforce_checks import cash_value_checks, inforce_checks
from suiteview.illustration.core.parwl.nsp import net_single_premium
from suiteview.illustration.core.parwl.policy_loader import is_par_whole_life
from suiteview.illustration.core.parwl.premiums import modal_premium, record_premium_date
from suiteview.illustration.core.ledger_report import format_ledger_pages
from suiteview.illustration.core.parwl.report import TITLE, build_parwl_report
from suiteview.illustration.core.parwl.rates import (
    CoverageDividendRates,
    CoverageRates,
    DividendScale,
    ParWLRates,
    ratio4,
)
from suiteview.illustration.core.parwl.service import ParWLBasis
from suiteview.illustration.models.parwl import (
    ROLE_BASE,
    ROLE_PUA_RIDER,
    ROLE_TERM_RIDER,
    DatedAmount,
    OptionChange,
    ParWLAdditions,
    ParWLBenefit,
    ParWLCoverage,
    ParWLDividendValue,
    ParWLInputs,
    ParWLLoan,
    ParWLPolicy,
)
from suiteview.polview.models.policy_sections.dividends import decode_month_year

ISSUE = date(2002, 2, 13)
LAST = date(2026, 2, 13)
NEXT = date(2027, 2, 13)


# -- fixture: 000282131 -------------------------------------------------------------

def _base_cv(duration: int) -> float:
    known = {23: 481.95, 24: 504.07, 25: 525.67, 26: 546.64}
    return known.get(duration, round(min(1000.0, 20.0 * duration + 20.0), 2))


def _base_dividends() -> dict:
    values = {d: (round(0.5 + d * 0.9, 2), round(1.5 + d * 1.4, 2), 500.0) for d in range(1, 51)}
    values[24] = (24.22, 35.11, 530.91)
    values[25] = (25.34, 36.03, 520.0)
    return values


def _pua_key() -> dict:
    values = {age: (round(age * 0.21, 2), 100.0) for age in range(49, 101)}
    values[73] = (15.60, 100.0)
    return values


def _rider_dividends() -> dict:
    values = {d: (round(0.4 * d, 2), round(0.6 * d, 2), 0.0) for d in range(1, 51)}
    values[24] = (10.11, 14.95, 0.0)
    return values


def _coverages(**changes):
    base = dict(
        phase=1, plancode="NB1XSL00", role=ROLE_BASE, product_line="0", issue_date=ISSUE, issue_age=49,
        rate_sex="M", rate_class="H", band_code="C", subseries="MH", units=100.0, value_per_unit=1000.0,
        annual_premium_per_unit=25.76, pay_up_date=date(2053, 2, 13), maturity_date=date(2053, 2, 13),
        nsp_table="N0", nsp_interest=0.04, dividend_key="1XSLMH",
        stored_low_duration=23, stored_cash_values=(481.95, 504.07, 525.67, 546.64))
    base.update(changes)
    rider = ParWLCoverage(
        phase=2, plancode="NB1PU300", role=ROLE_PUA_RIDER, product_line="C", issue_date=ISSUE, issue_age=49,
        rate_sex="M", rate_class="H", band_code="0", subseries="MH", units=0.0, value_per_unit=1000.0,
        annual_premium_per_unit=1.0, pay_up_date=date(2053, 2, 13), maturity_date=date(2053, 2, 13),
        nsp_table="N0", nsp_interest=0.045, dividend_key="1PU3MH", payments_ceased=True)
    return (ParWLCoverage(**base), rider)


def _unapplied():
    rows = [
        (2, "1", 0.853, 10.11, 14.95, 0.0), (2, "0", 7.881, 10.11, 14.95, 0.0),
        (1, "1", 38.038, 15.60, 22.6142, 341.9568), (1, "0", 100.0, 24.22, 35.11, 530.91),
    ]
    return tuple(ParWLDividendValue(phase, LAST, source, False, "", cash, pua, oyt, units, deposit_rate=0.035)
                 for phase, source, units, cash, pua, oyt in rows)


def make_policy(**changes) -> ParWLPolicy:
    values = dict(
        policy_number="000282131", company_code="26", region="CKPR", insured_name="Test Insured",
        issue_state="MA", issue_date=ISSUE, valuation_date=date(2026, 9, 13), last_anniversary=LAST,
        paid_to_date=date(2026, 10, 13), billing_frequency=1, bill_form="G", modal_premium=219.00,
        forced_premium=True, premium_status="22", premium_status_description="Premium Paying",
        dividend_option="4", secondary_dividend_option="3", nfo_option="1", loan_type_code="0", loan_rate=0.074,
        reinsurance_key="", coverages=_coverages(),
        additions=(ParWLAdditions(2, "1", 7880.95, "N0", 0.045), ParWLAdditions(2, "0", 865.97, "N0", 0.045),
                   ParWLAdditions(1, "0", 42409.06, "N0", 0.04)),
        additions_before_anniversary=(ParWLAdditions(2, "0", 735.40, "N0", 0.045),
                                      ParWLAdditions(1, "0", 38037.86, "N0", 0.04)),
        deposit_rate=0.035,
        loans=(ParWLLoan(63468.30, 4696.65, 0.074, True, True, NEXT, last_activity=LAST),),
        unapplied_dividends=_unapplied(),
    )
    values.update(changes)
    return ParWLPolicy(**values)


def make_rates(mode_factors=None) -> ParWLRates:
    base_scale = DividendScale(date(2022, 1, 1), None, _base_dividends(), "2",
                               ((date(2022, 1, 1), None, _pua_key()),))
    rpu_scale = DividendScale(date(2022, 1, 1), None, {d: (round(0.3 * d, 2), round(0.8 * d, 2), 0.0)
                                                       for d in range(1, 51)}, "1")
    rider_scale = DividendScale(date(2022, 1, 1), None, _rider_dividends(), "1")
    base = CoverageRates(1, "NB1XSL00", "00", "", cash_values=tuple(_base_cv(d) for d in range(0, 52)),
                         dividends=CoverageDividendRates("NB1XSL00", "1XSLMH ''",
                                                         {"D": [base_scale], "R": [rpu_scale]}))
    rider = CoverageRates(2, "NB1PU300", "00", "", pui={age: 700.0 + age for age in range(0, 101)},
                          dividends=CoverageDividendRates("NB1PU300", "1PU3MH ''", {"D": [rider_scale]}))
    factors = mode_factors if mode_factors is not None else (
        ModeFactors("*", "M", 0.085, 0.085, 0.0, "0"), ModeFactors("*", "A", 1.0, 1.0, 0.0, "0"))
    return ParWLRates({1: base, 2: rider}, loan_rate=0.074, mode_factors=factors)


# -- CyberLife arithmetic --------------------------------------------------------------

@pytest.mark.parametrize("number, expected", [
    (1514, (2026, 2)), (1505, (2025, 5)), (1500, (2024, 12)), (1838, (2053, 2)), (None, (None, None)),
])
def test_month_year_numbers_count_months_from_1900(number, expected):
    assert decode_month_year(number) == expected


@pytest.mark.parametrize("pua_div, base, base_div, expected", [
    (15.60, 35.11, 24.22, 22.6142),     # 000282131
    (15.60, 530.91, 24.22, 341.9568),   # OYT truncates (exact 341.95689)
    (4.54, 5.09, 2.37, 9.7504),         # 15906121 (rounding would give 9.7505)
    (0.33, 1.12, 0.06, 6.1599),         # E0104291: divide, keep 7 decimals, multiply
    (1.04, 5.76, 1.04, 5.76),           # additions on the base rate keep its value
])
def test_additions_per_unit_ratio_matches_cyberlife(pua_div, base, base_div, expected):
    assert ratio4(pua_div, base, base_div) == expected


def test_net_single_premiums_reproduce_cyberlife():
    assert round(net_single_premium("N0", 0.04, 74), 3) == 703.261         # workbook NSP 703.263
    assert round(net_single_premium("O", 0.03, 68), 2) == 722.75           # 10150100 RPU LOW_DUR_NSP
    assert round(net_single_premium("LP", 0.04, 30), 2) == 180.42          # ALB: immediate claims
    assert round(net_single_premium("LQ", 0.04, 45), 3) == 267.296        # workbook B111A100 F N


def test_modal_premium_multiply_orders_benefits_and_extras():
    policy = make_policy()
    base = policy.base

    def premium(cov_changes, factors, benefits=()):
        p = make_policy(coverages=(ParWLCoverage(**{**vars(base), **cov_changes}),), benefits=benefits,
                        additions=(), loans=())
        return modal_premium(p, ParWLRates({}, mode_factors=factors), date(2026, 10, 13))

    pac = (ModeFactors("PAC", "M", 0.0864, 0.0864, 60.0, "4", "1"),)
    benefits = (ParWLBenefit(1, "30", "", 10.0, 1000.0, 0.27, 1.0, None, None, date(2057, 4, 3)),
                ParWLBenefit(1, "70", "", 10.0, 1000.0, 0.71, 1.0, None, None, date(2037, 4, 3)))
    assert premium({"units": 10.0, "annual_premium_per_unit": 6.25}, pac, benefits).total == 11.43   # 14739485
    extras = premium({"units": 20.0, "annual_premium_per_unit": 40.01,
                      "extra_premiums": ((9.31, date(2080, 2, 1)),)}, pac)
    assert (extras.base, extras.extra, extras.total) == (69.14, 16.09, 90.41)                         # E0112582
    per_unit = (ModeFactors("PAC", "M", 0.0864, 0.1, 35.0, "4", "2"),)
    assert premium({"units": 60.0, "annual_premium_per_unit": 8.83}, per_unit).total == 49.10          # 12864500
    # bill form F bills at the PAC factors (13662970: 14.691 x 0.47 + 3.50)
    assert BILL_FORM_FAMILY["F"] == "PAC"
    assert premium({"units": 14.691, "annual_premium_per_unit": 5.46}, per_unit).total == 10.40


def test_fee_rule_z_adds_the_fee_to_the_annual_premium_before_one_rounding():
    base = make_policy().base

    def premium(coverages, factors, frequency=1):
        p = make_policy(coverages=coverages, additions=(), loans=(), billing_frequency=frequency)
        return modal_premium(p, ParWLRates({}, mode_factors=factors), date(2026, 10, 13))

    pac_z = (ModeFactors("PAC", "M", 0.0864, 0.0864, 60.0, "4", "1", "Z"),)
    one = premium((ParWLCoverage(**{**vars(base), "units": 10.0, "annual_premium_per_unit": 47.18}),), pac_z)
    assert (one.base, one.fee, one.rounding, one.total) == (40.76, 5.18, 0.01, 45.95)                 # E0022097
    rider = ParWLCoverage(**{**vars(base), "phase": 2, "plancode": "B75RN400", "role": ROLE_TERM_RIDER,
                             "units": 100.0, "annual_premium_per_unit": 4.95})
    dir_z = (ModeFactors("DIR", "S", 0.515, 0.515, 60.0, "4", "1", "Z"),)
    two = premium((ParWLCoverage(**{**vars(base), "units": 100.0, "annual_premium_per_unit": 16.95}), rider), dir_z,
                  frequency=6)
    assert (round(two.base + two.rider + two.fee, 2), two.rounding, two.total) == (1158.76, -0.01, 1158.75)  # NLS02292
    extras = premium((ParWLCoverage(**{**vars(base), "units": 20.0, "annual_premium_per_unit": 40.01,
                                       "extra_premiums": ((9.31, date(2080, 2, 1)),)}),), pac_z)
    assert extras.total == 90.41                                                                       # E0112582


def test_record_premium_is_the_one_in_effect_on_the_valuation_date():
    policy = make_policy()
    rider = ParWLCoverage(**{**vars(policy.base), "phase": 3, "plancode": "08572500", "role": ROLE_TERM_RIDER,
                             "units": 25.0, "annual_premium_per_unit": 17.48, "pay_up_date": policy.paid_to_date,
                             "maturity_date": policy.paid_to_date})
    policy = make_policy(coverages=policy.coverages + (rider,))
    rates = make_rates()
    assert record_premium_date(policy) == policy.valuation_date
    # 13302410: the term rider expiring at the paid-to date is still in the billed premium
    assert modal_premium(policy, rates, record_premium_date(policy)).rider > 0
    assert modal_premium(policy, rates, policy.paid_to_date).rider == 0


# -- engine -------------------------------------------------------------------------

def test_last_anniversary_dividend_and_additions_reproduce_cyberlife():
    engine = ParWLEngine(make_policy(), make_rates())
    assert engine.rider_units_include_purchase is True
    pieces = {(p.phase, p.source): p for p in engine.dividend_pieces(engine.state_before_last_anniversary(), LAST, 24)}
    assert (pieces[1, "0"].units, pieces[1, "0"].cash, pieces[1, "0"].pua) == (100.0, 2422.00, 3511.00)
    assert (pieces[1, "1"].units, pieces[1, "1"].cash, pieces[1, "1"].pua) == (38.038, 593.39, 860.20)
    assert (pieces[2, "0"].units, pieces[2, "0"].cash, pieces[2, "0"].pua) == (7.881, 79.68, 117.82)
    assert (pieces[2, "1"].units, pieces[2, "1"].cash) == (0.853, 8.62)
    assert round(38037.86 + pieces[1, "0"].pua + pieces[1, "1"].pua, 2) == 42409.06
    assert round(735.40 + pieces[2, "0"].pua + pieces[2, "1"].pua, 2) == 865.97


def test_rider_units_rule_follows_the_record():
    unapplied = tuple(v if (v.phase, v.source) != (2, "1") else ParWLDividendValue(
        2, LAST, "1", False, "", 10.11, 14.95, 0.0, 0.735) for v in _unapplied())
    engine = ParWLEngine(make_policy(unapplied_dividends=unapplied), make_rates())
    assert engine.rider_units_include_purchase is False


def test_pua_rider_dividends_follow_the_record_option():
    # NB1PUA00 000299710 (option 6) / NB1PU300 000284098 (option 2): rider dividends applied as option 4
    ny = [ParWLDividendValue(2, LAST, source, True, "4", 10.11, 14.95, 0.0, 0.0) for source in "01"]
    policy = make_policy(dividend_option="2", applied_dividends=tuple(ny))
    assert ParWLEngine(policy, make_rates()).rider_dividends_to_additions is True
    # 08129700 12197588 (company 01, option 3): the rider follows the policy's option
    follows = [ParWLDividendValue(2, LAST, "0", True, "3", 1.48, 3.71, 0.0, 0.0)]
    policy = make_policy(company_code="01", dividend_option="3", applied_dividends=tuple(follows))
    engine = ParWLEngine(policy, make_rates())
    assert engine.rider_dividends_to_additions is False
    row = next(m for m in engine.run().months if m.when == NEXT)
    assert row.dividend_rider > 0 and row.dividend_to_additions == 0.0


def test_paid_up_status_with_rpu_dividend_values_is_reduced_paid_up():
    # 8O1C1000 12197587: status 41 "Paid-Up (at issue)", fractional units, placed values on RPU (P record)
    rpu_rows = (ParWLDividendValue(1, LAST, "0", False, "", 0.25, 2.01, 0.0, 25.019, rpu_values=True),)
    policy = make_policy(premium_status="41", unapplied_dividends=rpu_rows, loans=(), modal_premium=0.0)
    assert policy.is_rpu
    assert not make_policy(premium_status="41").is_rpu
    assert not make_policy(unapplied_dividends=rpu_rows).is_rpu       # premium paying stays premium paying
    engine = ParWLEngine(policy, make_rates())
    assert engine.record_state().rpu
    pieces = engine.dividend_pieces(engine.state_before_last_anniversary(), LAST, 24)
    assert any(p.kind == "rider" for p in pieces)                     # kept rider additions still earn


def test_coverage_earns_no_dividend_when_premiums_are_not_paid_to_the_anniversary():
    # B111A100 14762446: status 41, paid to 12/20/2023, pay-up 2098; only the additions were paid
    policy = make_policy(premium_status="41", paid_to_date=date(2023, 2, 13), loans=())
    engine = ParWLEngine(policy, make_rates())
    kinds = {p.kind for p in engine.dividend_pieces(engine.state_before_last_anniversary(), LAST, 24)}
    assert "base" not in kinds and "additions" in kinds
    paid_up = make_policy(premium_status="41", paid_to_date=date(2023, 2, 13), loans=(),
                          coverages=(ParWLCoverage(**{**vars(policy.base), "pay_up_date": date(2023, 2, 13)}),
                                     policy.coverages[1]))
    engine = ParWLEngine(paid_up, make_rates())
    assert "base" in {p.kind for p in engine.dividend_pieces(engine.state_before_last_anniversary(), LAST, 24)}


def test_projection_starts_at_the_valuation_date_with_record_values():
    result = ParWLEngine(make_policy(), make_rates()).run()
    first = result.months[0]
    assert (first.when, first.policy_year, first.month_of_year) == (date(2026, 9, 13), 25, 7)
    # the mid-year base cash value interpolates the per-unit values and rounds them (CyberLife 62Q1)
    assert first.cv_per_unit == round((504.07 * 5 + 525.67 * 7) / 12, 2)
    assert first.base_cv == round(100 * first.cv_per_unit, 2)
    assert first.additions == round(42409.06 + 7880.95 + 865.97, 2)
    # premiums already paid to 10/13/2026 are not projected; year 25 keeps the four left
    assert result.years[0].premium == 4 * 219.00
    assert result.months[1].premium_paid == 219.00
    # the fixture's loan grows past the cash value and lapses the policy; without it, to maturity
    assert "lapses" in result.months[-1].notes
    unloaned = ParWLEngine(make_policy(loans=()), make_rates()).run()
    assert unloaned.months[-1].when == date(2053, 2, 13)
    assert unloaned.years[-1].policy_year == 51


def test_advance_loan_interest_is_charged_at_the_anniversary():
    result = ParWLEngine(make_policy(), make_rates()).run()
    anniversary = next(m for m in result.months if m.when == NEXT)
    assert anniversary.loan_principal == round(63468.30 / (1 - 0.074), 2)
    assert anniversary.loan_interest == round(63468.30 * 0.074 / 0.926, 2)
    assert anniversary.loan_payoff == 63468.30          # the new year's interest is unearned
    before = next(m for m in result.months if m.when == date(2027, 1, 13))
    assert before.loan_unearned == pytest.approx(4696.65 / 12, abs=0.02)   # one month left to earn


def test_next_dividend_uses_additions_held_going_into_the_anniversary():
    result = ParWLEngine(make_policy(), make_rates()).run()
    row = next(m for m in result.months if m.when == NEXT)
    assert row.dividend_base == round(100 * 25.34, 2)
    assert row.dividend_on_additions == round(42.409 * 0.21 * 74, 2)  # PUA key at attained age 49 + 25
    assert row.dividend_option == "4" and row.dividend_to_additions == row.dividend_total


def test_deposit_option_credits_interest_before_the_new_dividend():
    inputs = ParWLInputs(dividend_option="3")
    result = ParWLEngine(make_policy(deposits=2470.27), make_rates(), inputs).run()
    row = next(m for m in result.months if m.when == NEXT)
    assert row.deposit_interest == round(2470.27 * 0.035, 2)
    # the NY PUA rider's dividends buy additions whatever the option (000284098, 000299710)
    assert row.dividend_rider > 0 and row.dividend_to_additions == row.dividend_rider
    assert row.deposits == round(2470.27 + row.deposit_interest + row.dividend_total - row.dividend_rider, 2)


def test_premium_reduction_and_option_changes():
    inputs = ParWLInputs(dividend_option="2", option_changes=[OptionChange(date(2028, 1, 1), "1")])
    result = ParWLEngine(make_policy(), make_rates(), inputs).run()
    row = next(m for m in result.months if m.when == NEXT)
    assert row.dividend_to_premium == round(row.dividend_total - row.dividend_rider, 2) and row.premium_paid == 0.0
    later = next(m for m in result.months if m.when == date(2028, 2, 13))
    assert later.dividend_option == "1"
    assert later.dividend_cash == round(later.dividend_total - later.dividend_rider, 2)


def test_reduced_paid_up_conversion_uses_net_value_over_nsp():
    inputs = ParWLInputs(rpu_at=NEXT)
    result = ParWLEngine(make_policy(), make_rates(), inputs).run()
    row = next(m for m in result.months if m.when == NEXT)
    assert row.rpu and "Reduced paid-up" in row.notes
    after = [m for m in result.months if m.when > NEXT]
    assert all(m.premium_paid == 0 for m in after)
    assert after[0].loan_payoff == 0.0 and after[0].additions == 0.0
    later = next(m for m in result.months if m.when == date(2028, 2, 13))
    assert later.dividend_record == "R"


def test_new_loans_and_repayments():
    inputs = ParWLInputs(loans=[DatedAmount(NEXT, 1000.0)], loan_repayments=[DatedAmount(date(2028, 2, 13), 500.0)])
    result = ParWLEngine(make_policy(loans=()), make_rates(), inputs).run()
    row = next(m for m in result.months if m.when == NEXT)
    assert row.new_loan == 1000.0 and row.loan_payoff == 1000.0
    repay = next(m for m in result.months if m.when == date(2028, 2, 13))
    assert repay.loan_repayment == 500.0
    with pytest.raises(ParWLProjectionError, match="monthliversary"):
        ParWLEngine(make_policy(), make_rates(), ParWLInputs(loans=[DatedAmount(date(2027, 2, 14), 1.0)])).run()


def test_oyt_limited_to_cash_value_buys_additions_oyt_first():
    policy = make_policy(dividend_option="6", secondary_dividend_option="4")
    engine = ParWLEngine(policy, make_rates())
    result = engine.run()
    row = next(m for m in result.months if m.when == NEXT)
    limit = round(100 * _base_cv(26), 2)
    assert row.oyt_face == pytest.approx(limit, abs=0.01)
    assert 0 < row.dividend_to_oyt < row.dividend_total
    assert "secondary option 4" in row.notes
    # each anniversary's dividend buys the next year's OYT as last year's expires
    later = [m for m in result.months if m.anniversary and m.when > NEXT][:3]
    assert later and all(m.oyt_face > 0 and m.dividend_to_oyt > 0 for m in later)


def test_guaranteed_run_pays_no_dividends():
    result = ParWLEngine(make_policy(), make_rates()).run()
    assert all(m.dividend_total == 0 for m in result.guaranteed_months)
    assert result.years[0].guaranteed_cash_value < result.years[0].surrender_value


def test_eti_policies_are_refused_loudly():
    with pytest.raises(ParWLProjectionError, match="extended term"):
        ParWLEngine(make_policy(premium_status="44"), make_rates())


def test_inforce_checks_match_the_record():
    policy = make_policy()
    lines = inforce_checks(policy, make_rates())
    differs = [line for line in lines if line.status == "differs"]
    assert not differs, differs
    names = {line.item for line in lines if line.status == "match"}
    assert "NB1XSL00 CV per unit, duration 25" in names
    assert "Advance interest for the policy year" in names
    assert any(line.item == "Modal premium" and line.status == "info" for line in lines)   # forced premium


def test_negative_stored_cash_values_are_reported_not_failed():
    policy = make_policy()
    cov = ParWLCoverage(**{**vars(policy.base), "stored_low_duration": 2, "stored_cash_values": (-7.0, -3.0, 1.0, 6.0)})
    rates = ParWLRates({1: CoverageRates(1, "8X1D1500", "00", "", cash_values=(0.0, 0.0, 0.0, 0.0, 1.0, 6.0))})
    lines = cash_value_checks(make_policy(coverages=(cov,)), rates)       # 14318679
    assert [line.status for line in lines] == ["info", "info", "match", "match"]


class _Stub:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)


def test_par_whole_life_detection():
    def pi(advanced=False, participation="A", line="0"):
        facts = _Stub(dividend_participation_code=participation, product_line_code=line)
        coverages = _Stub(get_base_coverage=lambda: _Stub(cov_pha_nbr=1), traditional_facts=lambda _phase: facts)
        return _Stub(product=_Stub(is_advanced_product=advanced), coverages=coverages)

    assert is_par_whole_life(pi())
    assert not is_par_whole_life(pi(advanced=True))
    assert not is_par_whole_life(pi(participation="0"))


# -- workspace ----------------------------------------------------------------------

def test_workspace_runs_and_shows_monthly_values_and_the_annual_ledger(qtbot):
    from suiteview.illustration.ui.parwl_inputs import ParWLInputError
    from suiteview.illustration.ui.parwl_values import PAGES
    from suiteview.illustration.ui.parwl_workspace import ParWLWorkspace

    workspace = ParWLWorkspace()
    qtbot.addWidget(workspace)
    workspace.load(ParWLBasis(make_policy(), make_rates()))
    assert workspace.checks_view.summary.text().startswith("In-force check:")
    assert not workspace.inputs_tab.rider_table.isEnabled()          # the rider's payments ceased
    inputs = workspace.inputs_tab
    inputs.rpu_check.setChecked(True)
    inputs.rpu_when.setText("30")
    inputs.loan_table.item(0, 0).setText("27")
    inputs.loan_table.item(0, 1).setText("1,000")
    result = workspace.run()
    assert result.inputs.rpu_at == date(2031, 2, 13)
    assert result.inputs.loans == [DatedAmount(date(2028, 2, 13), 1000.0)]
    assert workspace.tabs.currentWidget() is workspace.report_view
    pages = workspace.report_view.pages
    assert pages and workspace.report_view._sheet_layout.count() == len(pages)
    assert workspace.report_view.print_pdf_btn.isEnabled()
    assert any("REDUCED PAID-UP INSURANCE ON 02/13/2031" in line for line in pages[0])
    for title, grid in workspace.values_tab._grids.items():
        frame = grid.model.get_original_data()
        assert len(frame) == len(result.months), title
        assert list(frame.columns)[:4] == ["Date", "Year", "Month", "Age"]
    assert set(workspace.values_tab._grids) == set(PAGES)
    workspace.values_tab.anniversaries_only.setChecked(True)
    assert len(workspace.values_tab._grids["Summary"].model.get_original_data()) < len(result.months)
    inputs.loan_table.item(1, 0).setText("x")
    inputs.loan_table.item(1, 1).setText("5")
    with pytest.raises(ParWLInputError, match="New loans row 2"):
        workspace.run()


def test_policy_page_lists_coverages_and_benefit_buttons(qtbot, monkeypatch):
    from PyQt6.QtWidgets import QPushButton

    from suiteview.illustration.ui import policy_snapshot_widgets
    from suiteview.illustration.ui.parwl_workspace import COVERAGE_COLUMNS, ParWLWorkspace

    waiver = ParWLBenefit(1, "30", "PREMIUM WAIVER", 10.0, 1000.0, 0.27, 1.0, date(2002, 2, 13), 49,
                          date(2017, 2, 13), form_number="WP-100")
    policy = make_policy(benefits=(waiver,))
    workspace = ParWLWorkspace()
    qtbot.addWidget(workspace)
    workspace.load(ParWLBasis(policy, make_rates()))
    view = workspace.policy_view
    assert not hasattr(view, "values")                                       # no "Values on Record" group
    table = view.coverages.table
    assert table.rowCount() == len(policy.coverages) and table.columnCount() == len(COVERAGE_COLUMNS)
    assert table.item(0, COVERAGE_COLUMNS.index("Plancode")).text() == "NB1XSL00"
    assert table.item(1, COVERAGE_COLUMNS.index("Type")).text() == "PUA Rider"
    buttons = view.benefit_group.findChildren(QPushButton)
    assert [b.text() for b in buttons] == ["WP-100"]
    shown = []
    monkeypatch.setattr(policy_snapshot_widgets, "show_detail_dialog",
                        lambda parent, title, rows: shown.append((title, rows)))
    buttons[0].click()
    title, rows = shown[0]
    assert title == "Benefit Detail" and ("Form:", "WP-100") in rows and ("Annual Premium:", "2.70") in rows


# -- illustration report ------------------------------------------------------------

RUN_DATE = date(2026, 9, 29)
LEDGER_ROW = re.compile(r"^\s*\d{1,3}\s+\d{1,3}\s+[\d,]+\.\d\d")


def _report_pages(policy=None, inputs=None):
    result = ParWLEngine(policy or make_policy(), make_rates(), inputs).run()
    report = build_parwl_report(result, RUN_DATE)
    return result, report, format_ledger_pages(report)


def test_report_pages_follow_the_ul_page_style():
    repay = [DatedAmount(date(2027, 2, 13), 2500.0), DatedAmount(date(2028, 2, 13), 2500.0)]
    result, report, pages = _report_pages(inputs=ParWLInputs(loan_repayments=repay))
    assert all(len(line) <= report.width for page in pages for line in page)
    for number, page in enumerate(pages, 1):
        assert page[0].startswith("09/29/2026") and page[0].endswith(f"Page {number} of {len(pages)}")
        assert "AMERICAN NATIONAL LIFE INSURANCE COMPANY OF NEW YORK" in page[0]
        assert page[1].strip() == TITLE and page[2].strip() == "PREPARED FOR TEST INSURED"
    cover = "\n".join(pages[0])
    assert "PLAN:  NB1XSL00" in cover and "MONTHLY PREMIUM:  $219.00" in cover
    assert "ANNUAL LOAN REPAYMENTS OF $2,500.00 FROM 02/13/2027 THROUGH 02/13/2028 (YEARS 26-27)" in cover
    assert "DIVIDENDS ARE ASSUMED TO PURCHASE PAID-UP ADDITIONS" in cover
    assert "DIVIDENDS ON DEPOSIT EARN" not in cover                  # option 4: no deposits
    rows = [line for page in pages[1:-1] for line in page if LEDGER_ROW.match(line)]
    assert len(rows) == len(result.years)
    first = result.years[0]
    assert rows[0].split()[:3] == [str(first.age), str(first.policy_year), f"{first.premium:,.2f}"]
    assert rows[0].endswith(f"{first.additions_base:,.0f}{first.additions_rider:>10,.0f}")
    assert all(round(y.additions_base + y.additions_rider, 2) == y.additions for y in result.years)
    ledger = "\n".join(pages[1])
    assert "GUARANTEED VALUES" in ledger and "NON-GUARANTEED VALUES" in ledger
    keys = [c.key for c in report.columns]
    assert {"loan_payments", "loan_balance", "additions_rider"} <= set(keys)
    assert not {"new_loans", "deposits", "oyt"} & set(keys)
    notes = "\n".join(pages[-1])
    assert "OTHER COVERAGE:" in notes and "PAID-UP ADDITIONS RIDER (NB1PU300) - PREMIUM PAYMENTS HAVE CEASED" in notes
    assert "DIVIDENDS ARE BASED ON THE COMPANY'S ILLUSTRATED SCALE AND ARE NOT GUARANTEED." in notes


def test_report_columns_and_statements_follow_the_policy():
    base = make_policy().base
    plain = make_policy(coverages=(base,), additions=(ParWLAdditions(1, "0", 42409.06, "N0", 0.04),),
                        additions_before_anniversary=(), loans=(), deposits=1200.0, dividend_option="3",
                        unapplied_dividends=tuple(v for v in _unapplied() if v.phase == 1))
    result, report, pages = _report_pages(plain)
    keys = [c.key for c in report.columns]
    assert "deposits" in keys and not {"loan_payments", "loan_balance", "additions_rider"} & set(keys)
    assert report.width == 112                                          # never narrower than the UL pages
    cover = "\n".join(pages[0])
    assert "DIVIDENDS ARE ASSUMED TO BE LEFT ON DEPOSIT AT 3.50% INTEREST" in cover
    assert "DIVIDENDS ON DEPOSIT:  $1,200.00" in cover
    _result, guaranteed, _pages = _report_pages(plain, ParWLInputs(dividends=False))
    assert guaranteed.subtitle == "GUARANTEED VALUES ONLY - NO DIVIDENDS ILLUSTRATED"


def test_report_prints_a_landscape_pdf(qtbot, tmp_path, monkeypatch):
    from suiteview.illustration.ui import report_pages
    from suiteview.illustration.ui.illustration_pages_view import IllustrationPagesView
    from suiteview.illustration.ui.parwl_workspace import ledger_frame, parwl_report_pages
    from suiteview.illustration.ui.report_pages import fitting_font_pt

    monkeypatch.setattr(report_pages, "report_settings_file", lambda: tmp_path / "settings.json")
    view = IllustrationPagesView(parwl_report_pages, ledger_frame, "Par WL Ledger")
    qtbot.addWidget(view)
    assert not view.print_pdf_btn.isEnabled()
    view.set_result(ParWLEngine(make_policy(), make_rates()).run(), RUN_DATE)
    path = tmp_path / "parwl.pdf"
    view.write_pdf(str(path))
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page\b", data)) == len(view.pages)
    assert re.findall(rb"/MediaBox \[0 0 792(?:\.0+)? 612(?:\.0+)?\]", data)        # Letter landscape
    assert fitting_font_pt(112) == 9.0 and fitting_font_pt(159) < 7.5            # wide ledgers shrink to fit
