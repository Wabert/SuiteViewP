from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import illustration_policy_service
from suiteview.illustration.models.plancode_config import PlancodeConfig


class _FakeRates:
    def get_band(self, _plancode, face_amount):
        return 2 if float(face_amount or 0.0) == 200_000.0 else 9


class _FakePolicyInfo:
    exists = True
    base_plancode = "TESTUL"
    issue_date = date(2000, 1, 1)
    valuation_date = date(2024, 1, 1)
    base_issue_age = 40
    base_sex_code = "M"
    base_rate_class = "N"
    base_total_face_amount = 300_000.0
    db_option_code = "A"
    modal_premium = 100.0
    billing_frequency = 1
    policy_year = 25
    policy_month = 1
    attained_age = 64
    age_at_maturity = 121
    def_of_life_ins_code = "1"
    glp = 1_200.0
    gsp = 2_400.0
    accumulated_glp_target = 0.0
    corridor_percent = 100.0
    mtp = 100.0
    ctp = 1_200.0
    accumulated_mtp_target = 0.0
    map_date = None
    premium_td = 0.0
    premium_ytd = 0.0
    cost_basis = 0.0
    total_regular_loan_principal = 0.0
    total_regular_loan_accrued = 0.0
    total_preferred_loan_principal = 0.0
    total_preferred_loan_accrued = 0.0
    total_variable_loan_principal = 0.0
    total_variable_loan_accrued = 0.0
    variable_loan_charge_rate = None
    total_withdrawals = 0.0
    gav = 0.0
    is_mec = False
    tamra_7pay_level = 0.0
    tamra_7pay_start_date = None
    tamra_7pay_av = 0.0
    company_code = "01"
    primary_insured_name = "Test Policy"
    primary_insured_birth_date = None
    product_type = "UL"
    issue_state = "TX"
    company_name = "TEST"
    preferred_loans_available = False

    def mv_av(self, _index):
        return 10_000.0

    def mv_coi_charge(self, _index):
        return 0.0

    def mv_expense_charge(self, _index):
        return 0.0

    def mv_other_charge(self, _index):
        return 0.0

    def mv_monthly_deduction(self, _index):
        return 0.0

    def tamra_7pay_premium_paid(self, _year):
        return 0.0

    def tamra_7pay_withdrawals(self, _year):
        return 0.0

    def get_base_coverages(self):
        return [
            self._coverage(1, "", None),
            self._coverage(2, "", None),
            self._coverage(3, "0", date(2009, 2, 3)),
        ]

    def get_substandard_ratings(self):
        return []

    def get_benefits(self):
        return []

    def get_riders(self):
        return []

    def cov_band(self, _cov_pha_nbr):
        return 1

    @staticmethod
    def _coverage(phase, status, status_date):
        return SimpleNamespace(
            cov_pha_nbr=phase,
            face_amount=100_000.0,
            orig_amount=100_000.0,
            units=100.0,
            vpu=1000.0,
            issue_date=date(2000, 1, 1),
            issue_age=40,
            sex_code="M",
            rate_class="N",
            table_rating=0,
            flat_extra=0.0,
            flat_cease_date=None,
            cov_status=status,
            nxt_chg_typ_cd=status,
            nxt_chg_dt=status_date,
            terminate_date=None,
            maturity_date=date(2121, 1, 1),
            coi_rate=None,
        )


def test_build_illustration_data_excludes_terminated_base_coverages(monkeypatch):
    monkeypatch.setattr(illustration_policy_service, "get_policy_info", lambda *_args: _FakePolicyInfo())
    monkeypatch.setattr(illustration_policy_service, "Rates", _FakeRates)
    monkeypatch.setattr(
        illustration_policy_service,
        "load_plancode",
        lambda _plancode: PlancodeConfig(plancode="TESTUL", gint=0.0, dbd=0.0),
    )

    policy = illustration_policy_service.build_illustration_data("U0126221")

    assert [segment.coverage_phase for segment in policy.segments] == [1, 2]
    assert policy.face_amount == pytest.approx(200_000.0)
    assert policy.units == pytest.approx(200.0)
    assert policy.total_face == pytest.approx(200_000.0)
    assert policy.band == 2