"""``load_plancode``: plan facts only from UL_Rates schema ``rates``, product rules from
the plancode table, the ISWL corridor fallback (tRates_CORR.json) and the plan-basis
notices the Illustration window shows.

Offline: ``plancode_config.load_plan_facts`` and the table cache are replaced by
synthetic facts/rows (``tests.plan_facts_fixtures``).
"""
from __future__ import annotations

import logging

import pytest

import suiteview.illustration.core.corridor_rates as corridor_rates
import suiteview.illustration.models.plancode_config as pc
from suiteview.illustration.core.corridor_rates import corridor_factor, uses_iswl_corridor_fallback
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


def test_iswl_gpt_policy_without_corridor_notices_the_standard_corridor():
    config = PlancodeConfig(plancode=PLAN, product_family="ISWL")
    notices = plan_basis_warnings(config, IllustrationPolicyData(def_of_life_ins="GPT"))
    assert len(notices) == 1
    assert "ISWL" in notices[0] and "standard 7702 corridor (tRates_CORR.json)" in notices[0]
    assert plan_basis_warnings(config, IllustrationPolicyData(def_of_life_ins="CVAT")) == []


# ── ISWL corridor fallback: tRates_CORR.json standard set ──────────────────


def test_iswl_without_corr_uses_the_standard_corridor_and_logs_once(monkeypatch, caplog):
    monkeypatch.setattr(corridor_rates, "_WARNED", set())
    config = PlancodeConfig(plancode=PLAN, product_family="ISWL")
    assert uses_iswl_corridor_fallback(config)
    with caplog.at_level(logging.WARNING, logger=corridor_rates.__name__):
        factors = {age: corridor_factor(config, age) for age in (10, 45, 94, 95, 121)}
    assert factors == {10: 2.5, 45: 2.15, 94: 1.01, 95: 1.01, 121: 1.01}
    for age in range(0, 95):
        assert corridor_factor(config, age) == CORRIDOR_1[age]
    assert len([r for r in caplog.records if PLAN in r.getMessage()]) == 1


def test_iswl_with_corr_and_non_iswl_without_corr_do_not_use_the_fallback():
    iswl = PlancodeConfig(plancode=PLAN, product_family="ISWL", corridor_by_age={0: 3.0, 95: 1.0})
    assert not uses_iswl_corridor_fallback(iswl)
    assert corridor_factor(iswl, 0) == 3.0 and corridor_factor(iswl, 100) == 1.0
    ul = PlancodeConfig(plancode=PLAN)
    assert not uses_iswl_corridor_fallback(ul)
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
