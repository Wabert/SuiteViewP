from __future__ import annotations

from suiteview.illustration.core.rate_loader import CHARGEABLE_BENEFIT_TYPES, IllustrationRates
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def missing_required_rate_warnings(
    policy: IllustrationPolicyData,
    rates: IllustrationRates,
) -> list[str]:
    """Return user-facing warnings for active riders/benefits without loaded rates.

    ``load_rates`` already raises for a chargeable benefit without a schedule;
    the benefit check here covers caller-supplied rate overrides."""
    missing: list[str] = []

    for rider in policy.riders:
        if not rider.is_active:
            continue
        if not rider.plancode:
            continue
        if not rates.rider_rates.get(rider.export_key):
            missing.append(f"Rider {rider.export_key}")

    for benefit in policy.benefits:
        if not benefit.is_active:
            continue
        benefit_type = (benefit.benefit_type or "").strip()
        if benefit_type not in CHARGEABLE_BENEFIT_TYPES:
            continue
        benefit_key = benefit_type + (benefit.benefit_subtype or "")
        if not benefit_key:
            continue
        if not rates.benefit_coi.get(benefit_key):
            missing.append(f"Benefit {benefit_key}")

    if not missing:
        return []

    return [
        "Missing illustration rates for active rider/benefit charges: "
        + ", ".join(sorted(missing))
    ]