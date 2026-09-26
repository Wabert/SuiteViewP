from __future__ import annotations

from types import SimpleNamespace

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
        abr_policy_service.build_abr_policy("U1234567", "CKPR", company_code="01")
