"""Corridor death benefit whole-dollar rounding: ISWL rounds half up, UL floors.

Evidence (CyberLife LH_POL_MVRY_VAL.NAR_AMT on the valuation month, 2026-10-04):
ISWL GPT 381/381 in-corridor policies reproduce NAR with ROUND (0 with FLOOR only);
UL GPT is centred on FLOOR. The fixtures are real valuation months:

* 01/10497580 80110429 (ISWL, GPT, CORR 1.05, GINT 4%): AV before the deduction
  46,004.29 (CSV 45,968.17 + MD 36.12) x 1.05 = 48,304.5045 -> 48,305; NAR 2,143.09
  (Robert Haessly's derivation).
* 01/11375306 08228100 (UL, GPT, CORR 1.05, DBD 4%): AV 39,138.72 x 1.05 = 41,095.656
  -> FLOOR 41,095; NAR 1,822.19 (ROUND would give 41,096 and NAR 1,823.19).
"""
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.constants import PRODUCT_FAMILY_ISWL
from suiteview.illustration.core.calc_engine import _ending_death_benefit
from suiteview.illustration.core.corridor_rates import corridor_death_benefit
from suiteview.illustration.core.monthly_deduction import _build_death_benefit_basis
from suiteview.illustration.core.withdrawal_handler import compute_withdrawal
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData

CORR_105 = {age: 1.05 for age in range(0, 121)}
ISWL_AV, ISWL_FACE = 46_004.29, 25_000.0
UL_AV, UL_FACE = 39_138.72, 20_700.0


def _iswl_config() -> PlancodeConfig:
    return PlancodeConfig(
        plancode="80110429", product_family=PRODUCT_FAMILY_ISWL, dbd=0.04,
        corridor_by_age=CORR_105)


def _ul_config() -> PlancodeConfig:
    return PlancodeConfig(plancode="08228100", dbd=0.04, corridor_by_age=CORR_105)


def _policy(plancode: str, face: float, av: float) -> IllustrationPolicyData:
    return IllustrationPolicyData(
        plancode=plancode, db_option="A", face_amount=face, account_value=av,
        segments=[CoverageSegment(coverage_phase=1, face_amount=face, units=face / 1000.0)])


def _nar(basis) -> float:
    return round(basis.discounted_db - basis.nar_av, 2)


def test_corridor_death_benefit_rounds_iswl_and_floors_ul():
    assert corridor_death_benefit(ISWL_AV, 1.05, _iswl_config()) == 48_305.0
    assert corridor_death_benefit(UL_AV, 1.05, _ul_config()) == 41_095.0
    # Below the half the ISWL rule rounds down; an exact product is unchanged by either.
    assert corridor_death_benefit(1_000.40, 1.0, _iswl_config()) == 1_000.0
    assert corridor_death_benefit(1_000.50, 1.0, _iswl_config()) == 1_001.0
    assert corridor_death_benefit(100_000.0, 1.35, _ul_config()) == 135_000.0


def test_iswl_gpt_corridor_reproduces_cyberlife_nar_10497580():
    basis = _build_death_benefit_basis(
        ISWL_AV, _policy("80110429", ISWL_FACE, ISWL_AV), _iswl_config(),
        attained_age=80, premiums_to_date=0.0)

    assert basis.gross_db == 48_305.0
    assert basis.corr_amount == pytest.approx(23_305.0)
    assert _nar(basis) == pytest.approx(2_143.09)


def test_ul_gpt_corridor_keeps_floor_11375306():
    basis = _build_death_benefit_basis(
        UL_AV, _policy("08228100", UL_FACE, UL_AV), _ul_config(),
        attained_age=80, premiums_to_date=0.0)

    assert basis.gross_db == 41_095.0
    assert _nar(basis) == pytest.approx(1_822.19)


def test_iswl_cvat_ratio_override_also_rounds():
    basis = _build_death_benefit_basis(
        ISWL_AV, _policy("80136200", ISWL_FACE, ISWL_AV), _iswl_config(),
        attained_age=80, premiums_to_date=0.0, corridor_rate=1.05)

    assert basis.gross_db == 48_305.0


@pytest.mark.parametrize(
    ("config", "plancode", "face", "av", "expected"),
    [
        (_iswl_config(), "80110429", ISWL_FACE, ISWL_AV, 48_305.0),
        (_ul_config(), "08228100", UL_FACE, UL_AV, 41_095.0),
    ],
)
def test_projected_ending_death_benefit_uses_the_same_rule(config, plancode, face, av, expected):
    ctx = SimpleNamespace(policy=_policy(plancode, face, av), config=config)
    work = SimpleNamespace(
        month_date=date(2026, 9, 25), av=av,
        prem=SimpleNamespace(premiums_to_date=0.0), withdrawals_to_date=0.0,
        ded=SimpleNamespace(corridor_rate=1.05),
        accrual_loan=SimpleNamespace(policy_debt=0.0))

    assert _ending_death_benefit(ctx, work) == expected


def _withdrawal(config, plancode, face, av):
    return compute_withdrawal(
        av, _policy(plancode, face, av), config, {1: 0.0}, 0.0,
        corridor_rate=1.05, prior_total_md=0.0, policy_debt=0.0, cost_basis=0.0,
        withdrawals_to_date=0.0, withdrawals_ytd=0.0, is_anniversary=False)


def test_withdrawal_corridor_slice_rounds_for_iswl_and_stays_unrounded_for_ul():
    iswl = _withdrawal(_iswl_config(), "80110429", ISWL_FACE, ISWL_AV)
    ul = _withdrawal(_ul_config(), "08228100", UL_FACE, UL_AV)

    assert iswl.corridor_amount == pytest.approx(23_305.0)
    # RERUN BG: the unrounded corridor slice for UL plans.
    assert ul.corridor_amount == pytest.approx(UL_AV * 1.05 - UL_FACE)
