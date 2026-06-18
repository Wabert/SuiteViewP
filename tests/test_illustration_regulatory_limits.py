from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.illustration_policy_service import _translate_doli
from suiteview.illustration.models.input_set import IllustrationOptions
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def test_blank_definition_of_life_code_stays_blank():
    assert _translate_doli("") == ""
    assert _translate_doli("   ") == ""


def test_blank_definition_of_life_disables_guideline_and_tamra_caps():
    policy = IllustrationPolicyData(
        def_of_life_ins="",
        is_mec=False,
        tamra_7pay_level=1_000.0,
    )

    cap = calc_engine._guideline_premium_cap(
        IllustrationOptions(),
        policy,
        guideline_limit=0.0,
        premiums_to_date=5_000.0,
        withdrawals_to_date=0.0,
        accumulated_7pay=5_000.0,
        tamra_year=1,
    )

    assert policy.has_defined_life_insurance is False
    assert cap is None
    assert calc_engine._guideline_limit_reached(
        IllustrationOptions(), policy, 0.0, 5_000.0, 0.0
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