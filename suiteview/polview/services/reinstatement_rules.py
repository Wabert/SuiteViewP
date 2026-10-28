"""Plancode-specific UL reinstatement rules.

The IUL formulas follow the S151972 *IUL Reinstatement Business Requirements*
(v2.0, 9/20/2023). Every other UL uses the standard continuous-coverage quote.

=================  ==========================================================
Formula            Reinstatement premium
=================  ==========================================================
``STANDARD``       SC(REINDT) + debt + 2 x MD(REINDT) - AV(LD), plus load
``IUL08``          SC(REINDT) + MD(REINDT) + MD(REINDT + 1 month) + debt
                   - AV(LD), plus load at the REINDT duration
``NO_LAPSE_IUL``   SC(LD) + 2 x MD(LD) + debt - AV(LD), plus load at
                   the LD duration; a lapse inside the No-Lapse period pays the
                   lesser of that and AccumMTP(LD) + withdrawals + debt
                   + MTP(REINDT) - premiums paid (no load)
``GIUL21``         SC(LD) + 2 x MD(LD) + debt - AV(LD); the contract omits the
                   premium load (an oversight that is honored)
=================  ==========================================================

Each MD includes the Percent of Account Value (PoAV) charge on the lapse account
value (the requirement's "PoAV based on AV as of LD - before MD"); the quote shows
it on its own line. CKAS checkout UE001742 confirms CyberLife charges it in both
deductions: expense $84.98 = 2 x ($41.50 EPU and fee + $0.99 PoAV).
``LD`` is the lapse date or the last monthliversary before it (the S151972
workbook's definition): MD(LD) is charged on that monthliversary, and AV, loans
and AccumMTP come from the last monthliversary values record. IUL14+ and GIUL21
resume their charge schedules at durations reduced by the months terminated, so
their charges are the lapse charges.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReinstatementFormula(str, Enum):
    STANDARD = "standard"
    IUL08 = "iul08"
    NO_LAPSE_IUL = "no_lapse_iul"
    GIUL21 = "giul21"


IUL08_PLANCODES = frozenset({"1U144600", "1U144700", "1U144800"})
NO_LAPSE_IUL_PLANCODES = frozenset({
    "1U145500", "1U146400", "1U145800",   # IUL14, IUL14U, IUL14 bonus
    "1U145600", "1U146500", "1U145900",   # IUL14 (NY) family
    "1U146800", "1U146900", "1U147500",   # IUL19, IUL21
    "1U147800",                           # IUL23
})
GIUL21_PLANCODES = frozenset({"1U147400"})

FORMULA_LABELS = {
    ReinstatementFormula.STANDARD: "Standard UL",
    ReinstatementFormula.IUL08: "IUL08 (modified skipped coverage)",
    ReinstatementFormula.NO_LAPSE_IUL: "IUL14/19/21/23",
    ReinstatementFormula.GIUL21: "GIUL21",
}


@dataclass(frozen=True)
class FormulaDisplay:
    """How the quote tab labels one formula's premium build-up."""

    surrender: str
    coi: str
    fees: str
    hint: str


FORMULA_DISPLAY = {
    ReinstatementFormula.STANDARD: FormulaDisplay(
        "Surrender charge (reinstatement date)", "2 \u00d7 COI", "2 \u00d7 Fees",
        "Surrender charge + policy debt + 2\u00d7COI + 2\u00d7fees \u2212 account value"),
    ReinstatementFormula.IUL08: FormulaDisplay(
        "Surrender charge (reinstatement date)", "COI (reinstatement + next month)",
        "Fees (reinstatement + next month)",
        "IUL08: surrender charge + MD(reinstatement) + MD(next month) + policy debt "
        "+ % of AV charge \u2212 account value"),
    ReinstatementFormula.NO_LAPSE_IUL: FormulaDisplay(
        "Surrender charge (lapse date)", "2 \u00d7 COI (lapse date)", "2 \u00d7 Fees (lapse date)",
        "IUL14/19/21/23: surrender charge + 2\u00d7MD at lapse + policy debt + % of AV charge "
        "\u2212 account value"),
    ReinstatementFormula.GIUL21: FormulaDisplay(
        "Surrender charge (lapse date)", "2 \u00d7 COI (lapse date)", "2 \u00d7 Fees (lapse date)",
        "GIUL21: surrender charge + 2\u00d7MD at lapse + policy debt \u2212 account value "
        "(no premium load)"),
}

# A lapse may be reinstated for this many years after its termination date.
REINSTATEMENT_WINDOW_YEARS = 5
SHORT_REINSTATEMENT_WINDOW_YEARS = 3
# Contracts with the 3-year reinstatement period; every other UL has 5 years.
THREE_YEAR_REINSTATEMENT_PLANCODES = frozenset({
    "1U147900", "1U148000", "1U148100",                         # GIUL23, GIUL23-N
    "1U147400", "1U147000",                                     # GIUL21, UL19
    "1U145700", "1U146000", "1U146100", "1U146200", "1U146300",  # SGUL15 family
    "1U146600", "1U146700", "1U147600", "1U147200", "1U147300",  # SGUL18/20/21
    "1U146800", "1U147500",                                     # IUL19, IUL21
    "1U145500", "1U146400", "1U145800",                         # IUL14, IUL14U, bonus
    "1U145600", "1U146500", "1U145900",                         # IUL14(NY) family
    "1U144900", "1U145000", "1U145100",                         # EXEC-UL(NY) family
    "1U145200", "1U145300", "1U145400",
})


def normalized_plancode(plancode) -> str:
    return str(plancode or "").strip().upper()


def reinstatement_formula(plancode) -> ReinstatementFormula:
    code = normalized_plancode(plancode)
    if code in IUL08_PLANCODES:
        return ReinstatementFormula.IUL08
    if code in NO_LAPSE_IUL_PLANCODES:
        return ReinstatementFormula.NO_LAPSE_IUL
    if code in GIUL21_PLANCODES:
        return ReinstatementFormula.GIUL21
    return ReinstatementFormula.STANDARD


def reinstatement_window_years(plancode) -> int:
    """Years after termination the plancode may be reinstated (3 or 5)."""
    return (SHORT_REINSTATEMENT_WINDOW_YEARS
            if normalized_plancode(plancode) in THREE_YEAR_REINSTATEMENT_PLANCODES
            else REINSTATEMENT_WINDOW_YEARS)
