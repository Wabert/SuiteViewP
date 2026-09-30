"""Participating whole life (par WL) in-force illustration data: snapshot, inputs, results.

A par WL policy is a traditional fixed-premium CyberLife policy whose values come
from tables rather than an account: tabular guaranteed cash values per unit,
annual dividends from the dividend rate file, paid-up additions (PUAs) valued at
a net single premium, one-year term additions (OYT), dividends on deposit and
traditional policy loans. ``ParWLPolicy`` is the in-force snapshot the engine
starts from, ``ParWLInputs`` the illustration choices, and ``ParWLResult`` the
monthly rows plus the annual ledger built from them.

Amounts are dollars (floats rounded to cents where CyberLife rounds); rates are
decimal fractions (0.074 = 7.4%).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

# CyberLife primary dividend options (LH_BAS_POL.PRI_DIV_OPT_CD, CyberDoc D20 FBRPROPD).
DIVIDEND_OPTION_LABELS: Dict[str, str] = {
    "1": "Cash",
    "2": "Reduce premium",
    "3": "Deposit at interest",
    "4": "Paid-up additions",
    "5": "One-year term (unlimited)",
    "6": "One-year term (limit cash value)",
    "7": "One-year term (limit face)",
    "8": "Loan reduction",
}
# Secondary options take the value left over from OYT or premium reduction (D20 FBRPROSD).
SECONDARY_OPTION_LABELS: Dict[str, str] = {
    "1": "Cash", "3": "Deposit at interest", "4": "Paid-up additions", "8": "Loan reduction",
}
OYT_OPTIONS = frozenset({"5", "6", "7"})

ROLE_BASE = "BASE"
ROLE_PUA_RIDER = "PUA_RIDER"
ROLE_TERM_RIDER = "TERM_RIDER"

STATUS_PREMIUM_PAYING = "22"
STATUS_WAIVER = "32"
STATUS_PAID_UP = frozenset({"41", "42", "43", "46", "47"})
STATUS_ETI = "44"
STATUS_RPU = "45"


@dataclass(frozen=True)
class ParWLCoverage:
    """One LH_COV_PHA coverage phase of a par WL policy."""

    phase: int
    plancode: str
    role: str                         # BASE / PUA_RIDER / TERM_RIDER
    product_line: str                 # PRD_LIN_TYP_CD (C = paid-up additions rider)
    issue_date: date
    issue_age: int
    rate_sex: str                     # schema rates sex M/F/U
    rate_class: str                   # renewal rate class (RT_CLS_CD)
    band_code: str                    # CyberLife RT_BAN_CD
    subseries: str                    # LIF_PLN_SUB_SRE_CD (cash value sub-series)
    units: float
    value_per_unit: float
    annual_premium_per_unit: float    # ANN_PRM_UNT_AMT
    pay_up_date: Optional[date]
    maturity_date: Optional[date]
    table_rating: int = 0
    # Substandard extra premiums: (annual extra per unit, cease date), billed apart from the premium.
    extra_premiums: Tuple[Tuple[float, Optional[date]], ...] = ()
    nsp_table: str = ""               # NSP_RPU_TBL_CD
    nsp_interest: Optional[float] = None
    stored_low_duration: Optional[int] = None
    stored_cash_values: Tuple[Optional[float], ...] = ()
    stored_nsp_values: Tuple[Optional[float], ...] = ()
    # CyberLife's dividend key: class + base series + sub-series (INS_CLS_CD, PLN_BSE_SRE_CD,
    # LIF_PLN_SUB_SRE_CD), e.g. "11E1MN"; RATE_ASSIGN_DIV.DIV_KEY carries the same key.
    dividend_key: str = ""
    # A PUA rider whose payments have ceased (CEA_REA_CD set) keeps its additions.
    payments_ceased: bool = False
    description: str = ""             # plancode common name (official plancode table)
    form_number: str = ""             # POL_FRM_NBR
    sex_description: str = ""         # INS_SEX_CD translated (Male / Female)

    @property
    def face_amount(self) -> float:
        return round(self.units * self.value_per_unit, 2)

    @property
    def annual_premium(self) -> float:
        return round(self.units * self.annual_premium_per_unit, 2)


@dataclass(frozen=True)
class ParWLBenefit:
    """A supplemental benefit (LH_SPM_BNF): waiver, ADB, children's term..."""

    phase: int
    code: str                         # type + subtype, e.g. "30"
    description: str
    units: float
    value_per_unit: float
    annual_premium_per_unit: float    # BNF_ANN_PPU_AMT
    rate_factor: float
    issue_date: Optional[date]
    issue_age: Optional[int]
    cease_date: Optional[date]
    form_number: str = ""             # BNF_FRM_NBR
    pay_up_date: Optional[date] = None

    @property
    def annual_premium(self) -> float:
        return round(self.units * self.annual_premium_per_unit * self.rate_factor, 2)


@dataclass(frozen=True)
class ParWLAdditions:
    """A current paid-up additions row (LH_PAID_UP_ADD, MVRY_DT 12/31/9999)."""

    phase: int
    source: str                       # PUA_PUR_SRC_CD: 0 dividends, 1 rider premium
    amount: float
    mortality_table: str
    interest: float
    maturity_date: Optional[date] = None
    nfo_code: str = ""


@dataclass(frozen=True)
class ParWLLoan:
    """The current traditional policy loan (LH_CSH_VAL_LOAN, MVRY_DT 12/31/9999)."""

    principal: float
    interest_amount: float            # POL_LN_ITS_AMT
    rate: float
    in_advance: bool                  # LN_ITS_PBL_TYP_CD = 1
    capitalized: bool                 # LN_ITS_AMT_TYP_CD = 1
    interest_paid_to: Optional[date]
    preferred: bool = False
    last_activity: Optional[date] = None      # LST_LN_ACY_DT


@dataclass(frozen=True)
class ParWLDividendValue:
    """A dividend value record (applied history or unapplied upcoming), per unit."""

    phase: int
    earn_date: date
    source: str                       # 0 coverage units, 1 paid-up additions
    applied: bool
    option: str
    cash_per_unit: float
    pua_per_unit: float
    oyt_per_unit: float
    units: float
    rpu_values: bool = False
    deposit_rate: Optional[float] = None
    direct_recognition: bool = False
    gross_interest_rate: Optional[float] = None


@dataclass(frozen=True)
class ParWLPolicy:
    """In-force snapshot of a par WL policy, read through PolicyInformation."""

    policy_number: str
    company_code: str
    region: str
    insured_name: str
    issue_state: str
    issue_date: date
    valuation_date: date              # monthliversary CyberLife values are processed to
    last_anniversary: date
    paid_to_date: Optional[date]
    billing_frequency: int            # months between premiums (12, 6, 3, 1)
    bill_form: str
    modal_premium: float              # POL_PRM_AMT
    forced_premium: bool
    premium_status: str               # PRM_PAY_STA_REA_CD
    premium_status_description: str
    dividend_option: str
    secondary_dividend_option: str
    nfo_option: str
    loan_type_code: str
    loan_rate: Optional[float]
    reinsurance_key: str
    coverages: Tuple[ParWLCoverage, ...]
    benefits: Tuple[ParWLBenefit, ...] = ()
    additions: Tuple[ParWLAdditions, ...] = ()
    additions_before_anniversary: Tuple[ParWLAdditions, ...] = ()
    oyt_amount: float = 0.0
    oyt_expiry: Optional[date] = None
    deposits: float = 0.0
    deposit_rate: Optional[float] = None
    loans: Tuple[ParWLLoan, ...] = ()
    applied_dividends: Tuple[ParWLDividendValue, ...] = ()
    unapplied_dividends: Tuple[ParWLDividendValue, ...] = ()
    notes: Tuple[str, ...] = ()

    @property
    def base(self) -> ParWLCoverage:
        return next(c for c in self.coverages if c.role == ROLE_BASE)

    @property
    def is_rpu(self) -> bool:
        """Reduced paid-up: status 45, or a paid-up status whose base coverage CyberLife pays
        on reduced paid-up values (``RPU_VAL_IND`` on its newest placed dividend; 8O1C1000
        12197587 and 12197588 are status 41 with fractional units and stored RPU NSPs)."""
        if self.premium_status == STATUS_RPU:
            return True
        if self.premium_status not in STATUS_PAID_UP:
            return False
        phase = self.base.phase
        placed = [r for r in self.unapplied_dividends if r.phase == phase and r.source == "0"]
        return bool(placed) and max(placed, key=lambda r: r.earn_date).rpu_values

    @property
    def is_eti(self) -> bool:
        return self.premium_status == STATUS_ETI

    @property
    def is_waiver(self) -> bool:
        return self.premium_status == STATUS_WAIVER

    @property
    def is_paid_up(self) -> bool:
        return self.premium_status in STATUS_PAID_UP

    @property
    def pua_rider(self) -> Optional[ParWLCoverage]:
        return next((c for c in self.coverages if c.role == ROLE_PUA_RIDER), None)

    @property
    def total_additions(self) -> float:
        return round(sum(a.amount for a in self.additions), 2)

    @property
    def loan_principal(self) -> float:
        return round(sum(loan.principal for loan in self.loans), 2)


@dataclass(frozen=True)
class DatedAmount:
    """An amount on a date (new loan, repayment, PUA rider payment...)."""

    when: date
    amount: float


@dataclass(frozen=True)
class OptionChange:
    """A dividend option change effective at the first anniversary on/after ``when``."""

    when: date
    option: str
    secondary: str = ""


@dataclass
class ParWLInputs:
    """Illustration choices for a par WL run (all optional; defaults project the record)."""

    dividends: bool = True                        # False: no dividends (guaranteed basis)
    dividend_option: Optional[str] = None         # replaces the primary option from the start
    secondary_option: Optional[str] = None
    option_changes: List[OptionChange] = field(default_factory=list)
    stop_premiums_at: Optional[date] = None       # last premium due before this date
    rpu_at: Optional[date] = None                 # convert to reduced paid-up at this anniversary
    loans: List[DatedAmount] = field(default_factory=list)            # new loans
    loan_repayments: List[DatedAmount] = field(default_factory=list)
    rider_payments: List[DatedAmount] = field(default_factory=list)   # PUA rider premiums
    pay_loan_interest: bool = False               # pay loan interest in cash instead of capitalizing
    deposit_rate: Optional[float] = None          # dividend deposit interest (default: the record's rate)
    end_age: Optional[int] = None                 # stop at this attained age (default maturity)


@dataclass
class ParWLMonth:
    """Values on one monthliversary (after that date's processing)."""

    index: int
    when: date
    policy_year: int
    month_of_year: int                # 0 = anniversary
    attained_age: int
    projected: bool                   # False for months before the valuation date
    status: str = ""
    anniversary: bool = False
    # premiums (cash outlay by the owner on this date)
    base_premium: float = 0.0
    rider_premium: float = 0.0
    benefit_premium: float = 0.0
    policy_fee: float = 0.0
    premium_billed: float = 0.0
    premium_by_dividend: float = 0.0
    premium_paid: float = 0.0
    rider_payment: float = 0.0        # PUA rider premium
    # dividends (anniversary rows)
    dividend_year: int = 0
    dividend_record: str = ""
    dividend_option: str = ""
    dividend_rate: float = 0.0        # base cash per unit
    dividend_base: float = 0.0
    dividend_on_additions: float = 0.0
    dividend_rider: float = 0.0       # dividends on the PUA rider's additions
    dividend_total: float = 0.0
    dividend_cash: float = 0.0
    dividend_to_premium: float = 0.0
    dividend_to_deposit: float = 0.0
    dividend_to_additions: float = 0.0
    dividend_to_oyt: float = 0.0
    dividend_to_loan: float = 0.0
    premium_credit: float = 0.0       # unused premium-reduction credit carried
    # paid-up additions
    additions_bought: float = 0.0
    additions_bought_by_rider: float = 0.0
    additions: float = 0.0            # total face
    additions_dividend: float = 0.0   # base coverage additions from dividends
    additions_rider: float = 0.0      # PUA rider additions (premium + its dividends)
    nsp_start: float = 0.0            # NSP per 1,000 at the policy year's start age
    nsp_end: float = 0.0
    additions_cv: float = 0.0
    # one-year term
    oyt_face: float = 0.0
    # deposits
    deposit_interest: float = 0.0
    deposits: float = 0.0
    # base coverage
    units: float = 0.0
    face: float = 0.0
    rpu: bool = False
    cv_per_unit_start: float = 0.0
    cv_per_unit_end: float = 0.0
    cv_per_unit: float = 0.0
    base_cv: float = 0.0
    term_rider_face: float = 0.0
    # loans
    new_loan: float = 0.0
    loan_repayment: float = 0.0
    loan_interest: float = 0.0        # charged (advance) or capitalized (arrears) this date
    loan_interest_paid: float = 0.0
    loan_principal: float = 0.0
    loan_accrued: float = 0.0         # arrears interest accrued, not yet capitalized
    loan_unearned: float = 0.0        # advance interest not yet earned (refunded on surrender)
    loan_payoff: float = 0.0
    # totals
    cash_value: float = 0.0           # base + additions + OYT + deposits
    surrender_value: float = 0.0      # cash value less loan payoff
    death_benefit: float = 0.0
    notes: str = ""


@dataclass
class ParWLYear:
    """One policy year of the annual ledger (values at the year's end)."""

    policy_year: int
    end_date: date
    age: int                          # attained age at the year's end
    premium: float
    rider_payments: float
    loan_interest_paid: float
    new_loans: float
    loan_repayments: float
    dividend: float
    dividend_cash: float
    guaranteed_cash_value: float
    guaranteed_death_benefit: float
    additions: float
    additions_cv: float
    oyt_face: float
    deposits: float
    loan_balance: float
    cash_value: float
    surrender_value: float
    death_benefit: float
    rpu: bool = False
    additions_base: float = 0.0       # base coverage's paid-up additions (dividends)
    additions_rider: float = 0.0      # PUA rider's additions (its premiums and dividends)


@dataclass
class ParWLResult:
    """A par WL projection: monthly rows, annual ledger and the basis notes."""

    policy: ParWLPolicy
    inputs: ParWLInputs
    months: List[ParWLMonth]
    guaranteed_months: List[ParWLMonth]
    years: List[ParWLYear]
    notes: List[str] = field(default_factory=list)
