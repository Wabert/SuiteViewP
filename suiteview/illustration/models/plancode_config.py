from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Optional

from suiteview.illustration.constants import (
    LAPSE_BASIS_SURRENDER_VALUE,
    RATE_CODE_TABLE,
    SA_BASIS_CURRENT,
    SA_BASIS_ORIGINAL,
)

_PLANCODE_DIR = Path(__file__).resolve().parent.parent / "plancodes"
_PLANCODE_TABLE_PATH = _PLANCODE_DIR / "plancode_table.json"
_CONFIG_CACHE: Dict[str, PlancodeConfig] = {}
_TABLE_CACHE: Optional[Dict[str, dict]] = None


@dataclass
class PlancodeConfig:
    """Product-level parameters loaded from plancode JSON file."""

    plancode: str = ""
    product_name: str = ""

    # Illustration gating — enforced ONLY in distribution builds (see
    # suiteview.core.build_env.is_distribution_build). True (default) when the
    # key is absent so existing plancodes keep illustrating.
    can_illustrate: bool = True

    # Interest
    cint_key: str = ""
    int_calc_method: str = "Declared"   # "Declared", "IUL_Blend"
    interest_method: str = "ExactDays"  # "ExactDays", "MonthlyCompounding"
    age_calc: str = ""

    # Premium loading
    premium_load: str = RATE_CODE_TABLE  # "Table" or flat rate (e.g., "0.05")
    prem_flat_load: float = 0.0         # Flat $ per premium

    # EPU
    epu_code: str = RATE_CODE_TABLE      # "Table" or flat rate

    # Monthly fee
    mfee: str = "5"                     # "Table" or flat $ (e.g., "5")

    # AV charge
    poav_code: str = "0"
    poav_table: str = "0"               # Local PoAV table code "1"-"3"; "0" = none

    # Bonus interest
    bonus: str = RATE_CODE_TABLE         # "Table" or "0" (none)
    dbd: float = 0.0
    gint: float = 0.0

    # Substandard
    table_rating_factor: float = 0.25

    # Company subsidiary (RERUN sCompanySub) — "FFL" switches the premium
    # waiver targets to the FFL basis (CalcEngine IW..JD via sblnFFL).
    company_sub: str = "ANICO"

    # PWoT (Stipulated Premium Waiver, benefit type 4) COI charge basis
    # (RERUN sPWoT_COI_Basis, CalcEngine RB CHOOSE):
    #   1 = Units  -> units x RA
    #   2 = MTP    -> vMTP x RA/100    (annual MTP)
    #   3 = CTP    -> vCTP x RA/100    (annual CTP)
    # then grossed up by (1 + tableRatingFactor x base-coverage table rating).
    # Non-FFL ULs are all basis 1; some FFL ULs use 2 or 3.
    pwot_coi_basis: int = 1

    # Withdrawals — RERUN sWithdrawalFee / sMD_HoldBack, plus the
    # post-withdrawal minimum face hardcoded in the workbook (AY: SA - 25,025
    # = 25,000 floor + the fee). Partial surrender charge eligibility is
    # derived from ``sa_basis`` below.
    withdrawal_fee: float = 25.0
    md_holdback: float = 0.0             # months of prior MD held back from max-net
    min_face_after_wd: float = 25000.0

    # Corridor
    corridor_code: int = 1              # CorridorCode key for tRates_CORR

    # Maturity
    premium_cease_age: int = 121
    maturity_age: int = 121
    mature_endow_value: str = LAPSE_BASIS_SURRENDER_VALUE

    # Safety Net / Lapse
    snet_period: int = 10             # Safety net period in years from issue
    lapse_value: str = LAPSE_BASIS_SURRENDER_VALUE  # "SV" = surrender value, "AV" = AV-loans (MLUL)

    # Dynamic banding
    dynamic_banding: int = 3            # 0 = none, 1 = issue band, 2 = current band, 3 = higher of
    rachet_banding: bool = False
    # Issue-date-dependent band boundary (RERUN Rates_Control column CZ,
    # "Use Band Table 2 by Issue Date", cutoff in CZ9 = 2018-10-01). For the
    # plancodes RERUN lists in CZ12:CZ32, policies ISSUED ON/AFTER this date
    # band with mBandTable2 (band 3 starts at 250,000 — the thresholds stored
    # in UL_Rates BANDSPECS), while policies issued BEFORE it band with
    # mBandTable1 (identical except band 3 starts at 250,001). None = banding
    # does not depend on issue date (every other plancode).
    band_table2_issue_date: Optional[date] = None
    skipped_cov_rein: bool = False
    # Specified-amount basis for EPU, MTP, CTP and full surrender charges.
    # OriginalSA also locks only MTP rates to each coverage's issue band;
    # CTP, COI, EPU and premium-load bands remain current (SCR is unbanded).
    # CurrentSA plans assess partial surrender charges on withdrawals and
    # specified-amount decreases; OriginalSA plans do not.
    sa_basis: str = SA_BASIS_CURRENT  # "CurrentSA" or "OriginalSA"
    # Surrender charge as a percent of the coverage's stored surrender target
    # (LH_COV_TARGET 'ST'), by coverage year 1..n (0 after). FFL EP/EP2 joint
    # plans: CyberLife SCR rule 6, the target itself is VP/MS. None = the plan's
    # per-unit SCR rate table.
    scr_pct_of_surrender_target: Optional[tuple] = None

    def __post_init__(self) -> None:
        if self.sa_basis not in (SA_BASIS_CURRENT, SA_BASIS_ORIGINAL):
            raise ValueError(f"{self.plancode}: invalid SA_Basis {self.sa_basis!r}")
        if self.scr_pct_of_surrender_target is not None and not all(
            0.0 <= pct <= 1.0 for pct in self.scr_pct_of_surrender_target
        ):
            raise ValueError(f"{self.plancode}: SCR_PctOfSurrenderTarget must be fractions 0-1")

    @property
    def partial_surrender_charge(self) -> bool:
        """Whether decreases assess a partial surrender charge.

        Specified-amount decreases additionally honor the policy's Decrease
        Charge Rule (``IllustrationPolicyData.decrease_charge_allowed``).
        """
        return self.sa_basis == SA_BASIS_CURRENT

    # Loans
    loan_type: str = "Arrears"           # "Arrears" or "Advance"
    loan_charge_rate_guar: float = 0.0   # sRates_LNCRG — regular guaranteed
    loan_charge_rate_curr: float = 0.0   # sRates_LNCRD — regular current
    pref_loan_charge_rate_guar: float = 0.0  # sRates_PrefLNCRG
    pref_loan_charge_rate_curr: float = 0.0  # sRates_PrefLNCRD
    var_loan_available: bool = False

    # Shadow Account (CCV)
    shadow_plancode: str = ""            # CCV plancode for shadow COI rates (e.g., "CCV00100")
    shadow_availability: str = ""        # "Rider", "Inherent", or "" (none)
    shadow_cease_age: int = 121          # Age at which shadow account ceases
    shadow_sa_basis: int = 2             # 1 = OriginalSA, 2 = CurrentSA
    shadow_target: str = "0"             # "Table" or "0" (flat)
    shadow_prem_load_code: str = "0"     # "Table" or flat rate string (e.g., "0.06")
    shadow_epu_code: str = "0"           # "Table" or flat rate string
    shadow_mfee: float = 0.0             # Flat monthly expense fee
    shadow_dbd_rate: str = "0.05"        # "Table" or flat rate for DB discount
    shadow_int_rate_code: str = "0.05"   # "Table" or flat interest rate
    shadow_loan_impact: str = "Reduce"   # "Reduce" or "None"

    @property
    def is_ffl(self) -> bool:
        """RERUN sblnFFL = (sCompanySub = "FFL")."""
        return self.company_sub == "FFL"


def _load_plancode_table() -> Dict[str, dict]:
    global _TABLE_CACHE
    if _TABLE_CACHE is not None:
        return _TABLE_CACHE

    if not _PLANCODE_TABLE_PATH.exists():
        raise FileNotFoundError(
            f"No plancode table found: {_PLANCODE_TABLE_PATH}"
        )

    with open(_PLANCODE_TABLE_PATH, "r") as f:
        table_data = json.load(f)

    rows = table_data.get("Plancodes", [])
    _TABLE_CACHE = {
        str(row.get("Plancode", "")).strip(): row
        for row in rows
        if str(row.get("Plancode", "")).strip()
    }
    return _TABLE_CACHE


def _int_or_default(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _date_or_none(value) -> Optional[date]:
    """Parse an ISO date string from the plancode table; None/blank -> None."""
    if not value:
        return None
    return date.fromisoformat(str(value).strip())


class MissingPlancodeError(KeyError):
    """The plan has no illustration configuration, rather than a malformed row."""


def load_plancode(plancode: str) -> PlancodeConfig:
    """Load plancode configuration from the plancode table JSON file.

    Args:
        plancode: Product plan code (e.g., "1U143900").

    Returns:
        PlancodeConfig populated from the JSON file.

    Raises:
        FileNotFoundError: If the plancode table does not exist.
        MissingPlancodeError: If the plancode has no row in the table.
    """
    if plancode in _CONFIG_CACHE:
        return _CONFIG_CACHE[plancode]

    data = _load_plancode_table().get(plancode)
    if data is None:
        raise MissingPlancodeError(
            f"No plancode config found for {plancode} in {_PLANCODE_TABLE_PATH}"
        )

    config = PlancodeConfig(
        plancode=plancode,
        product_name=data.get("ProductName", ""),
        can_illustrate=bool(data.get("CanIllustrate", True)),
        cint_key=data.get("CINT_Key", ""),
        int_calc_method=data.get("IntCalcMethod", "Declared"),
        interest_method=data.get("Interest_Method", data.get("InterestMethod", "ExactDays")),
        age_calc=data.get("AgeCalc", ""),
        premium_load=data.get("PremiumLoad", RATE_CODE_TABLE),
        prem_flat_load=float(data.get("PremFlatLoad", 0)),
        epu_code=data.get("EPU_Code", RATE_CODE_TABLE),
        mfee=str(data.get("MFEE", "5")),
        poav_code=str(data.get("PoAV_Table", data.get("PoAV_Code", "0"))),
        poav_table=str(data.get("PoAV_Table", data.get("PoAV_Code", "0"))),
        bonus=data.get("Bonus", RATE_CODE_TABLE),
        dbd=float(data.get("DBD", 0)),
        gint=float(data.get("GINT", data.get("DBD", 0))),
        table_rating_factor=float(data.get("TableRatingFactor", 0.25)),
        company_sub=str(data.get("CompanySub", "ANICO")).strip(),
        pwot_coi_basis=_int_or_default(data.get("PWoT_COI_Basis", 1), 1),
        withdrawal_fee=float(data.get("WithdrawalFee", 25)),
        md_holdback=float(data.get("MD_HoldBack", 0)),
        min_face_after_wd=float(data.get("MinFaceAfterWD", 25000)),
        corridor_code=int(data.get("CorridorCode", 1)),
        premium_cease_age=int(data.get("PremiumCeaseAge", 121)),
        maturity_age=int(data.get("MaturityAge", 121)),
        mature_endow_value=data.get("MatureEndowValue", LAPSE_BASIS_SURRENDER_VALUE),
        snet_period=_int_or_default(data.get("SafetyNetPeriod", 10), 0),
        lapse_value=data.get(
            "LapseTarget",
            data.get("LapseValue", LAPSE_BASIS_SURRENDER_VALUE),
        ),
        dynamic_banding=int(data.get("DynamicBanding", 3)),
        rachet_banding=bool(data.get("Rachet_Banding", False)),
        band_table2_issue_date=_date_or_none(data.get("BandTable2IssueDate")),
        skipped_cov_rein=bool(data.get("SkippedCovRein", False)),
        sa_basis=data["SA_Basis"],
        scr_pct_of_surrender_target=(
            tuple(float(pct) for pct in data["SCR_PctOfSurrenderTarget"])
            if data.get("SCR_PctOfSurrenderTarget") is not None else None
        ),
        loan_type=data.get("LoanType", "Arrears"),
        loan_charge_rate_guar=float(data.get("LoanChargeRate", data.get("LoanChargeRateGuar", 0))),
        loan_charge_rate_curr=float(data.get("LoanCollateralCreditRate", data.get("LoanChargeRateCurr", 0))),
        pref_loan_charge_rate_guar=float(data.get("PrefLoanChargeRate", data.get("PrefLoanChargeRateGuar", 0))),
        pref_loan_charge_rate_curr=float(data.get("PrefLoanCollateralCreditRate", data.get("PrefLoanChargeRateCurr", 0))),
        var_loan_available=bool(data.get("VarLoanAvailable", False)),
        # Shadow Account (CCV)
        shadow_plancode=data.get("ShadowPlancode", ""),
        shadow_availability=data.get("ShadowAvailability", ""),
        shadow_cease_age=int(data.get("ShadowCeaseAge", 121)),
        shadow_sa_basis=int(data.get("ShadowSABasis", 2)),
        shadow_target=str(data.get("ShadowTarget", "0")),
        shadow_prem_load_code=str(data.get("ShadowPremLoadCode", "0")),
        shadow_epu_code=str(data.get("ShadowEPUCode", "0")),
        shadow_mfee=float(data.get("ShadowMFEE", 0)),
        shadow_dbd_rate=str(data.get("ShadowDBDRate", "0.05")),
        shadow_int_rate_code=str(data.get("ShadowIntRateCode", "0.05")),
        shadow_loan_impact=data.get("ShadowLoanImpact", "Reduce"),
    )

    _CONFIG_CACHE[plancode] = config
    return config
