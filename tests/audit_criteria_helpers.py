"""Test helper for building CyberLife SQL criteria from tab fixtures."""
from __future__ import annotations

from datetime import date
from typing import Any

from suiteview.audit.cyberlife_criteria import AuditCriteriaBundle, CriteriaCollector


def collect_audit_criteria(
    schema: str,
    sys_code: str,
    max_count_text: str,
    policy_tab: Any,
    display_tab: Any,
    policy2_tab: Any,
    adv_tab: Any,
    coverages_tab: Any,
    plancode_tab: Any,
    benefits_tab: Any,
    transaction_tab: Any | None = None,
    coverage_level: bool = False,
    coverage_scope: str = "All Covs",
    custom_display_tab: Any | None = None,
    people_tab: Any | None = None,
    segment52_tab: Any | None = None,
    wl_tab: Any | None = None,
    as_of: date | None = None,
):
    return CriteriaCollector(AuditCriteriaBundle(
        schema=schema,
        sys_code=sys_code,
        max_count_text=max_count_text,
        coverage_level=coverage_level,
        coverage_scope=coverage_scope,
        as_of=as_of,
        tabs={
            "policy": policy_tab,
            "display": display_tab,
            "policy2": policy2_tab,
            "adv": adv_tab,
            "coverages": coverages_tab,
            "plancode": plancode_tab,
            "benefits": benefits_tab,
            "transaction": transaction_tab,
            "custom_display": custom_display_tab,
            "people": people_tab,
            "segment52": segment52_tab,
            "wl": wl_tab,
        },
    )).collect()
