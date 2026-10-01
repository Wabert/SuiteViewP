"""A coverage segment issued after the projection month adds no DB/NAR/COI/EPU (fix E04).

CyberLife carries a scheduled phase (26/000324822, 1U1F4M00 phase 12, issue
2026-10-26, face 25,000) before its issue date; RERUN charged it every month.
"""
from datetime import date

import pytest

from suiteview.illustration.core.monthly_deduction import calculate_deduction, in_force_face
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    BenefitInfo, CoverageSegment, IllustrationPolicyData,
)

FUTURE_ISSUE = date(2026, 10, 26)


def _policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        plancode="TEST", db_option="A", face_amount=125_000.0, account_value=5_000.0,
        issue_date=date(2020, 1, 26), valuation_date=date(2026, 7, 26),
        segments=[
            CoverageSegment(coverage_phase=1, issue_date=date(2020, 1, 26), issue_age=45,
                            face_amount=100_000.0, units=100.0),
            CoverageSegment(coverage_phase=12, issue_date=FUTURE_ISSUE, issue_age=51,
                            face_amount=25_000.0, units=25.0),
        ],
        benefits=[BenefitInfo(benefit_type="3", benefit_subtype="0", units=1.0, is_active=True)],
    )


def _config() -> PlancodeConfig:
    return PlancodeConfig(
        plancode="TEST", dbd=0.0, gint=0.0, corridor_code=None, epu_code="0.05", mfee="0",
    )


def _rates() -> IllustrationRates:
    return IllustrationRates(
        segment_coi={1: [None] + [1.2] * 10, 12: [None] + [1.5] * 10},
        benefit_coi={"30": [None] + [0.1] * 10},
    )


def _deduction(projection_date: date):
    return calculate_deduction(
        5_000.0, _policy(), _config(), _rates(), rate_year=7, attained_age=51,
        premiums_to_date=0.0, projection_date=projection_date,
    )


def test_segment_before_its_issue_date_is_not_charged():
    result = _deduction(date(2026, 9, 26))

    assert result.standard_db == pytest.approx(100_000.0)
    assert result.db_by_coverage["cov2"] == 0.0
    assert result.nar_by_coverage["cov2"] == 0.0
    assert result.coi_charges_by_coverage["cov2"] == 0.0
    assert result.coi_rates_by_coverage["cov2"] == 0.0
    assert result.epu_charges_by_coverage["cov2"] == 0.0
    assert result.coi_charges_by_coverage["cov1"] == pytest.approx(95.0 * 1.2)
    # The MD-based waiver basis excludes the pending segment too.
    base = result.coi_charge + result.epu_charge + result.mfee_charge + result.av_charge
    assert result.benefit_charge_detail["30"] == pytest.approx(round(base * 0.1, 2))


def test_segment_is_charged_from_its_issue_date():
    result = _deduction(FUTURE_ISSUE)

    assert result.standard_db == pytest.approx(125_000.0)
    assert result.nar_by_coverage["cov2"] == pytest.approx(25_000.0)
    assert result.coi_charges_by_coverage["cov2"] == pytest.approx(25.0 * 1.5)
    assert result.epu_charges_by_coverage["cov2"] == pytest.approx(25.0 * 0.05)


def test_in_force_face_excludes_pending_segments_only():
    policy = _policy()
    assert in_force_face(policy, date(2026, 9, 26)) == 100_000.0
    assert in_force_face(policy, FUTURE_ISSUE) == 125_000.0
    assert in_force_face(policy, None) == 125_000.0
