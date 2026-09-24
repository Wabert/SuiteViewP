"""Substandard cessation uses actual guideline months, not absolute policy-year offsets."""
from copy import deepcopy
from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.guideline_pv import guideline_glp_detail
from suiteview.illustration.core.monthly_deduction import _adjusted_coi_rate
from suiteview.illustration.core.monthly_guideline import build_guideline_basis
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData


def _basis_inputs():
    policy = IllustrationPolicyData(
        issue_date=date(2002, 2, 15), issue_age=34, maturity_age=95,
        face_amount=100000, units=100,
        segments=[CoverageSegment(
            coverage_phase=1, issue_date=date(2002, 2, 15), issue_age=34,
            face_amount=100000, units=100, table_rating=2,
            table_cease_date=date(2063, 2, 15),
        )],
    )
    config = PlancodeConfig(mfee="0", epu_code="0", premium_load="0", premium_cease_age=95)
    rates = IllustrationRates(segment_coi={1: [None] + [2.0] * 70})
    return policy, config, rates


def test_table_two_remains_in_guideline_qx_through_contract_maturity():
    policy, config, rates = _basis_inputs()
    original = deepcopy(policy)
    basis = build_guideline_basis(
        policy, config, rates, attained_age=62, as_of=date(2030, 2, 15),
    )
    assert len(basis.months) == 33 * 12
    assert basis.months[72].attained_age == 68
    assert all(month.coi_rate == pytest.approx(0.003) for month in basis.months)
    rows = guideline_glp_detail(basis)["glp_rows"]
    assert rows[72]["q'x"] == pytest.approx(0.003 / 1.003, abs=5e-9)
    assert rows[-2]["Age"] == 94
    assert rows[-2]["q'x"] == rows[72]["q'x"]
    assert policy == original


@pytest.mark.parametrize("as_of", [date(2030, 2, 15), None])
def test_table_and_flat_end_on_their_exact_guideline_months(as_of):
    policy, config, rates = _basis_inputs()
    policy.base_segment.table_cease_date = date(2030, 8, 15)
    policy.base_segment.flat_extra = 12.12
    policy.base_segment.flat_cease_date = date(2030, 10, 15)
    start = date(2030, 7, 15)
    basis = build_guideline_basis(
        policy, config, rates, attained_age=62, as_of=as_of and start,
        months_into_year=5,
    )
    for index, month in enumerate(basis.months):
        when = start + relativedelta(months=index)
        expected = _adjusted_coi_rate(2.0, policy.base_segment, config, when) / 1000
        assert month.coi_rate == pytest.approx(expected)
    assert basis.months[0].coi_rate == pytest.approx(0.00401)
    assert basis.months[1].coi_rate == pytest.approx(0.00301)
    assert basis.months[3].coi_rate == pytest.approx(0.002)


@pytest.mark.parametrize("cease", [date(2030, 1, 15), date(2030, 2, 15), date(2030, 2, 16), None])
def test_recalc_start_date_respects_rating_cease_boundary(cease):
    policy, config, rates = _basis_inputs()
    policy.base_segment.table_cease_date = cease
    start = date(2030, 2, 15)
    basis = build_guideline_basis(policy, config, rates, attained_age=62, as_of=start)
    expected = 0.003 if cease is None or cease > start else 0.002
    assert basis.months[0].coi_rate == pytest.approx(expected)


def test_month_end_projection_dates_do_not_drift_after_february():
    policy, config, rates = _basis_inputs()
    policy.issue_date = policy.base_segment.issue_date = date(2002, 1, 31)
    policy.base_segment.table_cease_date = date(2030, 3, 30)
    basis = build_guideline_basis(
        policy, config, rates, attained_age=62, as_of=date(2030, 1, 31),
    )
    assert [m.coi_rate for m in basis.months[:3]] == pytest.approx([0.003, 0.003, 0.002])
