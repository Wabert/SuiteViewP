"""Golden characterization for PolView refactor seams.

The fixtures are synthetic and in-memory. They pin policy/rate/service outputs
that are intentionally preserved while the implementations are split into
smaller spec-driven pieces.
"""
from __future__ import annotations

import dataclasses
import json
from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from suiteview.core.rates import Rates
from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from suiteview.polview.models.policy_sections.rates import RatesSection
from suiteview.polview.services import glp_exception
from suiteview.polview.services import policy_insights
from suiteview.polview.services import reinstatement as rein

GOLDEN_DIR = Path(__file__).parent / "golden" / "polview"


def _normalize(value):
    if dataclasses.is_dataclass(value):
        return _normalize(dataclasses.asdict(value))
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _normalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def _golden_text(value) -> str:
    return json.dumps(_normalize(value), indent=2, sort_keys=True, allow_nan=False) + "\n"


class _MatrixPolicy:
    build_coverage_rate_matrix = RatesSection.build_coverage_rate_matrix
    build_policy_rate_matrix = RatesSection.build_policy_rate_matrix
    build_benefit_rate_matrix = RatesSection.build_benefit_rate_matrix
    _whole_dollars = staticmethod(RatesSection._whole_dollars)
    _translate_sex_for_rates = RatesSection._translate_sex_for_rates

    policy_number = "U9990001"
    company_code = "01"
    product_type = "UL"
    is_advanced_product = True
    product_rules = SimpleNamespace(rate_family="UL", is_advanced=True)
    issue_state = "TX"

    @property
    def identity(self):
        return self

    @property
    def product(self):
        return self

    @property
    def coverages(self):
        return self

    @property
    def benefits(self):
        return self

    @property
    def rates(self):
        return self

    @property
    def status(self):
        return self

    def _product_rules_for_rate_display(self):
        return self.product_rules

    def cov_issue_date(self, _index):
        return date(2020, 1, 15)

    def cov_maturity_date(self, _index):
        return date(2025, 1, 15)

    def cov_issue_age(self, _index):
        return 40

    def cov_plancode(self, _index):
        return "TESTUL"

    def cov_amount(self, _index):
        return Decimal("250000")

    def cov_orig_amount(self, _index):
        return Decimal("200000")

    def cov_table_rating(self, _index):
        return 2

    def cov_flat_extra(self, _index):
        return Decimal("1.25")

    def cov_flat_cease_date(self, _index):
        return date(2023, 1, 15)

    def renewal_cov_sex_code(self, _index):
        return "1"

    def renewal_cov_rateclass_by_cov(self, _index):
        return "N"

    def cov_band(self, _index):
        return 3

    def rates_mtp(self, _index):
        return 100.25

    def rates_ctp(self, _index):
        return 80.5

    def rates_tbl1_mtp(self, _index):
        return "NA"

    def rates_tbl1_ctp(self, _index):
        return "NA"

    def rates_coi(self, _index, scale=1):
        return [None, 1.1, 1.2, 1.3] if scale == 1 else [None, 9.1, 9.2]

    def rates_epu(self, _index, scale=1):
        return [None, 0.1, 0.2] if scale == 1 else None

    def rates_scr(self, _index, scale=1):
        return [None, 5.0, 4.0, 3.0]

    def rates_tpp(self, _scale):
        return [None, 0.05, 0.04]

    def rates_epp(self, _scale):
        return None

    def rates_mfee(self, _scale):
        return [None, 7.5]

    def rates_corr(self):
        return [None, 250.0, 240.0, 230.0]

    def get_benefits(self):
        return [
            SimpleNamespace(
                benefit_code="10",
                benefit_type_cd="1",
                issue_age=42,
                issue_date=date(2022, 1, 15),
            )
        ]

    def rates_ben_mtp(self, _index):
        return 12.34

    def rates_ben_ctp(self, _index):
        return ""

    def rates_ben_coi(self, _index, _scale=1):
        return [None, 0.7, 0.8]


def _matrix_payload():
    policy = _MatrixPolicy()
    return {
        "coverage": policy.rates.build_coverage_rate_matrix(1),
        "policy": policy.rates.build_policy_rate_matrix(),
        "benefit": policy.rates.build_benefit_rate_matrix(1),
    }


def _rates_payload(monkeypatch):
    Rates._cache.clear()
    rates = Rates()

    def fetch(sql, _params):
        if "Select_RATE_BANDSPECS" in sql:
            return [(0, 1, date(1900, 1, 1)), (100000, 2, date(1900, 1, 1))]
        return [(Decimal("1.25"),), (Decimal("1.50"),)]

    monkeypatch.setattr(rates, "_fetch_rates", fetch)
    return {
        "keys": {
            "coi": rates._get_rate_key("COI", "TESTUL", 40, "M", "0", 3, 1),
            "epp": rates._get_rate_key("EPP", "TESTUL", sex="F", rateclass="N", band=2, scale=1),
            "corr": rates._get_rate_key("CORR", "TESTUL", issue_age=40),
            "scr": rates._get_rate_key("SCR", "TESTUL", 40, "M", "N", 3, 1, state="TX"),
            "benefit": rates._get_rate_key("BENCOI", "TESTUL", 40, "M", "N", 3, 1, "10"),
            "bands": rates._get_rate_key("BANDSPECS", "TESTUL"),
        },
        "lookups": {
            "coi": rates.get_coi("TESTUL", 40, "M", "N", 1, 3),
            "bandspecs": rates.get_rates("BANDSPECS", "TESTUL"),
            "band": rates.get_band("TESTUL", 125000, issue_date=date(2024, 1, 1)),
        },
    }


class _SummaryPolicy:
    exists = True
    region = "CKAS"
    company_code = "01"
    system_code = "I"
    policy_number = "U9990001"
    company_name = "ANICO"
    premium_pay_status_code = "54"
    premium_pay_status_description = "Grace period"
    is_advanced_product = True
    product_type = "UL"
    product_line_description = "Universal Life"
    in_grace = True
    grace_period_expiry_date = date(2026, 10, 5)
    valuation_date = date(2026, 9, 15)
    paid_to_date = date(2026, 8, 15)
    policy_year = 7
    attained_age = 46
    suspense_code = "0"
    mec_indicator = "1"
    policy_debt = Decimal("123.45")
    reins_partner = "R"
    gpt_cvat = "GPT"
    standard_death_benefit = Decimal("250000")
    corridor_death_benefit = Decimal("275000")
    insured_lives_description = "Joint Second to Die"
    primary_insured_birth_date = date(1980, 9, 26)
    db_option_description = "Option A"
    total_death_benefit = Decimal("275000")
    primary_insured_name = "Hidden In Copy"

    def cached_reads_only(self):
        return nullcontext()

    def get_coverages(self):
        return [
            SimpleNamespace(
                plancode="TESTUL",
                form_number="FORM1",
                issue_date=date(2020, 9, 26),
                issue_age=40,
            )
        ]


def _policy_summary_payload():
    summary = policy_insights.build_policy_summary(_SummaryPolicy(), today=date(2026, 9, 26))
    return {
        "summary": summary,
        "rows": policy_insights.summary_rows(summary),
        "text": policy_insights.summary_text(summary),
        "html": policy_insights.summary_html(summary),
    }


def _reinstatement_payload(monkeypatch):
    policy = IllustrationPolicyData(
        policy_number="SYNTHETIC",
        plancode="REINTEST",
        product_type="UL",
        issue_date=date(2000, 1, 15),
        valuation_date=date(2026, 1, 15),
        issue_age=30,
        attained_age=56,
        maturity_age=121,
        policy_year=27,
        policy_month=1,
        duration=313,
        face_amount=100000.0,
        units=100.0,
        account_value=10.0,
        modal_premium=999.0,
        billing_frequency=1,
        def_of_life_ins="GPT",
        glp=100000.0,
        gsp=100000.0,
        accumulated_glp=100000.0,
        premiums_paid_to_date=1000.0,
        cost_basis=1000.0,
        premiums_ytd=0.0,
        mtp=10.0,
        accumulated_mtp=1000.0,
        segments=[
            CoverageSegment(
                issue_date=date(2000, 1, 15),
                issue_age=30,
                face_amount=100000.0,
                original_face_amount=100000.0,
                units=100.0,
                rate_sex="M",
                rate_class="N",
            )
        ],
    )
    config = PlancodeConfig(
        plancode="REINTEST",
        gint=0.0,
        dbd=0.0,
        corridor_code=None,
        epu_code="0",
        mfee="10",
        premium_load="0",
        snet_period=0,
        lapse_value="SV",
        shadow_int_rate_code="0",
        shadow_dbd_rate="0",
        shadow_mfee=10.0,
    )
    rates = IllustrationRates(
        coi=[0.0, 0.0],
        segment_coi={1: [0.0, 0.0]},
        scr=[0.0, 0.0],
        shadow_coi=[0.0, 0.0],
    )
    monkeypatch.setattr(rein, "load_plancode", lambda _plancode: config)
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _plancode: config)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_args: BonusConfig())
    summary = rein.reinstatement_summary(
        SimpleNamespace(
            exists=True,
            product_type="UL",
            last_entry_code="Q",
            issue_date=date(2000, 1, 15),
            terminate_date=date(2025, 1, 15),
        ),
        date(2026, 2, 15),
    )
    result = rein.project_home_office_reinstatement(policy, summary, rates=rates)
    return {
        "summary": result.summary,
        "premium": result.premium,
        "basis": result.basis,
        "breakdown": result.breakdown,
        "explanation": result.explanation,
        "states": [
            {
                "date": state.date,
                "gross_premium": state.gross_premium,
                "av_after_deduction": state.av_after_deduction,
                "surrender_value": state.surrender_value,
            }
            for state in result.states
        ],
    }


def _glp_payload():
    policy = IllustrationPolicyData(
        issue_date=date(2020, 7, 1),
        valuation_date=date(2024, 6, 1),
        policy_year=4,
        account_value=50000.0,
        premiums_paid_to_date=9000.0,
        withdrawals_to_date=0.0,
        accumulated_glp=10000.0,
        glp=-2000.0,
        gsp=0.0,
    )
    return glp_exception._build_result(glp_exception.GlpResultInputs(
        policy,
        date(2025, 7, 1),
        13,
        1200.0,
        2500.0,
        0.1,
        15.0,
        3000.0,
        [
            glp_exception.GlpForecastRow(
                date(2024, 7, 1), 5, 1, 100.0, 20.0, 5.0, 49000.0
            )
        ],
        glp_exception.PremiumAdjustmentSinceValuation(gross_premium=200.0, net_premium=180.0),
        49820.0,
        8800.0,
    ))


def polview_characterization_payload(monkeypatch):
    return {
        "matrices": _matrix_payload(),
        "rates": _rates_payload(monkeypatch),
        "policy_summary": _policy_summary_payload(),
        "reinstatement": _reinstatement_payload(monkeypatch),
        "glp_result": _glp_payload(),
    }


def test_polview_refactor_characterization_matches_golden(monkeypatch):
    assert _golden_text(polview_characterization_payload(monkeypatch)) == (
        GOLDEN_DIR / "refactor_characterization.json"
    ).read_text(encoding="utf-8")
