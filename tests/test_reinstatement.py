"""UL reinstatement quote service: eligibility, lapse values and premium (no database)."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    BenefitInfo, CoverageSegment, IllustrationPolicyData,
)
from suiteview.polview.models.cl_polrec.policy_data_classes import BenefitInfo as RawBenefit
from suiteview.polview.services import reinstatement as rein
from suiteview.polview.services import reinstatement_rules as rules

YEARS = 40
ISSUE = date(2015, 3, 15)
LAPSE = date(2026, 3, 15)
TODAY = date(2026, 10, 7)
ELIGIBLE = rein.ReinstatementEligibility("Q", "Termination - Lapse", True, "Eligible")


def source(**changes):
    values = dict(
        exists=True, product_type="UL", last_entry_code="Q", terminate_date=None,
        get_live_transactions=lambda codes: [],
    )
    values.update(changes)
    return SimpleNamespace(**values)


def make_policy(**changes) -> IllustrationPolicyData:
    values = dict(
        policy_number="SYNTHETIC", plancode="SYNTHETIC", product_type="UL",
        issue_date=ISSUE, valuation_date=date(2026, 2, 15), issue_age=40, maturity_age=121,
        face_amount=100000.0, units=100.0, account_value=-25.0,
        premiums_paid_to_date=12000.0, premiums_ytd=0.0, ctp=1200.0,
        map_cease_date=date(2025, 3, 15),
        segments=[CoverageSegment(
            issue_date=ISSUE, issue_age=40, face_amount=100000.0,
            original_face_amount=100000.0, units=100.0, rate_sex="M", rate_class="N")],
    )
    values.update(changes)
    return IllustrationPolicyData(**values)


def make_rates(**changes) -> IllustrationRates:
    values = dict(
        segment_coi={1: [None] + [0.12] * YEARS},
        segment_epu={1: [None] + [0.05] * YEARS},
        # Year 11 = 5.00/unit, year 12 = 4.50/unit.
        segment_scr={1: [None] + [10.0 - 0.5 * year for year in range(YEARS)]},
        mfee=[None] + [7.5] * YEARS,
        tpp=[None] + [0.05] * YEARS,
        epp=[None] + [0.05] * YEARS,
    )
    values.update(changes)
    return IllustrationRates(**values)


def make_basis(policy=None, rates=None, config=None, **kwargs):
    kwargs.setdefault("lapse_date", LAPSE)
    kwargs.setdefault("today", TODAY)
    return rein.build_reinstatement_basis(
        policy or make_policy(), config or PlancodeConfig(plancode="SYNTHETIC"),
        rates or make_rates(), eligibility=ELIGIBLE, **kwargs)


def raw_benefit(type_cd="A", subtype="1", cease=LAPSE, original=date(2093, 12, 10)):
    return RawBenefit(
        cov_pha_nbr=1, benefit_code=type_cd + subtype, benefit_type_cd=type_cd,
        benefit_subtype_cd=subtype, benefit_desc="CCV", form_number="", issue_date=ISSUE,
        pay_up_date=original, cease_date=cease, orig_cease_date=original,
        units=Decimal("10"), vpu=Decimal("1000"), benefit_amount=Decimal("10000"),
        issue_age=40, rating_factor=None, renewal_indicator="1", coi_rate=Decimal("0.25"),
    )


# ── eligibility and dates ────────────────────────────────────────────────────

@pytest.mark.parametrize("product", ["UL", "IUL", "SGUL"])
def test_lapsed_ul_family_is_eligible(product):
    result = rein.reinstatement_eligibility(source(product_type=product))
    assert result.eligible
    assert result.last_entry_description == "Termination - Lapse"


@pytest.mark.parametrize("product", ["VUL", "ISWL", "WL", "TERM", "UNKNOWN"])
def test_non_ul_is_not_eligible(product):
    result = rein.reinstatement_eligibility(source(product_type=product))
    assert not result.eligible
    assert "only available for ULs" in result.message


@pytest.mark.parametrize("code", ["X", "A", "M", ""])
def test_only_lapse_or_internal_surrender_is_eligible(code):
    result = rein.reinstatement_eligibility(source(last_entry_code=code))
    assert not result.eligible
    assert "internal surrender" in result.message


def surrender(code, when=date(2023, 4, 30)):
    return SimpleNamespace(trans_code=code, trans_date=when, gross_amount=Decimal("-2955.20"))


def test_internal_surrender_is_eligible_and_dated_by_the_si_transaction():
    policy = source(last_entry_code="P",
                    get_live_transactions=lambda codes: [surrender("SI")] if "SI" in codes else [])
    result = rein.reinstatement_eligibility(policy, today=date(2025, 1, 1))
    assert result.eligible and "internal surrender" in result.last_entry_description
    assert rein.find_lapse_date(policy) == (date(2023, 4, 30), None)


def test_full_surrender_is_not_eligible():
    policy = source(last_entry_code="P", get_live_transactions=lambda codes: [surrender("SF")])
    result = rein.reinstatement_eligibility(policy)
    assert not result.eligible and "full surrender" in result.message
    assert rein.is_full_surrender(policy)


def test_internal_surrender_and_lapse_are_not_full_surrenders():
    internal = source(last_entry_code="P", get_live_transactions=lambda codes: [surrender("SI")])
    assert not rein.is_full_surrender(internal)
    assert not rein.is_full_surrender(source())


def lapse_on(when):
    return source(get_live_transactions=lambda codes: (
        [SimpleNamespace(trans_code="TL", trans_date=when, gross_amount=Decimal("-25"))]
        if "TL" in codes else []))


@pytest.mark.parametrize("today,eligible", [
    (date(2031, 3, 15), True),    # exactly five years after the lapse
    (date(2031, 3, 16), False),   # more than five years after the lapse
])
def test_lapse_is_reinstatable_for_five_years_by_default(today, eligible):
    result = rein.reinstatement_eligibility(lapse_on(LAPSE), today=today)
    assert result.eligible is eligible
    if not eligible:
        assert "more than 5 years ago" in result.message
        assert "03/15/2026" in result.message


@pytest.mark.parametrize("plancode", sorted(rules.THREE_YEAR_REINSTATEMENT_PLANCODES))
@pytest.mark.parametrize("today,eligible", [
    (date(2029, 3, 15), True),    # exactly three years after the lapse
    (date(2029, 3, 16), False),   # more than three years after the lapse
])
def test_listed_plancodes_are_reinstatable_for_three_years(plancode, today, eligible):
    policy = lapse_on(LAPSE)
    policy.base_plancode = plancode
    result = rein.reinstatement_eligibility(policy, today=today)
    assert result.eligible is eligible
    if not eligible:
        assert "more than 3 years ago" in result.message


def test_reinstatement_window_years_by_plancode():
    assert len(rules.THREE_YEAR_REINSTATEMENT_PLANCODES) == 29
    assert rules.reinstatement_window_years(" 1u147400 ") == 3
    assert rules.reinstatement_window_years("1U147100") == 5
    assert rules.reinstatement_window_years("") == 5


def test_internal_surrender_past_the_period_is_not_eligible():
    policy = source(last_entry_code="P", get_live_transactions=lambda codes: [surrender("SI")])
    assert rein.reinstatement_eligibility(policy, today=date(2026, 10, 7)).eligible
    result = rein.reinstatement_eligibility(policy, today=date(2028, 5, 1))
    assert not result.eligible and "reinstatement period" in result.message


def test_expired_lapse_is_never_loaded(monkeypatch):
    monkeypatch.setattr(rein, "load_projection_basis", pytest.fail)
    with pytest.raises(rein.ReinstatementError, match="more than 5 years ago"):
        rein.load_reinstatement_basis(lapse_on(date(2020, 1, 15)), today=TODAY)


def test_a_later_full_surrender_overrides_an_earlier_internal_surrender():
    policy = source(last_entry_code="P", get_live_transactions=lambda codes: [
        surrender("SI", date(2020, 1, 1)), surrender("SF", date(2021, 1, 1))])
    assert not rein.reinstatement_eligibility(policy).eligible


def test_surrender_without_a_transaction_is_not_eligible():
    assert not rein.reinstatement_eligibility(source(last_entry_code="P")).eligible


@pytest.mark.parametrize("today,expected", [
    (date(2024, 2, 28), date(2024, 1, 31)),
    (date(2024, 2, 29), date(2024, 2, 29)),
    (date(2024, 3, 30), date(2024, 2, 29)),
    (date(2024, 3, 31), date(2024, 3, 31)),
])
def test_latest_monthliversary_stays_issue_day_anchored(today, expected):
    assert rein.latest_monthliversary(date(2000, 1, 31), today) == expected


def test_lapse_date_comes_from_the_latest_tl_transaction():
    lapses = [SimpleNamespace(trans_code="TL", trans_date=date(2020, 1, 5), gross_amount=Decimal("1")),
              SimpleNamespace(trans_code="TL", trans_date=date(2026, 3, 15), gross_amount=Decimal("-25.00"))]
    policy = source(terminate_date=date(2026, 1, 1),
                    get_live_transactions=lambda codes: lapses if "TL" in codes else [])
    assert rein.find_lapse_date(policy) == (date(2026, 3, 15), Decimal("-25.00"))


@pytest.mark.parametrize("terminated,expected", [
    (date(2026, 3, 15), date(2026, 3, 15)), (date(9999, 12, 31), None), (None, None),
])
def test_lapse_date_falls_back_to_termination_date(terminated, expected):
    assert rein.find_lapse_date(source(terminate_date=terminated)) == (expected, None)


# ── lapse values ─────────────────────────────────────────────────────────────

def test_values_at_lapse():
    basis = make_basis(policy=make_policy(regular_loan_principal=100.0, regular_loan_accrued=4.5))
    lapse = basis.lapse
    assert lapse.lapse_date == LAPSE
    assert lapse.values_date == date(2026, 2, 15)
    assert lapse.account_value == Decimal("-25.00")
    assert lapse.loan_balance == Decimal("104.50")
    # An anniversary-dated surrender takes the prior year's rate (engine convention).
    assert lapse.surrender_charge == Decimal("500.00")
    assert lapse.snet_expiry_date == date(2025, 3, 15)
    assert not lapse.has_ccv and lapse.ccv_cease_date is None
    assert basis.default_date == date(2026, 9, 15)


def test_default_date_is_never_before_the_lapse():
    assert make_basis(today=LAPSE).default_date == LAPSE


def test_future_lapse_is_rejected():
    with pytest.raises(rein.ReinstatementError, match="future"):
        make_basis(today=date(2026, 3, 1))


def test_lapse_amount_mismatch_is_noted():
    notes = make_basis(lapse_amount=Decimal("-30.00")).notes
    assert any("differs" in note for note in notes)


# ── monthly deduction and premium ────────────────────────────────────────────

def test_reinstatement_premium_calculation():
    quote = make_basis().quote(date(2026, 9, 15))
    d = quote.deduction
    assert (d.policy_year, d.policy_month, d.attained_age) == (12, 7, 51)
    assert d.base_coi == Decimal("12.00")
    assert d.rider_coi == d.benefit_charges == Decimal("0.00")
    assert (d.epu, d.monthly_fee, d.av_charge) == (Decimal("5.00"), Decimal("7.50"), Decimal("0.00"))
    assert (d.coi_total, d.fee_total, d.total) == (Decimal("12.00"), Decimal("12.50"), Decimal("24.50"))
    p = quote.premium
    assert p.account_value == Decimal("-25.00")
    assert p.policy_debt == Decimal("0.00")
    assert p.surrender_charge == Decimal("450.00")
    assert (p.coi_x2, p.fees_x2) == (Decimal("24.00"), Decimal("25.00"))
    # 450 + 0 + 24 + 25 - (-25) = 524; 524 / 0.95 = 551.578... rounded up to the cent.
    assert p.subtotal == Decimal("524.00")
    assert p.premium == Decimal("551.58")
    assert p.premium_load == Decimal("27.58")
    assert p.load_description == "5.00%"
    assert p.formula == "standard" and p.poav_charge == Decimal("0.00") and p.no_lapse is None
    assert p.standard_premium == p.premium and p.net_premium == Decimal("524.00")
    assert quote.deduction.deduction_date == date(2026, 9, 15) and quote.next_deduction is None
    assert not any("GIUL21" in note for note in quote.notes)


# ── IUL reinstatement formulas (S151972 business requirements v2.0) ──────────

@pytest.mark.parametrize("plancode,formula", [
    ("1U144600", "iul08"), ("1U144700", "iul08"), ("1U144800", "iul08"),
    ("1U145500", "no_lapse_iul"), ("1U146400", "no_lapse_iul"), ("1U145800", "no_lapse_iul"),
    ("1U145600", "no_lapse_iul"), ("1U146500", "no_lapse_iul"), ("1U145900", "no_lapse_iul"),
    ("1U146800", "no_lapse_iul"), ("1U146900", "no_lapse_iul"), ("1U147500", "no_lapse_iul"),
    ("1U147800", "no_lapse_iul"), (" 1u147400 ", "giul21"),
    ("1U147900", "standard"), ("1U147000", "standard"), ("SYNTHETIC", "standard"), ("", "standard"),
])
def test_plancodes_map_to_their_reinstatement_formula(plancode, formula):
    assert rules.reinstatement_formula(plancode).value == formula


def test_giul21_uses_lapse_date_charges_without_premium_load():
    basis = make_basis(policy=make_policy(plancode="1U147400"), reinstatement_code="3")
    quote = basis.quote(date(2026, 9, 15))
    p = quote.premium
    assert quote.deduction.deduction_date == LAPSE
    assert (quote.deduction.policy_year, quote.deduction.policy_month) == (12, 1)
    assert p.surrender_charge == basis.lapse.surrender_charge == Decimal("500.00")
    # 500 + 0 + 24 + 25 - (-25) = 574, with no premium load.
    assert p.subtotal == p.premium == p.standard_premium == p.net_premium == Decimal("574.00")
    assert p.premium_load == p.poav_charge == Decimal("0.00")
    assert p.load_description == "none: GIUL21"
    assert any("1U147400 (GIUL21)" in note and "excludes the premium load" in note
               for note in quote.notes)
    after = basis.values_after_reinstatement(quote)
    assert after.net_premium == Decimal("574.00")
    assert after.snet_expiry_date == date(2025, 3, 15)  # never extended, even for code 3


def test_giul21_with_no_requirement_owes_no_premium():
    quote = make_basis(policy=make_policy(plancode="1U147400", account_value=5000.0)).quote(
        date(2026, 9, 15))
    assert quote.premium.premium == quote.premium.premium_load == Decimal("0.00")


def poav_config(plancode, **changes):
    return PlancodeConfig(plancode=plancode, poav_table="1", **changes)


def poav_rates(**changes):
    return make_rates(poav=[None] + [0.001] * YEARS, **changes)


def test_iul14_outside_the_no_lapse_period_uses_two_lapse_deductions_with_poav():
    basis = make_basis(policy=make_policy(plancode="1U145500", account_value=100.0),
                       config=poav_config("1U145500"), rates=poav_rates())
    quote = basis.quote(date(2026, 9, 15))
    d, p = quote.deduction, quote.premium
    assert d.deduction_date == LAPSE and d.av_charge == Decimal("0.10")
    assert p.no_lapse is None
    assert p.surrender_charge == basis.lapse.surrender_charge
    assert p.coi_x2 == 2 * d.coi_total
    assert p.fees_x2 == 2 * (d.fee_total - d.av_charge) == Decimal("25.00")
    # PoAV is part of each monthly deduction (CKAS UE001742: 2 x $0.99), shown apart.
    assert p.poav_charge == 2 * d.av_charge == Decimal("0.20")
    assert p.subtotal == p.surrender_charge + 2 * d.total - Decimal("100.00")
    assert p.premium == (p.subtotal / Decimal("0.95")).quantize(
        Decimal("0.01"), rounding="ROUND_CEILING")
    assert p.net_premium == p.subtotal


def no_lapse_basis(accumulated_mtp, **changes):
    policy = make_policy(plancode="1U145500", map_cease_date=date(2027, 3, 15), mtp=50.0,
                         accumulated_mtp=accumulated_mtp, **changes)
    return make_basis(policy=policy, reinstatement_code="1")


def test_iul14_in_the_no_lapse_period_quotes_the_lesser_no_lapse_premium():
    basis = no_lapse_basis(12500.0)
    quote = basis.quote(date(2026, 9, 15))
    p = quote.premium
    # Standard: (500 + 24 + 25 + 25) / 0.95 = 604.22.
    assert p.standard_premium == Decimal("604.22")
    nl = p.no_lapse
    # AccumMTP at lapse is the values record's accumulated MTP.
    assert nl.accumulated_mtp == Decimal("12500.00")
    assert nl.monthly_mtp == Decimal("50.00") and nl.premiums_paid == Decimal("12000.00")
    assert nl.no_lapse_expiry == date(2027, 3, 15)
    assert nl.premium == Decimal("550.00")  # 12,500 + 0 + 0 + 50 - 12,000
    assert p.premium == Decimal("550.00") and p.uses_no_lapse_premium
    assert p.net_premium == Decimal("522.50")  # the 5% load comes off when applied
    assert any("No-Lapse premium is lower" in note for note in quote.notes)
    after = basis.values_after_reinstatement(quote)
    assert after.net_premium == Decimal("522.50")
    # The guarantee is restored and extended by the 6 months terminated.
    assert after.snet_expiry_date == date(2027, 9, 15)


def test_iul14_no_lapse_premium_counts_withdrawals_and_debt():
    p = no_lapse_basis(12500.0, withdrawals_to_date=10.0, regular_loan_principal=20.0).quote(
        date(2026, 9, 15)).premium
    assert p.no_lapse.premium == Decimal("580.00")
    assert p.no_lapse.policy_debt == Decimal("20.00")


def test_iul14_in_the_no_lapse_period_keeps_a_lower_standard_premium():
    quote = no_lapse_basis(13000.0).quote(date(2026, 9, 15))
    p = quote.premium
    assert p.no_lapse.premium == Decimal("1050.00")
    assert p.premium == p.standard_premium == Decimal("604.22") and not p.uses_no_lapse_premium
    assert any("standard premium is lower" in note for note in quote.notes)


def test_no_lapse_premium_is_never_negative():
    p = no_lapse_basis(6000.0).quote(date(2026, 9, 15)).premium
    assert p.no_lapse.premium == p.premium == p.net_premium == Decimal("0.00")


def test_no_lapse_period_falls_back_to_the_plan_safety_net_years():
    policy = make_policy(plancode="1U147800", mtp=50.0, accumulated_mtp=12500.0)
    config = PlancodeConfig(plancode="1U147800", snet_by_issue_age={40: 15})
    basis = make_basis(policy=policy, config=config)
    # MAP date 03/15/2025 is before the lapse; 15 years from issue runs to 03/15/2030.
    assert basis.no_lapse_expiry() == date(2030, 3, 15)
    assert basis.quote(date(2026, 9, 15)).premium.uses_no_lapse_premium


def test_missing_mtp_inside_the_no_lapse_period_is_loud():
    with pytest.raises(rein.ReinstatementError, match="MTP"):
        no_lapse_basis(0.0).quote(date(2026, 9, 15))


def test_lapse_the_day_after_a_monthliversary_charges_that_monthliversary():
    # CyberLife's TL date usually falls the day after the monthliversary (LD = last MV).
    policy = make_policy(plancode="1U145500", map_cease_date=date(2027, 3, 15), mtp=50.0,
                         accumulated_mtp=12500.0)
    basis = make_basis(policy=policy, lapse_date=date(2026, 3, 16))
    quote = basis.quote(date(2026, 9, 15))
    assert quote.deduction.deduction_date == date(2026, 3, 15)
    # Monthliversaries after the 03/16 TL date through 09/15: 04/15 ... 09/15.
    assert basis.values_after_reinstatement(quote).snet_expiry_date == date(2027, 9, 15)


def test_iul08_charges_the_reinstatement_and_next_month_deductions():
    rates = poav_rates(segment_epu={1: [None] + [0.05] * 12 + [0.07] * (YEARS - 12)})
    basis = make_basis(policy=make_policy(plancode="1U144600", account_value=100.0),
                       config=poav_config("1U144600"), rates=rates, reinstatement_code="3")
    when = date(2027, 2, 15)  # policy year 12; the next month starts year 13
    quote = basis.quote(when)
    d, nxt, p = quote.deduction, quote.next_deduction, quote.premium
    assert d.deduction_date == when and nxt.deduction_date == date(2027, 3, 15)
    assert (d.epu, nxt.epu) == (Decimal("5.00"), Decimal("7.00"))
    assert p.surrender_charge == Decimal("450.00")  # reinstatement date, no duration adjustment
    assert p.coi_x2 == d.coi_total + nxt.coi_total
    assert p.fees_x2 == d.fee_total - d.av_charge + nxt.fee_total - nxt.av_charge
    assert p.poav_charge == d.av_charge + nxt.av_charge == Decimal("0.20")
    assert p.subtotal == p.surrender_charge + d.total + nxt.total - Decimal("100.00")
    assert p.premium > p.subtotal and p.no_lapse is None
    after = basis.values_after_reinstatement(quote)
    assert after.snet_expiry_date == date(2025, 3, 15)  # SafetyNet ends at termination


def test_policy_debt_is_added_to_the_subtotal():
    basis = make_basis(policy=make_policy(regular_loan_principal=100.0, preferred_loan_accrued=4.5))
    premium = basis.quote(date(2026, 9, 15)).premium
    assert premium.policy_debt == Decimal("104.50")
    assert premium.subtotal == Decimal("628.50")


def test_load_splits_at_the_commission_target():
    rates = make_rates(tpp=[None] + [0.10] * YEARS, epp=[None] + [0.02] * YEARS)
    premium = make_basis(policy=make_policy(ctp=100.0), rates=rates).quote(date(2026, 9, 15)).premium
    # 100 of gross at 10% (net 90), the rest at 2%: (524 - 90) / 0.98 = 442.857 -> 442.86.
    assert premium.premium == Decimal("542.86")
    assert premium.load_description == "10.00% to target, 2.00% excess"


def test_premiums_ytd_apply_only_in_the_same_policy_year():
    rates = make_rates(tpp=[None] + [0.10] * YEARS, epp=[None] + [0.02] * YEARS)
    policy = make_policy(ctp=100.0, premiums_ytd=100.0, valuation_date=date(2026, 4, 15))
    basis = make_basis(policy=policy, rates=rates, lapse_date=date(2026, 5, 15))
    same_year = basis.quote(date(2026, 9, 15)).premium
    next_year = basis.quote(date(2027, 3, 15)).premium
    assert same_year.premium_load == same_year.premium - same_year.subtotal
    assert same_year.premium == (same_year.subtotal / Decimal("0.98")).quantize(
        Decimal("0.01"), rounding="ROUND_CEILING")
    assert next_year.premium - next_year.subtotal > Decimal("10.00")


def test_no_premium_when_the_account_value_covers_the_requirement():
    quote = make_basis(policy=make_policy(account_value=5000.0)).quote(date(2026, 9, 15))
    assert quote.premium.subtotal < 0
    assert quote.premium.premium == quote.premium.premium_load == Decimal("0.00")
    assert any("no reinstatement premium" in note for note in quote.notes)


def test_non_monthliversary_date_is_noted():
    quote = make_basis().quote(date(2026, 9, 20))
    assert any("not a monthliversary" in note for note in quote.notes)


@pytest.mark.parametrize("when,match", [
    (date(2026, 3, 14), "before the lapse date"),
    (date(2096, 3, 15), "maturity"),
])
def test_invalid_reinstatement_dates_are_rejected(when, match):
    with pytest.raises(rein.ReinstatementError, match=match):
        make_basis().quote(when)


@pytest.mark.parametrize("missing,match", [
    (dict(segment_coi={1: []}, coi=[]), "COI rate schedule"),
    (dict(segment_scr={1: []}, scr=[]), "surrender charge rate schedule"),
])
def test_missing_rate_schedules_stop_the_quote(missing, match):
    with pytest.raises(rein.ReinstatementError, match=match):
        make_basis(rates=make_rates(**missing))


# ── CCV benefit terminated with the lapse ────────────────────────────────────

def test_ccv_benefit_ceased_with_the_lapse_is_restored_and_charged():
    policy = make_policy(benefits=[BenefitInfo(
        coverage_phase=1, benefit_type="A", benefit_subtype="1", units=10.0,
        issue_date=ISSUE, pay_up_date=LAPSE, cease_date=LAPSE, coi_rate=0.25)])
    notes = rein.restore_lapse_benefits(policy, [raw_benefit()], LAPSE)
    assert policy.benefits[0].cease_date == date(2093, 12, 10)
    assert policy.benefits[0].pay_up_date == date(2093, 12, 10)
    assert "12/10/2093 is restored" in notes[0]
    basis = make_basis(policy=policy, notes=tuple(notes))
    assert basis.lapse.has_ccv and basis.lapse.ccv_cease_date == date(2093, 12, 10)
    quote = basis.quote(date(2026, 9, 15))
    assert quote.deduction.benefit_charges == Decimal("2.50")
    assert quote.premium.coi_x2 == Decimal("29.00")
    assert notes[0] in quote.notes


def test_benefit_without_a_later_original_cease_date_is_not_restored():
    policy = make_policy(benefits=[BenefitInfo(
        coverage_phase=1, benefit_type="A", benefit_subtype="1", units=10.0,
        pay_up_date=LAPSE, cease_date=LAPSE, coi_rate=0.25)])
    assert rein.restore_lapse_benefits(policy, [raw_benefit(original=LAPSE)], LAPSE) == []
    basis = make_basis(policy=policy)
    assert basis.lapse.ccv_cease_date == LAPSE
    assert any("ceases on the lapse date" in note for note in basis.notes)
    assert basis.quote(date(2026, 9, 15)).deduction.benefit_charges == Decimal("0.00")


# ── loading ──────────────────────────────────────────────────────────────────

def test_ineligible_policy_is_never_loaded(monkeypatch):
    monkeypatch.setattr(rein, "load_projection_basis", pytest.fail)
    with pytest.raises(rein.ReinstatementError, match="full surrender"):
        rein.load_reinstatement_basis(source(last_entry_code="P"), today=TODAY)


def test_missing_lapse_date_is_explained(monkeypatch):
    monkeypatch.setattr(rein, "load_projection_basis", pytest.fail)
    with pytest.raises(rein.ReinstatementError, match="lapse date is not available"):
        rein.load_reinstatement_basis(source(), today=TODAY)


def test_load_uses_the_tl_lapse_and_restores_benefits(monkeypatch):
    calls = {}

    def fake_load(number, **kwargs):
        calls.update(kwargs, number=number)
        policy = make_policy(benefits=[BenefitInfo(
            coverage_phase=1, benefit_type="A", benefit_subtype="1", units=10.0,
            pay_up_date=LAPSE, cease_date=LAPSE, coi_rate=0.25)])
        return SimpleNamespace(policy=policy, config=PlancodeConfig(plancode="SYNTHETIC"),
                               rates=make_rates())

    monkeypatch.setattr(rein, "load_projection_basis", fake_load)
    lapse = SimpleNamespace(trans_code="TL", trans_date=LAPSE, gross_amount=Decimal("-25.00"))
    policy = source(policy_number="U1", region="CKPR", company_code="01",
                    get_live_transactions=lambda codes: [lapse],
                    fetch_table=lambda name: [{"REN_RLE_CD": "3 "}],
                    get_benefits=lambda: [raw_benefit()])
    basis = rein.load_reinstatement_basis(policy, today=TODAY)
    assert calls["number"] == "U1" and calls["illustration_date"] == TODAY
    assert calls["reinstatement_date"] is None  # no PLN_TMN_DT: nothing to restore
    assert basis.lapse.ccv_cease_date == date(2093, 12, 10)
    assert basis.reinstatement_code == "3"  # segment 66 REN_RLE_CD


def test_loader_failures_become_quote_errors(monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("DB2 unavailable")

    monkeypatch.setattr(rein, "load_projection_basis", broken)
    policy = source(policy_number="U1", region="CKPR", company_code="01",
                    terminate_date=LAPSE)
    with pytest.raises(rein.ReinstatementError, match="DB2 unavailable"):
        rein.load_reinstatement_basis(policy, today=TODAY)


# -- values after reinstatement (skipped coverage) ---------------------------

def ccv_policy(**changes):
    benefit = BenefitInfo(coverage_phase=1, benefit_type="A", benefit_subtype="1", units=10.0,
                          pay_up_date=date(2093, 12, 10), cease_date=date(2093, 12, 10), coi_rate=0.25)
    return make_policy(benefits=[benefit], map_cease_date=date(2027, 3, 15), **changes)


def test_values_after_reinstatement_for_a_non_three_code_end_at_termination():
    basis = make_basis(policy=ccv_policy(regular_loan_principal=100.0), reinstatement_code="1")
    quote = basis.quote(date(2026, 9, 15))
    after = basis.values_after_reinstatement(quote)
    assert after.reinstatement_date == date(2026, 9, 15)
    assert after.terminated_months == 6
    assert after.net_premium == quote.premium.premium - quote.premium.premium_load
    assert after.monthly_deduction == quote.deduction.total
    assert after.account_value == Decimal("-25.00") + after.net_premium - after.monthly_deduction
    assert after.loan_balance == Decimal("100.00")
    assert after.surrender_charge == quote.premium.surrender_charge
    assert after.surrender_value == after.account_value - after.surrender_charge - after.loan_balance
    assert after.snet_expiry_date == LAPSE
    assert after.ccv_cease_date == LAPSE


def test_code_three_extends_snet_by_the_terminated_months_and_ccv_stays_at_termination():
    basis = make_basis(policy=ccv_policy(), reinstatement_code="3")
    after = basis.values_after_reinstatement(basis.quote(date(2026, 9, 15)))
    assert after.snet_expiry_date == date(2027, 9, 15)
    assert after.ccv_cease_date == LAPSE


def test_snet_already_expired_before_termination_is_not_pushed_past_it_for_other_codes():
    basis = make_basis(reinstatement_code="1")
    after = basis.values_after_reinstatement(basis.quote(date(2026, 9, 15)))
    assert after.snet_expiry_date == date(2025, 3, 15)
    assert after.ccv_cease_date is None


def test_values_after_reinstatement_without_a_premium_keep_the_lapse_account_value():
    basis = make_basis(policy=make_policy(account_value=5000.0), reinstatement_code="3")
    after = basis.values_after_reinstatement(basis.quote(date(2026, 9, 15)))
    assert after.net_premium == Decimal("0.00")
    assert after.account_value == Decimal("5000.00") - after.monthly_deduction

@pytest.mark.parametrize("lapse,expected", [
    (date(2026, 3, 15), [date(2026, m, 15) for m in range(4, 11)]),
    # A recent lapse drops monthliversaries before it.
    (date(2026, 8, 20), [date(2026, 9, 15), date(2026, 10, 15)]),
])
def test_reinstatement_date_choices_span_six_months_back_to_next_month(lapse, expected):
    assert list(rein.reinstatement_date_choices(ISSUE, lapse, TODAY)) == expected


def test_reinstatement_date_choices_stop_before_maturity():
    assert rein.reinstatement_date_choices(ISSUE, LAPSE, TODAY, date(2026, 8, 15))[-1] == date(2026, 7, 15)


def test_basis_offers_the_choices_and_defaults_to_the_latest_monthliversary():
    basis = make_basis()
    assert basis.date_choices[0] == date(2026, 4, 15) and basis.date_choices[-1] == date(2026, 10, 15)
    assert basis.default_date == date(2026, 9, 15) and basis.default_date in basis.date_choices