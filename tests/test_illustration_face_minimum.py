"""Plan minimum face on requested face decreases (Robert Haessly, 10/6/2026).

``core.face_minimum``: a requested decrease (and the face reduction of a DB option
A->B change) stops at the plan's evidenced minimum face and is reported; a policy
already below the minimum keeps its face. Withdrawals keep their own DBO A cap.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import calc_engine as ce
from suiteview.illustration.core.face_minimum import (
    FACE_MIN_LIMITED_KEY,
    PLAN_MINIMUM_EXEMPT_KEY,
    decrease_floor,
    min_face_notices,
)
from suiteview.illustration.core.withdrawal_handler import compute_withdrawal
from suiteview.illustration.models.input_set import PolicyChangeEvent, PolicyChangeKind
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData

WHEN = date(2027, 3, 1)
NO_CHARGE = {"charge_surrender": False}


def _mlul(*, evidenced: bool = True) -> PlancodeConfig:
    # OriginalSA: no partial surrender charge on a decrease, so no rates are needed.
    return PlancodeConfig(sa_basis="OriginalSA", withdrawal_fee=25.0,
                          min_face_after_wd=100_000.0, min_face_evidenced=evidenced)


def _policy(face: float, dbo: str = "A") -> IllustrationPolicyData:
    return IllustrationPolicyData(
        db_option=dbo, face_amount=face,
        segments=[CoverageSegment(coverage_phase=1, face_amount=face, units=face / 1000.0)])


def _decrease(policy, config, new_face, metadata=None):
    outcome = ce._PolicyChangeOutcome()
    change = PolicyChangeEvent(kind=PolicyChangeKind.FACE_AMOUNT, effective_date=WHEN,
                               value=new_face, metadata={**NO_CHARGE, **(metadata or {})})
    ce._apply_face_amount_change(policy, config, change, 60, WHEN, None, 5,
                                 policy.total_face, change.metadata, outcome)
    return outcome


def test_decrease_below_the_minimum_is_limited_to_the_minimum():
    policy = _policy(150_000.0)
    outcome = _decrease(policy, _mlul(), 80_000.0)
    assert policy.total_face == pytest.approx(100_000.0)
    assert policy.segments[0].units == pytest.approx(100.0)
    detail = outcome.face_detail
    assert detail["Input Face"] == 80_000.0
    assert detail["Specified Face Decrease"] == pytest.approx(50_000.0)
    assert detail[FACE_MIN_LIMITED_KEY] is True
    assert outcome.coverage_changed


def test_decrease_to_or_above_the_minimum_is_not_limited():
    policy = _policy(150_000.0)
    outcome = _decrease(policy, _mlul(), 100_000.0)
    assert policy.total_face == pytest.approx(100_000.0)
    assert FACE_MIN_LIMITED_KEY not in outcome.face_detail


def test_policy_already_below_the_minimum_keeps_its_face():
    policy = _policy(86_031.0)
    outcome = _decrease(policy, _mlul(), 50_000.0)
    assert policy.total_face == pytest.approx(86_031.0)
    assert outcome.face_detail["Specified Face Decrease"] == 0.0
    assert outcome.face_detail[FACE_MIN_LIMITED_KEY] is True
    assert not outcome.coverage_changed
    assert not ce._will_alter_coverage(
        policy, _mlul(), PolicyChangeEvent(kind=PolicyChangeKind.FACE_AMOUNT,
                                           effective_date=WHEN, value=50_000.0),
        policy.total_face, 0.0)


def test_policy_below_the_minimum_may_still_increase():
    assert decrease_floor(_mlul(), 86_031.0) == 86_031.0


def test_unevidenced_minimum_takes_no_decrease_minimum():
    policy = _policy(150_000.0)
    outcome = _decrease(policy, _mlul(evidenced=False), 10_000.0)
    assert policy.total_face == pytest.approx(10_000.0)
    assert FACE_MIN_LIMITED_KEY not in outcome.face_detail


def test_abr_acceleration_is_exempt():
    policy = _policy(150_000.0)
    _decrease(policy, _mlul(), 30_000.0, {PLAN_MINIMUM_EXEMPT_KEY: True})
    assert policy.total_face == pytest.approx(30_000.0)


def test_dbo_a_to_b_face_reduction_stops_at_the_minimum():
    policy = _policy(120_000.0)
    detail: dict = {}
    outcome = ce._PolicyChangeOutcome()
    ce._apply_option_a_to_b(policy, _mlul(), None, WHEN, 5, 35_000.0, detail, outcome)
    assert policy.total_face == pytest.approx(100_000.0)
    assert detail["DBO Face Decrease"] == pytest.approx(20_000.0)
    assert detail[FACE_MIN_LIMITED_KEY] is True


def test_withdrawal_still_honors_the_minimum():
    policy = _policy(150_000.0)
    result = compute_withdrawal(
        120_000.0, policy, _mlul(), {1: 0.0}, 80_000.0,
        corridor_rate=1.0, prior_total_md=0.0, policy_debt=0.0, cost_basis=120_000.0,
        withdrawals_to_date=0.0, withdrawals_ytd=0.0, is_anniversary=True)
    # DBO A: SA - (100,000 + 25 fee) = 49,975 net.
    assert result.max_net_withdrawal == pytest.approx(49_975.0)
    assert result.applied_net_withdrawal == pytest.approx(49_975.0)
    assert 150_000.0 - result.face_decrease == pytest.approx(100_025.0)


def test_limited_decrease_is_a_run_notice():
    policy = _policy(150_000.0)
    outcome = _decrease(policy, _mlul(), 80_000.0)
    states = [SimpleNamespace(date=WHEN, face_change_detail=outcome.face_detail, dbo_change_detail={})]
    (notice,) = min_face_notices(states)
    assert notice == ("Face decrease on 03/01/2027 limited to the plan minimum face $100,000: "
                      "requested decrease $70,000.00, applied $50,000.00")
    assert min_face_notices([SimpleNamespace(date=WHEN, face_change_detail={}, dbo_change_detail={})]) == []
