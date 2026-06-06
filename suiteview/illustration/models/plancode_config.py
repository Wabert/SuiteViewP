from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


_PLANCODE_DIR = Path(__file__).resolve().parent.parent / "plancodes"
_PLANCODE_TABLE_PATH = _PLANCODE_DIR / "plancode_table.json"
_CONFIG_CACHE: Dict[str, PlancodeConfig] = {}
_TABLE_CACHE: Optional[Dict[str, dict]] = None


@dataclass
class PlancodeConfig:
    """Product-level parameters loaded from plancode JSON file."""

    plancode: str = ""
    product_name: str = ""

    # Interest
    cint_key: str = ""
    int_calc_method: str = "Declared"   # "Declared", "IUL_Blend"
    interest_method: str = "ExactDays"  # "ExactDays", "MonthlyCompounding"
    age_calc: str = ""

    # Premium loading
    premium_load: str = "Table"         # "Table" or flat rate (e.g., "0.05")
    prem_flat_load: float = 0.0         # Flat $ per premium

    # EPU
    epu_code: str = "Table"             # "Table" or flat rate
    epu_sa_basis: str = "CurrentSA"     # "CurrentSA", "OriginalSA"

    # Monthly fee
    mfee: str = "5"                     # "Table" or flat $ (e.g., "5")

    # AV charge
    poav_code: str = "0"                # "Table" or "0" (none)
    poav_table: str = "0"

    # Bonus interest
    bonus: str = "Table"                # "Table" or "0" (none)
    dbd: float = 0.0

    # Substandard
    table_rating_factor: float = 0.25

    # Corridor
    corridor_code: int = 1              # 1 = GPT corridor, 2 = CVAT MDBR

    # Maturity
    premium_cease_age: int = 121
    maturity_age: int = 121
    mature_endow_value: str = "SV"

    # Safety Net / Lapse
    snet_period: int = 10             # Safety net period in years from issue
    lapse_value: str = "SV"           # "SV" = surrender value, "AV" = AV-loans (MLUL)

    # Dynamic banding
    dynamic_banding: int = 3            # 0 = none, 1 = issue band, 2 = current band, 3 = higher of
    rachet_banding: bool = False
    skipped_cov_rein: bool = False

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


def load_plancode(plancode: str) -> PlancodeConfig:
    """Load plancode configuration from the plancode table JSON file.

    Args:
        plancode: Product plan code (e.g., "1U143900").

    Returns:
        PlancodeConfig populated from the JSON file.

    Raises:
        FileNotFoundError: If the plancode table does not exist.
        KeyError: If the plancode has no row in the table.
    """
    if plancode in _CONFIG_CACHE:
        return _CONFIG_CACHE[plancode]

    data = _load_plancode_table().get(plancode)
    if data is None:
        raise KeyError(
            f"No plancode config found for {plancode} in {_PLANCODE_TABLE_PATH}"
        )

    config = PlancodeConfig(
        plancode=plancode,
        product_name=data.get("ProductName", ""),
        cint_key=data.get("CINT_Key", ""),
        int_calc_method=data.get("IntCalcMethod", "Declared"),
        interest_method=data.get("Interest_Method", data.get("InterestMethod", "ExactDays")),
        age_calc=data.get("AgeCalc", ""),
        premium_load=data.get("PremiumLoad", "Table"),
        prem_flat_load=float(data.get("PremFlatLoad", 0)),
        epu_code=data.get("EPU_Code", "Table"),
        epu_sa_basis=data.get("EPU_SA_Basis", "CurrentSA"),
        mfee=str(data.get("MFEE", "5")),
        poav_code=str(data.get("PoAV_Table", data.get("PoAV_Code", "0"))),
        poav_table=str(data.get("PoAV_Table", data.get("PoAV_Code", "0"))),
        bonus=data.get("Bonus", "Table"),
        dbd=float(data.get("DBD", 0)),
        table_rating_factor=float(data.get("TableRatingFactor", 0.25)),
        corridor_code=int(data.get("CorridorCode", 1)),
        premium_cease_age=int(data.get("PremiumCeaseAge", 121)),
        maturity_age=int(data.get("MaturityAge", 121)),
        mature_endow_value=data.get("MatureEndowValue", "SV"),
        snet_period=_int_or_default(data.get("SafetyNetPeriod", 10), 0),
        lapse_value=data.get("LapseTarget", data.get("LapseValue", "SV")),
        dynamic_banding=int(data.get("DynamicBanding", 3)),
        rachet_banding=bool(data.get("Rachet_Banding", False)),
        skipped_cov_rein=bool(data.get("SkippedCovRein", False)),
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
