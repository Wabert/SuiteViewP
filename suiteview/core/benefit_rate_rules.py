"""Per-(plancode, benefit) monthly-deduction charge adjustments for CyberLife quirks.

Most benefit COI rates are stored (in CyberLife and in the UL_Rates DB) exactly
as they are applied: ``charge = units × rate``. A few plancodes store a benefit's
rate in a different unit/frequency than the deduction formula expects, and
CyberLife normalises the rate *at deduction time* — the stored/displayed rate is
left untouched. For example, ``MLUL`` / ``MLUL502`` benefit ``10`` stores an
*annual per-unit* rate (e.g. ``0.00144``) that CyberLife converts to
monthly-per-1000 (``÷ 12 × 1000`` → ``0.12``) before multiplying by the benefit
units to get the monthly charge.

Keeping the stored/displayed rate raw is deliberate: it mirrors what RERUN shows
(raw rate + converted charge) and keeps the rate tables identical to CyberLife's,
so nothing double-applies the factor.

Rather than scatter ``if plancode == ...`` branches through the monthly-deduction
engine(s), these exceptions live here as a single data-driven table. Both the
inforce monthly-deduction and the guideline-premium solve call
``benefit_charge_factor`` — one source of truth for the rule, no duplication.
Adding a new quirk is one line.

Keying:
    * ``plancode``  — matched case-insensitively, trimmed.
    * ``benefit_key`` — the benefit's ``type + subtype`` (e.g. ``"10"``), trimmed.

Each entry maps to a multiplier applied to the computed monthly charge. Purely
multiplicative adjustments (unit/frequency conversions) cover every known case;
if a future quirk needs a non-multiplicative transform, promote the value to a
callable and update ``benefit_charge_factor`` and every call site together.
"""

from __future__ import annotations

from typing import Dict, Tuple

# Annual-per-unit → monthly-per-1000: divide by 12 months, scale to per-1000.
_ANNUAL_UNIT_TO_MONTHLY_PER_1000 = 1000.0 / 12.0

# (PLANCODE, benefit_key) → multiplier applied to the monthly benefit charge.
_BENEFIT_CHARGE_FACTORS: Dict[Tuple[str, str], float] = {
    ("MLUL", "10"): _ANNUAL_UNIT_TO_MONTHLY_PER_1000,
    ("MLUL502", "10"): _ANNUAL_UNIT_TO_MONTHLY_PER_1000,
}


def benefit_charge_factor(plancode: str, benefit_key: str) -> float:
    """Multiplier to apply to a benefit's monthly charge (1.0 = no adjustment)."""
    key = ((plancode or "").strip().upper(), (benefit_key or "").strip())
    return _BENEFIT_CHARGE_FACTORS.get(key, 1.0)
