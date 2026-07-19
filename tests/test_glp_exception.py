from datetime import date
from types import SimpleNamespace

import pytest

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


def test_policy_support_forecast_tracks_guideline_forceout_and_negative_av(monkeypatch):
    ill_policy = IllustrationPolicyData(
        policy_number="FORECAST",
        issue_date=date(2020, 1, 1),
        valuation_date=date(2024, 1, 1),
        duration=48,
        policy_year=4,
        policy_month=1,
        account_value=1_000.0,
        premiums_paid_to_date=1_000.0,
        withdrawals_to_date=100.0,
        accumulated_glp=1_200.0,
        glp=500.0,
        gsp=0.0,
    )

    monkeypatch.setattr(
        glp_exception,
        "check_forecast_availability",
        lambda _policy: glp_exception.GlpForecastAvailability(True, "available", ill_policy),
    )

    class FakeEngine:
        def project(self, policy, *, months, future_inputs=None, **_kwargs):
            compiled = compile_month_inputs(policy, future_inputs, months)
            running_account_value = policy.account_value
            accumulated_glp = policy.accumulated_glp
            premiums_to_date = policy.premiums_paid_to_date
            withdrawals_to_date = policy.withdrawals_to_date
            states = [
                SimpleNamespace(
                    date=date(2024, 1, 1),
                    policy_year=4,
                    policy_month=1,
                    is_anniversary=False,
                    total_deduction=0.0,
                    gross_premium=0.0,
                    net_premium=0.0,
                    interest_credited=0.0,
                    monthly_interest_rate=0.01,
                    glp=policy.glp,
                    accumulated_glp=accumulated_glp,
                    premiums_to_date=premiums_to_date,
                    withdrawals_to_date=withdrawals_to_date,
                    guideline_forceout=0.0,
                    guideline_av_before_monthly_deduction=running_account_value,
                    av_end_of_month=running_account_value,
                )
            ]
            for offset, month_date, deduction in (
                (1, date(2024, 2, 1), 200.0),
                (2, date(2024, 3, 1), 1_000.0),
                (3, date(2024, 4, 1), 2_000.0),
            ):
                month_inputs = compiled[policy.duration + offset]
                gross_premium = month_inputs.total_premium
                net_premium = gross_premium * 0.9
                is_anniversary = offset == 2
                interest_credited = max(running_account_value * 0.01, 0.0)
                if is_anniversary:
                    accumulated_glp += policy.glp
                premiums_to_date += gross_premium
                forceout = max(0.0, (premiums_to_date - withdrawals_to_date) - accumulated_glp)
                withdrawals_to_date += forceout
                av_before_deduction = running_account_value + interest_credited + net_premium - forceout
                running_account_value = av_before_deduction - deduction
                states.append(
                    SimpleNamespace(
                        date=month_date,
                        policy_year=5 if offset == 2 else 4,
                        policy_month=1 if offset == 2 else offset + 1,
                        is_anniversary=is_anniversary,
                        total_deduction=deduction,
                        gross_premium=gross_premium,
                        net_premium=net_premium,
                        interest_credited=interest_credited,
                        monthly_interest_rate=0.01,
                        glp=policy.glp,
                        accumulated_glp=accumulated_glp,
                        premiums_to_date=premiums_to_date,
                        withdrawals_to_date=withdrawals_to_date,
                        guideline_forceout=forceout,
                        guideline_av_before_monthly_deduction=av_before_deduction,
                        av_end_of_month=running_account_value,
                    )
                )
            return states[: months + 1]

    monkeypatch.setattr(glp_exception, "IllustrationEngine", FakeEngine)

    source_policy = SimpleNamespace(fetch_table=lambda _name: [])

    result = glp_exception.calculate_policy_support_forecast(
        source_policy,
        date(2024, 5, 1),
        500.0,
        "Monthly",
    )

    month_one = result.rows[1]
    assert month_one.premiums_paid_to_date == 1_500.0
    assert month_one.accumulated_glp == 1_200.0
    assert month_one.force_out == 200.0
    assert month_one.accumulated_withdrawals == 300.0
    assert month_one.interest_credited == pytest.approx(10.0)
    assert month_one.account_value_before_monthly_deduction == pytest.approx(1_260.0)
    assert month_one.account_value == pytest.approx(1_060.0)

    anniversary_month = result.rows[2]
    assert anniversary_month.accumulated_glp == 1_700.0
    assert anniversary_month.force_out == 0.0

    assert result.rows[3].force_out == 500.0
    assert result.rows[3].interest_credited < anniversary_month.interest_credited
    assert result.rows[3].account_value == pytest.approx(-1_524.194)


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
        def get_band(self, *_args, **_kwargs):
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
        age_at_maturity = 100
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
        variable_loan_charge_rate = 0.0775
        total_withdrawals = 0.0
        gav = 0.0
        is_mec = False
        tamra_7pay_level = 0.0
        tamra_7pay_start_date = None
        tamra_7pay_av = 0.0
        company_code = "01"
        primary_insured_name = "Test Policy"
        primary_insured_birth_date = None
        product_type = "UL"
        issue_state = "TX"
        company_name = "TEST"
        preferred_loans_available = False

        def tamra_7pay_premium_paid(self, _year):
            return 0.0

        def tamra_7pay_withdrawals(self, _year):
            return 0.0

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
    assert policy.variable_loan_charge_rate == 0.0775