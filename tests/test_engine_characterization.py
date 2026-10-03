"""Golden characterization for the UL illustration monthly engine.

The golden JSON files intentionally record every ``MonthlyState`` field for a
small synthetic policy matrix.  They are generated from the current engine and
then treated as a byte-for-byte contract while refactoring the calculation
pipeline.
"""
from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine, ProjectionTiming
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.target_premium import TargetPremiumResult
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    PolicyChangeEvent,
    PolicyChangeKind,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)
from tests.corridor_fixtures import CORRIDOR_1

GOLDEN_ROOT = Path(__file__).parent / "golden" / "engine"
UPDATE_GOLDENS = os.environ.get("SV_UPDATE_ENGINE_GOLDENS") == "1"


@dataclass(frozen=True)
class EngineCase:
    """Synthetic no-DB projection case for byte-for-byte engine characterization."""

    name: str
    policy_factory: Callable[[], IllustrationPolicyData]
    config: PlancodeConfig
    rates: IllustrationRates
    months: int
    inputs_factory: Callable[[ProjectionTiming], IllustrationInputSet | None]
    options: IllustrationOptions = field(default_factory=IllustrationOptions)


def _coverage(*, phase: int = 1, face: float = 100_000.0, issue_age: int = 45) -> CoverageSegment:
    return CoverageSegment(
        coverage_phase=phase,
        issue_date=date(2016, 1, 15),
        issue_age=issue_age,
        rate_sex="M",
        rate_class="N",
        face_amount=face,
        original_face_amount=face,
        units=face / 1000.0,
    )


def _rates(*, coi: float = 2.4, scr: float = 4.0, tpp: float = 0.05) -> IllustrationRates:
    # Expense rates reproduce the cases' original flat configuration (5% premium load
    # on every premium, no EPU, $5 fee) now that the engine reads only rates.
    # ``tpp`` is the target load the exception-premium solve always read from rates.
    duration_rates = [0.0] + [coi] * 180
    expense_rates = [0.0] + [0.0] * 180
    surrender_rates = [0.0] + [scr] * 180
    return IllustrationRates(
        coi=duration_rates,
        segment_coi={1: duration_rates},
        epu=expense_rates,
        segment_epu={1: expense_rates},
        scr=surrender_rates,
        segment_scr={1: surrender_rates},
        mfee=[0.0] + [5.0] * 180,
        tpp=[0.0] + [tpp] * 180,
        epp=[0.0] + [0.05] * 180,
        mtp=420.0,
        ctp=600.0,
    )


def _config(plancode: str, *, lapse_value: str = "SV", cvat: bool = False) -> PlancodeConfig:
    return PlancodeConfig(
        plancode=plancode,
        prem_flat_load=1.25,
        gint=0.02,
        dbd=0.0,
        snet_by_issue_age={} if cvat else {age: 3 for age in range(0, 122)},
        lapse_value=lapse_value,
        interest_method="MonthlyCompounding",
    )


def _cashflow_policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        policy_number="CHAR-GPT",
        plancode="CHARGPT",
        def_of_life_ins="GPT",
        issue_date=date(2016, 1, 15),
        valuation_date=date(2026, 1, 15),
        issue_age=45,
        attained_age=55,
        maturity_age=121,
        policy_year=11,
        policy_month=1,
        duration=121,
        face_amount=100_000.0,
        units=100.0,
        db_option="B",
        account_value=15_000.0,
        cost_basis=13_500.0,
        premiums_paid_to_date=21_000.0,
        premiums_ytd=0.0,
        modal_premium=120.0,
        billing_frequency=1,
        glp=900.0,
        gsp=12_000.0,
        accumulated_glp=9_900.0,
        mtp=35.0,
        accumulated_mtp=4_200.0,
        ctp=600.0,
        current_interest_rate=0.045,
        guaranteed_interest_rate=0.02,
        tamra_7pay_start_date=date(2016, 1, 15),
        tamra_7pay_level=1_500.0,
        tamra_7year_contributions=[120.0, 120.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        regular_loan_principal=500.0,
        regular_loan_accrued=12.0,
        preferred_loan_principal=250.0,
        preferred_loan_accrued=6.0,
        segments=[_coverage()],
    )


def _cashflow_inputs(timing: ProjectionTiming) -> IllustrationInputSet:
    changes = []
    if timing == ProjectionTiming.ILLUSTRATION:
        changes.append(
            PolicyChangeEvent(
                PolicyChangeKind.DB_OPTION,
                date(2026, 3, 15),
                "A",
                {"new_glp": 960.0, "new_gsp": 12_600.0, "new_7pay": 1_650.0},
            )
        )
    return IllustrationInputSet(
        scheduled_transactions=[
            ScheduledTransaction(TransactionKind.PREMIUM, 11, 120.0, "M"),
            ScheduledTransaction(
                TransactionKind.LOAN,
                11,
                30.0,
                "M",
                {"loan_type": "regular"},
            ),
        ],
        dated_transactions=[
            DatedTransaction(TransactionKind.PREMIUM, date(2026, 2, 15), 75.0),
            DatedTransaction(TransactionKind.LOAN_REPAYMENT, date(2026, 3, 15), 40.0),
            DatedTransaction(TransactionKind.WITHDRAWAL, date(2026, 4, 15), 100.0),
        ],
        policy_changes=changes,
    )


def _run_from_issue_policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        policy_number="CHAR-CVAT",
        plancode="CHARCVAT",
        def_of_life_ins="CVAT",
        run_from_issue=True,
        issue_date=date(2024, 7, 31),
        valuation_date=date(2024, 6, 30),
        issue_age=50,
        attained_age=50,
        maturity_age=121,
        policy_year=1,
        policy_month=12,
        duration=0,
        face_amount=80_000.0,
        units=80.0,
        db_option="A",
        account_value=0.0,
        modal_premium=200.0,
        billing_frequency=1,
        current_interest_rate=0.04,
        guaranteed_interest_rate=0.02,
        segments=[_coverage(face=80_000.0, issue_age=50)],
    )


def _run_from_issue_inputs(_timing: ProjectionTiming) -> IllustrationInputSet:
    return IllustrationInputSet(
        scheduled_transactions=[
            ScheduledTransaction(TransactionKind.PREMIUM, 1, 200.0, "M"),
        ],
        dated_transactions=[
            DatedTransaction(TransactionKind.LOAN, date(2024, 8, 31), 25.0),
        ],
    )


def _iul_policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        policy_number="CHAR-IUL",
        plancode="CHARIUL",
        product_type="IUL",
        def_of_life_ins="GPT",
        issue_date=date(2017, 6, 1),
        valuation_date=date(2026, 6, 1),
        issue_age=42,
        attained_age=51,
        maturity_age=121,
        policy_year=10,
        policy_month=1,
        duration=109,
        face_amount=125_000.0,
        units=125.0,
        db_option="A",
        account_value=18_000.0,
        modal_premium=150.0,
        billing_frequency=1,
        glp=1_200.0,
        gsp=15_000.0,
        accumulated_glp=9_600.0,
        mtp=40.0,
        ctp=700.0,
        current_interest_rate=0.055,
        guaranteed_interest_rate=0.02,
        iul_declared_rate=0.045,
        iul_asset_charge_rate=0.003,
        premium_allocations={"FIXED": 0.4, "INDEX": 0.6},
        regular_loan_principal=300.0,
        variable_loan_principal=200.0,
        variable_loan_charge_rate=0.055,
        segments=[_coverage(face=125_000.0, issue_age=42)],
    )


def _iul_inputs(_timing: ProjectionTiming) -> IllustrationInputSet:
    return IllustrationInputSet(
        scheduled_transactions=[
            ScheduledTransaction(TransactionKind.PREMIUM, 10, 150.0, "M"),
        ],
        dated_transactions=[
            DatedTransaction(TransactionKind.LOAN, date(2026, 7, 1), 50.0, "variable"),
        ],
    )


def _mec_policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        policy_number="CHAR-MEC",
        plancode="CHARMEC",
        def_of_life_ins="GPT",
        issue_date=date(2000, 9, 1),
        valuation_date=date(2026, 10, 1),
        duration=314,
        policy_year=27,
        policy_month=2,
        issue_age=40,
        attained_age=66,
        maturity_age=95,
        face_amount=110_000.0,
        units=110.0,
        db_option="A",
        account_value=20_000.0,
        current_interest_rate=0.0,
        glp=100_000.0,
        tamra_7pay_start_date=date(2026, 10, 1),
        tamra_7pay_level=10_897.44,
        tamra_7year_contributions=[10_897.44, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        segments=[_coverage(face=110_000.0, issue_age=40)],
    )


def _mec_inputs(_timing: ProjectionTiming) -> IllustrationInputSet:
    return IllustrationInputSet(
        scheduled_transactions=[
            ScheduledTransaction(TransactionKind.PREMIUM, 1, 0.0, "A"),
            ScheduledTransaction(TransactionKind.PREMIUM, 28, 10_897.44, "A"),
        ]
    )


def _exception_policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        policy_number="CHAR-EXC",
        plancode="CHAREXC",
        def_of_life_ins="GPT",
        issue_date=date(2015, 1, 15),
        valuation_date=date(2026, 1, 15),
        issue_age=45,
        attained_age=56,
        maturity_age=121,
        policy_year=12,
        policy_month=1,
        duration=133,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        account_value=20.0,
        glp=0.0,
        gsp=1_000.0,
        accumulated_glp=1_000.0,
        premiums_paid_to_date=1_000.0,
        current_interest_rate=0.0,
        segments=[_coverage(face=100_000.0, issue_age=45)],
    )


def _lapse_policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        policy_number="CHAR-LAPSE",
        plancode="CHARLAPSE",
        def_of_life_ins="GPT",
        issue_date=date(2016, 9, 15),
        valuation_date=date(2026, 9, 15),
        issue_age=50,
        attained_age=60,
        maturity_age=121,
        policy_year=11,
        policy_month=1,
        duration=121,
        face_amount=150_000.0,
        units=150.0,
        db_option="A",
        account_value=50.0,
        current_interest_rate=0.0,
        glp=10_000.0,
        gsp=10_000.0,
        accumulated_glp=10_000.0,
        premiums_paid_to_date=10_000.0,
        segments=[_coverage(face=150_000.0, issue_age=50)],
    )


def _shadow_corridor_policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        policy_number="CHAR-SHADOW",
        plancode="CHARSHD",
        def_of_life_ins="GPT",
        issue_date=date(2016, 4, 15),
        valuation_date=date(2026, 4, 15),
        issue_age=45,
        attained_age=55,
        maturity_age=121,
        policy_year=11,
        policy_month=1,
        duration=121,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        account_value=90_000.0,
        current_interest_rate=0.04,
        ccv_active=True,
        ccv_units=100.0,
        shadow_account_value=2_500.0,
        glp=1_200.0,
        gsp=15_000.0,
        accumulated_glp=12_000.0,
        mtp=40.0,
        ctp=700.0,
        segments=[_coverage(face=100_000.0, issue_age=45)],
    )


def _no_inputs(_timing: ProjectionTiming) -> None:
    return None


CASES = [
    EngineCase(
        "gpt_cashflows_policy_change",
        _cashflow_policy,
        _config("CHARGPT"),
        _rates(),
        3,
        _cashflow_inputs,
        IllustrationOptions(
            allow_exception_prems=True,
            apply_prem_to_loan=True,
            apply_excess_repayment_as_premium=True,
        ),
    ),
    EngineCase(
        "run_from_issue_cvat",
        _run_from_issue_policy,
        _config("CHARCVAT", cvat=True),
        _rates(coi=1.8, scr=2.5),
        2,
        _run_from_issue_inputs,
        IllustrationOptions(),
    ),
    EngineCase(
        "iul_wair",
        _iul_policy,
        _config("CHARIUL", lapse_value="AV"),
        _rates(coi=2.1, scr=3.0),
        3,
        _iul_inputs,
        IllustrationOptions(iul_wair_crediting=True),
    ),
    EngineCase(
        "mec_off_cycle",
        _mec_policy,
        _config("CHARMEC"),
        _rates(coi=1.7, scr=0.0),
        12,
        _mec_inputs,
        IllustrationOptions(conform_to_tamra=False, conform_to_tefra=False),
    ),
    EngineCase(
        "exception_premium",
        _exception_policy,
        _config("CHAREXC"),
        _rates(coi=8.0, scr=0.0, tpp=0.06),
        2,
        _no_inputs,
        IllustrationOptions(allow_exception_prems=True),
    ),
    EngineCase(
        "lapse_corridor",
        _lapse_policy,
        _config("CHARLAPSE"),
        _rates(coi=12.0, scr=0.0),
        2,
        _no_inputs,
        IllustrationOptions(),
    ),
    EngineCase(
        "shadow_corridor",
        _shadow_corridor_policy,
        PlancodeConfig(
            plancode="CHARSHD",
            corridor_by_age=CORRIDOR_1,
            gint=0.02,
            dbd=0.0,
            lapse_value="SV",
            interest_method="MonthlyCompounding",
            shadow_mfee=3.0,
        ),
        # Flat 5% premium load, no EPU and the flat 4% shadow premium load of the
        # original configuration, expressed as the rates the engine reads.
        IllustrationRates(
            coi=[0.0] + [2.0] * 180,
            segment_coi={1: [0.0] + [2.0] * 180},
            epu=[0.0] * 181,
            segment_epu={1: [0.0] * 181},
            scr=[0.0] + [2.0] * 180,
            segment_scr={1: [0.0] + [2.0] * 180},
            mfee=[0.0] + [5.0] * 180,
            tpp=[0.0] + [0.05] * 180,
            epp=[0.0] + [0.05] * 180,
            shadow_coi=[0.0] + [1.5] * 180,
            shadow_epu=[0.0] + [0.1] * 180,
            shadow_tpp=[0.0] + [0.04] * 180,
            shadow_epp=[0.0] + [0.04] * 180,
            shadow_tpr=[0.0] + [3.0] * 180,
            shadow_tpr_tbl1=[0.0] * 181,
            shadow_int=[0.0] + [0.04] * 180,
            shadow_dbd=[0.0] * 181,
        ),
        2,
        _no_inputs,
        IllustrationOptions(),
    ),
]


def _normalize(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            field.name: _normalize(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {
            str(key): _normalize(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def _state_rows(states: list[MonthlyState]) -> list[dict[str, object]]:
    return [_normalize(state) for state in states]


def _golden_text(case: EngineCase, timing: ProjectionTiming, states: list[MonthlyState]) -> str:
    payload = {
        "case": case.name,
        "timing": timing.value,
        "monthly_state_fields": [field.name for field in fields(MonthlyState)],
        "states": _state_rows(states),
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


@pytest.mark.parametrize("case", CASES, ids=lambda item: item.name)
@pytest.mark.parametrize("timing", list(ProjectionTiming), ids=lambda item: item.value)
def test_engine_monthly_state_golden(monkeypatch, case: EngineCase, timing: ProjectionTiming):
    """Projection output must remain byte-identical while the engine is refactored."""
    policy = case.policy_factory()
    config = copy.deepcopy(case.config)
    rates = copy.deepcopy(case.rates)
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _plancode: config)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_args: BonusConfig())
    monkeypatch.setattr(calc_engine.IllustrationEngine, "_load_rates", lambda *_args: rates)
    monkeypatch.setattr(calc_engine.IllustrationEngine, "_guaranteed_rates", lambda *_args: rates)
    monkeypatch.setattr(calc_engine, "compute_target_premiums", lambda *_a, **_k: TargetPremiumResult())
    monkeypatch.setattr(calc_engine, "build_target_detail_snapshots", lambda *_a, **_k: ({}, {}))
    monkeypatch.setattr(calc_engine, "_reload_policy_band_rates", lambda *_a, **_k: None)
    monkeypatch.setattr(
        calc_engine,
        "_solve_guideline_state",
        lambda *_a, **_k: SimpleNamespace(glp=1_200.0, gsp=2_400.0, seven_pay=3_600.0),
    )
    states = IllustrationEngine().project(
        policy,
        months=case.months,
        future_inputs=case.inputs_factory(timing),
        timing=timing,
        stop_on_lapse=False,
        options=case.options,
        rates_override=rates,
        bonus_override=BonusConfig(),
    )
    actual = _golden_text(case, timing, states)
    golden_path = GOLDEN_ROOT / f"{case.name}__{timing.value}.json"
    if UPDATE_GOLDENS:
        GOLDEN_ROOT.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(actual, encoding="utf-8")
    assert actual == golden_path.read_text(encoding="utf-8")
