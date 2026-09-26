"""Convenience adapter from live CyberLife tabs to immutable criteria."""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from suiteview.audit.cyberlife_criteria import AuditCriteriaBundle, CriteriaCollector


def collect_cyberlife_tabs(
    schema: str,
    sys_code: str,
    max_count_text: str,
    tabs: Mapping[str, Any],
    *,
    coverage_level: bool = False,
    coverage_scope: str = "All Covs",
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
            "policy": tabs["policy_tab"],
            "display": tabs["display_tab"],
            "policy2": tabs["policy2_tab"],
            "adv": tabs["adv_tab"],
            "coverages": tabs["coverages_tab"],
            "plancode": tabs["plancode_tab"],
            "benefits": tabs["benefits_tab"],
            "transaction": tabs.get("transaction_tab"),
            "custom_display": tabs.get("custom_display_tab"),
            "people": tabs.get("people_tab"),
            "segment52": tabs.get("segment52_tab"),
            "wl": tabs.get("wl_tab"),
        },
    )).collect()
