"""PWoT (type-4 Stipulated Premium Waiver) COI charge basis — RERUN CalcEngine RB.

    COI Charge PWST = IF(vPWST_Active, ROUND(
        CHOOSE(sPWoT_COI_Basis,
               vPWST_Units*RA,    ' 1 = Units
               vMTP*RA/100,       ' 2 = MTP  (annual vMTP)
               vCTP*RA/100)       ' 3 = CTP  (annual vCTP)
        * (1 + sTableRatingFactor*vTableCov1), 2), 0)

Basis 1 (Units) is every non-FFL UL; some FFL ULs use 2 (MTP) or 3 (CTP). The
annual vMTP is ``policy.mtp*12`` and the annual vCTP is ``policy.ctp``; the
gross-up multiplies by the BASE coverage's table rating (vTableCov1), not the
benefit's own substandard.
"""
import pytest
from copy import deepcopy
from datetime import date

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.monthly_deduction import calculate_deduction
from suiteview.illustration.core.monthly_guideline import (
    build_guideline_basis, solve_guideline_premiums,
)
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.target_premium import TargetPremiumResult
from suiteview.illustration.models.input_set import (
    IllustrationInputSet, IllustrationOptions, PolicyChangeEvent, PolicyChangeKind,
)
from suiteview.illustration.debug.excel_export import _get_projection_value
from suiteview.illustration.ui.values_tab import IllustrationValuesTab
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.models.policy_data import (
    BenefitInfo,
    CoverageSegment,
    IllustrationPolicyData,
)


def _config(basis: int, *, table_rating_factor: float = 0.25) -> PlancodeConfig:
    return PlancodeConfig(
        plancode="NU1FU200",
        dbd=0.0,
        gint=0.0,
        corridor_code=None,
        epu_code="0",
        mfee="0",
        table_rating_factor=table_rating_factor,
        pwot_coi_basis=basis,
    )


def _policy(*, base_table: int = 0, mtp: float = 0.0, ctp: float = 0.0):
    policy = IllustrationPolicyData(
        plancode="NU1FU200",
        db_option="A",
        face_amount=100_000.0,
        account_value=10_000.0,
        segments=[
            CoverageSegment(
                coverage_phase=1,
                face_amount=100_000.0,
                units=100.0,
                issue_age=45,
                table_rating=base_table,
            )
        ],
        benefits=[
            BenefitInfo(benefit_type="4", benefit_subtype="9", units=50.0, is_active=True),
        ],
    )
    policy.mtp = mtp
    policy.ctp = ctp
    return policy


def _rates():
    # RA (PWST COI rate) = 3.0; the type-4 benefit key is "49".
    return IllustrationRates(benefit_coi={"49": [None, 3.0]})


def _charge(result):
    return result.benefit_charge_detail["49"]


def test_basis_1_units_unchanged():
    # Basis 1 keeps the existing units x rate path (no MTP/CTP, no base-table
    # gross-up beyond the benefit's own): 50 x 3.0 = 150.00.
    result = calculate_deduction(
        10_000.0, _policy(mtp=100.0, ctp=1200.0), _config(1), _rates(),
        rate_year=1, attained_age=45, premiums_to_date=0.0,
    )
    assert _charge(result) == pytest.approx(150.00)


def test_basis_2_uses_annual_mtp_over_100():
    # Basis 2: vMTP*RA/100 = (mtp*12) x 3.0/100. mtp=100 -> annual 1200.
    # 1200 x 3.0/100 = 36.00; no base table rating so gross-up = 1.
    result = calculate_deduction(
        10_000.0, _policy(mtp=100.0), _config(2), _rates(),
        rate_year=1, attained_age=45, premiums_to_date=0.0,
    )
    assert _charge(result) == pytest.approx(36.00)


def test_basis_3_uses_annual_ctp_over_100():
    # Basis 3: vCTP*RA/100 = 1500 x 3.0/100 = 45.00.
    result = calculate_deduction(
        10_000.0, _policy(ctp=1500.0), _config(3), _rates(),
        rate_year=1, attained_age=45, premiums_to_date=0.0,
    )
    assert _charge(result) == pytest.approx(45.00)


def test_basis_2_grosses_up_by_base_coverage_table_rating():
    # Base coverage Table B (rating 2), factor 0.25 -> gross = 1 + 0.25*2 = 1.5.
    # 1200 x 3.0/100 x 1.5 = 54.00.
    result = calculate_deduction(
        10_000.0, _policy(base_table=2, mtp=100.0), _config(2), _rates(),
        rate_year=1, attained_age=45, premiums_to_date=0.0,
    )
    assert _charge(result) == pytest.approx(54.00)


def test_basis_3_charge_rounds_to_cents():
    # vCTP=1234.55, RA=3.0 -> 1234.55*3/100 = 37.0365 -> ROUND 37.04.
    result = calculate_deduction(
        10_000.0, _policy(ctp=1234.55), _config(3), _rates(),
        rate_year=1, attained_age=45, premiums_to_date=0.0,
    )
    assert _charge(result) == pytest.approx(37.04)


def test_plancode_table_carries_pwot_coi_basis():
    assert load_plancode("1U14L400").pwot_coi_basis == 2   # UFF90022 benefit 4M
    assert load_plancode("NU1FU200").pwot_coi_basis == 3   # target policy plancode
    assert load_plancode("NU1F3A00").pwot_coi_basis == 2
    # A plancode not in the basis list defaults to 1 (Units).
    assert load_plancode("1U143900").pwot_coi_basis == 1


@pytest.mark.parametrize("guaranteed", [False, True])
@pytest.mark.parametrize("basis", [1, 2, 3])
@pytest.mark.parametrize("new_face", [50_000.0, 125_000.0])
def test_face_change_updates_target_based_benefit_amounts_and_charges(
    monkeypatch, guaranteed, basis, new_face,
):
    policy = _policy(mtp=100.0, ctp=1500.0)
    policy.issue_date = date(2020, 1, 15)
    policy.valuation_date = date(2026, 9, 15)
    policy.issue_age = 40
    policy.attained_age = 46
    policy.policy_year = 7
    policy.policy_month = 9
    policy.duration = 81
    policy.benefits[0].benefit_amount = 5000.0
    policy.benefits[0].vpu = 100.0
    original = deepcopy(policy)
    config = _config(basis)
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _: config)
    monkeypatch.setattr(calc_engine, "_reload_policy_band_rates", lambda *_: None)
    monkeypatch.setattr(calc_engine, "_load_segment_rates", lambda *_: None)
    monkeypatch.setattr(
        calc_engine, "compute_target_premiums",
        lambda current, *_args, **_kwargs: TargetPremiumResult(
            mtp_annual=current.total_face * 0.012,
            ctp_annual=current.total_face * 0.015,
        ),
    )
    change_date = date(2026, 11, 15)
    inputs = IllustrationInputSet(policy_changes=[PolicyChangeEvent(
        kind=PolicyChangeKind.FACE_AMOUNT, effective_date=change_date,
        value=new_face,
        metadata={"new_glp": 0.0, "new_gsp": 0.0, "new_7pay": 0.0},
    )])
    states = IllustrationEngine().project(
        policy, months=4, future_inputs=inputs,
        options=IllustrationOptions(guaranteed_assumption=guaranteed),
        rates_override=_rates(), bonus_override=BonusConfig(),
    )
    assert len(states) == 5
    for state in states:
        face = 100_000.0 if state.date < change_date else new_face
        annual_mtp = face * 0.012
        annual_ctp = face * 0.015
        if basis == 1:
            assert state.benefit_amounts["49"] == 5000.0
            assert state.benefit_charge_detail["49"] == 150.0
        else:
            expected = annual_mtp if basis == 2 else annual_ctp
            assert state.benefit_amounts["49"] == pytest.approx(expected)
            assert state.benefit_charge_detail["49"] == pytest.approx(expected * 3.0 / 100.0)
        if state.date >= change_date:
            assert state.mtp_detail["vMTP"] == pytest.approx(annual_mtp)
            assert state.ctp_detail["vCTP"] == pytest.approx(annual_ctp)
        displayed = IllustrationValuesTab._benefit_values(state, ["49"])
        assert displayed["Benefit Amount 49"] == state.benefit_amounts["49"]
        assert displayed["Benefit Charge 49"] == state.benefit_charge_detail["49"]
        assert _get_projection_value(state, "benefit_49_amount") == state.benefit_amounts["49"]
    assert policy == original


@pytest.mark.parametrize("basis", [1, 2, 3])
def test_guideline_pwot_uses_configured_basis_and_rating_cease_date(basis):
    policy = _policy(base_table=2, mtp=100.0125, ctp=1500.55)
    policy.issue_date = date(2020, 1, 15)
    policy.issue_age = 40
    policy.maturity_age = 48
    policy.base_segment.table_cease_date = date(2026, 3, 15)
    policy.benefits[0].rating_factor = 1.75
    policy.benefits[0].pay_up_date = date(2027, 1, 15)
    config = _config(basis)
    rates = IllustrationRates(benefit_coi={"49": [None] + [3.0] * 10})
    result = build_guideline_basis(
        policy, config, rates, attained_age=46, as_of=date(2026, 1, 15),
    )
    for index, month in enumerate(result.months):
        if index >= 12:
            assert month.benefit_charges == 0.0
            continue
        if basis == 1:
            expected = 50.0 * 3.0 * 1.75
        else:
            amount = 1200.15 if basis == 2 else 1500.55
            factor = 1.5 if index < 2 else 1.0
            expected = round(amount * 3.0 / 100.0 * factor, 2)
        assert month.benefit_charge_detail["Benefit 4 9"] == pytest.approx(expected)
        assert month.benefit_charges == pytest.approx(expected)


@pytest.mark.parametrize("basis", [1, 2, 3])
@pytest.mark.parametrize("new_face", [50_000.0, 125_000.0])
@pytest.mark.parametrize("guaranteed", [False, True])
def test_real_guideline_recalc_uses_new_pwot_target(
    monkeypatch, basis, new_face, guaranteed,
):
    policy = _policy(mtp=100.0, ctp=1500.0)
    policy.issue_date = date(2020, 1, 15)
    policy.valuation_date = date(2026, 1, 15)
    policy.issue_age = 40
    policy.attained_age = 46
    policy.maturity_age = 65
    policy.policy_year = 7
    policy.policy_month = 1
    policy.duration = 73
    policy.def_of_life_ins = "GPT"
    policy.glp = 2000.0
    policy.gsp = 20_000.0
    policy.tamra_7pay_start_date = policy.issue_date
    policy.tamra_7pay_level = 2000.0
    original = deepcopy(policy)
    config = _config(basis)
    rates = IllustrationRates(benefit_coi={"49": [None] + [3.0] * 30})
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _: config)
    monkeypatch.setattr(calc_engine, "load_rates", lambda *_a, **_kw: rates)
    monkeypatch.setattr(calc_engine, "_reload_policy_band_rates", lambda *_: None)
    monkeypatch.setattr(calc_engine, "_load_segment_rates", lambda *_: None)
    monkeypatch.setattr(
        calc_engine, "compute_target_premiums",
        lambda current, *_a, **_kw: TargetPremiumResult(
            mtp_annual=current.total_face * 0.012,
            ctp_annual=current.total_face * 0.015,
        ),
    )
    change_date = date(2026, 3, 15)
    states = IllustrationEngine().project(
        policy, months=3,
        options=IllustrationOptions(guaranteed_assumption=guaranteed),
        future_inputs=IllustrationInputSet(policy_changes=[PolicyChangeEvent(
            PolicyChangeKind.FACE_AMOUNT, change_date, new_face,
        )]),
        rates_override=rates, bonus_override=BonusConfig(),
    )
    changed = next(state for state in states if state.date == change_date)
    detail = changed.guideline_recalc
    for side, face in [("before", 100_000.0), ("after", new_face)]:
        expected_charge = {
            1: 150.0, 2: face * 0.012 * 0.03, 3: face * 0.015 * 0.03,
        }[basis]
        for kind in ("glp", "gsp"):
            rows = detail["monthly_pv_recalc"][side][kind]["glp_rows"]
            assert rows[0]["Benefit 4 9"] == pytest.approx(expected_charge)
        expected_policy = deepcopy(original)
        expected_policy.face_amount = face
        expected_policy.base_segment.face_amount = face
        expected_policy.mtp = face * 0.012 / 12.0
        expected_policy.ctp = face * 0.015
        expected_basis = build_guideline_basis(
            expected_policy, config, rates, attained_age=46,
            as_of=change_date, months_into_year=2,
        )
        for month in expected_basis.months:
            month.benefit_charges = expected_charge
        solved = solve_guideline_premiums(expected_basis)
        assert detail[f"glp_{side}"] == pytest.approx(solved.glp)
        assert detail[f"gsp_{side}"] == pytest.approx(solved.gsp)
    assert changed.benefit_charge_detail["49"] == pytest.approx(expected_charge)
    start = detail["seven_pay_window_start"]
    seven_basis = build_guideline_basis(
        expected_policy, config, rates,
        attained_age=40 + start.year - 2020, as_of=start,
        months_into_year=2 if start == change_date else 0,
        active_as_of=change_date,
    )
    for month in seven_basis.months:
        month.benefit_charges = expected_charge
    assert detail["seven_pay_after"] == pytest.approx(
        solve_guideline_premiums(
            seven_basis, starting_av=detail["seven_pay_start_av"],
        ).seven_pay,
    )
    assert detail["seven_pay_pv"]["glp_rows"][0]["Charges"] == pytest.approx(
        expected_charge,
    )
    assert policy == original


@pytest.mark.parametrize("basis", [2, 3])
def test_guideline_zero_target_does_not_fall_back_to_recorded_units(basis):
    policy = _policy(mtp=0.0, ctp=0.0)
    policy.issue_age = 45
    policy.maturity_age = 46
    result = build_guideline_basis(
        policy, _config(basis), _rates(), attained_age=45,
    )
    assert result.months
    assert all(month.benefit_charges == 0.0 for month in result.months)
