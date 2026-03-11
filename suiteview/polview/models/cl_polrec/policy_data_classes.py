"""
Policy Data Classes
====================
Dataclass definitions for structured policy data.

These are the objects returned by CL_POLREC record modules and exposed
via PolicyInformation.  Field names use friendly Python-style naming;
each field's comment documents the source DB2 column.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional, Dict, Any


# =============================================================================
# RECORD 02 — COVERAGE PHASE
# =============================================================================

@dataclass
class CoverageInfo:
    """Coverage phase information (from LH_COV_PHA / TH_COV_PHA)."""
    cov_pha_nbr: int                    # COV_PHA_NBR
    plancode: str                       # PLN_DES_SER_CD
    form_number: str                    # POL_FRM_NBR
    issue_date: Optional[date]          # ISSUE_DT
    maturity_date: Optional[date]       # COV_MT_EXP_DT
    issue_age: Optional[int]            # INS_ISS_AGE
    face_amount: Optional[Decimal]      # COV_UNT_QTY × COV_VPU_AMT
    orig_amount: Optional[Decimal]      # OGN_SPC_UNT_QTY × COV_VPU_AMT
    units: Optional[Decimal]            # COV_UNT_QTY
    orig_units: Optional[Decimal]       # OGN_SPC_UNT_QTY
    vpu: Optional[Decimal]              # COV_VPU_AMT
    person_code: str                    # PRS_CD
    person_desc: str
    sex_code: str                       # INS_SEX_CD (display letter)
    sex_desc: str
    product_line_code: str              # PRD_LIN_TYP_CD
    product_line_desc: str
    class_code: str                     # INS_CLS_CD
    rate_class: str                     # RT_CLS_CD
    rate_class_desc: str
    table_rating: Optional[int]         # From LH_SST_XTR_CRG (numeric: A=1..P=16)
    table_rating_code: str              # From LH_SST_XTR_CRG (letter: "A"-"P" or "")
    cola_indicator: str                 # TH_COV_PHA.COLA_INCR_IND
    gio_indicator: str                  # TH_COV_PHA.OPT_EXER_IND
    flat_extra: Optional[Decimal]       # From LH_SST_XTR_CRG
    flat_cease_date: Optional[date]     # From LH_SST_XTR_CRG
    prs_seq_nbr: int                    # PRS_SEQ_NBR
    lives_cov_cd: str                   # LIVES_COV_CD
    cov_status: str                     # PRM_PAY_STS_CD
    cov_status_desc: str
    cov_status_date: Optional[date]     # Coverage status effective date
    # Premium rate per unit – from LH_COV_PHA.ANN_PRM_UNT_AMT.
    # This is the annual premium rate used for Traditional products.
    premium_rate: Optional[Decimal]     # ANN_PRM_UNT_AMT
    nxt_chg_typ_cd: str                 # NXT_CHG_TYP_CD
    nxt_chg_dt: Optional[date]          # NXT_CHG_DT
    terminate_date: Optional[date]      # TMN_DT
    is_base: bool
    # Total annual premium for this coverage (ANN_PRM_UNT_AMT × units)
    cov_annual_premium: Optional[Decimal]
    # Raw per-unit annual premium rate (ANN_PRM_UNT_AMT) — not multiplied by units
    annual_premium_per_unit: Optional[Decimal]
    cv_amount: Optional[Decimal] = None           # TH_COV_PHA.CV_AMT
    nsp_amount: Optional[Decimal] = None          # TH_COV_PHA.NSP_AMT
    elimination_period: str = ""        # ELM_PER_CD (DI)
    benefit_period: str = ""            # BNF_PER_CD (DI)
    # Cost-of-insurance rate – from LH_COV_INS_RNL_RT.RNL_RT (type "C").
    # This is the COI rate for Advanced (UL/IUL/VUL) products, already
    # divided by 100 (product line "I") or 100,000 (other product lines).
    coi_rate: Optional[Decimal] = None  # RNL_RT (type C)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    # Backwards compatibility aliases
    @property
    def premium_paying_status(self) -> str:
        return self.cov_status

    @property
    def premium_paying_status_desc(self) -> str:
        return self.cov_status_desc

    @property
    def rate(self) -> Optional[Decimal]:
        """Return the appropriate display rate based on product type.

        Advanced products (UL/IUL/VUL) → coi_rate  (from LH_COV_INS_RNL_RT)
        Traditional products           → premium_rate (from LH_COV_PHA.ANN_PRM_UNT_AMT)
        """
        if self.coi_rate is not None:
            return self.coi_rate
        return self.premium_rate


# =============================================================================
# RECORD 03 — SUBSTANDARD RATINGS
# =============================================================================

@dataclass
class SubstandardRatingInfo:
    """Substandard/flat extra rating from LH_SST_XTR_CRG."""
    coverage_phase: int                 # COV_PHA_NBR
    person_seq: int                     # PRS_SEQ_NBR
    joint_indicator: str                # JT_INS_IND
    type_code: str                      # T=Table, F=Flat (translated from SST_XTR_TYP_CD)
    type_desc: str
    table_rating: str                   # SST_XTR_RT_TBL_CD
    table_rating_numeric: int
    flat_amount: Optional[Decimal]      # XTR_PER_1000_AMT (annual flat extra per $1000)
    flat_cease_date: Optional[date]     # SST_XTR_CEA_DT
    duration: Optional[int]             # SST_XTR_CEA_DUR
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# RECORD 09 — SKIPPED PERIODS
# =============================================================================

@dataclass
class SkippedPeriodInfo:
    """Skipped/reinstatement period from LH_COV_SKIPPED_PER."""
    coverage_phase: int                 # COV_PHA_NBR
    period_type: str                    # SKP_TYP_CD
    skip_from_date: Optional[date]      # SKP_FRM_DT
    skip_to_date: Optional[date]        # SKP_TO_DT
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# RECORD 67 — RENEWAL RATES & COVERAGE TARGETS
# =============================================================================

@dataclass
class RenewalCovRateInfo:
    """Coverage renewal rate from LH_COV_INS_RNL_RT."""
    coverage_phase: int                 # COV_PHA_NBR
    rate_type: str                      # PRM_RT_TYP_CD
    rate_type_desc: str
    joint_indicator: str                # JT_INS_IND
    rate_class: str                     # RT_CLS_CD
    rate_class_desc: str
    issue_age: Optional[int]            # ISS_AGE  # TODO: verify column name
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CoverageTargetInfo:
    """Coverage-level target from LH_COV_TARGET."""
    coverage_phase: int                 # COV_PHA_NBR
    target_type: str                    # TAR_TYP_CD
    target_type_desc: str
    target_amount: Optional[Decimal]    # TAR_PRM_AMT or TAR_VAL_AMT
    target_date: Optional[date]         # TAR_DT
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# RECORD 04 — BENEFITS
# =============================================================================

@dataclass
class BenefitInfo:
    """Benefit information from LH_SPM_BNF."""
    cov_pha_nbr: int                    # COV_PHA_NBR
    benefit_code: str                   # SPM_BNF_TYP_CD + SPM_BNF_SBY_CD
    benefit_type_cd: str                # Benefit type code (first char)
    benefit_subtype_cd: str             # Benefit subtype code
    benefit_desc: str
    form_number: str                    # BNF_FRM_NBR
    issue_date: Optional[date]          # BNF_ISS_DT
    cease_date: Optional[date]          # BNF_CEA_DT
    orig_cease_date: Optional[date]     # BNF_OGN_CEA_DT
    units: Optional[Decimal]            # BNF_UNT_QTY
    vpu: Optional[Decimal]              # BNF_VPU_AMT
    benefit_amount: Optional[Decimal]   # BNF_UNT_QTY × BNF_VPU_AMT
    issue_age: Optional[int]            # BNF_ISS_AGE
    rating_factor: Optional[Decimal]    # BNF_RT_FCT
    renewal_indicator: str              # RNL_RT_IND
    coi_rate: Optional[Decimal]         # BNF_ANN_PPU_AMT
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# RECORD 04 — BENEFIT RENEWAL RATES
# =============================================================================

@dataclass
class RenewalBenRateInfo:
    """Benefit renewal rate from LH_BNF_INS_RNL_RT."""
    coverage_phase: int                 # COV_PHA_NBR
    benefit_type: str                   # SPM_BNF_TYP_CD
    benefit_subtype: str                # SPM_BNF_SBY_CD
    rate_type: str                      # PRM_RT_TYP_CD
    rate_type_desc: str
    joint_indicator: str                # JT_INS_IND
    rate_class: str                     # RT_CLS_CD
    issue_age: Optional[int]            # ISS_AGE
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# RECORDS 12-15, 18-19, 74 — DIVIDENDS
# =============================================================================

@dataclass
class AppliedDividendInfo:
    """Applied dividend record from LH_APPLIED_PTP."""
    dividend_date: Optional[date]       # PTP_APL_DT
    dividend_type: str                  # PTP_APL_TYP_CD
    dividend_type_desc: str             # Translated description
    gross_amount: Optional[Decimal]     # PTP_GRS_AMT
    net_amount: Optional[Decimal]       # PTP_NET_AMT
    year: Optional[int]                 # POL_DUR_NBR
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnappliedDividendInfo:
    """Unapplied dividend record from LH_UNAPPLIED_PTP."""
    dividend_date: Optional[date]       # PTP_PRO_DT
    dividend_type: str                  # PTP_TYP_CD
    dividend_type_desc: str             # Translated description
    gross_amount: Optional[Decimal]     # PTP_GRS_AMT
    net_amount: Optional[Decimal]       # PTP_NET_AMT
    year: Optional[int]                 # POL_DUR_NBR
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DivOYTInfo:
    """One Year Term dividend addition from LH_ONE_YR_TRM_ADD."""
    coverage_phase: int                 # COV_PHA_NBR
    issue_date: Optional[date]          # OYT_ISS_DT
    face_amount: Optional[Decimal]      # OYT_FCE_AMT
    csv_amount: Optional[Decimal]       # OYT_CSV_AMT
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DivPUAInfo:
    """Paid-Up Addition from LH_PAID_UP_ADD."""
    coverage_phase: int                 # COV_PHA_NBR
    issue_date: Optional[date]          # PUA_ISS_DT
    face_amount: Optional[Decimal]      # PUA_FCE_AMT
    csv_amount: Optional[Decimal]       # PUA_CSV_AMT
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DivDepositInfo:
    """Dividend on deposit from LH_PTP_ON_DEP."""
    deposit_date: Optional[date]        # DEP_DT
    deposit_type: str                   # PTP_TYP_CD
    deposit_type_desc: str              # Translated description
    deposit_amount: Optional[Decimal]   # CUM_DEP_AMT
    interest_amount: Optional[Decimal]  # ITS_AMT
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# RECORDS 20, 77 — LOANS
# =============================================================================

@dataclass
class LoanInfo:
    """Policy loan summary from LH_CSH_VAL_LOAN / LH_FND_VAL_LOAN."""
    loan_type: str                      # LN_TYP_CD
    loan_type_desc: str
    principal: Decimal                  # LN_PRI_AMT
    accrued_interest: Decimal           # Accrued interest
    interest_rate: Optional[Decimal]    # LN_ITS_RT
    preferred_loan: bool                # PRF_LN_IND
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradLoanInfo:
    """Traditional loan detail from LH_CSH_VAL_LOAN."""
    mv_date: Optional[date]             # MVRY_DT
    principal: Optional[Decimal]        # LN_PRI_AMT
    accrued_interest: Optional[Decimal] # POL_LN_ITS_AMT
    interest_rate: Optional[Decimal]    # LN_ITS_RT
    interest_type: str                  # LN_ITS_AMT_TYP_CD
    interest_type_desc: str
    interest_status: str                # LN_ITS_STS_CD
    interest_status_desc: str
    preferred_indicator: str            # PRF_LN_IND
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoanRepayInfo:
    """Loan repayment schedule from LH_LN_RPY_TRM."""
    payment_number: int                 # PMT_NBR
    payment_date: Optional[date]        # PMT_DT
    payment_amount: Optional[Decimal]   # PMT_AMT
    principal_amount: Optional[Decimal] # LN_PRI_AMT
    interest_amount: Optional[Decimal]  # LN_ITS_AMT
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# RECORDS 38, 48 — AGENTS
# =============================================================================

@dataclass
class AgentInfo:
    """Agent/commission information from LH_AGT_COM_AMT."""
    agt_com_pha_nbr: int                # AGT_COM_PHA_NBR
    agent_id: str                       # AGT_ID
    commission_pct: Optional[Decimal]   # COM_PCT
    market_org_cd: str                  # MKT_ORG_CD
    svc_agt_ind: str                    # SVC_AGT_IND
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# RECORDS 55, 57, 65 — FUNDS
# =============================================================================

@dataclass
class FundBucketInfo:
    """Fund bucket value from LH_POL_FND_VAL_TOT."""
    fund_id: str                        # FND_ID_CD
    fund_name: str                      # Translated fund name
    mv_date: Optional[date]             # MVRY_DT
    csv_amount: Optional[Decimal]       # CSV_AMT
    units: Optional[Decimal]            # FND_UNT_QTY
    interest_rate: Optional[Decimal]    # CRE_ITS_RT
    start_date: Optional[date]          # BKT_STR_DT
    phase: int                          # COV_PHA_NBR
    is_current: bool                    # True if MVRY_DT contains 9999
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# RECORD 69 — TRANSACTIONS
# =============================================================================

@dataclass
class TransactionInfo:
    """Transaction record from FH_FIXED."""
    trans_date: date                    # ASOF_DT
    trans_code: str                     # Full code (TRN_TYP_CD + TRN_SBY_CD)
    trans_type: str                     # TRN_TYP_CD
    trans_subtype: str                  # TRN_SBY_CD
    trans_desc: str                     # Translated description
    gross_amount: Optional[Decimal]     # TOT_TRS_AMT
    net_amount: Optional[Decimal]       # ACC_VAL_GRS_AMT
    sequence_number: int                # SEQ_NO
    fund_id: str                        # FND_ID_CD
    coverage_phase: int                 # COV_PHA_NBR
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# RECORDS 89, 90 — PERSONS
# =============================================================================

@dataclass
class PersonInfo:
    """Person information from LH_CTT_CLIENT / VH_POL_HAS_LOC_CLT."""
    person_code: str                    # PRS_CD
    person_seq: int                     # PRS_SEQ_NBR
    person_desc: str                    # Translated person code
    first_name: str                     # CK_FST_NM
    last_name: str                      # CK_LST_NM
    birth_date: Optional[date]          # BIR_DT
    gender_code: str                    # GENDER_CD
    gender_desc: str                    # Translated gender
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AddressInfo:
    """Address information from LH_LOC_CLT_ADR."""
    address_line_1: str                 # ADR_LIN_1
    address_line_2: str                 # ADR_LIN_2
    city: str                           # CIT_TXT
    state_code: str                     # CK_ST_CD
    zip_code: str                       # ZIP_CD
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# RECORDS 58, 59 — TARGETS
# =============================================================================

@dataclass
class PolicyTargetInfo:
    """Policy-level target from LH_POL_TARGET / LH_COM_TARGET."""
    target_type_cd: str                 # TAR_TYP_CD
    target_type_desc: str               # Translated description
    target_premium: Optional[Decimal]   # TAR_PRM_AMT
    target_date: Optional[date]         # TAR_DT
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GuidelinePremiumInfo:
    """Guideline premium from LH_COV_INS_GDL_PRM."""
    coverage_phase: int                 # COV_PHA_NBR
    rate_type_cd: str                   # PRM_RT_TYP_CD — A=GLP, S=GSP
    rate_type_desc: str
    guideline_premium: Optional[Decimal]  # GDL_PRM_AMT
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# RECORDS 60, 62-64, 75 — TOTALS / MONTHLIVERSARY VALUES
# =============================================================================

@dataclass
class MVValueInfo:
    """Monthly anniversary value record from TH_POL_MVRY_VAL / LH_POL_MVRY_VAL."""
    mvry_dt: Optional[date]             # MVRY_DT
    accum_value: Optional[Decimal]      # Cash surrender / accumulation value
    cash_surr_value: Optional[Decimal]  # CSV_AMT (alias for display)
    death_benefit: Optional[Decimal]    # DB_AMT
    net_amt_at_risk: Optional[Decimal]  # NAR_AMT
    cins_amount: Optional[Decimal] = None        # CINS_AMT — COI charge
    expense_charge: Optional[Decimal] = None     # EXP_CRG_AMT
    other_premium: Optional[Decimal] = None      # OTH_PRM_AMT
    duration: Optional[int] = None               # POL_DUR_NBR
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActivityInfo:
    """Policy activity/transaction summary."""
    activity_date: date
    activity_type_cd: str
    activity_desc: str
    amount: Optional[Decimal]
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# RECORD 52 — USER FIELDS
# =============================================================================

@dataclass
class UserFieldInfo:
    """User generic fields from TH_USER_GENERIC."""
    initial_pay_duration: Optional[int]   # Short pay duration
    initial_mode: Optional[str]           # Short pay mode
    dial_to_premium_age: Optional[int]    # DB dial-to-premium age
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# RECORDS 32, 33, 35 — BILLING
# =============================================================================

@dataclass
class BillingInfo:
    """Billing information from LH_BAS_POL billing fields."""
    payment_frequency: int              # PMT_FQY_PER
    billing_mode_desc: str              # Translated billing mode
    non_standard_mode_cd: str           # NSD_MD_CD
    bill_day: int                       # BL_DAY_NBR
    bill_form_cd: str                   # BIL_FRM_CD
    billing_form_desc: str              # Translated billing form
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# RECORDS 05-08, 68 — CHANGES
# =============================================================================

@dataclass
class PolicyChangeInfo:
    """Policy change history record."""
    change_date: Optional[date]
    change_type: str
    change_desc: str
    original_entry_cd: str              # OGN_ETR_CD
    last_entry_cd: str                  # LST_ETR_CD
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# EXCEPTIONS
# =============================================================================

class PolicyNotFoundError(Exception):
    """Raised when policy does not exist in database."""
    pass
