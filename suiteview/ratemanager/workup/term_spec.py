"""User-supplied settings for a Term Rate Workup run.

Term rates come from a single IAF — there is no MPF, CKULTB04 or CKULTB01
input. What the IAF cannot tell us is the *shape* of the premium schedule
(how long each select rate is held) and the plan's modal/band/fee setup, so
those arrive here from the user.

Maturity is deliberately absent: it is derived from the IAF plan header
(ME-AGE + its use code) by :mod:`term_builder` and is never user-supplied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# Physical column order of TERM_RATE_MODEFACT (premium factors, then the
# matching policy-fee factors).
MODEFACT_FIELDS = (
    "PACS", "PACQ", "PACM", "DIRS", "DIRQ", "DIRM",
    "PACS_FEE", "PACQ_FEE", "PACM_FEE", "DIRS_FEE", "DIRQ_FEE", "DIRM_FEE",
)

# A FIRSTLEVEL at or above this marks a rate that never steps — the issue-age
# rate is held for every duration.
NON_RENEWABLE_LEVEL = 999


@dataclass
class TermBenefitSelection:
    """One IAF benefit (plan_option) to include in the workup.

    ``code`` is the raw 2-character IAF plan_option ('30' = PWoC, '3N', '34')
    and becomes the ``Index(BEN)`` suffix verbatim, so '1001_30' pairs with
    the base '1001_PL'.

    ``renewable`` says whether the charge follows attained age or stays level
    at the issue-age rate — a non-renewable benefit holds its first rate for
    every duration. ``first_level``/``ren_level`` override that derivation
    when a benefit needs its own schedule; both default to the plan values.

    ``cease_age`` and ``max_duration`` both cap the schedule and combine as
    'whichever comes first', which is how benefits written as "level for 20
    years or to age 60" are expressed.
    """

    code: str
    label: str = ""
    include: bool = True
    renewable: bool = True
    first_level: Optional[int] = None
    ren_level: Optional[int] = None
    # Charges stop *before* this attained age; None = use the plan maturity.
    cease_age: Optional[int] = None
    # Cap on policy years, for '20 years or age 60, whichever comes first'.
    max_duration: Optional[int] = None

    def levels(self, plan_first: int, plan_ren: int) -> tuple:
        """Resolve (FIRSTLEVEL, RENLEVEL) for this benefit.

        An explicit override always wins. Otherwise a non-renewable benefit
        locks its issue-age rate (999/0) and a renewable one inherits the
        plan's schedule.
        """
        if not self.renewable:
            default_first, default_ren = NON_RENEWABLE_LEVEL, 0
        else:
            default_first, default_ren = plan_first, plan_ren
        first = self.first_level if self.first_level is not None else default_first
        ren = self.ren_level if self.ren_level is not None else default_ren
        return first, ren


@dataclass
class ModeFactorSelection:
    """Which TERM_RATE_MODEFACT row this plancode points at.

    Either reference an index that already exists in the database (``values``
    empty) or define a new one, in which case the factors are written out as
    a new TERM_RATE_MODEFACT row.
    """

    index: str = "0"
    values: Dict[str, float] = field(default_factory=dict)

    @property
    def is_new(self) -> bool:
        return bool(self.values)


@dataclass
class BandSpecRow:
    """One face-amount breakpoint in a TERM_RATE_BANDSPECS structure."""

    issue_date: str          # YYYY-MM-DD
    specified_amount: float
    band: int
    band_code: str


@dataclass
class BandStructureSelection:
    """Which TERM_RATE_BANDSPECS structure this plancode points at.

    As with the modal factors: reference an existing index, or supply the
    breakpoints to define a new one. Index '0' is the unbanded structure.
    """

    index: str = "0"
    rows: List[BandSpecRow] = field(default_factory=list)

    @property
    def is_new(self) -> bool:
        return bool(self.rows)


@dataclass
class TermWorkupSpec:
    """Everything needed to build one Term plancode's rate workup."""

    plancode: str = ""
    output_dir: str = ""
    iaf_path: str = ""

    issue_version: int = 1

    # The plancode's base index — a free multiple of 1000. Combos allocate
    # from base_index + 1, so a plan can hold up to 999 rate combos.
    base_index: Optional[int] = None

    # Premium schedule shape. first_level holds the first select rate for N
    # policy years; ren_level holds each later select rate for N years.
    # first_level >= 999 means the issue-age rate never changes.
    first_level: int = 1
    ren_level: int = 1

    # TERM_POINT_PV
    fee: float = 0.0
    modefact: ModeFactorSelection = field(default_factory=ModeFactorSelection)
    bandspec: BandStructureSelection = field(
        default_factory=BandStructureSelection)

    benefits: List[TermBenefitSelection] = field(default_factory=list)

    @property
    def selected_benefits(self) -> List[TermBenefitSelection]:
        return [b for b in self.benefits if b.include]
