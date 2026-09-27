"""Shared policy instances, interactive resolution and cache invalidation."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from suiteview.polview.services import policy_service
from suiteview.polview.models import policy_information


@pytest.fixture
def factory(monkeypatch):
    policy_service.clear_cache()
    factory = Mock(return_value=SimpleNamespace(
        exists=True, company_code="01", system_code="I",
    ))
    monkeypatch.setattr(policy_information, "PolicyInformation", factory)
    yield factory
    policy_service.clear_cache()


def test_company_autodetection_shares_the_resolved_instance(factory):
    policy = policy_service.get_policy_info("SYNTHETIC", include_unresolved=True)
    assert policy_service.get_policy_info("synthetic", company_code="01") is policy
    factory.assert_called_once()


@pytest.mark.parametrize("company", [None, "01"])
def test_removing_a_policy_invalidates_both_aliases(factory, company):
    policy_service.get_policy_info("SYNTHETIC")
    policy_service.remove_from_cache("SYNTHETIC", company_code=company)
    assert not policy_service._cache


@pytest.mark.parametrize("state", [
    {"available_companies": ["01", "04"], "last_error": ""},
    {"available_companies": [], "last_error": "Policy not found"},
    {"available_companies": [], "last_error": "ODBC connection failed"},
])
def test_unresolved_instances_are_opt_in_and_never_cached(factory, state):
    unresolved = SimpleNamespace(exists=False, **state)
    factory.return_value = unresolved
    assert policy_service.get_policy_info("SYNTHETIC", include_unresolved=True) is unresolved
    assert policy_service.get_policy_info("SYNTHETIC") is None
    assert factory.call_count == 2
    assert not policy_service._cache


def test_interactive_errors_propagate_to_ui(factory, caplog):
    factory.side_effect = RuntimeError("Connection failed")
    with pytest.raises(RuntimeError, match="Connection failed"):
        policy_service.get_policy_info("SYNTHETIC", include_unresolved=True)
    assert policy_service.get_policy_info("SYNTHETIC") is None
    assert "Connection failed" in caplog.text


def test_region_company_and_system_remain_separate(factory):
    first = policy_service.get_policy_info("SYNTHETIC", company_code="01")
    second = SimpleNamespace(exists=True, company_code="04", system_code="I")
    factory.return_value = second
    assert policy_service.get_policy_info("SYNTHETIC", company_code="04") is second
    pending = SimpleNamespace(exists=True, company_code="01", system_code="P")
    factory.return_value = pending
    assert policy_service.get_policy_info(
        "SYNTHETIC", company_code="01", system_code="P",
    ) is pending
    model = SimpleNamespace(exists=True, company_code="01", system_code="I")
    factory.return_value = model
    assert policy_service.get_policy_info("SYNTHETIC", region="CKMO", company_code="01") is model
    assert policy_service.get_policy_info("SYNTHETIC", company_code="01") is first
    assert factory.call_count == 4


def test_uncached_read_does_not_replace_shared_snapshot(factory):
    first = policy_service.get_policy_info("SYNTHETIC", company_code="01")
    factory.return_value = SimpleNamespace(exists=True, company_code="01", system_code="I")
    fresh = policy_service.get_policy_info("SYNTHETIC", company_code="01", use_cache=False)
    assert fresh is not first
    assert policy_service.get_policy_info("SYNTHETIC", company_code="01") is first
