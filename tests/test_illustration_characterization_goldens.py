"""Golden characterization for policy-data mapping and illustration solvers."""
from __future__ import annotations

import dataclasses
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from dateutil.relativedelta import relativedelta

from suiteview.illustration.core import calc_engine, illustration_policy_service
from suiteview.illustration.core.guideline_calc import search_guideline_premiums
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.solve_level_to_exception import (
    solve_level_to_exception,
)
from suiteview.illustration.core.solve_loan_payoff import solve_loan_payoff
from suiteview.illustration.core.solve_lumpsum_to_next_premium import (
    solve_lumpsum_to_next_premium,
)
from suiteview.illustration.core.solve_max_level_allowed import solve_max_level_allowed
from suiteview.illustration.core.solve_premium_duration import solve_premium_duration
from suiteview.illustration.core.solve_premium_to_target import solve_premium_to_target
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    PolicyChangeEvent,
    PolicyChangeKind,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)
from tests.test_illustration_policy_service import _FakePolicyInfo, _FakeRates

GOLDEN_DIR = Path(__file__).parent / "golden" / "policy_data"


def _normalize(value):
    if dataclasses.is_dataclass(value):
        return _normalize(dataclasses.asdict(value))
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _normalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def _golden_text(value) -> str:
    return json.dumps(_normalize(value), indent=2, sort_keys=True, allow_nan=False) + "\n"


def _build_policy(source, *, iul: bool = False, config: PlancodeConfig | None = None):
    old_get_policy_info = illustration_policy_service.get_policy_info
    old_rates = illustration_policy_service.ULRates
    old_tables = illustration_policy_service.IndexAssumptionTables
    old_load_plancode = illustration_policy_service.load_plancode
    old_is_iul_plan = illustration_policy_service.is_iul_plan
    try:
        illustration_policy_service.get_policy_info = lambda *_args: source
        illustration_policy_service.ULRates = lambda *_args, **_kwargs: _FakeRates()
        illustration_policy_service.IndexAssumptionTables = _FakeRates
        illustration_policy_service.load_plancode = (
            lambda _plancode: config
            or PlancodeConfig(plancode="TESTUL", gint=0.0, dbd=0.0)
        )
        illustration_policy_service.is_iul_plan = lambda _plancode: iul
        return illustration_policy_service.build_illustration_data(
            "U0126221",
            illustration_date=date(2026, 7, 29),
        )
    finally:
        illustration_policy_service.get_policy_info = old_get_policy_info
        illustration_policy_service.ULRates = old_rates
        illustration_policy_service.IndexAssumptionTables = old_tables
        illustration_policy_service.load_plancode = old_load_plancode
        illustration_policy_service.is_iul_plan = old_is_iul_plan


def policy_data_cases() -> dict[str, IllustrationPolicyData]:
    standard = _build_policy(_FakePolicyInfo())

    rated_source = _FakePolicyInfo()
    rated_table_cease = date(2030, 6, 15)
    rated_flat_cease = date(2031, 7, 15)
    rated_source.get_substandard_ratings = lambda: [
        SimpleNamespace(
            coverage_phase=1,
            type_code="T",
            table_rating_numeric=3,
            flat_cease_date=rated_table_cease,
        ),
        SimpleNamespace(
            coverage_phase=1,
            type_code="F",
            table_rating_numeric=0,
            flat_amount=12.50,
            flat_cease_date=rated_flat_cease,
        ),
    ]
    rated = _build_policy(rated_source)

    iul_source = _FakePolicyInfo()
    iul_source.product_type = "IUL"
    iul_source.get_fund_buckets = lambda *, current_only: [
        SimpleNamespace(fund_id="FIXED", csv_amount=6_000.0),
        SimpleNamespace(fund_id="IX", csv_amount=4_000.0),
    ]
    iul_source.get_loan_values_dict = lambda: {"IX": 250.0}
    iul_source.get_premium_allocation_dict = lambda: {"FIXED": 60.0, "IX": 40.0}
    iul = _build_policy(iul_source, iul=True)
    return {
        "fake_standard_policy": standard,
        "fake_substandard_policy": rated,
        "fake_iul_policy": iul,
    }


def _premium_level(future_inputs: IllustrationInputSet, start_year: int) -> float:
    return max(
        transaction.amount
        for transaction in future_inputs.scheduled_transactions
        if transaction.kind == TransactionKind.PREMIUM
        and transaction.policy_year == start_year
    )


def _target_states(issue_age: int, years: int, value_fn) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            policy_year=year,
            policy_month=month,
            attained_age=issue_age + year - 1,
            av_end_of_month=value_fn(year) if month == 12 else 0.0,
            ending_sv=value_fn(year) if month == 12 else 0.0,
            shadow_eav=value_fn(year) if month == 12 else 0.0,
        )
        for year in range(1, years + 1)
        for month in range(1, 13)
    ]


def _premium_duration_years(future_inputs: IllustrationInputSet) -> int:
    stops = [
        entry.policy_year
        for entry in future_inputs.scheduled_transactions
        if entry.kind == TransactionKind.PREMIUM
        and entry.policy_year > 1
        and entry.amount == 0.0
    ]
    return (min(stops) - 1) if stops else 20


class _PremiumTargetEngine:
    def project(self, _policy, *, future_inputs=None, **_kwargs):
        premium = _premium_level(future_inputs, 1)
        return _target_states(50, 20, lambda _year: premium * 100.0)


class _PremiumDurationEngine:
    def project(self, _policy, *, future_inputs=None, **_kwargs):
        years = _premium_duration_years(future_inputs)
        return _target_states(50, 20, lambda _year: years * 1_000.0)


class _LumpsumEngine:
    def project(self, policy, months, future_inputs, options, stop_on_lapse):
        forecast = policy.issue_date + relativedelta(months=policy.duration)
        lumpsum = sum(
            transaction.amount
            for transaction in future_inputs.dated_transactions
            if transaction.kind == TransactionKind.PREMIUM
            and transaction.effective_date == forecast
        )
        states = [MonthlyState(date=policy.issue_date + relativedelta(months=policy.duration - 1))]
        for offset in range(1, months + 1):
            when = policy.issue_date + relativedelta(months=policy.duration - 1 + offset)
            surrender_value = -100.0 + lumpsum
            states.append(MonthlyState(
                date=when,
                policy_year=2,
                surrender_value=surrender_value,
                av_less_loans=surrender_value,
                accum_mtp_less_prem=surrender_value,
                lapsed=surrender_value < 0.0,
                applied_lumpsum=lumpsum if when == forecast else 0.0,
            ))
        return states


class _LoanEngine:
    def project(self, policy, months, future_inputs, options, stop_on_lapse):
        repayments = {}
        for transaction in future_inputs.dated_transactions:
            if transaction.kind == TransactionKind.LOAN_REPAYMENT:
                repayments[transaction.effective_date] = (
                    repayments.get(transaction.effective_date, 0.0) + transaction.amount
                )
        balance = 1_200.0
        states = []
        for offset in range(months + 1):
            when = policy.issue_date + relativedelta(months=policy.duration - 1 + offset)
            balance = max(0.0, balance - repayments.get(when, 0.0))
            beginning = balance
            states.append(MonthlyState(
                date=when,
                rg_loan_princ=beginning,
                policy_debt=balance,
            ))
        return states


def _level_state(**overrides) -> SimpleNamespace:
    state = {
        "attained_age": 60,
        "policy_year": 1,
        "date": date(2030, 6, 6),
        "exception_prem_mode": False,
        "gp_exception_prem_gross": 0.0,
        "guideline_limit": 100_000.0,
        "prem_less_wd": 0.0,
        "applied_scheduled_premium": 0.0,
        "applied_lumpsum": 0.0,
        "av_end_of_month": 1.0,
        "premiums_to_date": 0.0,
        "applied_loan_repayment": 0.0,
    }
    state.update(overrides)
    return SimpleNamespace(**state)


class _LevelEngine:
    def project(self, _policy, *, future_inputs=None, **_kwargs):
        premium = _premium_level(future_inputs, 1)
        if premium < 2_000.0 - 1e-9:
            return [_level_state(), _level_state(attained_age=70, policy_year=5)]
        room = 0.0 if premium >= 2_500.0 - 1e-9 else 500.0
        return [
            _level_state(),
            _level_state(attained_age=80, policy_year=3),
            _level_state(
                attained_age=90,
                policy_year=6,
                exception_prem_mode=True,
                gp_exception_prem_gross=250.0,
                prem_less_wd=100_000.0 - room,
            ),
            _level_state(
                attained_age=121,
                policy_year=7,
                exception_prem_mode=True,
                gp_exception_prem_gross=250.0,
                premiums_to_date=premium,
            ),
        ]


def _max_level_projection(issue_age: int, years: int) -> list[SimpleNamespace]:
    states = [SimpleNamespace(
        policy_year=0,
        policy_month=0,
        attained_age=0,
        gsp=0.0,
        accumulated_glp=0.0,
        prem_less_wd=0.0,
        av_end_of_month=1.0,
        premiums_to_date=0.0,
        gp_exception_prem_gross=0.0,
        applied_loan_repayment=0.0,
    )]
    for year in range(1, years + 1):
        for month in range(1, 13):
            states.append(SimpleNamespace(
                policy_year=year,
                policy_month=month,
                attained_age=issue_age + year - 1,
                gsp=1_000.0,
                accumulated_glp=10_000.0,
                prem_less_wd=200.0,
                av_end_of_month=1.0,
                premiums_to_date=0.0,
                gp_exception_prem_gross=0.0,
                applied_loan_repayment=0.0,
            ))
    return states


class _MaxLevelEngine:
    def project(self, _policy, *, future_inputs=None, **_kwargs):
        return _max_level_projection(50, 71)


def _lumpsum_policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        plancode="TEST",
        issue_date=date(2020, 1, 15),
        duration=8,
        billing_frequency=12,
        modal_premium=500.0,
    )


def _guideline_policy(maturity: int) -> IllustrationPolicyData:
    return IllustrationPolicyData(
        plancode="MATURITY",
        issue_date=date(2000, 6, 1),
        issue_age=40,
        face_amount=12_000.0,
        units=12.0,
        db_option="A",
        maturity_age=maturity,
        current_interest_rate=0.0,
        glp=1_000.0,
        segments=[CoverageSegment(
            coverage_phase=1,
            issue_date=date(2000, 6, 1),
            issue_age=40,
            face_amount=12_000.0,
            units=12.0,
        )],
    )


def _guideline_result():
    policy = _guideline_policy(95)
    config = PlancodeConfig(
        plancode="MATURITY",
        maturity_age=95,
        premium_load="0",
        epu_code="0",
        mfee="0",
        poav_code="0",
        corridor_code=None,
        snet_period=0,
    )
    old_load_plancode = calc_engine.load_plancode
    try:
        calc_engine.load_plancode = lambda _plancode: config
        return search_guideline_premiums(
            policy,
            config,
            IllustrationRates(),
            attained_age=94,
            as_of=date(2054, 6, 1),
        )
    finally:
        calc_engine.load_plancode = old_load_plancode


def solver_output_cases() -> dict[str, object]:
    premium_policy = IllustrationPolicyData(
        def_of_life_ins="GPT",
        maturity_age=121,
        issue_age=50,
        billing_frequency=1,
        modal_premium=100.0,
        ccv_active=True,
    )
    duration_policy = IllustrationPolicyData(issue_age=50, maturity_age=70)
    loan_policy = IllustrationPolicyData(
        plancode="TEST",
        issue_date=date(2020, 1, 15),
        duration=12,
    )
    loan_dates = [date(2020, 1, 15) + relativedelta(years=year) for year in (1, 2, 3)]
    max_policy = IllustrationPolicyData(
        def_of_life_ins="GPT",
        maturity_age=121,
        issue_age=50,
        billing_frequency=1,
        modal_premium=100.0,
    )
    change = PolicyChangeEvent(
        kind=PolicyChangeKind.FACE_AMOUNT,
        effective_date=date(2027, 11, 9),
        value=75_000.0,
    )
    return {
        "premium_to_target": solve_premium_to_target(
            premium_policy,
            target="shadow",
            amount=3_437.99,
            at_age=60,
            mode="M",
            start_policy_year=1,
            engine=_PremiumTargetEngine(),
        ),
        "lumpsum_to_next_premium": solve_lumpsum_to_next_premium(
            _lumpsum_policy(),
            config=PlancodeConfig(lapse_value="SV", snet_period=10),
            engine=_LumpsumEngine(),
        ),
        "loan_payoff": solve_loan_payoff(
            loan_policy,
            repayment_dates=loan_dates,
            check_date=date(2020, 1, 15) + relativedelta(years=4),
            engine=_LoanEngine(),
        ),
        "level_to_exception": solve_level_to_exception(
            IllustrationPolicyData(
                def_of_life_ins="GPT",
                maturity_age=121,
                issue_age=50,
                billing_frequency=1,
                modal_premium=100.0,
                glp=1_200.0,
            ),
            mode="A",
            engine=_LevelEngine(),
            base_future_inputs=IllustrationInputSet(),
        ),
        "premium_duration": solve_premium_duration(
            duration_policy,
            premium=100.0,
            mode="M",
            target="av",
            amount=5_500.0,
            at_age=60,
            engine=_PremiumDurationEngine(),
        ),
        "max_level_allowed": solve_max_level_allowed(
            max_policy,
            mode="M",
            start_policy_year=3,
            base_future_inputs=IllustrationInputSet(policy_changes=[change]),
            engine=_MaxLevelEngine(),
        ),
        "guideline_search": _guideline_result(),
    }


def test_build_illustration_data_matches_policy_data_goldens():
    for name, policy in policy_data_cases().items():
        assert _golden_text(policy) == (GOLDEN_DIR / f"{name}.json").read_text(encoding="utf-8")


def test_solver_characterization_outputs_match_golden():
    assert _golden_text(solver_output_cases()) == (
        GOLDEN_DIR / "solver_outputs.json"
    ).read_text(encoding="utf-8")
