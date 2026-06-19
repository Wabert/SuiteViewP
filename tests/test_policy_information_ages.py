from datetime import date

from suiteview.polview.models.policy_information import PolicyInformation


def test_coverage_issue_age_zero_drives_attained_age(monkeypatch):
    policy = object.__new__(PolicyInformation)
    policy._coverages = None

    def fetch_table(table_name):
        if table_name == "LH_COV_PHA":
            return [
                {
                    "COV_PHA_NBR": 1,
                    "PLN_DES_SER_CD": "1U135D00",
                    "POL_FRM_NBR": "FORM",
                    "ISSUE_DT": date(2020, 6, 1),
                    "COV_MT_EXP_DT": date(2121, 6, 1),
                    "INS_ISS_AGE": 0,
                    "COV_UNT_QTY": 100,
                    "COV_VPU_AMT": 1000,
                    "PRS_CD": "01",
                    "INS_SEX_CD": "M",
                    "PRD_LIN_TYP_CD": "U",
                    "INS_CLS_CD": "N",
                }
            ]
        return []

    policy.fetch_table = fetch_table
    policy.get_substandard_ratings = lambda: []
    policy.cov_renewal_index = lambda *_args: -1
    policy.data_item = lambda *_args: None

    monkeypatch.setattr(PolicyInformation, "valuation_date", property(lambda _self: date(2022, 6, 1)))

    coverages = policy.get_coverages()

    assert coverages[0].issue_age == 0
    assert policy.base_issue_age == 0
    assert policy.policy_year == 3
    assert policy.attained_age == 2


def test_optional_int_parser_preserves_zero():
    assert PolicyInformation._parse_optional_int(0) == 0
    assert PolicyInformation._parse_optional_int("0") == 0
    assert PolicyInformation._parse_optional_int("") is None
    assert PolicyInformation._parse_optional_int(None) is None


def test_tamra_7pay_start_date_treats_9999_sentinel_as_missing():
    policy = object.__new__(PolicyInformation)
    policy.data_item = lambda *_args: date(9999, 12, 31)

    assert policy.tamra_7pay_start_date is None
