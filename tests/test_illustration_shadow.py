from types import SimpleNamespace

import pytest

from suiteview.illustration.core.calc_engine import _shadow_rider_charges_from_deduction
from suiteview.illustration.core.rate_loader import (
    IllustrationRates,
    RateLookupError,
    _load_shadow_rates,
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
        shadow_dbd_fallback=0.0,
        shadow_int_rate_fallback=0.0,
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
        shadow_dbd_fallback=0.0,
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
        shadow_dbd_fallback=0.0,
        shadow_int_rate_fallback=0.0,
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
        shadow_dbd_fallback=0.0,
        shadow_int_rate_fallback=0.12,
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


def test_shadow_subtracts_gross_withdrawal_before_nar():
    policy = _shadow_policy()
    config = PlancodeConfig(
        shadow_dbd_fallback=0.0,
        shadow_int_rate_fallback=0.0,
    )
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


def test_missing_table_shadow_rates_raise_loudly():
    policy = _shadow_policy()
    policy.plancode = "MISSINGSHADOW"
    config = PlancodeConfig(
        shadow_plancode="CCVTEST",
        shadow_availability="Inherent",
        shadow_epu_fallback=0.0,
        shadow_int_rate_fallback=0.0,
        shadow_dbd_fallback=0.0,
    )

    class Rates:
        def get_rates(self, rate_type, *_args, **_kwargs):
            return [None, 1.0] if rate_type == "COI" else None

        def get_mtp(self, *_args, **_kwargs):
            return 1.0

        def get_tbl1_mtp(self, *_args, **_kwargs):
            return 0.0

        def is_loaded(self, _plancode):
            return True

    with pytest.raises(RateLookupError, match="shadow TPP"):
        _load_shadow_rates(
            IllustrationRates(),
            policy,
            config,
            Rates(),
            policy.base_segment,
        )


def test_sgul15s_ny_has_shadow_config_on_base_scale_s_rates():
    config = load_plancode("1U146200")

    assert config.shadow_plancode == "CCV46100"
    assert config.shadow_target_fallback is None
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