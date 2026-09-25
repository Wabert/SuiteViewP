from datetime import date

import pytest

from suiteview.illustration.core.calc_engine import IllustrationEngine, ProjectionTiming
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    PolicyChangeEvent,
    PolicyChangeKind,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def test_cyberlife_monthliversary_rejects_policy_changes():
    policy = IllustrationPolicyData(plancode="TEST", issue_date=date(2020, 1, 1))
    future_inputs = IllustrationInputSet(policy_changes=[
        PolicyChangeEvent(
            kind=PolicyChangeKind.FACE_AMOUNT,
            effective_date=date(2026, 10, 1),
            value=100_000,
        )
    ])

    with pytest.raises(ValueError, match="CYBERLIFE_MONTHLIVERSARY.*policy changes.*CyberLife-monthliversary"):
        IllustrationEngine().project(
            policy,
            months=1,
            future_inputs=future_inputs,
            timing=ProjectionTiming.CYBERLIFE_MONTHLIVERSARY,
        )
