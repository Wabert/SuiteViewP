from __future__ import annotations

from types import SimpleNamespace
from datetime import date

import pytest

from suiteview.abrquote.core import abr_policy_service


def test_find_policy_companies_uses_policy_service_unresolved_lookup(monkeypatch):
    calls = []
    unresolved = SimpleNamespace(exists=False, available_companies=["01", "04"])

    def get_policy_info(*args, **kwargs):
        calls.append((args, kwargs))
        return unresolved

    monkeypatch.setattr(abr_policy_service, "get_policy_info", get_policy_info)

    assert abr_policy_service.find_policy_companies("U1234567", "CKPR") == ["01", "04"]
    assert calls == [
        (
            ("U1234567",),
            {
                "company_code": None,
                "region": "CKPR",
                "include_unresolved": True,
            },
        )
    ]


def test_find_policy_companies_propagates_lookup_failure(monkeypatch):
    def get_policy_info(*args, **kwargs):
        raise RuntimeError("DB2 unavailable")

    monkeypatch.setattr(abr_policy_service, "get_policy_info", get_policy_info)

    with pytest.raises(RuntimeError, match="DB2 unavailable"):
        abr_policy_service.find_policy_companies("U1234567", "CKPR")


def test_build_abr_policy_raises_when_policy_lookup_missing(monkeypatch):
    monkeypatch.setattr(abr_policy_service, "get_policy_info", lambda *a, **k: None)

    with pytest.raises(abr_policy_service.ABRPolicyLookupError, match="not found"):
        abr_policy_service.build_abr_policy(
            "U1234567",
            "CKPR",
            company_code="01",
            as_of_date=date(2026, 9, 3),
        )


def test_rider_extraction_uses_explicit_as_of_date():
    identity = abr_policy_service.PolicyIdentity(
        policy_number="U1234567",
        region="CKPR",
        insured_name="",
        issue_age=40,
        attained_age=46,
        sex="F",
        rate_sex="F",
        rate_class="N",
        face_amount=100000,
        db_option="",
        issue_date=date(2020, 1, 15),
        maturity_age=75,
        maturity_date=date(2055, 1, 15),
        issue_state="TX",
        plan_code="TEST",
        product_type="TERM",
        base_plancode="TEST",
        billing_mode=1,
        policy_month=8,
        policy_year=7,
        paid_to_date=None,
        modal_premium=0,
        annual_premium=0,
    )
    coverage = SimpleNamespace(
        is_base=True,
        cov_pha_nbr=1,
        sex_code="2",
        rate_class="N",
        table_rating=0,
        issue_age=40,
        face_amount=100000,
        plancode="TEST",
        cov_annual_premium=None,
        premium_rate=None,
        units=100,
        person_code="00",
    )

    def benefit(cease_date):
        return SimpleNamespace(
            cov_pha_nbr=1,
            benefit_type_cd="3",
            benefit_subtype_cd="0",
            units=1,
            vpu=0,
            benefit_amount=100000,
            issue_age=40,
            rating_factor=0,
            coi_rate=1.23,
            cease_date=cease_date,
        )

    pi = SimpleNamespace(
        get_coverages=lambda: [coverage],
        get_benefits=lambda: [benefit(date(2026, 9, 2)), benefit(date(2026, 9, 3))],
        primary_insured_db_layers=[],
    )
    result = abr_policy_service.extract_riders_and_layers(
        "U1234567",
        pi,
        identity,
        as_of_date=date(2026, 9, 3),
    )

    assert len(result.riders) == 1
    assert result.riders[0].cease_date == date(2026, 9, 3)
