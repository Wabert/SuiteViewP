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
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Module-level cache keyed by (policy_number, company_code, system_code, region)
_cache: Dict[Tuple[str, Optional[str], str, str], object] = {}


def get_policy_info(
    policy_number: str,
    region: str = "CKPR",
    company_code: Optional[str] = None,
    system_code: str = "I",
    *,
    use_cache: bool = True,
):
    """Return a PolicyInformation object for the given policy.

    Args:
        policy_number: Policy number to look up.
        region: DB2 region code (default ``"CKPR"``).
        company_code: Optional company code filter.
        system_code: System code (default ``"I"``).
        use_cache: If *True* (default), reuse a previously loaded instance.

    Returns:
        A :class:`PolicyInformation` instance if the policy exists,
        or *None* if the policy was not found or DB2 is unreachable.
    """
    key = (
        policy_number.strip().upper(),
        company_code.strip().upper() if company_code else None,
        system_code.strip().upper(),
        region.upper(),
    )

    if use_cache and key in _cache:
        return _cache[key]

    try:
        from suiteview.polview.models.policy_information import PolicyInformation

        pi = PolicyInformation(
            policy_number,
            company_code=company_code,
            system_code=system_code,
            region=region,
        )
        if not pi.exists:
            return None

        if use_cache:
            _cache[key] = pi
        return pi

    except ImportError:
        logger.warning("PolicyInformation module not available")
        return None
    except Exception as e:
        logger.error(f"Failed to load policy {policy_number}: {e}")
        return None


def clear_cache() -> None:
    """Remove all cached PolicyInformation instances."""
    _cache.clear()


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
    _cache.pop(key, None)
