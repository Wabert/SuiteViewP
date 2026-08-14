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
from datetime import date

from suiteview.illustration.core.monthly_deduction import calculate_deduction
from suiteview.illustration.core.rate_loader import IllustrationRates
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
    assert load_plancode("NU1FU200").pwot_coi_basis == 3   # target policy plancode
    assert load_plancode("NU1F3A00").pwot_coi_basis == 2
    # A plancode not in the basis list defaults to 1 (Units).
    assert load_plancode("1U143900").pwot_coi_basis == 1
