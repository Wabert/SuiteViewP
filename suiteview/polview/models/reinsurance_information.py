"""Cached reinsurance lookup data for PolView."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from suiteview.core.reinsurance import TAICessionResult, fetch_tai_cession

from .policy_information import PolicyInformation


@dataclass(frozen=True)
class ReinsuranceInformation:
    """TAICession and related CyberLife context for a policy."""

    policy_number: str
    region: str = "CKPR"
    tai_cession: TAICessionResult = field(default_factory=TAICessionResult)
    companies: tuple[str, ...] = ()

    _tai_cache: ClassVar[dict[str, TAICessionResult]] = {}
    _companies_cache: ClassVar[dict[tuple[str, str], tuple[str, ...]]] = {}

    @classmethod
    def load(cls, policy_number: str, region: str = "CKPR") -> "ReinsuranceInformation":
        normalized_policy = cls._normalize_policy(policy_number)
        normalized_region = (region or "CKPR").strip().upper()

        if normalized_policy not in cls._tai_cache:
            cls._tai_cache[normalized_policy] = fetch_tai_cession(normalized_policy)

        companies_key = (normalized_policy, normalized_region)
        if companies_key not in cls._companies_cache:
            try:
                companies = PolicyInformation.find_companies(
                    normalized_policy, normalized_region
                )
            except Exception:
                companies = []
            cls._companies_cache[companies_key] = tuple(companies)

        return cls(
            policy_number=normalized_policy,
            region=normalized_region,
            tai_cession=cls._tai_cache[normalized_policy],
            companies=cls._companies_cache[companies_key],
        )

    @classmethod
    def clear_cache(cls):
        cls._tai_cache.clear()
        cls._companies_cache.clear()

    @staticmethod
    def _normalize_policy(policy_number: str) -> str:
        return str(policy_number or "").strip().upper()