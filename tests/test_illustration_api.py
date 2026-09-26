"""Projection façade behavior."""

import pytest

from suiteview.illustration.api import project_policy
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def test_project_policy_rejects_unknown_projection_keyword():
    with pytest.raises(TypeError):
        project_policy(IllustrationPolicyData(), unsupported_projection_option=True)
