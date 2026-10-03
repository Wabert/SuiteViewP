"""Synthetic UL_Rates schema ``rates`` plan facts for ``load_plancode`` unit tests.

``plan_facts`` builds a ``PlanFacts`` with the minimum facts a UL plan needs to load
(PLAN_DEF ages, GINT and the regular loan rates); tests override what they exercise and
monkeypatch ``plancode_config.load_plan_facts`` to return it.
"""
from __future__ import annotations

from suiteview.illustration.models.plan_facts import PlanFacts


def plan_facts(plancode: str, **overrides) -> PlanFacts:
    values = dict(
        plancode=plancode,
        company="01",
        schema_family="UL",
        description="",
        maturity_age=121,
        premium_cease_age=121,
        cirf_key="",
        fund_keys="",
        shadow_legacy_plancode="",
        gint=0.03,
        db_discount=None,
        loan_reg_chg=0.06,
        loan_reg_crd=0.04,
        loan_pref_chg=None,
        loan_pref_crd=None,
        snet_by_issue_age=None,
        corridor_by_age=None,
    )
    values.update(overrides)
    return PlanFacts(**values)
