"""ISWL in RERUN: schema-rates loading, the fixed-premium split and the monthly roll.

The expected numbers are CyberLife's own, read from live records by
``tools/rerun/verify_iswl_rollforward.py`` and ``tools/rerun/sample_iswl_receipts.py``:

* 11580276 (81335200, 25 units at 3.89, PAC monthly): gross 11.60 = 8.85 base + 2.75 fee,
  net credited 6.90 = 25 x round(0.85 x 3.89, 2) / 12.
* 11761012 (25.004 units at 12.26, direct quarterly): net 65.14 = 25.004 x 10.42 / 4.
* 11580276 on 2026-04-11: COI 4.08 on NAR 19219.73 at the annual rate 2.55 / 12.
"""
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from suiteview.core.rates_schema import (
    BandSpec, CellAssignment, FundAssignment, FundRate, ModeFactor, PlanAssignment, PlanDef,
    RateSetInfo, ScheduleWindow, SubseriesRow,
)
from suiteview.illustration.core.calc_engine import _split_requested_premium
from suiteview.illustration.core.corridor_rates import corridor_factor
from suiteview.illustration.core.iswl_rates import (
    FundBucketRate,
    ISWLItemPremium,
    ISWLRateBasis,
    iswl_current_credited_rate,
    iswl_recorded_credited_rate,
    load_iswl_rates,
    split_iswl_premium,
)
from suiteview.illustration.core.monthly_deduction import calculate_deduction
from suiteview.illustration.core.premium_handler import apply_premium
from suiteview.illustration.core.rate_loader import RateLookupError
from suiteview.illustration.core.target_premium import compute_target_premiums
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.models.policy_data import (
    BenefitInfo, CoverageSegment, IllustrationPolicyData, RiderInfo,
)

ISSUE = date(1988, 4, 11)
PLAN = "81335200"


def _basis(**changes) -> ISWLRateBasis:
    values = dict(
        plan_company="00", plan_note="", units=25.0, base_premium_per_unit=3.89,
        load_pct=[None, 0.5] + [0.15] * 70, net_premium_per_unit=[None, 1.95] + [3.31] * 70,
        billing_frequency=1, mode="M", bill_form_family="PAC", prem_factor=0.091,
        fee_factor=0.09167, policy_fee_annual=30.0, billed_premium=11.60,
        anchor_date=date(2026, 9, 11),
    )
    values.update(changes)
    return ISWLRateBasis(**values)


def _config(**changes) -> PlancodeConfig:
    values = dict(
        plancode=PLAN, product_family="ISWL", maturity_age=95, premium_cease_age=95,
        gint=0.04, dbd=0.04, poav_table="0", loan_charge_rate_guar=0.08,
        loan_charge_rate_curr=0.04, corridor_by_age={0: 2.5, 40: 2.5, 100: 1.0},
    )
    values.update(changes)
    return PlancodeConfig(**values)


def _policy(**changes) -> IllustrationPolicyData:
    segment = CoverageSegment(
        coverage_phase=1, issue_date=ISSUE, issue_age=4, rate_sex="F", rate_class="N",
        face_amount=25000.0, original_face_amount=25000.0, units=25.0)
    values = dict(
        policy_number="11580276", company_code="01", plancode=PLAN, product_type="ISWL",
        issue_state="TX", issue_date=ISSUE, issue_age=4, rate_sex="F", rate_class="N",
        face_amount=25000.0, units=25.0, modal_premium=11.60, billing_frequency=1,
        bill_form_code="G", valuation_date=date(2026, 9, 11), maturity_age=95,
        segments=[segment],
    )
    values.update(changes)
    return IllustrationPolicyData(**values)


# -- the fixed-premium split (premium load rule 4) --------------------------------

def test_rule_4_net_premium_is_units_times_rounded_net_rate():
    basis = _basis()
    assert basis.net_per_payment(39) == 6.90
    quarterly = _basis(units=25.004, net_premium_per_unit=[None] + [10.42] * 70, billing_frequency=3)
    assert quarterly.net_per_payment(39) == 65.14


def test_split_keeps_fee_and_load_out_of_the_account_value():
    split = split_iswl_premium(_basis(), 11.60, 11.60, 39, date(2026, 10, 11))
    assert (split.payments, split.gross_premium, split.net_premium) == (1, 11.60, 6.90)
    assert split.policy_fee == 2.75
    assert split.benefit_premium == 0.0
    assert split.premium_load == 1.95                       # 8.85 base - 6.90 net
    assert split.premium_load + split.policy_fee + split.net_premium == pytest.approx(11.60)


def test_split_accepts_several_or_no_payments_and_rejects_partial_amounts():
    assert split_iswl_premium(_basis(), 0.0, 11.60, 39, None).payments == 0
    catch_up = split_iswl_premium(_basis(), 3 * 11.60, 11.60, 39, None)
    assert (catch_up.payments, catch_up.net_premium) == (3, 20.70)
    with pytest.raises(ValueError, match="fixed-premium"):
        split_iswl_premium(_basis(), 15.00, 11.60, 39, None)


def test_bill_drops_a_benefit_premium_when_the_benefit_ceases():
    waiver = ISWLItemPremium("Benefit 10", date(2032, 7, 6), 25.20, 2.34)
    basis = _basis(billed_premium=33.02, units=25.982, base_premium_per_unit=11.29, prem_factor=0.093,
                   fee_factor=0.11333, ceasing_items=[waiver])
    assert basis.billed_per_payment(date(2032, 6, 6)) == 33.02
    assert basis.benefit_premium_per_payment(date(2032, 6, 6)) == 2.34   # 33.02 - 27.28 - 3.40
    assert basis.billed_per_payment(date(2032, 7, 6)) == 30.68
    assert basis.benefit_premium_per_payment(date(2032, 7, 6)) == 0.0


def test_apply_premium_routes_iswl_through_the_fixed_premium_split():
    from suiteview.illustration.core.rate_loader import IllustrationRates

    rates = IllustrationRates(iswl=_basis())
    result = apply_premium(1000.0, _policy(), _config(), rates, 39, 0.0, 0.0, 0.0,
                           gross_premium_override=11.60, projection_date=date(2026, 10, 11))
    assert result.av_after_premium == pytest.approx(1006.90)
    assert (result.gross_premium, result.net_premium, result.policy_fee) == (11.60, 6.90, 2.75)
    assert result.total_premium_load == pytest.approx(4.70)
    assert result.tpp_rate == 0.15
    assert result.premiums_to_date == 11.60


def test_iswl_without_a_schedule_bills_only_in_billing_months():
    quarterly = _policy(billing_frequency=3, modal_premium=30.0)
    config = _config()
    assert _split_requested_premium(quarterly, config, None, 40, policy_month=1) == (30.0, 0.0)
    assert _split_requested_premium(quarterly, config, None, 40, policy_month=2) == (0.0, 0.0)
    assert _split_requested_premium(quarterly, config, None, 40, policy_month=4) == (30.0, 0.0)


# -- the monthly deduction -------------------------------------------------------

def test_iswl_monthly_deduction_is_the_coi_only():
    from suiteview.illustration.core.rate_loader import IllustrationRates

    coi = [None] + [2.55 / 12.0] * 91
    rates = IllustrationRates(coi=coi, segment_coi={1: coi}, iswl=_basis())
    policy = _policy(
        benefits=[BenefitInfo(benefit_type="1", benefit_subtype="0", units=25.0, coi_rate=0.97,
                              cease_date=date(2040, 1, 1))],
        riders=[RiderInfo(plancode="06582016", face_amount=5000.0, units=5.0, premium_rate=7.39,
                          maturity_date=date(2040, 1, 1))],
    )
    # 2026-04-11 AV before COI 5698.69 (5694.61 + 4.08) gives CyberLife's NAR 19219.73.
    ded = calculate_deduction(5698.69, policy, _config(), rates, 39, 42, 0.0,
                              projection_date=date(2026, 4, 11))
    assert round(ded.nar, 2) == 19219.73
    assert round(ded.total_coi_charge, 2) == 4.08
    assert ded.benefit_charges == 0.0 and ded.rider_charges == 0.0
    assert ded.mfee_charge == 0.0 and ded.epu_charge == 0.0
    assert ded.total_deduction == pytest.approx(ded.total_coi_charge)


def test_iswl_coi_is_not_substandard_rated():
    # 13447734 (81335600, Table B): CyberLife charged 3.20 = NAR 26500.57 x 1.45 / 12000, unrated;
    # the table extra is in the fixed premium.
    from suiteview.illustration.core.monthly_deduction import _adjusted_coi_rate

    segment = replace(_policy().segments[0], table_rating=2, flat_extra=5.0)
    assert _adjusted_coi_rate(1.45 / 12, segment, _config(), date(2026, 6, 6), round_5=True) == 1.45 / 12
    ul = PlancodeConfig(plancode="UL", table_rating_factor=0.25)
    assert _adjusted_coi_rate(1.0, segment, ul, date(2026, 6, 6)) == pytest.approx(1.5 + 0.41)


def test_iswl_coi_rate_is_not_rounded_to_five_decimals():
    """80136200 15902845: CyberLife CINS 11.07 = 55,790.84 x 2.38 / 12 / 1000 = 11.0652.
    The UL 5-decimal rate 0.19833 would give 11.0650 -> 11.06."""
    from suiteview.illustration.core.monthly_deduction import _adjusted_coi_rate

    segment = _policy().segments[0]
    rate = _adjusted_coi_rate(2.38 / 12, segment, _config(), date(2026, 9, 6), round_5=True)
    assert rate == 2.38 / 12
    assert round(55_790.84 * rate / 1000 + 1e-9, 2) == 11.07
    ul = PlancodeConfig(plancode="UL")
    assert _adjusted_coi_rate(2.38 / 12, segment, ul, date(2026, 9, 6), round_5=True) == 0.19833


def test_iswl_has_no_ul_target_premiums():
    result = compute_target_premiums(_policy(), _config())
    assert result.mtp_annual == 0.0 and result.ctp_annual == 0.0


def test_iswl_plancode_configuration():
    # Product family, ages, GINT (= DBD) and loan rates come from schema rates.
    config = load_plancode(PLAN)
    assert config.is_iswl
    assert (config.maturity_age, config.premium_cease_age, config.gint, config.dbd) == (95, 95, 0.04, 0.04)
    assert (config.loan_charge_rate_guar, config.loan_charge_rate_curr) == (0.08, 0.04)
    # The GPT ISWL plans carry the standard 7702 CORR in schema rates; the table
    # carries no plan facts.
    assert corridor_factor(config, 45) == 2.15 and corridor_factor(config, 94) == 1.01
    assert corridor_factor(config, 95) == 1.0
    assert config.illustration_overrides == ()


def test_schema_product_family_outside_the_engine_families_is_rejected():
    from suiteview.core.rates_errors import RatesError
    from suiteview.illustration.models.plan_facts import PlanFacts

    facts = PlanFacts(
        plancode=PLAN, company="00", schema_family="WL", description="", maturity_age=95,
        premium_cease_age=95, cirf_key="", fund_keys="", shadow_legacy_plancode="", gint=0.04,
        db_discount=None, loan_reg_chg=0.08, loan_reg_crd=0.04, loan_pref_chg=None,
        loan_pref_crd=None, snet_by_issue_age=None, corridor_by_age=None,
    )
    with pytest.raises(RatesError, match="PRODUCT_FAMILY WL"):
        facts.engine_family


# -- rates from schema ``rates`` -----------------------------------------------------

I2_PERCENTAGES = [Decimal(p) / 100 for p in (
    100, 100, 94, 89, 83, 78, 72, 67, 61, 56, 50, 44, 39, 33, 28, 22, 17, 11, 6)]


class _FakeSchema:
    """The schema-rates rows of one ISWL plan (company 00) at issue age 4."""

    def __init__(self, *, rules="400", loan_credit=0.04, cint=(0.04, 0.04), star_modal=False, funds=True,
                 scr_rules="60", scr_table="I4", scr_cells=("SCR",)):
        self.funds = funds
        self.plan = PlanDef("00", PLAN, "00", "ISWL", "BASE", "ISWL CEIL88", (
            ("PREMIUM_CEASE_AGE", 95), ("MATURITY_AGE", 95), ("VALUE_PER_UNIT", Decimal("1000.00")),
            ("PREMLOAD_RULES", rules), ("SCR_TABLE", scr_table), ("SCR_RULES", scr_rules)))
        cell = dict(benefit="", sex="F", rate_class="N", band="0", state="**", subseries="")
        scr_schedule = {"SCR": 2, "SCR_PCT": 6}
        self.cells = [
            CellAssignment(rate_type="COI", schedule_id=1, **cell),
            *(CellAssignment(rate_type=t, schedule_id=scr_schedule[t], **cell) for t in scr_cells),
            CellAssignment(rate_type="PREMLOAD_PCT", schedule_id=3, **cell),
            CellAssignment(rate_type="PREM", schedule_id=4, **cell),
            CellAssignment(rate_type="CV", schedule_id=5, **{**cell, "subseries": "11"}),
        ]
        self.windows = {
            1: [ScheduleWindow(1, "C", date(1900, 1, 1), date(2000, 4, 11), 10),
                ScheduleWindow(1, "C", date(2000, 4, 11), None, 11),
                ScheduleWindow(1, "G", date(1900, 1, 1), None, 12)],
            2: [ScheduleWindow(2, "G", date(1900, 1, 1), None, 20)],
            3: [ScheduleWindow(3, "C", date(1900, 1, 1), None, 30),
                ScheduleWindow(3, "G", date(1900, 1, 1), None, 31)],
            4: [ScheduleWindow(4, "G", date(1900, 1, 1), None, 40)],
            5: [ScheduleWindow(5, "G", date(1900, 1, 1), None, 60)],
            6: [ScheduleWindow(6, "G", date(1900, 1, 1), None, 21)],
        }
        grains = {10: "IA_DUR", 11: "IA_DUR", 12: "IA_DUR", 20: "IA_DUR", 21: "IA_DUR", 30: "DUR",
                  31: "DUR", 40: "IA", 50: "DUR", 51: "SCALAR", 52: "SCALAR", 60: "IA_DUR"}
        self.sets = {i: RateSetInfo(i, "", g, "", "") for i, g in grains.items()}
        years = range(1, 92)
        self.values = {
            10: {(4, d): Decimal("1.00") for d in years},
            11: {(4, d): Decimal("2.40") if d < 39 else Decimal("2.55") for d in years},
            12: {(4, d): Decimal("3.00") for d in years},
            20: {(4, 1): Decimal("50"), (4, 2): Decimal("20"), (4, 3): Decimal("0")},
            # CKULTB04 table I2 (rule 5) as stored: fractions of the AV, zero to maturity.
            21: {(4, d): (I2_PERCENTAGES[d - 1] if d <= len(I2_PERCENTAGES) else Decimal(0))
                 for d in years},
            30: {(0, d): Decimal("0.5") if d == 1 else Decimal("0.15") for d in years},
            31: {(0, d): Decimal("0.5") if d == 1 else Decimal("0.15") for d in years},
            40: {(4, 0): Decimal("3.89")},
            50: {(0, d): Decimal("0.04") for d in years},
            51: {(0, 0): Decimal("0.08")},
            52: {(0, 0): Decimal(str(loan_credit))},
            # CV per unit by duration 0..90; duration 91 (maturity) is not stored.
            60: {(4, d): Decimal(10 * d) for d in range(0, 91)},
        }
        self.cint = cint
        self.star_modal = star_modal

    def plan_subseries(self, company, plancode):
        return [SubseriesRow("F", "N", "11", "00-2-352")]

    def plan_defs(self, plancode):
        return [self.plan] if plancode == PLAN else []

    def plan_bands(self, company, plancode):
        return [BandSpec("0", date(1900, 1, 1), "00", None, "0")]

    def cell_assignments(self, company, plancode):
        return list(self.cells)

    def schedule_windows(self, ids):
        return [w for i in ids for w in self.windows[i]]

    def rate_sets(self, ids):
        return {i: self.sets[i] for i in ids}

    def rate_values(self, ids, issue_age):
        return {i: dict(self.values[i]) for i in ids}

    def plan_assignments(self, company, plancode):
        return [PlanAssignment("**", "GINT", "G", 50), PlanAssignment("**", "LOAN_REG_CHG", "G", 51),
                PlanAssignment("**", "LOAN_REG_CRD", "G", 52)]

    def modal_factors(self, company, plancode):
        common = dict(market_org="", fee_amount_from=Decimal(0), fee_amount_to=Decimal(0),
                      policy_fee_annual=Decimal("30.00"), policy_fee_add="4", policy_fee_rule="3",
                      collection_fee=Decimal(0), collection_fee_add="0", multiply_order="1",
                      rating_order="1", rounding_rule="1")
        if self.star_modal:
            star = {**common, "policy_fee_annual": Decimal("7.50")}
            return [ModeFactor(billing_form="*", mode="M", prem_factor=Decimal("0.085"),
                               fee_factor=Decimal("0.10"), **star),
                    ModeFactor(billing_form="*", mode="S", prem_factor=Decimal("0.505"),
                               fee_factor=Decimal("0.50"), **star)]
        return [ModeFactor(billing_form="PAC", mode="M", prem_factor=Decimal("0.091"),
                           fee_factor=Decimal("0.09167"), **common),
                ModeFactor(billing_form="DIR", mode="M", prem_factor=Decimal("0.093"),
                           fee_factor=Decimal("0.11333"), **common)]

    def fund_assignments(self, company, plancode):
        return [FundAssignment("I1", "", "LPGRP0002", "CIRF", "", "")] if self.funds else []

    def fund_rates(self, keys):
        new, roll = self.cint
        return [
            FundRate("LPGRP0002", "CINT_NEW", "C", date(2009, 9, 1), 1, 12, None, Decimal(str(new))),
            FundRate("LPGRP0002", "CINT_ROLL", "C", date(2008, 2, 1), 0, None, None, Decimal(str(roll))),
            FundRate("LPGRP0002", "CINT_ROLL", "C", date(2001, 4, 1), 0, None, None, Decimal("0.05")),
        ]


def test_load_iswl_rates_reads_every_schedule_from_schema_rates():
    rates = load_iswl_rates(_policy(), _config(), repo=_FakeSchema())
    # COI is the IAF annual rate / 12 from the window in effect on each policy year's start.
    assert rates.coi[1] == pytest.approx(1.00 / 12)          # 1988 window
    assert rates.coi[13] == pytest.approx(2.40 / 12)         # year starting 04/11/2000
    assert rates.coi[39] == pytest.approx(2.55 / 12)
    assert rates.segment_coi[1] is rates.coi
    assert len(rates.coi) == 92                              # years 1..91 (age 4 to 95)
    assert rates.scr[1:5] == [50.0, 20.0, 0.0, 0.0]          # zero tail after the table ends
    assert rates.gint[1] == 0.04
    assert rates.mfee == [] and rates.epu == [] and rates.tpp == []
    basis = rates.iswl
    assert basis.base_premium_per_unit == 3.89
    assert basis.net_premium_per_unit[1] == 1.95             # round(0.5 x 3.89, 2)
    assert basis.net_premium_per_unit[39] == 3.31            # round(0.85 x 3.89, 2)
    assert (basis.bill_form_family, basis.mode, basis.prem_factor, basis.fee_modal) == ("PAC", "M", 0.091, 2.75)
    assert basis.plan_note == "CyberLife rate user of policy company 01"


def test_guaranteed_scale_uses_the_g_coi_schedule():
    rates = load_iswl_rates(_policy(), _config(), coi_scale=0, expense_scale=0, repo=_FakeSchema())
    assert rates.coi[39] == pytest.approx(3.00 / 12)


def test_plan_without_surrender_charge_rules_has_no_surrender_charge():
    # 56070 series (FN2VN/MN2VN): PLAN_DEF SCR_TABLE 00, SCR_RULES 00.
    rates = load_iswl_rates(_policy(), _config(), repo=_FakeSchema(scr_rules="00"))
    assert set(rates.scr[1:]) == {0.0}
    assert any("no surrender charge" in note for note in rates.iswl.notes)


def test_ceasing_benefits_and_riders_come_from_the_stored_billing_premiums():
    policy = _policy(
        benefits=[BenefitInfo(benefit_type="1", benefit_subtype="0", units=25.0, coi_rate=0.97,
                              rating_factor=1.0, cease_date=date(2032, 7, 6)),
                  BenefitInfo(benefit_type="3", benefit_subtype="3", units=25.0, coi_rate=0.44,
                              cease_date=date(2021, 7, 6))],
        riders=[RiderInfo(plancode="06582016", units=5.0, premium_rate=7.39,
                          maturity_date=date(2031, 4, 11))],
    )
    items = load_iswl_rates(policy, _config(), repo=_FakeSchema()).iswl.ceasing_items
    assert [(i.label, i.cease_date, i.modal_premium) for i in items] == [
        ("Benefit 10", date(2032, 7, 6), 2.21),   # 25 x 0.97 x 0.091
        ("Rider 06582016", date(2031, 4, 11), 3.36),
    ]


@pytest.mark.parametrize("fake, config, message", [
    (_FakeSchema(rules="200"), _config(), "premium load rules 200"),
    (_FakeSchema(), _config(maturity_age=100, premium_cease_age=100), "illustration age override"),
])
def test_unsupported_iswl_plan_facts_fail_loudly(fake, config, message):
    with pytest.raises(RateLookupError, match=message):
        load_iswl_rates(_policy(), config, repo=fake)


def test_unverified_bill_form_fails_loudly():
    with pytest.raises(RateLookupError, match="Bill form"):
        load_iswl_rates(_policy(bill_form_code="H"), _config(), repo=_FakeSchema())


def test_several_base_phases_are_rejected():
    policy = _policy()
    policy.segments.append(replace(policy.segments[0], coverage_phase=2))
    with pytest.raises(RateLookupError, match="exactly one base coverage"):
        load_iswl_rates(policy, _config(), repo=_FakeSchema())


def test_cvat_iswl_loads_its_rates_for_the_nsp_corridor():
    """The CVAT corridor (cvat_nsp) is modelled, so a CVAT ISWL loads like a GPT one."""
    rates = load_iswl_rates(_policy(def_of_life_ins="CVAT"), _config(), repo=_FakeSchema())
    assert rates.coi[1] > 0


def test_current_credited_rate_is_the_declared_fixed_fund_rate_floored_at_gint():
    assert iswl_current_credited_rate("01", PLAN, date(2026, 9, 29), 0.04, repo=_FakeSchema()) == 0.04
    assert iswl_current_credited_rate("01", PLAN, date(2026, 9, 29), 0.03,
                                      repo=_FakeSchema(cint=(0.045, 0.045))) == 0.045
    assert iswl_current_credited_rate("01", PLAN, date(2002, 1, 1), 0.04,
                                      repo=_FakeSchema(cint=(0.045, 0.045))) == 0.05
    with pytest.raises(RateLookupError, match="buckets"):
        iswl_current_credited_rate("01", PLAN, date(2026, 9, 29), 0.03, repo=_FakeSchema(cint=(0.045, 0.04)))
    assert iswl_current_credited_rate("01", PLAN, date(2026, 9, 29), 0.04, repo=_FakeSchema(funds=False)) is None


def _buckets(*rows):
    return [FundBucketRate(*row) for row in rows]


def test_recorded_bucket_rate_is_the_fallback_current_rate():
    assert iswl_recorded_credited_rate(_buckets((9863.47, 4.0, "F1"), (4.82, 4.0, "F1")), 0.03) == 0.04
    assert iswl_recorded_credited_rate(
        _buckets((100.0, 4.5, "F1"), (300.0, 3.5, "F2")), 0.03) == pytest.approx(0.0375)
    assert iswl_recorded_credited_rate(_buckets((100.0, 2.5, "F1")), 0.03) == 0.03
    with pytest.raises(RateLookupError, match="no current fund bucket rate"):
        iswl_recorded_credited_rate(_buckets((100.0, None, "F1")), 0.03)


def test_negative_gp_holding_bucket_does_not_set_the_credited_rate():
    """B71SP600 16867267: GP holds the negative AV at 0%; new money is credited in I1 at 2%."""
    assert iswl_recorded_credited_rate(_buckets((0.0, 2.0, "I1"), (-325.06, 0.0, "GP")), 0.02) == 0.02
    assert iswl_recorded_credited_rate(_buckets(*[(0.0, 4.0, "I1")] * 3, (-22.3, 0.0, "GP")), 0.03) == 0.04
    with pytest.raises(RateLookupError, match="hold no value"):
        iswl_recorded_credited_rate(_buckets((0.0, 4.0, "I1"), (0.0, 3.0, "I2"), (-50.0, 0.0, "GP")), 0.03)


def test_negative_zero_rate_bucket_in_another_fund_still_weights_the_rate():
    """Only fund GP is CyberLife's negative-AV holding fund; other funds keep their weight."""
    assert iswl_recorded_credited_rate(
        _buckets((300.0, 4.0, "F1"), (-100.0, 0.0, "F2")), 0.01) == pytest.approx(0.06)
    with pytest.raises(RateLookupError, match="hold no value"):
        iswl_recorded_credited_rate(_buckets((0.0, 2.0, "I1"), (-325.06, 0.0, "F2")), 0.02)


def test_net_premium_uses_the_stored_premium_per_unit():
    # 11673995: 25.507 units stored at 6.31 while schema PREM at the record issue age differs;
    # CyberLife credited 68.36 = 25.507 x round(0.85 x 6.31, 2) / 2 each semi-annual payment.
    policy = _policy(billing_frequency=6)
    policy.segments[0] = replace(policy.segments[0], units=25.507, premium_rate=6.31)
    rates = load_iswl_rates(policy, _config(), repo=_FakeSchema(star_modal=True))
    basis = rates.iswl
    assert basis.base_premium_per_unit == 6.31 and basis.schema_premium_per_unit == 3.89
    assert basis.net_per_payment(39) == 68.36
    assert any("stored premium per unit 6.31" in note for note in basis.notes)


def test_mode_factors_for_every_bill_form_apply_when_no_exact_row():
    basis = load_iswl_rates(_policy(), _config(), repo=_FakeSchema(star_modal=True)).iswl
    assert (basis.prem_factor, basis.fee_factor, basis.policy_fee_annual) == (0.085, 0.10, 7.50)


def test_guaranteed_cash_value_is_interpolated_monthly_and_endows_at_maturity():
    basis = load_iswl_rates(_policy(), _config(), repo=_FakeSchema()).iswl
    assert basis.cash_value_per_unit[:3] == [0.0, 10.0, 20.0]
    assert basis.cash_value_per_unit[-1] == 1000.0          # duration 91 = endowment per unit
    # 38 years 3 months after issue: 25 x (380 x 9 + 390 x 3) / 12
    assert basis.guaranteed_cash_value(date(2026, 7, 11)) == pytest.approx(25 * (380 * 9 + 390 * 3) / 12)


def test_iswl_surrender_value_is_floored_at_the_guaranteed_cash_value():
    from suiteview.illustration.core.calc_engine import _iswl_cash_value_floor
    from suiteview.illustration.core.rate_loader import IllustrationRates

    basis = load_iswl_rates(_policy(), _config(), repo=_FakeSchema()).iswl
    rates = IllustrationRates(iswl=basis)
    on = date(2026, 4, 11)                                   # duration 38 -> 25 x 380
    assert _iswl_cash_value_floor(rates, on, -50.0) == pytest.approx(9500.0)
    assert _iswl_cash_value_floor(rates, on, 12000.0) == 12000.0
    assert _iswl_cash_value_floor(IllustrationRates(), on, -50.0) == -50.0   # UL unchanged


# -- surrender charge rules (CyberDoc D10 p. 177) -----------------------------------

def _rule_5_rates():
    return load_iswl_rates(_policy(), _config(), repo=_FakeSchema(
        scr_rules="50", scr_table="I2", scr_cells=("SCR_PCT",)))


def _full_surrender(rates, on, rate_year, account_value):
    from suiteview.illustration.core.calc_engine import _calculate_surrender_charge

    return _calculate_surrender_charge(_policy(), rates, rate_year, on, _config(),
                                       account_value=account_value)


def test_rule_5_loads_scr_pct_as_a_fraction_of_the_account_value():
    rates = _rule_5_rates()
    assert set(rates.scr[1:]) == {0.0}                       # no per-unit charge
    pct = rates.iswl.surrender_charge_pct
    assert pct[1:4] == [1.0, 1.0, 0.94]
    assert (pct[19], pct[20], pct[91]) == (0.06, 0.0, 0.0)
    assert any("rule 5, SCR_PCT x account value" in note for note in rates.iswl.notes)


def test_rule_5_charge_is_the_percentage_of_the_account_value_floored_at_guaranteed_cv():
    from suiteview.illustration.core.calc_engine import _iswl_cash_value_floor

    rates = _rule_5_rates()
    on = date(2006, 6, 11)                                   # policy year 19: 6%
    rate, charge, rate_detail, charge_detail = _full_surrender(rates, on, 19, 10000.0)
    assert (rate, charge) == (0.06, pytest.approx(600.0))
    assert rate_detail == {"cov1": 0.06} and charge_detail == {"cov1": pytest.approx(600.0)}
    assert _iswl_cash_value_floor(rates, on, 10000.0 - charge) == pytest.approx(9400.0)
    # Guaranteed CV: duration 18 + 2 months = 25 x (180 x 10 + 190 x 2) / 12 = 4,541.67.
    _, small_charge, _, _ = _full_surrender(rates, on, 19, 4000.0)
    assert small_charge == pytest.approx(240.0)
    assert _iswl_cash_value_floor(rates, on, 4000.0 - small_charge) == pytest.approx(25 * 2180 / 12)
    assert _full_surrender(rates, on, 19, -100.0)[1] == 0.0  # no charge on a negative AV


def test_rule_5_has_no_charge_from_policy_year_20():
    rates = _rule_5_rates()
    assert not rates.iswl.surrender_charge_graded            # company 01: flat by policy year
    assert _full_surrender(rates, date(2007, 4, 11), 20, 10000.0)[:2] == (0.0, 0.0)
    assert _full_surrender(rates, date(2026, 9, 11), 39, 10000.0)[:2] == (0.0, 0.0)


# CKULTB04 table C9/58 percentages (fractions), years 1-12, then 0.
C9_PCT = [None, 0.12, 0.11, 0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02, 0.01] + [0.0] * 80


@pytest.mark.parametrize("year, months, gross, charge", [
    (4, 10, 18139.60, 1662.86),    # 26/000329760 B11SB300: 9.167%
    (6, 4, 227681.79, 17456.36),   # 26/000323263 B11SB500: 7.667%
    (3, 5, 13459.79, 1424.45),     # 26/FF000030 B11SW100 (table 58): 10.583%
    (12, 3, 50854.47, 889.95),     # 26/000322377 B11SB500: 1.750%
    (13, 6, 177418.52, 887.09),    # 26/000296307 N61SB400: 0.500%, a year past the table
    (11, 0, 67364.90, 2020.95),    # 26/000321190 B11SB500: pct(10) = 3.000% on the anniversary
])
def test_company_26_graded_percentage_matches_cyberlife_full_surrenders(year, months, gross, charge):
    """FH_FIXED SF charges (loan-free, CKPR) are the graded percentage x the fund to the cent."""
    basis = _basis(surrender_charge_pct=C9_PCT, surrender_charge_graded=True)
    pct = basis.surrender_charge_rate(year, months)
    assert round(pct * gross + 1e-9, 2) == pytest.approx(charge)


def test_graded_percentage_starts_at_the_prior_year_and_year_1_is_flat():
    graded = _basis(surrender_charge_pct=C9_PCT, surrender_charge_graded=True)
    flat = _basis(surrender_charge_pct=C9_PCT)
    assert graded.surrender_charge_rate(1, 7) == 0.12          # pct(0) is pct(1)
    assert graded.surrender_charge_rate(4, 0) == 0.10
    assert graded.surrender_charge_rate(4, 10) == 0.09167
    assert graded.surrender_charge_rate(14, 3) == 0.0
    assert flat.surrender_charge_rate(4, 10) == 0.09


def test_company_26_rule_5_loads_graded_and_charges_by_months_since_the_anniversary():
    rates = load_iswl_rates(_policy(company_code="26"), _config(), repo=_FakeSchema(
        scr_rules="50", scr_table="C9", scr_cells=("SCR_PCT",)))
    assert rates.iswl.surrender_charge_graded
    assert any("graded monthly between policy years" in note for note in rates.iswl.notes)
    policy = _policy(company_code="26")

    def charge(on, year, av=10000.0):
        from suiteview.illustration.core.calc_engine import _calculate_surrender_charge
        return _calculate_surrender_charge(policy, rates, year, on, _config(), account_value=av)[:2]

    # Year 19, two months after the 4/11 anniversary: 6% + (11% - 6%) x 10 / 12 = 10.167%.
    assert charge(date(2006, 6, 11), 19) == (0.10167, pytest.approx(1016.70))
    assert charge(date(2006, 4, 11), 19) == (0.11, pytest.approx(1100.0))
    # Year 20 still carries the tail of year 19's 6%; the flat model has none.
    assert charge(date(2007, 6, 11), 20) == (0.05, pytest.approx(500.0))
    assert charge(date(2008, 4, 11), 21) == (0.0, 0.0)


def test_rule_6_dollar_per_unit_charge_is_unchanged():
    rates = load_iswl_rates(_policy(), _config(), repo=_FakeSchema())
    assert rates.iswl.surrender_charge_pct == []
    on = date(1988, 6, 11)                                   # policy year 1: 50 per unit
    for account_value in (0.0, 10000.0):
        rate, charge, _, _ = _full_surrender(rates, on, 1, account_value)
        assert (rate, charge) == (50.0, 1250.0)               # 25 units x 50


@pytest.mark.parametrize("fake, message", [
    (_FakeSchema(scr_rules="50", scr_table="I2", scr_cells=()), "has no SCR_PCT rate"),
    (_FakeSchema(scr_rules="50", scr_table="Z9", scr_cells=("SCR_PCT",)), "table Z9, whose free"),
    (_FakeSchema(scr_rules="50", scr_table="I2", scr_cells=("SCR", "SCR_PCT")), "ambiguous"),
    (_FakeSchema(scr_rules="56", scr_table="I2", scr_cells=("SCR_PCT",)), "combined with another"),
    (_FakeSchema(scr_rules="60", scr_cells=("SCR_PCT",)), "has no SCR rate"),
])
def test_missing_or_unverified_surrender_charge_rates_fail_loudly(fake, message):
    with pytest.raises(RateLookupError, match=message):
        load_iswl_rates(_policy(), _config(), repo=fake)


def test_rule_5_partial_surrender_charges_are_rejected_inside_the_charge_period():
    from suiteview.illustration.core.calc_engine import _reduce_base_face

    rates = _rule_5_rates()
    with pytest.raises(ValueError, match="face decrease in a rule-5 ISWL"):
        _reduce_base_face(_policy(), 5000.0, rates, date(2006, 6, 11), 19, True, _config())
    policy = _policy()
    _reduce_base_face(policy, 5000.0, rates, date(2007, 6, 11), 20, True, _config())
    assert policy.face_amount == 20000.0
