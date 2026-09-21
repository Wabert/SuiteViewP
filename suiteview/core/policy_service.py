"""
Shared Policy Information Service.

Provides clean, cached access to PolicyInformation for all SuiteView apps.
Any module in SuiteView can retrieve policy data with a single call:

    from suiteview.core.policy_service import get_policy_info

    pi = get_policy_info("E0213651")
    if pi:
        name = pi.primary_insured_name
        face = pi.base_face_amount
        ...

The service caches PolicyInformation objects so repeated lookups for the
same policy don't hit DB2 again.  Call ``clear_cache()`` or
``remove_from_cache()`` when you need fresh data.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from suiteview.polview.models.policy_information import PolicyInformation

logger = logging.getLogger(__name__)

# Module-level cache keyed by (policy_number, company_code, system_code, region)
_cache: Dict[Tuple[str, Optional[str], str, str], "PolicyInformation"] = {}
_scoped_cache = ContextVar("policy_service_cache", default=None)


def _active_cache():
    private = _scoped_cache.get()
    return _cache if private is None else private


@contextmanager
def policy_cache_scope(cache):
    """Use an owner-local cache without reading or altering the global GUI cache."""
    token = _scoped_cache.set(cache)
    try:
        yield
    finally:
        _scoped_cache.reset(token)


def cache_policy_info(policy: "PolicyInformation") -> None:
    """Register a resolved GUI policy without creating an ambiguous blank alias."""
    if not policy.exists:
        return
    key = (policy.policy_number.strip().upper(), policy.company_code,
           policy.system_code, policy.region.upper())
    cache = _active_cache()
    cache[key] = policy
    # Explicit-company registration is not proof that a blank-company lookup
    # is unique, and an older alias must not retain a stale GUI instance.
    cache.pop((key[0], None, key[2], key[3]), None)


def get_policy_info(
    policy_number: str,
    region: str = "CKPR",
    company_code: Optional[str] = None,
    system_code: str = "I",
    *,
    use_cache: bool = True,
    include_unresolved: bool = False,
):
    """Return a PolicyInformation object for the given policy.

    Args:
        policy_number: Policy number to look up.
        region: DB2 region code (default ``"CKPR"``).
        company_code: Optional company code filter.
        system_code: System code (default ``"I"``).
        use_cache: If *True* (default), reuse a previously loaded instance.
        include_unresolved: Return unresolved lookups so interactive callers can
            inspect ``available_companies`` / ``last_error`` and try pending
            policies. Unresolved instances are never cached. Unexpected errors
            propagate to these callers for their normal error UI.

    Returns:
        A :class:`PolicyInformation` instance if the policy exists,
        or *None* if the policy was not found or DB2 is unreachable.
        With ``include_unresolved=True``, also returns unresolved instances.
        A unique company-autodetected policy shares its explicit-company key.
    """
    key = (
        policy_number.strip().upper(),
        company_code.strip().upper() if company_code else None,
        system_code.strip().upper(),
        region.upper(),
    )

    cache = _active_cache()
    if use_cache and key in cache:
        return cache[key]

    try:
        from suiteview.polview.models.policy_information import PolicyInformation

        pi = PolicyInformation(
            policy_number,
            company_code=company_code,
            system_code=system_code,
            region=region,
        )
        if not pi.exists:
            return pi if include_unresolved else None

        if use_cache:
            cache[key] = pi
            resolved_key = (key[0], pi.company_code, pi.system_code, key[3])
            cache[resolved_key] = pi
        return pi

    except ImportError:
        if include_unresolved:
            raise
        logger.warning("PolicyInformation module not available")
        return None
    except Exception as e:
        if include_unresolved:
            raise
        logger.error(f"Failed to load policy {policy_number}: {e}")
        return None


def clear_cache() -> None:
    """Remove all cached PolicyInformation instances."""
    _active_cache().clear()


def remove_from_cache(
    policy_number: str,
    region: str = "CKPR",
    company_code: Optional[str] = None,
    system_code: str = "I",
) -> None:
    """Remove a specific policy from the cache."""
    key = (
        policy_number.strip().upper(),
        company_code.strip().upper() if company_code else None,
        system_code.strip().upper(),
        region.upper(),
    )
    cache = _active_cache()
    policy = cache.pop(key, None)
    if policy is not None:
        for alias in [alias for alias, cached in cache.items() if cached is policy]:
            del cache[alias]
