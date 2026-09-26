from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.illustration_policy_service import _translate_doli
from suiteview.illustration.core.premium_allowance import (
    PremiumAllowanceInput,
    compute_premium_allowances,
)
from suiteview.illustration.core.target_premium import floor_monthly_cent
from suiteview.illustration.models.input_set import IllustrationOptions
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def test_blank_definition_of_life_code_stays_blank():
    assert _translate_doli("") == ""
    assert _translate_doli("   ") == ""


def test_glp_and_gsp_are_both_monthly_normalized():
    annual_amount = 1_000.009

    assert floor_monthly_cent(annual_amount) == 999.96


def test_blank_definition_of_life_disables_guideline_and_tamra_caps():
    policy = IllustrationPolicyData(
        def_of_life_ins="",
        is_mec=False,
        tamra_7pay_level=1_000.0,
    )

    # Premiums far past the guideline limit and the 7-pay level, but with no
    # defined life insurance neither the GP nor the TAMRA side may bind.
    options = IllustrationOptions()
    allowances = compute_premium_allowances(PremiumAllowanceInput(
        is_cvat=policy.is_cvat,
        is_gpt=policy.is_gpt,
        tefra_force=options.guideline_cap_enabled,
        tamra_force=(
            options.tamra_cap_enabled
            and policy.has_defined_life_insurance
            and policy.tamra_7pay_level > 0
        ),
        mec_bypass=policy.is_mec,
        guideline_limit=0.0,
        prem_less_wd=5_000.0,
        force_out=0.0,
        loan_repay_from_forceout=0.0,
        seven_pay_level=policy.tamra_7pay_level,
        amount_in_7pay=5_000.0,
        tamra_year=1,
        tamra_month_of_year=1,
        policy_month=1,
        npt_premium=0.0,
        tamra_reset=False,
        requested_scheduled=600.0,
        requested_lumpsum=0.0,
        payment_count_policy_year=12,
        payment_count_tamra_year=12,
        has_loan_balance=False,
        beginning_of_year=True,
        policy_anniversary=True,
        prior_scheduled_prem_cap=0.0,
        levelizing_premium=options.levelizing_premium,
        loan_repay_from_lumpsum=0.0,
        loan_repay_from_scheduled=0.0,
        ln_repay_left_over=0.0,
    ))

    assert policy.has_defined_life_insurance is False
    # No cap binds -> the full requested premium is accepted.
    assert allowances.applied_total_premium == 600.0
    # SX: the GP level cap (NU) never binds the premium here, so Levelized Max
    # Premium (NW) sits at the full requested premium, not at NU -> not reached.
    config = PlancodeConfig(plancode="1U143900", maturity_age=121)
    assert calc_engine._guideline_limit_reached(
        config, allowances,
        attained_age=45,
        beginning_of_year=True,
        prior_limit_reached=False,
    ) is False


def test_blank_definition_of_life_disables_guideline_forceout():
    forceout, withdrawals, av = calc_engine._apply_guideline_forceout(
        gsp=0.0,
        accumulated_glp=0.0,
        premiums_to_date=5_000.0,
        withdrawals_to_date=0.0,
        account_value_before_premium=1_000.0,
        enabled=True,
        has_guideline_limit=False,
        prior_exception_mode=False,
    )

    assert forceout == 0.0
    assert withdrawals == 0.0
    assert av == 1_000.0