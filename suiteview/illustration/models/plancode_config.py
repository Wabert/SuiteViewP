"""Illustration plancode configuration: UL_Rates schema ``rates`` first, the plancode
table for product rules and fallbacks.

``load_plancode`` builds a ``PlancodeConfig`` from two sources:

* **Schema ``rates``** (``plan_facts``) supplies the plan facts and rates: product
  family, maturity and premium-cease ages, CINT key, GINT, the death-benefit discount,
  the four loan rates, the safety-net period by issue age, corridor factors by attained
  age and the shadow account's legacy plancode. The rate loaders read EPU, MFEE, the
  premium loads and the shadow account's scale ``S`` rates per policy.
* **``plancodes/plancode_table.json``** supplies the product rules the schema does not
  hold (SA_Basis, LoanType, banding, shadow-account behaviour, ...). A database-sourced
  field appears on a row only as the **fallback** for a plan whose database value is
  missing; using one is logged and listed in ``PlancodeConfig.table_fallbacks``.
  ``IllustrationMaturityAgeOverride`` / ``IllustrationPremiumCeaseAgeOverride`` are
  the one exception: an explicit illustration age that replaces ``PLAN_DEF``.

``tools/rates/plancode_db_coverage.py`` reports which rows still need fallbacks and
removes the ones the database has since filled.
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
    PRODUCT_FAMILY_UL,
    SA_BASIS_CURRENT,
    SA_BASIS_ORIGINAL,
)
from suiteview.illustration.models.plan_facts import PlanFacts, load_plan_facts

logger = logging.getLogger(__name__)

_PLANCODE_DIR = Path(__file__).resolve().parent.parent / "plancodes"
_PLANCODE_TABLE_PATH = _PLANCODE_DIR / "plancode_table.json"
_CONFIG_CACHE: Dict[str, PlancodeConfig] = {}
_TABLE_CACHE: Optional[Dict[str, dict]] = None

# Explicit illustration ages that replace PLAN_DEF (kept for Robert's review: mostly
# a table 100 against a PLAN_DEF 120/121).
MATURITY_OVERRIDE_KEY = "IllustrationMaturityAgeOverride"
PREMIUM_CEASE_OVERRIDE_KEY = "IllustrationPremiumCeaseAgeOverride"


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
    # PREMLOAD_EXS; ``premium_load_fallback`` is a flat load on every premium used
    # only when the plan has no PREMLOAD_PCT cells.
    premium_load_fallback: Optional[float] = None
    prem_flat_load: float = 0.0         # Flat $ per premium

    # Monthly fee: schema MFEE; ``mfee_fallback`` only when the plan has no MFEE cells.
    mfee_fallback: Optional[float] = None

    # AV charge
    poav_table: str = "0"               # Local PoAV table code "1"-"3"; "0" = none

    # Guaranteed interest and the death-benefit discount rate (DB_DISCOUNT, else GINT).
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

    # Corridor: schema PLAN CORR by attained age; ``corridor_code`` selects a
    # tRates_CORR.json set only for a plan without CORR (see core.corridor_rates).
    corridor_by_age: Optional[Mapping[int, float]] = None
    corridor_code: Optional[int] = 1

    # Maturity
    premium_cease_age: int = 121
    maturity_age: int = 121

    # Safety Net / Lapse. ``snet_by_issue_age`` is schema SNET_PERIOD; without it
    # ``snet_period`` (table fallback) applies to every issue age.
    snet_period: int = 10
    snet_by_issue_age: Optional[Mapping[int, int]] = None
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

    # Loans (schema LOAN_REG_CHG / LOAN_REG_CRD / LOAN_PREF_CHG / LOAN_PREF_CRD)
    loan_type: str = "Arrears"           # "Arrears" or "Advance"
    loan_charge_rate_guar: float = 0.0   # sRates_LNCRG — regular charged rate
    loan_charge_rate_curr: float = 0.0   # sRates_LNCRD — regular credited rate
    pref_loan_charge_rate_guar: float = 0.0  # sRates_PrefLNCRG — preferred charged rate
    pref_loan_charge_rate_curr: float = 0.0  # sRates_PrefLNCRD — preferred credited rate

    # Shadow Account (CCV). Its rates are schema scale S on the base plancode; the
    # ``*_fallback`` values apply only where the plan has no scale S rate of that kind
    # (``shadow_target_fallback`` 0 = no shadow target premium).
    shadow_plancode: str = ""            # legacy CCV plancode (PLAN_ATTR SHADOW_LEGACY_PLANCODE)
    shadow_availability: str = ""        # "Rider", "Inherent", or "" (none)
    shadow_cease_age: int = 121          # Age at which shadow account ceases
    shadow_sa_basis: int = 2             # 1 = OriginalSA, 2 = CurrentSA
    shadow_target_fallback: Optional[float] = None
    shadow_prem_load_fallback: Optional[float] = None
    shadow_epu_fallback: Optional[float] = None
    shadow_mfee: float = 0.0             # Flat monthly expense fee
    shadow_dbd_fallback: Optional[float] = None
    shadow_int_rate_fallback: Optional[float] = None
    shadow_loan_impact: str = "Reduce"   # "Reduce" or "None"
    shadow_late_payment_forgiveness: bool = False
    shadow_aps205_load_relief: bool = False
    shadow_target_rate_basis: str = "MTP"  # "MTP" or "CTP"

    # Plan-level fields taken from the plancode table because schema ``rates`` lacks
    # them, and the illustration age overrides in force (both logged at load).
    table_fallbacks: Tuple[str, ...] = field(default_factory=tuple)
    illustration_overrides: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.sa_basis not in (SA_BASIS_CURRENT, SA_BASIS_ORIGINAL):
            raise ValueError(f"{self.plancode}: invalid SA_Basis {self.sa_basis!r}")
        if self.scr_pct_of_surrender_target is not None and not all(
            0.0 <= pct <= 1.0 for pct in self.scr_pct_of_surrender_target
        ):
            raise ValueError(f"{self.plancode}: SCR_PctOfSurrenderTarget must be fractions 0-1")
        if self.shadow_target_rate_basis not in ("MTP", "CTP"):
            raise ValueError(
                f"{self.plancode}: invalid ShadowTargetRateBasis {self.shadow_target_rate_basis!r}"
            )
        if self.shadow_target_fallback not in (None, 0.0):
            raise ValueError(
                f"{self.plancode}: ShadowTarget fallback must be 0 (no shadow target premium)")

    @property
    def partial_surrender_charge(self) -> bool:
        """Whether decreases assess a partial surrender charge.

        Specified-amount decreases additionally honor the policy's Decrease
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

    def safety_net_years(self, issue_age: int) -> int:
        """Safety-net (no-lapse) period in policy years for a base issue age."""
        if self.snet_by_issue_age is not None:
            return int(self.snet_by_issue_age.get(int(issue_age), 0))
        return int(self.snet_period)


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


def _product_family(plancode: str, value) -> str:
    family = str(value or "").strip().upper()
    if family not in (PRODUCT_FAMILY_UL, PRODUCT_FAMILY_ISWL):
        raise ValueError(f"{plancode}: invalid ProductFamily {value!r}")
    return family


def _optional_float(plancode: str, data: dict, key: str) -> Optional[float]:
    if key not in data or data[key] is None:
        return None
    try:
        return float(data[key])
    except (TypeError, ValueError):
        raise ValueError(
            f"{plancode}: plancode-table {key} {data[key]!r} is not a number (a database "
            "fallback must be a flat value).") from None


class _PlanFactResolver:
    """Database value first; the table value only when the database lacks it."""

    def __init__(self, plancode: str, data: dict, facts: Optional[PlanFacts]):
        self.plancode = plancode
        self.data = data
        self.facts = facts
        self.fallbacks: list[str] = []
        self.overrides: list[str] = []

    def pick(self, db_value, key: str, convert=lambda v: v, *, required: bool = False, default=None):
        if db_value is not None:
            return db_value
        if key in self.data and self.data[key] is not None:
            self.fallbacks.append(key)
            return convert(self.data[key])
        if required:
            source = ("is not loaded in UL_Rates schema rates" if self.facts is None
                      else "has no such value in UL_Rates schema rates")
            raise ValueError(
                f"{self.plancode} {source} and the plancode table has no {key} fallback.")
        return default

    def age(self, attr: str, key: str, override_key: str) -> int:
        db_value = getattr(self.facts, attr) if self.facts is not None else None
        value = self.pick(db_value, key, int, required=True)
        if override_key in self.data:
            override = int(self.data[override_key])
            self.overrides.append(f"{key} {override} (PLAN_DEF {db_value})")
            return override
        return value


def _fact(facts: Optional[PlanFacts], name: str):
    return None if facts is None else getattr(facts, name)


def load_plancode(plancode: str) -> PlancodeConfig:
    """Load a plancode's configuration: schema ``rates`` first, then the table.

    Args:
        plancode: Product plan code (e.g., "1U143900").

    Returns:
        PlancodeConfig with plan facts from UL_Rates schema ``rates`` and product
        rules (and any fallbacks) from the plancode table.

    Raises:
        FileNotFoundError: If the plancode table does not exist.
        MissingPlancodeError: If the plancode has no row in the table.
        RatesError / ConnectionUnavailable: If schema ``rates`` cannot be read.
        ValueError: If a required fact is in neither source.
    """
    if plancode in _CONFIG_CACHE:
        return _CONFIG_CACHE[plancode]

    data = _load_plancode_table().get(plancode)
    if data is None:
        raise MissingPlancodeError(
            f"No plancode config found for {plancode} in {_PLANCODE_TABLE_PATH}"
        )
    facts = load_plan_facts(plancode)
    resolve = _PlanFactResolver(plancode, data, facts)
    family = (
        facts.engine_family if facts is not None
        else _product_family(plancode, resolve.pick(None, "ProductFamily", default=PRODUCT_FAMILY_UL))
    )
    gint = resolve.pick(_fact(facts, "gint"), "GINT", float, required=True)
    db_discount = _fact(facts, "db_discount")
    snet_by_age = _fact(facts, "snet_by_issue_age")
    corridor_by_age = _fact(facts, "corridor_by_age")
    db_cint = _fact(facts, "cint_key") or None
    db_shadow = _fact(facts, "shadow_legacy_plancode") or None

    config = PlancodeConfig(
        plancode=plancode,
        description=facts.description if facts is not None else "",
        product_family=family,
        can_illustrate=bool(data.get("CanIllustrate", True)),
        cint_key=resolve.pick(db_cint, "CINT_Key", str, default=""),
        int_calc_method=data.get("IntCalcMethod", "Declared"),
        interest_method=data.get("Interest_Method", data.get("InterestMethod", "ExactDays")),
        age_calc=data.get("AgeCalc", ""),
        premium_load_fallback=_optional_float(plancode, data, "PremiumLoad"),
        prem_flat_load=float(data.get("PremFlatLoad", 0)),
        mfee_fallback=_optional_float(plancode, data, "MFEE"),
        poav_table=str(data.get("PoAV_Table", "0")),
        dbd=db_discount if db_discount is not None else gint,
        gint=gint,
        table_rating_factor=float(data.get("TableRatingFactor", 0.25)),
        company_sub=str(data.get("CompanySub", "ANICO")).strip(),
        pwot_coi_basis=_int_or_default(data.get("PWoT_COI_Basis", 1), 1),
        withdrawal_fee=float(data.get("WithdrawalFee", 25)),
        md_holdback=float(data.get("MD_HoldBack", 0)),
        min_face_after_wd=float(data.get("MinFaceAfterWD", 25000)),
        corridor_by_age=corridor_by_age,
        corridor_code=(
            None if corridor_by_age is not None
            else resolve.pick(None, "CorridorCode", int, default=None)
        ),
        premium_cease_age=resolve.age("premium_cease_age", "PremiumCeaseAge", PREMIUM_CEASE_OVERRIDE_KEY),
        maturity_age=resolve.age("maturity_age", "MaturityAge", MATURITY_OVERRIDE_KEY),
        snet_period=(
            0 if snet_by_age is not None
            else resolve.pick(None, "SafetyNetPeriod", lambda v: _int_or_default(v, 0), default=0)
        ),
        snet_by_issue_age=snet_by_age,
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
        loan_charge_rate_guar=resolve.pick(
            _fact(facts, "loan_reg_chg"), "LoanChargeRate", float, required=True),
        loan_charge_rate_curr=resolve.pick(
            _fact(facts, "loan_reg_crd"), "LoanCollateralCreditRate", float, required=True),
        pref_loan_charge_rate_guar=resolve.pick(
            _fact(facts, "loan_pref_chg"), "PrefLoanChargeRate", float, default=0.0),
        pref_loan_charge_rate_curr=resolve.pick(
            _fact(facts, "loan_pref_crd"), "PrefLoanCollateralCreditRate", float, default=0.0),
        # Shadow Account (CCV)
        shadow_plancode=resolve.pick(db_shadow, "ShadowPlancode", str, default=""),
        shadow_availability=data.get("ShadowAvailability", ""),
        shadow_cease_age=int(data.get("ShadowCeaseAge", 121)),
        shadow_sa_basis=int(data.get("ShadowSABasis", 2)),
        shadow_target_fallback=_optional_float(plancode, data, "ShadowTarget"),
        shadow_prem_load_fallback=_optional_float(plancode, data, "ShadowPremLoadCode"),
        shadow_epu_fallback=_optional_float(plancode, data, "ShadowEPUCode"),
        shadow_mfee=float(data.get("ShadowMFEE", 0)),
        shadow_dbd_fallback=_optional_float(plancode, data, "ShadowDBDRate"),
        shadow_int_rate_fallback=_optional_float(plancode, data, "ShadowIntRateCode"),
        shadow_loan_impact=data.get("ShadowLoanImpact", "Reduce"),
        shadow_late_payment_forgiveness=bool(data.get("ShadowLatePaymentForgiveness", False)),
        shadow_aps205_load_relief=bool(data.get("ShadowAPS205LoadRelief", False)),
        shadow_target_rate_basis=str(data.get("ShadowTargetRateBasis", "MTP")).strip().upper() or "MTP",
        table_fallbacks=tuple(dict.fromkeys(resolve.fallbacks)),
        illustration_overrides=tuple(resolve.overrides),
    )
    if config.table_fallbacks:
        logger.warning(
            "%s: UL_Rates schema rates %s; using plancode-table fallback for %s",
            plancode, "does not load the plan" if facts is None else "lacks a value",
            ", ".join(config.table_fallbacks))
    if config.illustration_overrides:
        logger.info("%s: illustration age override %s", plancode, "; ".join(config.illustration_overrides))

    _CONFIG_CACHE[plancode] = config
    return config
