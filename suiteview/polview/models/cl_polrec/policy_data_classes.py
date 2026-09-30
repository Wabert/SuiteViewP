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
    table_cease_date: Optional[date]    # From LH_SST_XTR_CRG table rating row
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
    number_of_lives_code: str = ""      # NBR_OF_LIVES_CD ("3" = joint survivor)
    joint_issue_age: Optional[int] = None  # JNT_ISU_ISS_AGE (person 01)
    joint_mortality_table_code: str = ""   # JNT_ISU_MTL_TBL_CD
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
    # Traditional fixed premiums bill the rating as an annual extra premium per unit
    # (SST_XTR_UNT_AMT), modalized on its own (CyberLife E0112582, 14738679).
    extra_premium_per_unit: Optional[Decimal] = None   # SST_XTR_UNT_AMT
    extra_percent: Optional[Decimal] = None            # SST_XTR_PCT
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
    issue_age: Optional[int]            # ISS_AGE
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
    pay_up_date: Optional[date]         # BNF_PAY_UP_DT
    cease_date: Optional[date]          # BNF_CEA_DT
    orig_cease_date: Optional[date]     # BNF_OGN_CEA_DT
    units: Optional[Decimal]            # BNF_UNT_QTY
    vpu: Optional[Decimal]              # BNF_VPU_AMT
    benefit_amount: Optional[Decimal]   # BNF_UNT_QTY × BNF_VPU_AMT
    issue_age: Optional[int]            # BNF_ISS_AGE
    rating_factor: Optional[Decimal]    # BNF_RT_FCT
    renewal_indicator: str              # RNL_RT_IND
    coi_rate: Optional[Decimal]         # BNF_ANN_PPU_AMT (issue rate, Record 04)
    renewal_rate: Optional[Decimal] = None  # LH_BNF_INS_RNL_RT.RNL_RT (Record 67, PRM_RT_TYP_CD="B")
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
    """Applied (history) participation value from LH_APPLIED_PTP (segment 19 history).

    The cash/PUA/OYT amounts are CyberLife's per-unit values: the base coverage row
    (source ``0``) is per unit of coverage; the paid-up-additions row (source ``1``) is
    per $1,000 of additions, with ``units`` (PUA_UNT_QTY) the additions in thousands.
    """
    coverage_phase: int                 # COV_PHA_NBR
    participation_type: str             # CK_PTP_TYP_CD (D dividend)
    earn_year: Optional[int]            # ERN_DT_MO_YR_NBR decoded (anniversary year)
    earn_month: Optional[int]           # ERN_DT_MO_YR_NBR decoded (anniversary month)
    source: str                         # PTP_SRC_IND (0 coverage, 1 paid-up additions)
    applied_option: str                 # APP_OPT_CD
    cash_per_unit: Decimal              # CSH_AMT
    pua_per_unit: Decimal               # PUA_AMT
    oyt_per_unit: Decimal               # OYT_AMT
    units: Decimal                      # PUA_UNT_QTY (0 on applied history rows)
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnappliedDividendInfo:
    """Unapplied participation value from LH_UNAPPLIED_PTP (segment 19).

    Placed before the anniversary it is earned on; ``units`` are the coverage units
    (source ``0``) or the paid-up additions in thousands (source ``1``) it applies to.
    """
    coverage_phase: int                 # COV_PHA_NBR
    participation_type: str             # CK_PTP_TYP_CD
    earn_year: Optional[int]            # ERN_DT_MO_YR_NBR decoded
    earn_month: Optional[int]           # ERN_DT_MO_YR_NBR decoded
    source: str                         # PTP_SRC_IND
    rpu_values: bool                    # RPU_VAL_IND = 1
    earn_rule: str                      # ERN_RLE_CD
    deposit_interest_rate: Optional[Decimal]  # DEP_ITS_RT (percent)
    cash_per_unit: Decimal              # CSH_AMT
    pua_per_unit: Decimal               # PUA_AMT
    oyt_per_unit: Decimal               # OYT_AMT
    projected_cash_per_unit: Optional[Decimal]  # PRJ_CSH_AMT
    units: Decimal                      # PUA_UNT_QTY
    pua_mortality_table: str            # PUA_MTL_TBL_CD
    pua_interest_rate: Optional[Decimal]  # PUA_ITS_RT (percent)
    raw_data: Dict[str, Any] = field(default_factory=dict)
    direct_recognition: bool = False    # DIR_RCG_DIV_IND = 1 (direct recognition dividend)
    gross_interest_rate: Optional[Decimal] = None  # DIV_GRS_ITS_RT (percent; direct recognition)


@dataclass
class DivOYTInfo:
    """One-year term additions from LH_ONE_YR_TRM_ADD (segment 15)."""
    mv_date: Optional[date]             # MVRY_DT (12/31/9999 = current)
    before_anniversary: bool            # ANV_PRC_CRN_IND = 1 (snapshot before anniversary processing)
    expiry_year: Optional[int]          # OYT_EXP_MO_YR_NBR decoded
    expiry_month: Optional[int]
    nfo_code: str                       # OYT_ADD_NF_CD
    mortality_table: str                # OYT_MTL_TBL_CD
    interest_rate: Optional[Decimal]    # OYT_ITS_RT (percent)
    amount: Decimal                     # OYT_ADD_AMT
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_current(self) -> bool:
        return self.mv_date is not None and self.mv_date.year >= 9999


@dataclass
class DivPUAInfo:
    """Paid-up additions from LH_PAID_UP_ADD (segment 14)."""
    coverage_phase: int                 # COV_PHA_NBR
    purchase_source: str                # PUA_PUR_SRC_CD (0 dividends, 1 premium)
    mv_date: Optional[date]             # MVRY_DT (12/31/9999 = current)
    before_anniversary: bool            # ANV_PRC_CRN_IND = 1 (snapshot before anniversary processing)
    maturity_year: Optional[int]        # PUA_MT_MO_YR_NBR decoded
    maturity_month: Optional[int]
    nfo_code: str                       # PUA_NF_CD
    mortality_table: str                # PUA_MTL_TBL_CD
    interest_rate: Optional[Decimal]    # PUA_ITS_RT (percent)
    pua_class: str                      # PUA_CLS_CD (1 life additions)
    amount: Decimal                     # PUA_AMT
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_current(self) -> bool:
        return self.mv_date is not None and self.mv_date.year >= 9999


@dataclass
class DivDepositInfo:
    """Participation values on deposit from LH_PTP_ON_DEP (segments 12/13)."""
    participation_type: str             # CK_PTP_TYP_CD
    mv_date: Optional[date]             # MVRY_DT (12/31/9999 = current)
    before_anniversary: bool            # ANV_PRC_CRN_IND = 1
    interest_applied_year: Optional[int]   # ITS_APP_MO_YR_NBR decoded
    interest_applied_month: Optional[int]
    nfo_code: str                       # DEP_NF_CD
    interest_rate: Optional[Decimal]    # DEP_ITS_RT (percent)
    deposit_amount: Decimal             # PTP_DEP_AMT
    interest_amount: Decimal            # DEP_ITS_AMT
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_current(self) -> bool:
        return self.mv_date is not None and self.mv_date.year >= 9999


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
    # LN_ITS_PBL_TYP_CD: 1 interest payable in advance, 2 in arrears (CyberDoc D202 FUBBILLC).
    interest_payable_code: str = ""
    interest_paid_to_date: Optional[date] = None    # LN_ITS_PAY_TO_DT
    last_activity_date: Optional[date] = None       # LST_LN_ACY_DT

    @property
    def interest_in_advance(self) -> bool:
        return self.interest_payable_code == "1"


@dataclass(frozen=True)
class TraditionalCoverageFacts:
    """Fixed-value coverage facts on LH_COV_PHA that traditional valuation needs.

    ``stored_cash_values`` / ``stored_nsp_values`` are CyberLife's per-unit tabular
    values for the durations starting at ``stored_low_duration`` (LOW_DUR_PER).
    """
    cov_pha_nbr: int                    # COV_PHA_NBR
    pay_up_date: Optional[date]         # PAY_UP_DT
    subseries_code: str                 # LIF_PLN_SUB_SRE_CD
    base_series_code: str               # PLN_BSE_SRE_CD
    class_code: str                     # INS_CLS_CD
    product_line_code: str              # PRD_LIN_TYP_CD
    dividend_participation_code: str    # DIV_PTP_TYP_CD
    nsp_rpu_table: str                  # NSP_RPU_TBL_CD
    nsp_extended_table: str             # NSP_EI_TBL_CD
    nsp_interest_rate: Optional[Decimal]  # NSP_ITS_RT (percent)
    rpu_benefit_code: str               # RPU_BNF_CD
    coverage_nfo_code: str              # COV_NFO_CD
    stored_low_duration: Optional[int]  # LOW_DUR_PER
    stored_cash_values: tuple           # LOW_DUR_CSV_AMT .. LOW_DUR_3_CSV_AMT
    stored_nsp_values: tuple            # LOW_DUR_NSP_AMT .. LOW_DUR_2_NSP_AMT
    rate_band_code: str                 # LH_COV_INS_RNL_RT.RT_BAN_CD (current row)
    cease_reason_code: str = ""         # CEA_REA_CD (blank while the coverage has not ceased)
    # Renewable / indeterminate premium term (CyberDoc D10 plan additional information):
    renewable_premium_code: str = ""    # RENEWABLE_PRM_CD: C renewable, E select renewable
    initial_renewal_period: Optional[int] = None    # INT_RNL_PER (level period, years)
    renewal_start_duration: Optional[int] = None    # SBQ_RNL_STR_DUR
    renewal_period: Optional[int] = None            # SBQ_RNL_PER (1 = renews annually)
    indeterminate_guaranteed_months: Optional[int] = None   # IDT_PRM_GUA_PER
    refresh_or_renewal_age: Optional[int] = None    # REFRESH_OR_RNL_AGE


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
    interest_rate: Optional[Decimal]    # VAL_PHA_ITS_RT (percent)
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
# EXCEPTIONS
# =============================================================================

class PolicyNotFoundError(Exception):
    """Raised when policy does not exist in database."""
    pass
