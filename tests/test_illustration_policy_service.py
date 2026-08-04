from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import illustration_policy_service
from suiteview.illustration.models.plancode_config import PlancodeConfig


class _FakeRates:
    def get_band(self, _plancode, face_amount, issue_date=None):
        return 2 if float(face_amount or 0.0) == 200_000.0 else 9

    def get_index_illustration_rates(
        self, company, plancode, illustration_date, rga_indicator
    ):
        assert (company, plancode, illustration_date, rga_indicator) == (
            "01", "TESTUL", date(2026, 7, 29), "R")
        return {"IX": 0.061}

    def get_index_strategy_parameters(
        self, plancode, illustration_date, rga_indicator
    ):
        assert (plancode, illustration_date, rga_indicator) == (
            "TESTUL", date(2026, 7, 29), "R")
        return {"IX": {"cap": 0.095}}

    def get_index_benchmark_minmax(
        self, plancode, illustration_date, rga_indicator
    ):
        assert (plancode, illustration_date, rga_indicator) == (
            "TESTUL", date(2026, 7, 29), "R")
        return {"minimum": 0.044, "maximum": 0.0786}

    def get_index_market_returns(self):
        return {"SP500": [{"date": date(2023, 12, 31), "return": 0.2423}]}


class _FakePolicyInfo:
    exists = True
    base_plancode = "TESTUL"
    issue_date = date(2000, 1, 1)
    valuation_date = date(2024, 1, 1)
    base_issue_age = 40
    base_sex_code = "M"
    base_rate_class = "N"
    base_total_face_amount = 300_000.0
    base_band_specified_amount = 200_000.0  # two active 100k covs (third terminated)
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
    reins_partner = "R"
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


def test_active_rider_benefit_codes_excludes_hash_and_ceased():
    """Active riders + premium benefits, in order; '#'-type and ceased dropped."""
    pi = SimpleNamespace(
        valuation_date=date(2024, 1, 1),
        issue_date=date(2000, 1, 1),
        get_riders=lambda: [
            SimpleNamespace(plancode="RIDER1", cease_date=None, terminate_date=None),
            # ceased before the valuation date -> dropped
            SimpleNamespace(plancode="RIDERX", cease_date=date(2010, 1, 1), terminate_date=None),
        ],
        get_benefits=lambda: [
            SimpleNamespace(benefit_code="12", benefit_type_cd="1", cease_date=None, terminate_date=None),
            # type "3" with a "#" subtype is still a premium benefit -> kept
            SimpleNamespace(benefit_code="3#", benefit_type_cd="3", cease_date=None, terminate_date=None),
            # "#"-type ABR accelerated rider, no premium -> dropped
            SimpleNamespace(benefit_code="#4", benefit_type_cd="#", cease_date=None, terminate_date=None),
            # future cease date -> still active
            SimpleNamespace(benefit_code="76", benefit_type_cd="7", cease_date=date(2099, 1, 1), terminate_date=None),
        ],
    )

    assert illustration_policy_service.active_rider_benefit_codes(pi) == "RIDER1, 12, 3#, 76"


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


def test_build_illustration_data_loads_illustration_date_index_data(monkeypatch):
    class _FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 29)

    monkeypatch.setattr(
        illustration_policy_service, "get_policy_info", lambda *_args: _FakePolicyInfo())
    monkeypatch.setattr(illustration_policy_service, "Rates", _FakeRates)
    monkeypatch.setattr(illustration_policy_service, "date", _FixedDate)
    monkeypatch.setattr(illustration_policy_service, "is_iul_plan", lambda _plan: True)
    monkeypatch.setattr(
        illustration_policy_service,
        "load_plancode",
        lambda _plancode: PlancodeConfig(plancode="TESTUL", gint=0.0, dbd=0.0),
    )

    policy = illustration_policy_service.build_illustration_data("U0126221")

    assert policy.reins_partner == "R"
    assert policy.valuation_date == date(2024, 1, 1)
    assert policy.illustration_date == date(2026, 7, 29)
    assert policy.index_illustration_rates == {"IX": 0.061}
    assert policy.index_strategy_parameters == {"IX": {"cap": 0.095}}
    assert policy.index_benchmark_minimum == pytest.approx(0.044)
    assert policy.index_benchmark_maximum == pytest.approx(0.0786)
    assert policy.index_market_returns == {
        "SP500": [{"date": date(2023, 12, 31), "return": 0.2423}]
    }


def test_coverage_segment_data_warnings_identifies_blank_active_fields():
    policy = _FakePolicyInfo()
    coverages = policy.get_base_coverages()
    coverages[1].face_amount = None
    coverages[1].rate_class = " "
    coverages[1].issue_age = None
    coverages[2].face_amount = None
    policy.get_base_coverages = lambda: coverages

    warnings = illustration_policy_service.coverage_segment_data_warnings(policy)

    assert warnings == [
        "CyberLife coverage data is incomplete: Segment 2: Current Specified "
        "Amount, Rate Class, Issue Age."
    ]


def test_coverage_segment_data_warnings_is_clear_for_complete_segments():
    assert illustration_policy_service.coverage_segment_data_warnings(
        _FakePolicyInfo()
    ) == []