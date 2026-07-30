"""Terminated base coverages must not inflate the band face amount.

Regression for policy UIP69169: PolView placed the policy in band 3
(face > 250,000) while CyberLife had it in band 2. One of the base
coverages was terminated, so its face should be excluded from the total
specified amount used for band determination.
"""
from datetime import date
from decimal import Decimal

from suiteview.polview.models.policy_information import PolicyInformation

PLANCODE = "1U135D00"
VALUATION = date(2022, 6, 1)


def _build_policy(cov_rows):
    policy = object.__new__(PolicyInformation)
    policy._coverages = None
    policy._band_cache = {}

    def fetch_table(table_name):
        if table_name == "LH_COV_PHA":
            return cov_rows
        return []

    policy.fetch_table = fetch_table
    policy.get_substandard_ratings = lambda: []
    policy.cov_renewal_index = lambda *_args: -1
    policy.data_item = lambda *_args, **_kwargs: None
    return policy


def _cov_row(cov_nbr, face, terminate_date=None):
    return {
        "COV_PHA_NBR": cov_nbr,
        "PLN_DES_SER_CD": PLANCODE,
        "POL_FRM_NBR": "FORM",
        "ISSUE_DT": date(2018, 6, 1),
        "COV_MT_EXP_DT": date(2121, 6, 1),
        "INS_ISS_AGE": 45,
        "COV_UNT_QTY": face / 1000,
        "COV_VPU_AMT": 1000,
        "PRS_CD": "00",
        "INS_SEX_CD": "M",
        "PRD_LIN_TYP_CD": "U",
        "INS_CLS_CD": "N",
        "PLN_TMN_DT": terminate_date,
    }


def test_terminated_base_coverage_excluded_from_total_specified_amount(monkeypatch):
    monkeypatch.setattr(
        PolicyInformation, "valuation_date", property(lambda _self: VALUATION)
    )
    policy = _build_policy([
        _cov_row(1, 200_000),
        _cov_row(2, 100_000, terminate_date=date(2021, 1, 1)),  # terminated
    ])

    assert policy.total_specified_amount == Decimal("200000")


def test_active_base_coverages_still_summed(monkeypatch):
    monkeypatch.setattr(
        PolicyInformation, "valuation_date", property(lambda _self: VALUATION)
    )
    policy = _build_policy([
        _cov_row(1, 200_000),
        _cov_row(2, 100_000),  # active increase
    ])

    assert policy.total_specified_amount == Decimal("300000")


def test_cov_band_uses_active_total(monkeypatch):
    monkeypatch.setattr(
        PolicyInformation, "valuation_date", property(lambda _self: VALUATION)
    )
    monkeypatch.setattr(
        PolicyInformation, "issue_date", property(lambda _self: date(2018, 6, 1))
    )
    policy = _build_policy([
        _cov_row(1, 200_000),
        _cov_row(2, 100_000, terminate_date=date(2021, 1, 1)),  # terminated
    ])

    class _FakeRates:
        def get_band(self, _plancode, face, issue_date=None):
            return 3 if face >= 250_000 else 2

    policy._get_rates = lambda: _FakeRates()

    # 200,000 active total -> band 2 (matches CyberLife), not band 3.
    assert policy.cov_band(1) == 2
