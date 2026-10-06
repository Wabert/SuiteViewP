"""``load_plancode``: plan facts only from UL_Rates schema ``rates``, product rules from
the plancode table and the plan-basis notices the Illustration window shows.

Offline: ``plancode_config.load_plan_facts`` and the table cache are replaced by
synthetic facts/rows (``tests.plan_facts_fixtures``).
"""
from __future__ import annotations

from datetime import date

import pytest

import suiteview.illustration.models.plancode_config as pc
from suiteview.illustration.core.corridor_rates import corridor_factor
from suiteview.illustration.core.rate_loader import premium_load_schedules
from suiteview.illustration.core.rate_validation import plan_basis_warnings
from suiteview.illustration.models.plancode_config import (
    DATABASE_KEYS,
    MissingPlancodeError,
    PlancodeConfig,
    load_plancode,
)
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from tests.corridor_fixtures import CORRIDOR_1
from tests.plan_facts_fixtures import plan_facts

PLAN = "ZZPLAN00"


def _load(monkeypatch, *, facts=None, **row):
    monkeypatch.setattr(pc, "_CONFIG_CACHE", {})
    monkeypatch.setattr(pc, "_TABLE_CACHE", {PLAN: {"Plancode": PLAN, "SA_Basis": "CurrentSA", **row}})
    monkeypatch.setattr(pc, "load_plan_facts", lambda _plancode: facts)
    return load_plancode(PLAN)


@pytest.mark.parametrize("key", ["MFEE", "PremiumLoad", "CorridorCode", "SafetyNetPeriod",
                                 "ShadowEPUCode", "GINT"])
def test_stale_plan_fact_key_in_the_table_raises(monkeypatch, key):
    assert key in DATABASE_KEYS
    with pytest.raises(ValueError, match=f"carries {key}"):
        _load(monkeypatch, facts=plan_facts(PLAN), **{key: 1})


def test_shipped_table_carries_no_plan_facts():
    for plancode, row in pc._load_plancode_table().items():
        assert not set(DATABASE_KEYS) & row.keys(), plancode


def test_plan_not_loaded_in_schema_rates_is_a_missing_plancode(monkeypatch):
    with pytest.raises(MissingPlancodeError, match="not loaded in UL_Rates schema rates"):
        _load(monkeypatch, facts=None)


def test_plan_without_a_table_row_is_a_missing_plancode(monkeypatch):
    monkeypatch.setattr(pc, "_CONFIG_CACHE", {})
    monkeypatch.setattr(pc, "_TABLE_CACHE", {})
    with pytest.raises(MissingPlancodeError):
        load_plancode(PLAN)


@pytest.mark.parametrize("missing,label", [
    ("gint", "PLAN GINT"),
    ("loan_reg_chg", "LOAN_REG_CHG"),
    ("loan_reg_crd", "LOAN_REG_CRD"),
    ("maturity_age", "MaturityAge"),
    ("premium_cease_age", "PremiumCeaseAge"),
])
def test_schema_without_a_required_fact_raises(monkeypatch, missing, label):
    with pytest.raises(ValueError, match=label):
        _load(monkeypatch, facts=plan_facts(PLAN, **{missing: None}))


def test_plan_facts_come_from_schema_rates(monkeypatch):
    config = _load(monkeypatch, facts=plan_facts(
        PLAN, gint=0.04, loan_reg_chg=0.08, loan_reg_crd=0.06,
        loan_pref_chg=0.065, loan_pref_crd=0.06,
        snet_by_issue_age={45: 5}, corridor_by_age=CORRIDOR_1,
    ))
    assert (config.gint, config.dbd) == (0.04, 0.04)  # no DB_DISCOUNT: DBD is GINT
    assert (config.loan_charge_rate_guar, config.loan_charge_rate_curr) == (0.08, 0.06)
    assert (config.pref_loan_charge_rate_guar, config.pref_loan_charge_rate_curr) == (0.065, 0.06)
    assert config.safety_net_years(45) == 5 and config.safety_net_years(46) == 0
    assert corridor_factor(config, 45) == 2.15
    assert config.illustration_overrides == ()


def test_no_loan_pref_rows_means_no_preferred_loan(monkeypatch):
    config = _load(monkeypatch, facts=plan_facts(PLAN))
    assert (config.pref_loan_charge_rate_guar, config.pref_loan_charge_rate_curr) == (0.0, 0.0)


def test_db_discount_replaces_gint_as_the_death_benefit_discount(monkeypatch):
    config = _load(monkeypatch, facts=plan_facts(PLAN, gint=0.03, db_discount=0.045))
    assert (config.gint, config.dbd) == (0.03, 0.045)


def test_plan_without_snet_or_corr_has_no_safety_net_and_no_corridor(monkeypatch):
    config = _load(monkeypatch, facts=plan_facts(PLAN))
    assert config.snet_by_issue_age == {} and config.safety_net_years(45) == 0
    assert config.corridor_by_age is None and corridor_factor(config, 45) == 1.0


def test_illustration_age_override_replaces_plan_def_and_is_noticed(monkeypatch):
    config = _load(monkeypatch, facts=plan_facts(PLAN, corridor_by_age=CORRIDOR_1),
                   IllustrationMaturityAgeOverride=100)
    assert (config.maturity_age, config.premium_cease_age) == (100, 121)
    assert config.illustration_overrides == ("MaturityAge 100 (PLAN_DEF 121)",)
    assert plan_basis_warnings(config, IllustrationPolicyData(def_of_life_ins="GPT")) == [
        f"{PLAN}: illustration age override MaturityAge 100 (PLAN_DEF 121)."]


# ── plan_basis_warnings: GPT policy on a plan without CORR ─────────────────


def test_gpt_policy_on_a_plan_without_corridor_is_noticed():
    config = PlancodeConfig(plancode=PLAN)
    notices = plan_basis_warnings(config, IllustrationPolicyData(def_of_life_ins="GPT"))
    assert len(notices) == 1
    assert "no GPT corridor (CORR)" in notices[0] and notices[0].startswith(PLAN)


def test_iswl_gpt_policy_without_corridor_has_no_corridor_and_is_noticed():
    """No ISWL fallback: GPT ISWL plans carry CORR in schema rates; one without it is
    noticed like any plan, and a CVAT ISWL policy has no corridor and no notice."""
    config = PlancodeConfig(plancode=PLAN, product_family="ISWL")
    assert corridor_factor(config, 45) == 1.0
    notices = plan_basis_warnings(config, IllustrationPolicyData(def_of_life_ins="GPT"))
    assert len(notices) == 1 and "no GPT corridor (CORR)" in notices[0]
    assert plan_basis_warnings(config, IllustrationPolicyData(def_of_life_ins="CVAT")) == []


def test_iswl_with_corr_uses_it():
    iswl = PlancodeConfig(plancode=PLAN, product_family="ISWL", corridor_by_age={0: 3.0, 95: 1.0})
    assert corridor_factor(iswl, 0) == 3.0 and corridor_factor(iswl, 100) == 1.0
    ul = PlancodeConfig(plancode=PLAN)
    assert corridor_factor(ul, 45) == 1.0


def test_cvat_policy_or_plan_with_corridor_has_no_corridor_notice():
    assert plan_basis_warnings(PlancodeConfig(plancode=PLAN),
                               IllustrationPolicyData(def_of_life_ins="CVAT")) == []
    assert plan_basis_warnings(PlancodeConfig(plancode=PLAN, corridor_by_age=CORRIDOR_1),
                               IllustrationPolicyData(def_of_life_ins="GPT")) == []


# ── premium loads: schema cells only ───────────────────────────────────────


class _NoLoadRates:
    def get_rates(self, *_args, **_kwargs):
        return None


def test_plan_without_premium_load_cells_has_no_percentage_load():
    segment = CoverageSegment(issue_age=45, rate_sex="M", rate_class="N")
    assert premium_load_schedules(_NoLoadRates(), PLAN, segment, scale=1, band=1) == ([], [])


# ── interest day count: CyberLife PDF DIFFCMPD-FIX-COMPOUND ──────────────────


@pytest.mark.parametrize("plancode, method", [
    # All 16 rows corrected to CyberLife's DIFFCMPD (2026-10-06). DIFFCMPD 1 = daily
    # (exact days); the history replay credits exact days on these ASL plans, incl.
    # 1S135C00 where DULCVICP is 2.
    ("1S133229", "ExactDays"), ("1S133729", "ExactDays"), ("1S133A29", "ExactDays"),
    ("1S133B2X", "ExactDays"), ("1S133C29", "ExactDays"), ("1S133D2X", "ExactDays"),
    ("1S133E29", "ExactDays"), ("1S133F29", "ExactDays"), ("1S133G29", "ExactDays"),
    ("1S133H29", "ExactDays"), ("1S135C00", "ExactDays"), ("1S135M0X", "ExactDays"),
    ("1S135N00", "ExactDays"), ("1S135W29", "ExactDays"), ("1S135X2X", "ExactDays"),
    # DIFFCMPD 2 = monthly (1/12 of a year): the corrected row and two unchanged ones.
    ("1S135A00", "1/12th"), ("1S134A00", "1/12th"), ("1S133I29", "1/12th"),
])
def test_asl_interest_method_follows_cyberlife_diffcmpd(plancode, method):
    import json
    from pathlib import Path

    table = Path(pc.__file__).resolve().parents[1] / "plancodes" / "plancode_table.json"
    rows = {row["Plancode"]: row for row in json.loads(table.read_text(encoding="utf-8"))["Plancodes"]}
    assert rows[plancode]["Interest_Method"] == method


# ── minimum face after a withdrawal: CyberLife PDF DBSMIAMT issue minimum ────


@pytest.mark.parametrize("plancode, minimum", [
    # DB2 CKPR 2026-10-06: reduced DBO A faces sit at, never below, the plan's issue
    # minimum (01_UL055639 1U130N2X at 10,000; 18 MLUL502 at 100,000).
    ("1U130N2X", 10_000), ("1U130M29", 10_000), ("1U134500", 5_000),
    ("MLUL502", 100_000), ("1U135000", 50_000),
    ("1U135D00", 25_000),  # PDF minimum equals the default
    # MLUL spec minimum 100,000 (Robert Haessly 10/6). 1U135F00 is the MLUL product
    # (PDF form MLUL, user field MLUL2000; every in-force policy issued at >= 100,000)
    # although CyberLife's PDF DBSMIAMT carries the ANICO2000 21,000.
    ("MLUL", 100_000), ("1U135F00", 100_000),
])
def test_min_face_after_withdrawal_is_the_plan_issue_minimum(plancode, minimum):
    import json
    from pathlib import Path

    table = Path(pc.__file__).resolve().parents[1] / "plancodes" / "plancode_table.json"
    rows = {row["Plancode"]: row for row in json.loads(table.read_text(encoding="utf-8"))["Plancodes"]}
    assert rows[plancode].get("MinFaceAfterWD", 25_000) == minimum
    assert rows[plancode]["MinFaceEvidenced"] is True


@pytest.mark.parametrize("plancode", [
    # DBSMIUSE 0 / '#': the 25,000 default is unevidenced, so no decrease minimum.
    "1U145700", "1U1F4A00",
])
def test_unevidenced_minimum_face_is_not_flagged(plancode):
    import json
    from pathlib import Path

    table = Path(pc.__file__).resolve().parents[1] / "plancodes" / "plancode_table.json"
    rows = {row["Plancode"]: row for row in json.loads(table.read_text(encoding="utf-8"))["Plancodes"]}
    assert "MinFaceAfterWD" not in rows[plancode]
    assert "MinFaceEvidenced" not in rows[plancode]


def test_min_face_evidenced_is_read_from_the_table(monkeypatch):
    config = _load(monkeypatch, facts=plan_facts(PLAN), MinFaceAfterWD=100_000, MinFaceEvidenced=True)
    assert (config.min_face_after_wd, config.min_face_evidenced) == (100_000.0, True)
    default = _load(monkeypatch, facts=plan_facts(PLAN))
    assert (default.min_face_after_wd, default.min_face_evidenced) == (25_000.0, False)


# ── plancode-driven interest (exact_days_interest=None) on DIFFCMPD plans ────


def _table_interest_method(plancode: str) -> str:
    import json
    from pathlib import Path

    table = Path(pc.__file__).resolve().parents[1] / "plancodes" / "plancode_table.json"
    rows = {row["Plancode"]: row for row in json.loads(table.read_text(encoding="utf-8"))["Plancodes"]}
    return rows[plancode]["Interest_Method"]


@pytest.mark.parametrize("plancode, monthly_credit", [
    ("1S135A00", True),    # DIFFCMPD 2: 1/12 of a year
    ("1S133A29", False),   # DIFFCMPD 1: exact days
])
@pytest.mark.parametrize("month_date, days", [(date(2026, 7, 18), 31), (date(2026, 6, 18), 30)])
def test_plancode_interest_method_credits_by_diffcmpd_and_accrues_loans_on_actual_days(
    plancode, monthly_credit, month_date, days,
):
    from suiteview.illustration.core.bonus_rates import BonusConfig
    from suiteview.illustration.core.interest_calc import credit_interest
    from suiteview.illustration.core.rate_loader import IllustrationRates

    config = PlancodeConfig(plancode=plancode, interest_method=_table_interest_method(plancode))
    policy = IllustrationPolicyData(plancode=plancode, current_interest_rate=0.04)
    result = credit_interest(10_000.0, policy, config, IllustrationRates(), BonusConfig(), 20, 70,
                             month_date, exact_days_interest=None)
    expected = 1.04 ** (1 / 12) - 1 if monthly_credit else 1.04 ** (days / 365) - 1
    assert result.monthly_interest_rate == pytest.approx(expected)
    # CyberLife accrues fixed-loan interest on actual days on both compounding codes
    # (1S135A00 S1376650 and 1S133K29 S1338936 loan steps follow month length).
    assert result.fixed_loan_accrual_days == days
    # Variable (IUL) loans keep the crediting day count.
    assert result.loan_accrual_days == pytest.approx(365 / 12 if monthly_credit else days)


@pytest.mark.parametrize("forced, loan_days", [(True, 31.0), (False, 365 / 12)])
def test_explicit_interest_choice_drives_loan_accrual_too(forced, loan_days):
    from suiteview.illustration.core.bonus_rates import BonusConfig
    from suiteview.illustration.core.interest_calc import credit_interest
    from suiteview.illustration.core.rate_loader import IllustrationRates

    config = PlancodeConfig(plancode="1S135A00", interest_method="1/12th")
    policy = IllustrationPolicyData(plancode="1S135A00", current_interest_rate=0.04)
    result = credit_interest(10_000.0, policy, config, IllustrationRates(), BonusConfig(), 20, 70,
                             date(2026, 7, 18), exact_days_interest=forced)
    assert result.fixed_loan_accrual_days == pytest.approx(loan_days)
    assert result.loan_accrual_days == pytest.approx(loan_days)


def test_fixed_loans_accrue_on_their_own_day_count_and_variable_on_the_crediting_one():
    from suiteview.illustration.core.loan_handler import LoanState, accrue_loan_interest

    config = PlancodeConfig(plancode="1S135A00", loan_type="Arrears",
                            loan_charge_rate_guar=0.08, pref_loan_charge_rate_guar=0.06)
    loan = LoanState(rg_loan_princ=1_000.0, pf_loan_princ=1_000.0, vbl_loan_princ=1_000.0)
    accrued = accrue_loan_interest(loan, config, 365 / 12, 0.05, fixed_days_in_month=31.0)
    assert accrued.reg_loan_charge == pytest.approx(1_000.0 * 0.08 * 31 / 365)
    assert accrued.pref_loan_charge == pytest.approx(1_000.0 * 0.06 * 31 / 365)
    assert accrued.vbl_loan_charge == pytest.approx(1_000.0 * 0.05 / 12)
