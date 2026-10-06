"""Illustration plancode configuration: plan facts from UL_Rates schema ``rates``,
product rules from the plancode table.

``load_plancode`` builds a ``PlancodeConfig`` from two sources:

* **Schema ``rates``** (``plan_facts``) is the only source of the plan facts and rates:
  product family, maturity and premium-cease ages, CINT key, GINT, the death-benefit
  discount, the four loan rates, the safety-net period by issue age, corridor factors
  by attained age and the shadow account's legacy plancode. The rate loaders read EPU,
  MFEE, the premium loads and the shadow account's scale ``S`` rates per policy. A rate
  the schema does not carry is "none" where that is the product rule (no preferred
  loan, no safety net, no GPT corridor, no fee or load) and an error where the plan
  cannot be illustrated without it (GINT, regular loan rates, ages, the plan itself).
* **``plancodes/plancode_table.json``** supplies the product rules the schema does not
  hold (SA_Basis, LoanType, banding, shadow-account behaviour, ...), including
  ``PremiumAndChargeCeaseAge``: the attained age from which a plan accepts no premium and
  takes no monthly deduction at all (COI, EPU, %-of-AV, MFEE, benefit or rider charge)
  while staying in force to the ``PLAN_DEF`` maturity (Robert Haessly, 10/3/2026 and
  10/5/2026). Its only plan-fact keys are ``IllustrationMaturityAgeOverride`` /
  ``IllustrationPremiumCeaseAgeOverride``: an explicit illustration maturity that
  replaces ``PLAN_DEF`` (premiums cease at that same maturity).

``tools/rates/plancode_db_coverage.py`` reports what the schema lacks for each row.
"""
from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple

from suiteview.illustration.constants import (
    LAPSE_BASIS_SURRENDER_VALUE,
    PRODUCT_FAMILY_ISWL,
    SA_BASIS_CURRENT,
    SA_BASIS_ORIGINAL,
)
from suiteview.illustration.models.plan_facts import load_plan_facts

logger = logging.getLogger(__name__)

_PLANCODE_DIR = Path(__file__).resolve().parent.parent / "plancodes"
_PLANCODE_TABLE_PATH = _PLANCODE_DIR / "plancode_table.json"
COI_RATE_BASIS_ANNUAL = "Annual"
COI_RATE_BASIS_MONTHLY = "Monthly"
_CONFIG_CACHE: Dict[str, PlancodeConfig] = {}
_TABLE_CACHE: Optional[Dict[str, dict]] = None

# Explicit illustration maturity that replaces PLAN_DEF (1U14L300 100, 1A130500 90,
# 1A130600 85: Robert Haessly, 10/3/2026); premiums may not cease before it.
MATURITY_OVERRIDE_KEY = "IllustrationMaturityAgeOverride"
PREMIUM_CEASE_OVERRIDE_KEY = "IllustrationPremiumCeaseAgeOverride"
# Product rule: premiums and every monthly deduction (the MFEE included) stop at this
# attained age; the policy stays in force to the PLAN_DEF maturity, its account value
# earning interest.
CHARGE_CEASE_KEY = "PremiumAndChargeCeaseAge"
# Plan facts that come only from schema ``rates``; the plancode table must not carry them.
DATABASE_KEYS = (
    "ProductFamily", "MaturityAge", "PremiumCeaseAge", "CINT_Key", "GINT", "DBD", "EPU_Code",
    "MFEE", "PremiumLoad", "LoanChargeRate", "LoanCollateralCreditRate", "PrefLoanChargeRate",
    "PrefLoanCollateralCreditRate", "SafetyNetPeriod", "CorridorCode", "ShadowPlancode",
    "ShadowTarget", "ShadowPremLoadCode", "ShadowEPUCode", "ShadowIntRateCode", "ShadowDBDRate",
)


@dataclass
class PlancodeConfig:
    """Product-level parameters: schema ``rates`` plan facts plus table product rules."""

    plancode: str = ""
    # PLAN_DEF.DESCRIPTION (display only).
    description: str = ""
    # "UL" (UL/IUL/SGUL engine family) or "ISWL". ISWL is a fixed-premium
    # advanced product: the premium load, policy fee and benefit/rider premiums
    # come out of the gross premium and only the monthly COI is deducted from
    # the account value. ISWL rates are read from UL_Rates schema ``rates``.
    product_family: str = "UL"
    # Illustration gating — enforced ONLY in distribution builds (see
    # suiteview.core.build_env.is_distribution_build). True (default) when the
    # key is absent so existing plancodes keep illustrating.
    can_illustrate: bool = True

    # Interest
    cint_key: str = ""
    int_calc_method: str = "Declared"   # "Declared", "IUL_Blend"
    interest_method: str = "ExactDays"  # "ExactDays", "MonthlyCompounding"
    age_calc: str = ""

    # Premium loading. The target/excess load rates are schema PREMLOAD_PCT /
    # PREMLOAD_EXS (none loaded = no percentage load).
    prem_flat_load: float = 0.0         # Flat $ per premium

    # AV charge
    poav_table: str = "0"               # Local PoAV table code "1"-"3"; "0" = none

    # Guaranteed interest and the death-benefit discount rate (DB_DISCOUNT, else GINT).
    dbd: float = 0.0
    gint: float = 0.0

    # Substandard
    table_rating_factor: float = 0.25

    # ISWL COI rate basis (CyberLife CKDRECUL DULCVCRU): "Annual" rates per $1,000 are
    # divided by 12 (calc rules 0/1); "Monthly" rates (calc rule 2, the UL convention,
    # e.g. B11SP400) are charged as stored.
    coi_rate_basis: str = COI_RATE_BASIS_ANNUAL

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

    # Corridor: schema PLAN CORR (7702 GPT corridor factor) by attained age. None =
    # the plan has no GPT corridor (CVAT plans, ISWL); see core.corridor_rates.
    corridor_by_age: Optional[Mapping[int, float]] = None

    # Maturity
    premium_cease_age: int = 121
    maturity_age: int = 121
    # Table PremiumAndChargeCeaseAge (None = charges run to maturity). From this attained
    # age no premium is accepted and no monthly deduction is taken: COI, EPU, %-of-AV,
    # benefit, rider charges and the monthly policy fee (MFEE) are all 0, although
    # UL_Rates loads a $5 MFEE to 120 on 1U143800/1U144500 and CyberLife deducts it
    # (Robert Haessly, 10/5/2026: a CyberLife defect). The account value earns interest
    # and the death benefit stays in force to ``maturity_age``. ``premium_cease_age``
    # equals it.
    charge_cease_age: Optional[int] = None

    # Safety Net / Lapse: schema SNET_PERIOD years by base issue age (an issue age
    # not in the mapping, or a plan without SNET_PERIOD, has no safety net).
    snet_by_issue_age: Mapping[int, int] = field(default_factory=dict)
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

    # Loans (schema LOAN_REG_CHG / LOAN_REG_CRD / LOAN_PREF_CHG / LOAN_PREF_CRD; a plan
    # without LOAN_PREF rows has no preferred loan option, so its preferred rates are 0)
    loan_type: str = "Arrears"           # "Arrears" or "Advance"
    loan_charge_rate_guar: float = 0.0   # sRates_LNCRG — regular charged rate
    loan_charge_rate_curr: float = 0.0   # sRates_LNCRD — regular credited rate
    pref_loan_charge_rate_guar: float = 0.0  # sRates_PrefLNCRG — preferred charged rate
    pref_loan_charge_rate_curr: float = 0.0  # sRates_PrefLNCRD — preferred credited rate

    # Shadow Account (CCV). Its rates are schema scale S on the base plancode (see
    # rate_loader._load_shadow_rates); the table holds only the behaviour flags.
    shadow_plancode: str = ""            # legacy CCV plancode (PLAN_ATTR SHADOW_LEGACY_PLANCODE)
    shadow_availability: str = ""        # "Rider", "Inherent", or "" (none)
    shadow_cease_age: int = 121          # Age at which shadow account ceases
    shadow_sa_basis: int = 2             # 1 = OriginalSA, 2 = CurrentSA
    shadow_mfee: float = 0.0             # Flat monthly expense fee
    shadow_loan_impact: str = "Reduce"   # "Reduce" or "None"
    shadow_late_payment_forgiveness: bool = False
    shadow_aps205_load_relief: bool = False
    shadow_target_rate_basis: str = "MTP"  # "MTP" or "CTP"

    # Illustration age overrides in force (logged at load).
    illustration_overrides: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.sa_basis not in (SA_BASIS_CURRENT, SA_BASIS_ORIGINAL):
            raise ValueError(f"{self.plancode}: invalid SA_Basis {self.sa_basis!r}")
        if self.coi_rate_basis not in (COI_RATE_BASIS_ANNUAL, COI_RATE_BASIS_MONTHLY):
            raise ValueError(f"{self.plancode}: invalid COI_RateBasis {self.coi_rate_basis!r}")
        if self.scr_pct_of_surrender_target is not None and not all(
            0.0 <= pct <= 1.0 for pct in self.scr_pct_of_surrender_target
        ):
            raise ValueError(f"{self.plancode}: SCR_PctOfSurrenderTarget must be fractions 0-1")
        if self.shadow_target_rate_basis not in ("MTP", "CTP"):
            raise ValueError(
                f"{self.plancode}: invalid ShadowTargetRateBasis {self.shadow_target_rate_basis!r}"
            )

    def charges_ceased(self, attained_age: int) -> bool:
        """Whether premiums and every monthly deduction have stopped (``charge_cease_age``)."""
        return self.charge_cease_age is not None and int(attained_age) >= self.charge_cease_age

    @property
    def partial_surrender_charge(self) -> bool:
        """Whether a withdrawal's face reduction assesses a partial surrender charge.

        Specified-amount decreases use ``face_decrease_surrender_charge`` (this rule,
        except FFL UL per-unit plans) and additionally honor the policy's Decrease
        Charge Rule (``IllustrationPolicyData.decrease_charge_allowed``).
        """
        return self.sa_basis == SA_BASIS_CURRENT

    @property
    def is_ffl(self) -> bool:
        """RERUN sblnFFL = (sCompanySub = "FFL")."""
        return self.company_sub == "FFL"

    @property
    def is_iswl(self) -> bool:
        """Interest Sensitive Whole Life (fixed premium, schema ``rates``)."""
        return self.product_family == PRODUCT_FAMILY_ISWL

    @property
    def ffl_per_unit_surrender_charge(self) -> bool:
        """FFL UL dollar-per-unit (rule 6) surrender charge: FFL, not ISWL and not a
        percent of the stored surrender target. The FFL plancodes are company 26."""
        return self.is_ffl and not self.is_iswl and self.scr_pct_of_surrender_target is None

    @property
    def surrender_charge_on_original_units(self) -> bool:
        """Whether the full surrender charge applies to each coverage's original
        (pre-decrease) units instead of its current units.

        OriginalSA plans, and FFL UL per-unit plans (Robert, 10/5/2026: "switch FFL to the
        original"; FFL takes no partial surrender charge on a decrease). FFL stays
        ``CurrentSA``: SA_Basis also drives the COI band, EPU, targets and withdrawals.
        """
        return self.sa_basis == SA_BASIS_ORIGINAL or self.ffl_per_unit_surrender_charge

    @property
    def face_decrease_surrender_charge(self) -> bool:
        """Whether a specified-amount decrease (elective, or the A->B level-DB reduction)
        assesses a partial surrender charge. FFL UL per-unit plans do not: their full
        charge stays on the original units. Withdrawals use ``partial_surrender_charge``."""
        return self.partial_surrender_charge and not self.ffl_per_unit_surrender_charge

    def safety_net_years(self, issue_age: int) -> int:
        """Safety-net (no-lapse) period in policy years for a base issue age."""
        return int(self.snet_by_issue_age.get(int(issue_age), 0))


def _load_plancode_table() -> Dict[str, dict]:
    global _TABLE_CACHE
    if _TABLE_CACHE is not None:
        return _TABLE_CACHE

    if not _PLANCODE_TABLE_PATH.exists():
        raise FileNotFoundError(
            f"No plancode table found: {_PLANCODE_TABLE_PATH}"
        )

    with open(_PLANCODE_TABLE_PATH, "r", encoding="utf-8") as f:
        table_data = json.load(f)

    rows = table_data.get("Plancodes", [])
    _TABLE_CACHE = {
        str(row.get("Plancode", "")).strip(): row
        for row in rows
        if str(row.get("Plancode", "")).strip()
    }
    return _TABLE_CACHE


def clear_plancode_cache() -> None:
    """Forget resolved configurations (e.g. after a rate load changed schema ``rates``)."""
    _CONFIG_CACHE.clear()


def plancode_table_path() -> Path:
    """Return the illustration plancode table JSON file path."""
    return _PLANCODE_TABLE_PATH


def plancode_table_rows() -> list[dict]:
    """Return every plancode table row, in file order, as independent copies.

    One row per plancode (the same rows :func:`load_plancode` reads), for
    read-only display; callers may mutate the copies without touching the
    engine's cache.
    """
    return copy.deepcopy(list(_load_plancode_table().values()))


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


def _required(plancode: str, value, label: str):
    if value is None:
        raise ValueError(
            f"{plancode} has no {label} in UL_Rates schema rates; the plan cannot be illustrated "
            "without it.")
    return value


def _age(plancode: str, data: dict, db_value, label: str, override_key: str,
         overrides: list[str]) -> int:
    value = int(_required(plancode, db_value, f"PLAN_DEF {label}"))
    if override_key in data:
        override = int(data[override_key])
        overrides.append(f"{label} {override} (PLAN_DEF {value})")
        return override
    return value


def _plan_ages(plancode: str, data: dict, facts, overrides: list[str]) -> tuple[int, int, Optional[int]]:
    """``(maturity_age, premium_cease_age, charge_cease_age)`` from PLAN_DEF and the table.

    An illustration override that has premiums cease before maturity is an error;
    premiums and charges ceasing before maturity is ``PremiumAndChargeCeaseAge``,
    which cannot be combined with an override.
    """
    maturity = _age(plancode, data, facts.maturity_age, "MaturityAge", MATURITY_OVERRIDE_KEY, overrides)
    cease = _age(plancode, data, facts.premium_cease_age, "PremiumCeaseAge",
                 PREMIUM_CEASE_OVERRIDE_KEY, overrides)
    if CHARGE_CEASE_KEY not in data:
        if overrides and cease < maturity:
            raise ValueError(
                f"{plancode}: illustration premium cease age {cease} is before maturity "
                f"{maturity}; premiums and charges ceasing before maturity is {CHARGE_CEASE_KEY}.")
        return maturity, cease, None
    if overrides:
        raise ValueError(
            f"{plancode}: {CHARGE_CEASE_KEY} cannot be combined with an illustration age override "
            f"({'; '.join(overrides)}); maturity comes from PLAN_DEF.")
    charge_cease = data[CHARGE_CEASE_KEY]
    whole_age = isinstance(charge_cease, int) and not isinstance(charge_cease, bool)
    if not whole_age or not 0 < charge_cease < maturity or charge_cease > cease:
        raise ValueError(
            f"{plancode}: {CHARGE_CEASE_KEY} {charge_cease!r} must be a whole age below the PLAN_DEF "
            f"maturity {maturity} and at or below the PLAN_DEF premium cease age {cease}.")
    return maturity, charge_cease, charge_cease


def load_plancode(plancode: str) -> PlancodeConfig:
    """Load a plancode's configuration: plan facts from schema ``rates``, product rules
    from the plancode table.

    Args:
        plancode: Product plan code (e.g., "1U143900").

    Raises:
        FileNotFoundError: If the plancode table does not exist.
        MissingPlancodeError: If the plancode has no table row or is not loaded in
            schema ``rates``.
        RatesError / ConnectionUnavailable: If schema ``rates`` cannot be read.
        ValueError: If the table carries a plan fact, or the schema lacks a required
            one (GINT, regular loan rates, ages).
    """
    if plancode in _CONFIG_CACHE:
        return _CONFIG_CACHE[plancode]

    data = _load_plancode_table().get(plancode)
    if data is None:
        raise MissingPlancodeError(
            f"No plancode config found for {plancode} in {_PLANCODE_TABLE_PATH}"
        )
    stale = [key for key in DATABASE_KEYS if key in data]
    if stale:
        raise ValueError(
            f"{plancode}: plancode_table.json carries {', '.join(stale)}, which come only from "
            "UL_Rates schema rates. Remove them (tools/rates/plancode_db_coverage.py --write).")
    facts = load_plan_facts(plancode)
    if facts is None:
        raise MissingPlancodeError(
            f"Plancode {plancode} is not loaded in UL_Rates schema rates (PLAN_DEF).")
    gint = _required(plancode, facts.gint, "PLAN GINT")
    overrides: list[str] = []
    maturity_age, premium_cease_age, charge_cease_age = _plan_ages(plancode, data, facts, overrides)

    config = PlancodeConfig(
        plancode=plancode,
        description=facts.description,
        product_family=facts.engine_family,
        can_illustrate=bool(data.get("CanIllustrate", True)),
        cint_key=facts.cint_key,
        int_calc_method=data.get("IntCalcMethod", "Declared"),
        interest_method=data.get("Interest_Method", data.get("InterestMethod", "ExactDays")),
        age_calc=data.get("AgeCalc", ""),
        prem_flat_load=float(data.get("PremFlatLoad", 0)),
        poav_table=str(data.get("PoAV_Table", "0")),
        dbd=facts.dbd if facts.dbd is not None else gint,
        gint=gint,
        table_rating_factor=float(data.get("TableRatingFactor", 0.25)),
        coi_rate_basis=str(data.get("COI_RateBasis", COI_RATE_BASIS_ANNUAL)),
        company_sub=str(data.get("CompanySub", "ANICO")).strip(),
        pwot_coi_basis=_int_or_default(data.get("PWoT_COI_Basis", 1), 1),
        withdrawal_fee=float(data.get("WithdrawalFee", 25)),
        md_holdback=float(data.get("MD_HoldBack", 0)),
        min_face_after_wd=float(data.get("MinFaceAfterWD", 25000)),
        corridor_by_age=facts.corridor_by_age,
        premium_cease_age=premium_cease_age,
        maturity_age=maturity_age,
        charge_cease_age=charge_cease_age,
        snet_by_issue_age=dict(facts.snet_by_issue_age or {}),
        lapse_value=data.get(
            "LapseTarget",
            data.get("LapseValue", LAPSE_BASIS_SURRENDER_VALUE),
        ),
        dynamic_banding=int(data.get("DynamicBanding", 3)),
        rachet_banding=bool(data.get("Rachet_Banding", False)),
        band_table2_issue_date=_date_or_none(data.get("BandTable2IssueDate")),
        sa_basis=data["SA_Basis"],
        scr_pct_of_surrender_target=(
            tuple(float(pct) for pct in data["SCR_PctOfSurrenderTarget"])
            if data.get("SCR_PctOfSurrenderTarget") is not None else None
        ),
        loan_type=data.get("LoanType", "Arrears"),
        loan_charge_rate_guar=_required(plancode, facts.loan_reg_chg, "LOAN_REG_CHG"),
        loan_charge_rate_curr=_required(plancode, facts.loan_reg_crd, "LOAN_REG_CRD"),
        pref_loan_charge_rate_guar=facts.loan_pref_chg or 0.0,
        pref_loan_charge_rate_curr=facts.loan_pref_crd or 0.0,
        # Shadow Account (CCV): behaviour flags from the table, rates from scale S.
        shadow_plancode=facts.shadow_legacy_plancode,
        shadow_availability=data.get("ShadowAvailability", ""),
        shadow_cease_age=int(data.get("ShadowCeaseAge", 121)),
        shadow_sa_basis=int(data.get("ShadowSABasis", 2)),
        shadow_mfee=float(data.get("ShadowMFEE", 0)),
        shadow_loan_impact=data.get("ShadowLoanImpact", "Reduce"),
        shadow_late_payment_forgiveness=bool(data.get("ShadowLatePaymentForgiveness", False)),
        shadow_aps205_load_relief=bool(data.get("ShadowAPS205LoadRelief", False)),
        shadow_target_rate_basis=str(data.get("ShadowTargetRateBasis", "MTP")).strip().upper() or "MTP",
        illustration_overrides=tuple(overrides),
    )
    if config.illustration_overrides:
        logger.info("%s: illustration age override %s", plancode, "; ".join(config.illustration_overrides))

    _CONFIG_CACHE[plancode] = config
    return config
