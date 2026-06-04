from datetime import date
from types import SimpleNamespace

from suiteview.illustration.core import illustration_policy_service
from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.illustration.core.input_compiler import compile_month_inputs
from suiteview.polview.services import glp_exception


def test_zero_premium_survival_still_reports_negative_glp_anniversary_adjustment(monkeypatch):
    ill_policy = IllustrationPolicyData(
        policy_number="GLPNEG",
        issue_date=date(2020, 7, 1),
        valuation_date=date(2024, 6, 1),
        policy_year=4,
        account_value=50_000.0,
        premiums_paid_to_date=9_000.0,
        withdrawals_to_date=0.0,
        accumulated_glp=10_000.0,
        glp=-2_000.0,
        gsp=0.0,
    )

    monkeypatch.setattr(
        glp_exception,
        "check_forecast_availability",
        lambda _policy: glp_exception.GlpForecastAvailability(True, "available", ill_policy),
    )

    class FakeEngine:
        def project(self, *_args, months, **_kwargs):
            return [
                SimpleNamespace(
                    date=date(2024, 6, 1),
                    policy_year=4,
                    policy_month=1,
                    total_deduction=0.0,
                    av_end_of_month=50_000.0,
                    lapsed=False,
                    gross_premium=0.0,
                    net_premium=0.0,
                    target_load=0.0,
                    excess_load=0.0,
                    flat_load=0.0,
                    interest_credited=0.0,
                )
            ] + [
                SimpleNamespace(
                    date=date(2024, 6, 1),
                    policy_year=4,
                    policy_month=month,
                    total_deduction=100.0,
                    av_end_of_month=50_000.0 - (month * 100.0),
                    lapsed=False,
                    gross_premium=0.0,
                    net_premium=0.0,
                    target_load=0.0,
                    excess_load=0.0,
                    flat_load=0.0,
                    interest_credited=0.0,
                )
                for month in range(1, months + 1)
            ]

    monkeypatch.setattr(glp_exception, "IllustrationEngine", FakeEngine)

    source_policy = SimpleNamespace(fetch_table=lambda _name: [])

    result = glp_exception.calculate_glp_exception(source_policy, date(2025, 7, 1))

    assert result.total_required_premium_after_load == 0.0
    assert result.accumulated_glp_prior_to_target == 8_000.0
    assert result.premium_td_on_target_date == 9_000.0
    assert result.adjustment_to_accum_glp_pre_calc == 1_000.0
    assert result.force_out_required is True
    assert result.force_out_amount == 1_000.0
    assert result.new_glp is None
    assert result.adjustment_to_accum_glp == 0.0
    assert result.new_accum_glp == result.premium_td_on_target_date


def test_glp_level_premium_inputs_add_catch_up_premium_for_negative_account_value():
    policy = IllustrationPolicyData(
        issue_date=date(2020, 1, 15),
        duration=53,
        policy_year=5,
        account_value=-24.75,
    )

    inputs = glp_exception._level_premium_inputs(policy, 3, 100.0)
    compiled = compile_month_inputs(policy, inputs, 3)

    assert compiled[54].unscheduled_premium == 25.75
    assert compiled[54].scheduled_premium is None
    assert compiled[55].unscheduled_premium == 100.0
    assert compiled[55].scheduled_premium is None
    assert compiled[56].unscheduled_premium == 100.0


def test_glp_result_reports_no_glp_adjustment_when_pre_calc_not_needed():
    policy = IllustrationPolicyData(
        issue_date=date(2020, 7, 1),
        valuation_date=date(2024, 6, 1),
        policy_year=4,
        account_value=50_000.0,
        premiums_paid_to_date=1_000.0,
        withdrawals_to_date=0.0,
        accumulated_glp=10_000.0,
        glp=-2_000.0,
        gsp=0.0,
    )

    result = glp_exception._build_result(
        policy,
        date(2025, 7, 1),
        13,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        [],
        glp_exception.PremiumAdjustmentSinceValuation(),
        policy.account_value,
        policy.premiums_paid_to_date,
    )

    assert result.adjustment_to_accum_glp_pre_calc == 0.0
    assert result.new_glp is None
    assert result.adjustment_to_accum_glp == 0.0
    assert result.new_accum_glp == result.premium_td_on_target_date
    assert result.glp_adjustment_message == "NO ADJUSTMENT NEEDED"


def test_glp_result_uses_premiums_less_accum_withdrawals_for_target_test():
    policy = IllustrationPolicyData(
        issue_date=date(2020, 7, 1),
        valuation_date=date(2024, 6, 1),
        policy_year=4,
        account_value=50_000.0,
        premiums_paid_to_date=12_000.0,
        withdrawals_to_date=4_000.0,
        accumulated_glp=10_000.0,
        glp=-2_000.0,
        gsp=0.0,
    )

    result = glp_exception._build_result(
        policy,
        date(2025, 7, 1),
        13,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        [],
        glp_exception.PremiumAdjustmentSinceValuation(),
        policy.account_value,
        policy.premiums_paid_to_date,
    )

    assert result.accumulated_glp_prior_to_target == 8_000.0
    assert result.premium_td_on_target_date == 8_000.0
    assert result.adjustment_to_accum_glp_pre_calc == 0.0
    assert result.force_out_required is False
    assert result.glp_adjustment_message == "NO ADJUSTMENT NEEDED"


def test_glp_result_with_premium_needed_recalculates_adjustment_with_zero_glp():
    policy = IllustrationPolicyData(
        issue_date=date(2020, 7, 1),
        valuation_date=date(2024, 6, 1),
        policy_year=4,
        account_value=50_000.0,
        premiums_paid_to_date=9_000.0,
        withdrawals_to_date=0.0,
        accumulated_glp=10_000.0,
        glp=-2_000.0,
        gsp=0.0,
    )

    result = glp_exception._build_result(
        policy,
        date(2025, 7, 1),
        13,
        0.0,
        0.0,
        0.0,
        0.0,
        3_000.0,
        [],
        glp_exception.PremiumAdjustmentSinceValuation(),
        policy.account_value,
        policy.premiums_paid_to_date,
    )

    assert result.accumulated_glp_prior_to_target == 8_000.0
    assert result.premium_td_on_target_date == 12_000.0
    assert result.new_glp == 0.0
    assert result.adjustment_to_accum_glp == 2_000.0
    assert result.new_accum_glp == 12_000.0
    assert result.force_out_required is False


def test_glp_result_new_accum_glp_equals_target_premium_basis_when_adjustment_needed():
    policy = IllustrationPolicyData(
        issue_date=date(2020, 7, 1),
        valuation_date=date(2024, 6, 1),
        policy_year=4,
        account_value=50_000.0,
        premiums_paid_to_date=10_000.0,
        withdrawals_to_date=1_000.0,
        accumulated_glp=7_000.0,
        glp=1_000.0,
        gsp=0.0,
    )

    result = glp_exception._build_result(
        policy,
        date(2025, 7, 1),
        13,
        0.0,
        0.0,
        0.0,
        0.0,
        4_000.0,
        [],
        glp_exception.PremiumAdjustmentSinceValuation(),
        policy.account_value,
        policy.premiums_paid_to_date,
    )

    assert result.accumulated_glp_prior_to_target == 8_000.0
    assert result.premium_td_on_target_date == 13_000.0
    assert result.adjustment_to_accum_glp == 5_000.0
    assert result.new_accum_glp == result.premium_td_on_target_date
    assert result.force_out_required is False


def test_illustration_policy_data_uses_regular_plus_additional_premium(monkeypatch):
    class FakeRates:
        def get_band(self, *_args):
            return 1

    class FakePolicyInfo:
        exists = True
        base_plancode = "TESTUL"
        issue_date = date(2020, 1, 1)
        valuation_date = date(2024, 6, 1)
        base_issue_age = 35
        base_sex_code = "M"
        base_rate_class = "N"
        base_total_face_amount = 100_000.0
        db_option_code = "A"
        modal_premium = 100.0
        billing_frequency = 1
        policy_year = 5
        policy_month = 6
        attained_age = 39
        guaranteed_interest_rate = 4.0
        def_of_life_ins_code = "1"
        glp = 1_000.0
        gsp = 5_000.0
        accumulated_glp_target = 4_000.0
        corridor_percent = 100.0
        mtp = 100.0
        ctp = 1_200.0
        accumulated_mtp_target = 3_000.0
        map_date = None
        premium_td = 19_435.85
        premium_ytd = 500.0
        cost_basis = 19_435.85
        total_regular_loan_principal = 0.0
        total_regular_loan_accrued = 0.0
        total_preferred_loan_principal = 0.0
        total_preferred_loan_accrued = 0.0
        total_variable_loan_principal = 0.0
        total_variable_loan_accrued = 0.0
        total_withdrawals = 0.0
        gav = 0.0
        is_mec = False
        company_code = "01"
        primary_insured_name = "Test Policy"
        product_type = "UL"
        issue_state = "TX"
        company_name = "TEST"
        preferred_loans_available = False

        def mv_av(self, _index):
            return 1_000.0

        def mv_coi_charge(self, _index):
            return 0.0

        def mv_expense_charge(self, _index):
            return 0.0

        def mv_other_charge(self, _index):
            return 0.0

        def mv_monthly_deduction(self, _index):
            return 0.0

        def get_base_coverages(self):
            return []

        def get_substandard_ratings(self):
            return []

        def get_benefits(self):
            return []

        def get_riders(self):
            return []

    monkeypatch.setattr(illustration_policy_service, "get_policy_info", lambda *_args: FakePolicyInfo())
    monkeypatch.setattr(illustration_policy_service, "Rates", FakeRates)

    policy = illustration_policy_service.build_illustration_data("UL001892")

    assert policy.premiums_paid_to_date == 19_435.85