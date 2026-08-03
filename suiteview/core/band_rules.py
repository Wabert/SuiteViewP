"""Riders whose face counts toward the BASE plancode's band.

Normally a rider is banded on its own face using its own band table, and its
face does not affect the base plancode's band. A few riders behave like an
extension of base coverage: the policy's band is looked up on the COMBINED face
of the base coverage(s) PLUS the rider. For example, rider ``1U144A00`` (added to
some IUL08 plans) is folded into the base specified amount when determining the
band — it "acts like a segment of base coverage" for banding.

This module is the single source of truth for that rule. Callers ask
``rider_bands_as_base(plancode)`` and add the rider's face to the base specified
amount before the band lookup. The rider still charges its own COI on its own
band table — this rule only affects the BASE band, never the rider's own band,
and never the death-benefit / NAR face.

Adding a new such rider is one line here; every band call site stays generic.
"""

from __future__ import annotations

# Rider plancodes whose face is folded into the base specified amount for band
# determination (matched case-insensitively, trimmed).
_BASE_BANDING_RIDER_PLANCODES = frozenset({"1U144A00"})


def rider_bands_as_base(plancode: str) -> bool:
    """True if this rider's face counts toward the base plancode's band."""
    return (plancode or "").strip().upper() in _BASE_BANDING_RIDER_PLANCODES
