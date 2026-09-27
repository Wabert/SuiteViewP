from datetime import date
from types import MethodType

from suiteview.illustration.models.case_store import (
    decode_policy_snapshot,
    encode_policy_snapshot,
)
from suiteview.illustration.models.policy_data import (
    IllustrationPolicyData,
    PremiumTransaction,
)
from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.models.policy_sections.activity import ActivitySection


def test_get_premium_transactions_filters_reversals_and_nonpremium_codes():
    rows = [
        {
            "ASOF_DT": date(2020, 3, 1),
            "SEQ_NO": 3,
            "TRANS": "PW",
            "GROSS_AMT": "300.00",
            "FCB0_REV_IND": "0",
            "FCB2_REV_APPL_IND": "0",
        },
        {
            "ASOF_DT": date(2020, 2, 1),
            "SEQ_NO": 2,
            "TRANS": "PR",
            "GROSS_AMT": "200.00",
            "FCB0_REV_IND": "1",
            "FCB2_REV_APPL_IND": "0",
        },
        {
            "ASOF_DT": date(2020, 1, 1),
            "SEQ_NO": 1,
            "TRN_TYP_CD": "P",
            "TRN_SBY_CD": "I",
            "TOT_TRS_AMT": "100.00",
            "FCB0_REV_IND": "0",
            "FCB2_REV_APPL_IND": "0",
        },
        {
            "ASOF_DT": date(2020, 4, 1),
            "SEQ_NO": 4,
            "TRANS": "PN",
            "GROSS_AMT": "400.00",
            "FCB0_REV_IND": "0",
            "FCB2_REV_APPL_IND": "0",
        },
        {
            "ASOF_DT": date(2020, 5, 1),
            "SEQ_NO": 5,
            "TRANS": "PB",
            "GROSS_AMT": "500.00",
            "FCB0_REV_IND": "0",
            "FCB2_REV_APPL_IND": "1",
        },
    ]
    policy = PolicyInformation.__new__(PolicyInformation)
    policy.fetch_table = lambda table: rows
    policy.activity.get_transactions = MethodType(ActivitySection.get_transactions, policy.activity)

    transactions = policy.activity.get_premium_transactions()

    assert [
        (item.trans_date, item.trans_code, item.gross_amount)
        for item in transactions
    ] == [
        (date(2020, 1, 1), "PI", 100),
        (date(2020, 3, 1), "PW", 300),
    ]
    assert ActivitySection.PREMIUM_TRANSACTION_CODES == {
        "PR", "PI", "PA", "PF", "PT", "PB", "PW",
    }


def test_policy_premium_transactions_round_trip_in_saved_snapshot():
    policy = IllustrationPolicyData(
        premium_transactions=[
            PremiumTransaction(date(2020, 1, 1), 100.25, "PI"),
        ]
    )

    restored = decode_policy_snapshot(encode_policy_snapshot(policy))

    assert restored.premium_transactions == policy.premium_transactions
