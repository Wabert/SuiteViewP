"""ABR Quote product eligibility.

Some product families are not available for ABR quoting. Business users are
blocked from quoting them; ADMIN/SUPPORT roles may still quote them for
research and support work (see ``core.access_control.has_support_privileges``).
"""

from __future__ import annotations

WHOLE_LIFE_NOT_AVAILABLE = "Whole Life policies are not available for ABR quote."

# PolicyInformation classifies both Par and Non-Par Whole Life as ``WL``.
_RESTRICTED_PRODUCTS = {"WL": WHOLE_LIFE_NOT_AVAILABLE}


def abr_product_restriction(product_type: str | None) -> str | None:
    """Return the user-facing reason *product_type* cannot be quoted, else ``None``."""
    return _RESTRICTED_PRODUCTS.get(str(product_type or "").strip().upper())
