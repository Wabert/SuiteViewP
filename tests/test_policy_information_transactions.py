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


def test_get_live_transactions_selects_codes_and_drops_reversals():
    rows = [
        {"ASOF_DT": date(2022, 3, 1), "SEQ_NO": 2, "TRANS": "SG", "GROSS_AMT": "1000.00",
         "FCB0_REV_IND": "0", "FCB2_REV_APPL_IND": "0"},
        {"ASOF_DT": date(2022, 2, 1), "SEQ_NO": 1, "TRANS": "SN", "GROSS_AMT": "50.00",
         "FCB0_REV_IND": "1", "FCB2_REV_APPL_IND": "0"},
        {"ASOF_DT": date(2021, 1, 5), "SEQ_NO": 1, "TRANS": "PU", "GROSS_AMT": "1652.84",
         "FCB0_REV_IND": "0", "FCB2_REV_APPL_IND": "0"},
        {"ASOF_DT": date(2021, 1, 5), "SEQ_NO": 2, "TRANS": "PQ", "GROSS_AMT": "250.00",
         "FCB0_REV_IND": "0", "FCB2_REV_APPL_IND": "0"},
    ]
    policy = PolicyInformation.__new__(PolicyInformation)
    policy.fetch_table = lambda table: rows

    transactions = policy.activity.get_live_transactions({"SG", "SN", "PQ"})

    assert [(t.trans_date, t.trans_code, t.gross_amount) for t in transactions] == [
        (date(2021, 1, 5), "PQ", 250), (date(2022, 3, 1), "SG", 1000)]


def test_get_skipped_periods_reads_lap_dt_and_ren_dt():
    """LH_COV_SKIPPED_PER's columns are LAP_DT/REN_DT/SKIPPED_COV_STA_CD (DB2TAB catalog
    2026-10-04); UIP88048 phase 1 has two closed periods."""
    rows = [
        {"COV_PHA_NBR": 1, "LAP_DT": date(2019, 10, 6), "REN_DT": date(2019, 11, 5),
         "SKIPPED_COV_STA_CD": " ", "PRM_PAY_CD": " "},
        {"COV_PHA_NBR": 1, "LAP_DT": date(2020, 11, 6), "REN_DT": date(2021, 1, 5),
         "SKIPPED_COV_STA_CD": " ", "PRM_PAY_CD": " "},
        {"COV_PHA_NBR": 2, "LAP_DT": date(2020, 11, 6), "REN_DT": None,
         "SKIPPED_COV_STA_CD": "1", "PRM_PAY_CD": " "},
    ]
    policy = PolicyInformation.__new__(PolicyInformation)
    policy.fetch_table = lambda table: rows if table == "LH_COV_SKIPPED_PER" else []

    periods = policy.coverages.get_skipped_periods(cov_pha_nbr=1)

    assert [(p.coverage_phase, p.lapse_date, p.reinstatement_date) for p in periods] == [
        (1, date(2019, 10, 6), date(2019, 11, 5)), (1, date(2020, 11, 6), date(2021, 1, 5))]
    assert policy.coverages.get_skipped_periods(cov_pha_nbr=2)[0].reinstatement_date is None
    assert policy.coverages.get_skipped_periods(cov_pha_nbr=2)[0].status_code == "1"


def test_policy_premium_transactions_round_trip_in_saved_snapshot():
    policy = IllustrationPolicyData(
        premium_transactions=[
            PremiumTransaction(date(2020, 1, 1), 100.25, "PI"),
        ]
    )

    restored = decode_policy_snapshot(encode_policy_snapshot(policy))

    assert restored.premium_transactions == policy.premium_transactions
