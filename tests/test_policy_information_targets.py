from decimal import Decimal

from suiteview.polview.models.policy_information import PolicyInformation


def test_shadow_account_value_uses_segment_58_xp_premium_amount():
    policy = object.__new__(PolicyInformation)
    calls = []

    def data_item_where(table, return_field, filter_field, filter_value):
        calls.append((table, return_field, filter_field, filter_value))
        return "4872.53"

    policy.data_item_where = data_item_where

    assert policy.targets.shadow_account_value == Decimal("4872.53")
    assert calls == [
        ("LH_COV_TARGET", "TAR_PRM_AMT", "TAR_TYP_CD", "XP")
    ]


def test_shadow_account_value_preserves_zero():
    policy = object.__new__(PolicyInformation)
    policy.data_item_where = lambda *_args: 0

    assert policy.targets.shadow_account_value == Decimal("0")
