"""Name-based reads for code that accepts a PolicyInformation or a flat snapshot.

Some services read policy facts by name so they can take either a live
``PolicyInformation`` (facts on section objects such as ``pi.product``) or a
flat object such as ``IllustrationPolicyData`` or a test double.
``policy_attr``/``policy_hasattr`` mirror ``getattr``/``hasattr``:

* an attribute defined directly on the object wins (flat snapshots);
* otherwise a name owned by a PolicyInformation section is read from that
  section, e.g. ``policy_attr(pi, "product_type")`` reads
  ``pi.product.product_type``.

Code that knows it holds a PolicyInformation should use the section property
directly; these helpers exist only for genuinely polymorphic readers.
"""

from __future__ import annotations

from typing import Any

from .activity import ActivitySection
from .agents import AgentsSection
from .benefits import BenefitsSection
from .billing import BillingSection
from .coverages import CoveragesSection
from .dividends import DividendsSection
from .loans import LoansSection
from .persons import PersonsSection
from .product import ProductSection
from .rates import RatesSection
from .status import StatusSection
from .support import SupportSection
from .targets import TargetsSection
from .values import ValuesSection
from .base import PolicySection

_SECTION_CLASSES = {
    "status": StatusSection,
    "product": ProductSection,
    "billing": BillingSection,
    "coverages": CoveragesSection,
    "benefits": BenefitsSection,
    "loans": LoansSection,
    "values": ValuesSection,
    "targets": TargetsSection,
    "dividends": DividendsSection,
    "persons": PersonsSection,
    "agents": AgentsSection,
    "activity": ActivitySection,
    "rates": RatesSection,
    "support": SupportSection,
}

_MISSING = object()


def _member_sections() -> dict[str, str]:
    base_names = set(vars(PolicySection))
    owners: dict[str, str] = {}
    for section, cls in _SECTION_CLASSES.items():
        names = {
            name
            for klass in cls.__mro__
            if klass not in (PolicySection, object)
            for name in vars(klass)
        }
        for name in sorted(names):
            if name.startswith("__") or name in base_names or name == "CACHE_ATTRS":
                continue
            if name in owners:
                raise RuntimeError(f"{name!r} is defined on both {owners[name]} and {section}")
            owners[name] = section
    return owners


MEMBER_SECTION: dict[str, str] = _member_sections()


def _defines(obj: Any, name: str) -> bool:
    """True when ``name`` is defined on the object itself (no property evaluation)."""
    if hasattr(type(obj), name):
        return True
    try:
        return name in vars(obj)
    except TypeError:
        return False


def _owner(policy: Any, name: str) -> Any:
    if _defines(policy, name):
        return policy
    section = MEMBER_SECTION.get(name)
    if section is None:
        return policy
    holder = getattr(policy, section, None)
    if holder is None or isinstance(holder, (str, bytes, list, tuple, dict, set)):
        return policy
    return holder


def policy_attr(policy: Any, name: str, default: Any = _MISSING) -> Any:
    """``getattr`` that also finds facts moved to PolicyInformation sections."""
    owner = _owner(policy, name)
    if default is _MISSING:
        return getattr(owner, name)
    return getattr(owner, name, default)


def policy_hasattr(policy: Any, name: str) -> bool:
    """``hasattr`` counterpart of :func:`policy_attr`."""
    return hasattr(_owner(policy, name), name)
