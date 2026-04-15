from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


_PLANCODE_DIR = Path(__file__).resolve().parent.parent / "plancodes"
_CONFIG_CACHE: Dict[str, PlancodeConfig] = {}


@dataclass
class PlancodeConfig:
    """Product-level parameters loaded from plancode JSON file."""

    plancode: str = ""
    product_name: str = ""

    # Interest
    int_calc_method: str = "Declared"   # "Declared", "IUL_Blend"
    interest_method: str = "ExactDays"  # "ExactDays", "MonthlyCompounding"

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

    # Bonus interest
    bonus: str = "Table"                # "Table" or "0" (none)

    # Substandard
    table_rating_factor: float = 0.25

    # Corridor
    corridor_code: int = 1              # 1 = GPT corridor, 2 = CVAT MDBR

    # Maturity
    premium_cease_age: int = 121
    maturity_age: int = 121

    # Safety Net / Lapse
    snet_period: int = 10             # Safety net period in years from issue
    lapse_value: str = "SV"           # "SV" = surrender value, "AV" = AV-loans (MLUL)

    # Dynamic banding
    dynamic_banding: int = 3            # 0 = none, 1 = issue band, 2 = current band, 3 = higher of

    # Surrender charge
    scr_code: str = "Table"

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


def load_plancode(plancode: str) -> PlancodeConfig:
    """Load plancode configuration from JSON file.

    Args:
        plancode: Product plan code (e.g., "1U143900").

    Returns:
        PlancodeConfig populated from the JSON file.

    Raises:
        FileNotFoundError: If no JSON config exists for the plancode.
    """
    if plancode in _CONFIG_CACHE:
        return _CONFIG_CACHE[plancode]

    json_path = _PLANCODE_DIR / f"{plancode}.json"
    if not json_path.exists():
        raise FileNotFoundError(
            f"No plancode config found: {json_path}"
        )

    with open(json_path, "r") as f:
        data = json.load(f)

    config = PlancodeConfig(
        plancode=plancode,
        product_name=data.get("ProductName", ""),
        int_calc_method=data.get("IntCalcMethod", "Declared"),
        interest_method=data.get("InterestMethod", "ExactDays"),
        premium_load=data.get("PremiumLoad", "Table"),
        prem_flat_load=float(data.get("PremFlatLoad", 0)),
        epu_code=data.get("EPU_Code", "Table"),
        epu_sa_basis=data.get("EPU_SA_Basis", "CurrentSA"),
        mfee=str(data.get("MFEE", "5")),
        poav_code=str(data.get("PoAV_Code", "0")),
        bonus=data.get("Bonus", "Table"),
        table_rating_factor=float(data.get("TableRatingFactor", 0.25)),
        corridor_code=int(data.get("CorridorCode", 1)),
        premium_cease_age=int(data.get("PremiumCeaseAge", 121)),
        maturity_age=int(data.get("MaturityAge", 121)),
        snet_period=int(data.get("SafetyNetPeriod", 10)),
        lapse_value=data.get("LapseValue", "SV"),
        dynamic_banding=int(data.get("DynamicBanding", 3)),
        scr_code=data.get("SCR_Code", "Table"),
        loan_type=data.get("LoanType", "Arrears"),
        loan_charge_rate_guar=float(data.get("LoanChargeRateGuar", 0)),
        loan_charge_rate_curr=float(data.get("LoanChargeRateCurr", 0)),
        pref_loan_charge_rate_guar=float(data.get("PrefLoanChargeRateGuar", 0)),
        pref_loan_charge_rate_curr=float(data.get("PrefLoanChargeRateCurr", 0)),
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
