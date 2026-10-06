from types import SimpleNamespace

import pytest

from suiteview.illustration.core.calc_engine import _shadow_rider_charges_from_deduction
from suiteview.illustration.core.rate_loader import (
    IllustrationRates,
    RateLookupError,
    _load_shadow_rates,
    get_rate,
)
from suiteview.illustration.core.shadow_calc import ShadowInput, calculate_shadow
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.models.policy_data import (
    BenefitInfo,
    CoverageSegment,
    IllustrationPolicyData,
)


def _shadow_rates(**overrides) -> IllustrationRates:
    values = dict(
        shadow_coi=[None, 0.0],
        shadow_epu=[None, 0.0],
        shadow_tpp=[None, 0.0],
        shadow_epp=[None, 0.0],
        shadow_int=[None, 0.0],
        shadow_dbd=[None, 0.0],
    )
    values.update(overrides)
    return IllustrationRates(**values)


def test_shadow_rider_charges_use_regular_charges_less_ccv():
    policy = IllustrationPolicyData(
        benefits=[
            BenefitInfo(benefit_type="A", benefit_subtype=""),
            BenefitInfo(benefit_type="3", benefit_subtype="9"),
        ]
    )
    deduction = SimpleNamespace(
        rider_charges=12.0,
        benefit_charges=18.0,
        benefit_charge_detail={"A": 5.0, "39": 7.0},
    )

    assert _shadow_rider_charges_from_deduction(policy, deduction) == 25.0


def test_shadow_calculation_applies_regular_rider_charges():
    policy = IllustrationPolicyData(
        face_amount=100_000.0,
        db_option="A",
        ccv_active=True,
        segments=[CoverageSegment(face_amount=100_000.0, original_face_amount=100_000.0)],
    )
    config = PlancodeConfig(
        shadow_mfee=2.0,
    )

    result = calculate_shadow(ShadowInput(
        prev_shadow_eav=100.0,
        gross_premium=0.0,
        premiums_ytd=0.0,
        policy=policy,
        config=config,
        rates=_shadow_rates(),
        rate_year=1,
        attained_age=40,
        days_in_month=30,
        policy_debt=0.0,
        shadow_rider_charges=7.5,
    ))

    assert result.shadow_rider_charges == 7.5
    assert result.shadow_md == 9.5


@pytest.mark.parametrize("age, charged", [(99, True), (100, False), (110, False)])
def test_shadow_charges_stop_at_the_charge_cease_age(age, charged):
    """PremiumAndChargeCeaseAge (LTGUL, Robert Haessly 10/5/2026): no shadow charges either."""
    policy = IllustrationPolicyData(
        face_amount=100_000.0, db_option="A", ccv_active=True,
        segments=[CoverageSegment(face_amount=100_000.0, original_face_amount=100_000.0)])
    config = PlancodeConfig(shadow_mfee=5.0, charge_cease_age=100, shadow_cease_age=100)
    result = calculate_shadow(ShadowInput(
        prev_shadow_eav=1_000.0, gross_premium=0.0, premiums_ytd=0.0, policy=policy,
        config=config, rates=_shadow_rates(shadow_coi=[None, 1.0], shadow_epu=[None, 0.05]),
        rate_year=1, attained_age=age, days_in_month=30, policy_debt=0.0))
    charges = (result.shadow_coi, result.shadow_epu, result.shadow_mfee, result.shadow_md)
    if charged:
        assert all(c > 0 for c in charges) and result.shadow_eav > 0
    else:
        assert charges == (0.0, 0.0, 0.0, 0.0) and result.shadow_eav == 0.0


def _shadow_policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        face_amount=100_000.0,
        db_option="A",
        ccv_active=True,
        premiums_paid_to_date=0.0,
        segments=[CoverageSegment(
            face_amount=100_000.0,
            original_face_amount=100_000.0,
            issue_age=45,
            rate_sex="M",
            rate_class="N",
            band=1,
            original_band=1,
        )],
    )


def test_sgul_late_premium_is_added_after_deduction_and_credited():
    policy = _shadow_policy()
    config = PlancodeConfig(
        shadow_late_payment_forgiveness=True,
    )
    rates = _shadow_rates(
        shadow_coi=[None, 0.12],
        shadow_tpr=[None, 0.0],
        shadow_tpr_tbl1=[None, 0.0],
        shadow_tpp=[None, 0.0],
        shadow_epp=[None, 0.0],
        shadow_int=[None, 0.12],
    )

    on_monthliversary = calculate_shadow(ShadowInput(
        prev_shadow_eav=1_000.0,
        gross_premium=100.0,
        premiums_ytd=100.0,
        premiums_to_date=100.0,
        policy=policy,
        config=config,
        rates=rates,
        rate_year=1,
        attained_age=45,
        days_in_month=31,
        policy_debt=0.0,
        display_days_in_month=31,
    ))
    late = calculate_shadow(ShadowInput(
        prev_shadow_eav=1_000.0,
        gross_premium=0.0,
        post_deduction_gross_premium=100.0,
        premiums_ytd=100.0,
        premiums_to_date=100.0,
        policy=policy,
        config=config,
        rates=rates,
        rate_year=1,
        attained_age=45,
        days_in_month=31,
        policy_debt=0.0,
        display_days_in_month=31,
    ))

    assert late.shadow_coi > on_monthliversary.shadow_coi
    assert late.shadow_av == late.shadow_nar_av - late.shadow_md + 100.0
    assert late.shadow_interest > 0.0


def test_aps205_relief_uses_policy_month_and_cumulative_target():
    policy = _shadow_policy()
    config = PlancodeConfig(
        shadow_aps205_load_relief=True,
    )
    rates = _shadow_rates(
        shadow_coi=[None, 0.0],
        shadow_tpr=[None, 10.0],
        shadow_tpr_tbl1=[None, 0.0],
        shadow_tpp=[None, 0.0],
        shadow_epp=[None, 0.45],
    )

    result = calculate_shadow(ShadowInput(
        prev_shadow_eav=0.0,
        gross_premium=1_500.0,
        premiums_ytd=1_500.0,
        premiums_to_date=1_500.0,
        policy=policy,
        config=config,
        rates=rates,
        rate_year=1,
        policy_month=7,
        attained_age=45,
        days_in_month=30,
        policy_debt=0.0,
    ))

    assert result.shadow_target_prem == 1_000.0
    assert result.shadow_excess_load == 0.0
    assert result.shadow_net_prem == 1_500.0


def test_aps205_premium_earns_receipt_to_monthliversary_interest():
    policy = _shadow_policy()
    config = PlancodeConfig(
        shadow_aps205_load_relief=True,
    )
    rates = _shadow_rates(
        shadow_coi=[None, 0.0],
        shadow_tpr=[None, 10.0],
        shadow_tpr_tbl1=[None, 0.0],
        shadow_tpp=[None, 0.0],
        shadow_epp=[None, 0.45],
        shadow_int=[None, 0.12],
    )

    result = calculate_shadow(ShadowInput(
        prev_shadow_eav=0.0,
        gross_premium=500.0,
        premiums_ytd=500.0,
        premiums_to_date=500.0,
        policy=policy,
        config=config,
        rates=rates,
        rate_year=1,
        policy_month=1,
        attained_age=45,
        days_in_month=30,
        policy_debt=0.0,
        gross_premium_interest_days=15,
    ))

    assert result.shadow_net_prem > 500.0
    assert result.shadow_nar_av == result.shadow_net_prem


def _aps205_load(*, gross, ytd, ptd, year, month, tpr=10.0, flat=0.0, waiver=0.0, cease=None, when=None):
    policy = _shadow_policy()
    policy.segments[0].flat_extra = flat
    rates = _shadow_rates(
        shadow_tpr=[None, tpr],
        shadow_tpr_tbl1=[None, 0.0],
        shadow_epp=[None, 0.45],
        shadow_target_waiver_pct=waiver,
        shadow_target_waiver_cease=cease,
    )
    return calculate_shadow(ShadowInput(
        prev_shadow_eav=0.0, gross_premium=gross, premiums_ytd=ytd, premiums_to_date=ptd,
        policy=policy, config=PlancodeConfig(shadow_aps205_load_relief=True), rates=rates,
        rate_year=year, policy_month=month, attained_age=45, days_in_month=30, policy_debt=0.0,
        projection_date=when,
    ))


def test_aps205_cumulative_n_plus_1_relief_applies_without_a_month_gate():
    # U0592771 year 19 month 4-6: YTD 2.05 targets but premium to date 19.08 targets <= 20.
    result = _aps205_load(gross=319.37, ytd=2_048.0, ptd=19_078.0, year=19, month=6)
    assert result.shadow_target_prem == 1_000.0
    assert result.shadow_excess_load == 0.0


def test_aps205_loads_above_n_plus_1_even_within_two_yearly_targets():
    # U0570491 year 18: YTD 1.3 targets, premium to date above 19 targets -> loaded.
    result = _aps205_load(gross=100.0, ytd=1_300.0, ptd=19_040.0, year=18, month=8)
    assert result.shadow_prem_over_target == 40.0
    assert result.shadow_excess_load == pytest.approx(18.0)


def test_aps205_first_six_policy_months_allow_one_target_only():
    # U0592771 issue premium: 1.38 targets in month 1 is loaded above one target.
    result = _aps205_load(gross=1_382.0, ytd=1_382.0, ptd=1_382.0, year=1, month=1)
    assert result.shadow_excess_load == pytest.approx(382.0 * 0.45)
    assert result.shadow_net_prem == pytest.approx(1_382.0 - 171.9)


def test_aps205_unknown_premium_to_date_falls_back_to_the_per_year_rule():
    # No cumulative relief without PTD: 500 over one target is loaded (old code: 225).
    result = _aps205_load(gross=1_500.0, ytd=1_500.0, ptd=None, year=5, month=1)
    assert result.shadow_excess_load == pytest.approx(225.0)


def _flat_target(*, annual_flag, cease=None, when=None):
    policy = _shadow_policy()
    policy.face_amount = 10_000_000.0
    policy.segments[0].face_amount = policy.segments[0].original_face_amount = 10_000_000.0
    policy.segments[0].flat_extra = 2.40
    policy.segments[0].flat_cease_date = cease
    return calculate_shadow(ShadowInput(
        prev_shadow_eav=0.0, gross_premium=0.0, premiums_ytd=0.0, policy=policy,
        config=PlancodeConfig(shadow_aps205_load_relief=True, shadow_target_annual_flat=annual_flag),
        rates=_shadow_rates(shadow_tpr=[None, 40.38], shadow_tpr_tbl1=[None, 0.0]),
        rate_year=1, attained_age=73, days_in_month=30, policy_debt=0.0, projection_date=when,
    )).shadow_target_prem


def test_shadow_target_adds_the_annual_flat_extra_when_flagged():
    # U0588909: CTP-S 40.38 + $2.40 annual flat on 10M -> 42.78/1000 reproduces XP.
    assert _flat_target(annual_flag=True) == 427_800.0
    # Unflagged plans keep flat/12 (no evidence there).
    assert _flat_target(annual_flag=False) == 405_800.0


def test_shadow_target_drops_the_flat_extra_at_its_cease_date():
    from datetime import date

    cease = date(2034, 12, 14)
    assert _flat_target(annual_flag=True, cease=cease, when=date(2034, 11, 14)) == 427_800.0
    assert _flat_target(annual_flag=True, cease=cease, when=cease) == 403_800.0
    assert _flat_target(annual_flag=False, cease=cease, when=cease) == 403_800.0


def test_project_receipt_charges_the_ltgul_shadow_load(monkeypatch):
    """Reinstatement receipt posting passes PTD and policy month to the APS205 load."""
    from datetime import date

    from suiteview.polview.services import reinstatement_receipt as rr

    config = load_plancode("1U143800")
    policy = _shadow_policy()
    policy.plancode = "1U143800"
    rates = _shadow_rates(shadow_tpr=[None, 10.0], shadow_tpr_tbl1=[None, 0.0], shadow_epp=[None, 0.45])
    pay_to = date(2026, 1, 15)
    state = SimpleNamespace(
        date=pay_to, av_after_deduction=5_000.0, policy_year=5, policy_month=1, attained_age=50,
        guideline_limit=0.0, premiums_to_date_after_exception=5_500.0, withdrawals_to_date=0.0,
        accumulated_7pay=0.0, scheduled_prem_cap=0.0, premiums_ytd_after_exception=0.0,
        cost_basis_after_exception=0.0, interest_credited=0.0, av_end_of_month=0.0,
        shadow_av=2_000.0, shadow_eff_rate=0.005, shadow_interest=0.0, shadow_eav=2_010.0,
    )
    monkeypatch.setattr(rr, "project_policy", lambda *a, **k: SimpleNamespace(states=[state]))
    monkeypatch.setattr(rr, "_partial_interest", lambda *a, **k: 0.0)
    monkeypatch.setattr(rr, "_tamra_year", lambda *a: 10)
    monkeypatch.setattr(rr, "_tamra_month_of_year", lambda *a: 1)
    monkeypatch.setattr(rr, "compute_premium_allowances",
                        lambda _inp: SimpleNamespace(applied_total_premium=1_500.0))
    monkeypatch.setattr(rr, "apply_premium", lambda *a, **k: SimpleNamespace(
        gross_premium=1_500.0, premiums_ytd=1_500.0, premiums_to_date=6_300.0, cost_basis=0.0,
        av_after_premium=6_500.0, net_premium=1_500.0, total_premium_load=0.0))
    monkeypatch.setattr(rr, "run_month", lambda ctx, _timing: ctx.state)
    options = SimpleNamespace(guideline_cap_enabled=False, tamra_cap_enabled=False, levelizing_premium=False)

    _states, amounts = rr.project_receipt(
        policy, config, rates, None, options, date(2026, 1, 25), pay_to, date(2026, 2, 15), 1, 1_500.0)

    # T = 1,000; year 5: YTD 1,500 (500 over one target), PTD 6,300 (300 over 6 targets)
    # -> 300 x 45% = 135.  Without PTD it would be 225 (per-year); the old call gave 0.
    assert amounts.shadow_loads == pytest.approx(135.0)


def test_shadow_target_waiver_uplift_applies_until_the_waiver_ceases():
    from datetime import date

    cease = date(2046, 2, 5)
    before = _aps205_load(gross=0.0, ytd=0.0, ptd=0.0, year=5, month=1, tpr=4.1, waiver=0.053,
                          cease=cease, when=date(2026, 2, 5))
    after = _aps205_load(gross=0.0, ytd=0.0, ptd=0.0, year=40, month=1, tpr=4.1, waiver=0.053,
                         cease=cease, when=cease)
    assert before.shadow_target_prem == 431.73
    assert after.shadow_target_prem == 410.0


@pytest.mark.parametrize("basis, expected_db", [("Shadow", 101_000.0), ("Policy", 104_000.0)])
def test_option_b_shadow_death_benefit_basis(basis, expected_db):
    """Passport Select II (ShadowDBBasis Policy): NAR uses SA + the regular AV."""
    policy = _shadow_policy()
    policy.db_option = "B"
    result = calculate_shadow(ShadowInput(
        prev_shadow_eav=1_000.0, gross_premium=0.0, premiums_ytd=0.0, policy=policy,
        config=PlancodeConfig(shadow_db_basis=basis), rates=_shadow_rates(),
        rate_year=1, attained_age=45, days_in_month=30, policy_debt=0.0,
        policy_death_benefit=104_000.0,
    ))
    assert result.shadow_db == expected_db


def test_invalid_shadow_db_basis_is_rejected():
    with pytest.raises(ValueError, match="ShadowDBBasis"):
        PlancodeConfig(plancode="X", shadow_db_basis="Regular")


def test_ltgul_and_passport_select_ii_shadow_flags():
    for plancode in ("1U143800", "1U144500"):
        config = load_plancode(plancode)
        assert config.shadow_aps205_load_relief and config.shadow_target_waiver_uplift
        assert config.shadow_target_annual_flat
        assert config.shadow_db_basis == "Policy"
    for plancode in ("1U135200", "1U135400", "1U135L00"):
        config = load_plancode(plancode)
        assert config.shadow_db_basis == "Policy" and not config.shadow_target_waiver_uplift
    assert load_plancode("1U146600").shadow_db_basis == "Shadow"
    assert not load_plancode("1U146600").shadow_target_annual_flat


class _WaiverRatesDb:
    def __init__(self, rate):
        self.rate = rate

    def get_ben_mtp(self, *args, **_kwargs):
        assert args[-1] == "39"
        return self.rate


def _waiver_policy():
    policy = _shadow_policy()
    policy.plancode = "1U143800"
    policy.benefits = [BenefitInfo(benefit_type="3", benefit_subtype="9", cease_date=None)]
    return policy


def test_shadow_target_waiver_rate_loads_when_flagged():
    from suiteview.illustration.core.rate_loader import _load_shadow_target_waiver

    policy = _waiver_policy()
    result = IllustrationRates(shadow_tpr=[None, 4.1])
    _load_shadow_target_waiver(result, policy, PlancodeConfig(shadow_target_waiver_uplift=True),
                               _WaiverRatesDb(5.3), policy.base_segment)
    assert result.shadow_target_waiver_pct == pytest.approx(0.053)

    unflagged = IllustrationRates(shadow_tpr=[None, 4.1])
    _load_shadow_target_waiver(unflagged, policy, PlancodeConfig(), _WaiverRatesDb(5.3), policy.base_segment)
    assert unflagged.shadow_target_waiver_pct == 0.0

    with pytest.raises(RateLookupError, match="waiver"):
        _load_shadow_target_waiver(IllustrationRates(shadow_tpr=[None, 4.1]), policy,
                                   PlancodeConfig(shadow_target_waiver_uplift=True),
                                   _WaiverRatesDb(None), policy.base_segment)


def test_shadow_subtracts_gross_withdrawal_before_nar():
    policy = _shadow_policy()
    config = PlancodeConfig()
    rates = _shadow_rates()

    result = calculate_shadow(ShadowInput(
        prev_shadow_eav=1_000.0,
        gross_premium=0.0,
        premiums_ytd=0.0,
        premiums_to_date=0.0,
        policy=policy,
        config=config,
        rates=rates,
        rate_year=1,
        attained_age=45,
        days_in_month=30,
        policy_debt=0.0,
        gross_withdrawal=125.0,
    ))

    assert result.shadow_wd_charges == 125.0
    assert result.shadow_nar_av == 875.0


class _ShadowRatesDb:
    """Scale S schedules for the listed rate types; everything else is not loaded."""

    def __init__(self, *loaded):
        self.loaded = set(loaded)

    def get_rates(self, rate_type, *_args, **_kwargs):
        return [None, 1.0] if rate_type in self.loaded else None

    def get_mtp(self, *_args, **_kwargs):
        return None

    def get_tbl1_mtp(self, *_args, **_kwargs):
        return None

    def is_loaded(self, _plancode):
        return True


def _shadow_config() -> PlancodeConfig:
    return PlancodeConfig(shadow_plancode="CCVTEST", shadow_availability="Inherent")


def test_missing_required_shadow_int_raises_loudly():
    policy = _shadow_policy()
    policy.plancode = "MISSINGSHADOW"

    with pytest.raises(RateLookupError, match="shadow SHADOW_INT"):
        _load_shadow_rates(
            IllustrationRates(), policy, _shadow_config(),
            _ShadowRatesDb("COI", "DBD"), policy.base_segment,
        )
    with pytest.raises(RateLookupError, match="shadow DBD"):
        _load_shadow_rates(
            IllustrationRates(), policy, _shadow_config(),
            _ShadowRatesDb("COI", "SHADOW_INT"), policy.base_segment,
        )


def test_missing_optional_shadow_epu_loads_and_target_read_zero():
    policy = _shadow_policy()
    policy.plancode = "NOSHADOWEPU"
    result = IllustrationRates()

    _load_shadow_rates(
        result, policy, _shadow_config(),
        _ShadowRatesDb("COI", "SHADOW_INT", "DBD"), policy.base_segment,
    )

    assert result.shadow_int == [None, 1.0] and result.shadow_dbd == [None, 1.0]
    assert result.shadow_epu == [] and result.shadow_tpp == [] and result.shadow_epp == []
    assert result.shadow_tpr == [] and result.shadow_tpr_tbl1 == []
    for name in ("shadow_epu", "shadow_tpp", "shadow_epp"):
        assert get_rate(result, name, 1) == 0.0
    with pytest.raises(RateLookupError, match="shadow_int"):
        get_rate(IllustrationRates(), "shadow_int", 1)


def test_sgul15s_ny_has_shadow_config_on_base_scale_s_rates():
    config = load_plancode("1U146200")

    assert config.shadow_plancode == "CCV46100"
    assert config.shadow_late_payment_forgiveness is True


def _totals_ctx(*, forgiveness, ytd=None, td=None):
    return SimpleNamespace(
        config=SimpleNamespace(shadow_late_payment_forgiveness=forgiveness),
        state=SimpleNamespace(shadow_premiums_ytd=ytd, shadow_premiums_to_date=td),
    )


def _totals_work(*, month, av_ytd, av_td, av_gross):
    return SimpleNamespace(
        next_month=month,
        prem=SimpleNamespace(premiums_ytd=av_ytd, premiums_to_date=av_td, gross_premium=av_gross),
    )


def test_shadow_premium_totals_follow_the_shadow_crediting_month():
    from suiteview.illustration.core.calc_engine import _shadow_premium_totals

    # Annual 1,200 received just before the anniversary: the AV buckets it to
    # month 1, the shadow credits it in month 12 (forgiveness). In the next
    # month 12 the shadow's YTD before the new premium is 0, not the AV's 1,200.
    ctx = _totals_ctx(forgiveness=True, ytd=0.0, td=1_200.0)
    work = _totals_work(month=12, av_ytd=1_200.0, av_td=2_400.0, av_gross=0.0)
    assert _shadow_premium_totals(ctx, work, 1_200.0) == (1_200.0, 2_400.0)
    # Month 1: the AV's bucketed 1,200 was already credited by the shadow.
    ctx = _totals_ctx(forgiveness=True, ytd=1_200.0, td=2_400.0)
    work = _totals_work(month=1, av_ytd=1_200.0, av_td=3_600.0, av_gross=1_200.0)
    assert _shadow_premium_totals(ctx, work, 0.0) == (0.0, 2_400.0)


def test_shadow_premium_totals_use_av_totals_without_forgiveness_or_history():
    from suiteview.illustration.core.calc_engine import _shadow_premium_totals

    work = _totals_work(month=5, av_ytd=500.0, av_td=5_500.0, av_gross=100.0)
    assert _shadow_premium_totals(_totals_ctx(forgiveness=False), work, 100.0) == (500.0, 5_500.0)
    assert _shadow_premium_totals(_totals_ctx(forgiveness=True), work, 60.0) == (460.0, 5_460.0)