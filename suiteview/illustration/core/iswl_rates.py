"""ISWL projection rates and fixed-premium arithmetic from UL_Rates schema ``rates``.

Interest Sensitive Whole Life (``PlancodeConfig.product_family == "ISWL"``, CyberLife
advanced product line ``I``) is projected with the UL account-value mechanics: the
account value earns declared interest, and the monthly COI is deducted on the net
amount at risk. What differs is the premium. CyberLife bills a fixed premium whose
premium load, policy fee and benefit/rider premiums come out of the gross premium;
only the net goes into the account. No expense charge, MFEE or benefit/rider charge
is deducted from the account value.

Every rate comes from the four-structure tables in schema ``rates``
(``RatesSchemaRepository``); the legacy dbo ``Select_RATE_*`` views are never read.
Cell selection reuses PolView's schema lookup (``resolve_plan``, ``choose_cell``,
``rate_at``): exact cell first, then unisex, class ``0``/``*``, band ``0`` and state
``**``.

Rules reproduced from live CyberLife records (``tools/rerun/verify_iswl_rollforward.py``):

* **COI.** The IAF prints an *annual* rate per $1,000 (``COI``, scale C current with
  calendar-dated schedule windows, G guaranteed). The monthly charge is
  ``NAR x rate / 12 / 1000`` with ``NAR = DB / (1 + GINT) ** (1/12) - AV``.
* **Net premium (premium load rule 4).** CyberDoc D10 (CKDRECUL ``DULPLRUL``) rule 4
  "is unique for fixed premium advanced products. It deducts a percentage of the net
  annual premium for the basic coverage from the total premium to determine the load."
  The amount credited per payment is
  ``round(units x round((1 - PREMLOAD_PCT) x premium per unit, 2) x months_between_payments / 12, 2)``,
  where the premium per unit is the coverage's stored ``ANN_PRM_UNT_AMT`` (schema ``PREM``
  is the cross-check; a record rated at another age keeps its stored rate). It does not
  depend on the billing mode's factors, the policy fee or benefits.
* **Guaranteed cash value.** The surrender value is never below the tabular guaranteed
  cash value (schema ``CV`` per unit, interpolated monthly), and a premium-paying ISWL
  does not lapse while it is positive (CyberDoc B10 "Interest Sensitive Life Plans" and
  its sample illustration, p. 402).
* **Surrender charge.** ``PLAN_DEF.SCR_RULES`` names CyberLife's full-surrender rules
  (CyberDoc D10 p. 177). Rule 6 plans carry a dollar-per-unit ``SCR`` schedule. Rule 5
  (``"50"``) charges a CKULTB04 percentage (schema ``SCR_PCT``) of the account value in
  excess of a free amount; for tables I2 and I3 the free percentage and flat charge
  are zero, so the full-surrender charge is ``SCR_PCT(policy year) x AV``. CyberLife
  ``FH_FIXED`` SF history agrees: year-19 surrenders were charged exactly 6.00% of the
  fund value and year-20 surrenders nothing.
* **Gross premium.** The billed premium (``LH_BAS_POL.POL_PRM_AMT``) is the anchor. When
  a supplemental benefit or rider coverage ceases later, its modal premium,
  ``round(units x stored annual premium per unit x mode factor, 2)``, drops out of the
  bill. The stored per-unit premiums are CyberLife's own billing amounts
  (``BNF_ANN_PPU_AMT`` / ``ANN_PRM_UNT_AMT``); the mode factor is schema ``PLAN_MODEFACT``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from dateutil.relativedelta import relativedelta

from suiteview.core.modal_premium import (
    POLICY_FEE_ADD_MODES,
    VERIFIED_RULES,
    ModalPremiumError,
    billing_mode,
    factor_family,
)
from suiteview.core.rates_schema import CellAssignment, PlanDef
from suiteview.illustration.constants import MONTHS_PER_YEAR, PRODUCT_FAMILY_ISWL
from suiteview.illustration.core.rate_loader import IllustrationRates, RateLookupError
from suiteview.illustration.core.schema_reader import SchemaReader, open_schema_reader
from suiteview.illustration.models.plancode_config import COI_RATE_BASIS_MONTHLY, PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.polview.models.schema_rates import (
    RateKey,
    band_for_amount,
    choose_cell,
    rate_at,
    rates_sex,
    resolve_plan,
)

CENT = Decimal("0.01")
# Premium load rules verified for ISWL: rule 4 alone (CKDRECUL DULPLRUL "400").
VERIFIED_PREMLOAD_RULES = "400"
# Rule-5 surrender charge tables whose CKULTB04 rows have FREE_PCT 0 and CHARGE_AMOUNT 0
# (CKULTB04 print 08/12/2026): the charge is the percentage of the whole account value.
# 58 matches 54 company-01 FH_FIXED full surrenders to the cent; I5 rests on the print
# (allow code P, like I2/I3).
VERIFIED_PCT_OF_AV_SCR_TABLES = ("I2", "I3", "I5", "58")
# Company 26 grades the rule-5 percentage monthly between policy years (44 FH_FIXED
# surrenders on C9/58), which is not modelled.
GRADED_RULE_5_COMPANIES = ("26",)
CURRENT_INTEREST_RATE_TYPES = ("CINT_NEW", "CINT_ROLL")

def round_cents(value) -> float:
    """Half-up rounding to cents, as CyberLife rounds premium arithmetic."""
    return float(Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class ISWLItemPremium:
    """A benefit or rider whose premium is part of the bill until it ceases."""

    label: str
    cease_date: date
    annual_premium: float
    modal_premium: float


@dataclass
class ISWLRateBasis:
    """Fixed-premium facts the ISWL premium step needs, all resolved at load time."""

    plan_company: str
    plan_note: str
    units: float
    base_premium_per_unit: float             # schema PREM (G) at the base issue age
    load_pct: List                           # 1-indexed by policy year (PREMLOAD_PCT)
    net_premium_per_unit: List               # 1-indexed: round((1 - load) x PREM, 2)
    billing_frequency: int                   # months between payments
    mode: str                                # A/S/Q/M
    bill_form_family: str                    # DIR / PAC
    prem_factor: float
    fee_factor: float
    policy_fee_annual: float                 # 0 when the fee is not added for the mode
    billed_premium: float                    # POL_PRM_AMT anchor at ``anchor_date``
    anchor_date: Optional[date]
    ceasing_items: List[ISWLItemPremium] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    schema_premium_per_unit: Optional[float] = None   # schema PREM, the cross-check
    issue_date: Optional[date] = None
    # Tabular guaranteed cash value per unit by duration (index 0 = issue).
    cash_value_per_unit: List = field(default_factory=list)
    # Rule-5 full-surrender charge as a fraction of the account value, 1-indexed by
    # policy year (schema SCR_PCT). Empty when the charge is per unit (rates.scr).
    surrender_charge_pct: List = field(default_factory=list)
    # Single-premium policy (premium pay status 42): no premium is due, so there is
    # no premium load, mode factor or billed premium; a requested premium raises.
    single_premium: bool = False

    @property
    def surrender_charge_is_pct_of_av(self) -> bool:
        return bool(self.surrender_charge_pct)

    def surrender_charge_rate(self, policy_year: int) -> float:
        """Rule-5 fraction of the account value charged on a full surrender."""
        if not self.surrender_charge_pct:
            return 0.0
        return _year_value(self.surrender_charge_pct, policy_year, "surrender charge percentage")

    def guaranteed_cash_value(self, month_date: Optional[date]) -> float:
        """Guaranteed cash value on a monthliversary: units x the tabular value
        interpolated monthly, ``(BOY x months remaining + EOY x months elapsed) / 12``."""
        values = self.cash_value_per_unit
        if not values or month_date is None or self.issue_date is None:
            return 0.0
        delta = relativedelta(month_date, self.issue_date)
        months = max(delta.years * 12 + delta.months, 0)
        duration, elapsed = divmod(months, 12)
        last = len(values) - 1
        boy = float(values[min(duration, last)])
        eoy = float(values[min(duration + 1, last)])
        return self.units * (boy * (12 - elapsed) + eoy * elapsed) / 12.0

    @property
    def fee_modal(self) -> float:
        return round_cents(Decimal(str(self.policy_fee_annual)) * Decimal(str(self.fee_factor)))

    def net_per_payment(self, rate_year: int) -> float:
        """Premium credited to the account value for one billed payment (rule 4)."""
        per_unit = _year_value(self.net_premium_per_unit, rate_year, "net premium per unit")
        return round_cents(
            Decimal(str(self.units)) * Decimal(str(per_unit))
            * Decimal(self.billing_frequency) / Decimal(MONTHS_PER_YEAR))

    def billed_per_payment(self, month_date: Optional[date]) -> float:
        """Gross billed premium per payment on ``month_date``."""
        dropped = sum(
            item.modal_premium for item in self.ceasing_items
            if month_date is not None and item.cease_date <= month_date
        )
        return round_cents(Decimal(str(self.billed_premium)) - Decimal(str(dropped)))

    def benefit_premium_per_payment(self, month_date: Optional[date]) -> float:
        """Benefit/rider premiums still in the bill: billed less base premium and fee."""
        base_modal = round_cents(
            Decimal(str(self.units)) * Decimal(str(self.base_premium_per_unit))
            * Decimal(str(self.prem_factor)))
        return round_cents(
            Decimal(str(self.billed_per_payment(month_date))) - Decimal(str(base_modal))
            - Decimal(str(self.fee_modal)))


@dataclass(frozen=True)
class ISWLPremiumSplit:
    """One month's ISWL premium: whole billed payments, gross, net and the load parts."""

    payments: int
    gross_premium: float
    net_premium: float
    premium_load: float
    policy_fee: float
    benefit_premium: float


def split_iswl_premium(
    basis: ISWLRateBasis, requested: float, reference_premium: float,
    rate_year: int, month_date: Optional[date],
) -> ISWLPremiumSplit:
    """Split a requested ISWL premium into whole billed payments.

    ``requested`` is a number of billed premiums of ``reference_premium`` (the
    policy's billed premium, ``IllustrationPolicyData.modal_premium``). Each payment
    is billed at ``basis.billed_per_payment(month_date)``, so the bill drops when a
    benefit or rider ceases. A fixed-premium ISWL cannot accept a partial or excess
    amount, so any other amount raises.
    """
    if requested <= 0.005:
        return ISWLPremiumSplit(0, 0.0, 0.0, 0.0, 0.0, 0.0)
    if basis.single_premium:
        raise ValueError(
            f"Single-premium ISWL (premium pay status 42): a premium of {requested:,.2f} cannot "
            "be illustrated. No further premium is due and additional premiums are not supported.")
    if reference_premium <= 0:
        raise ValueError("ISWL premiums need the policy's billed premium, which is zero.")
    payments = round(requested / reference_premium)
    if payments < 1 or abs(requested - payments * reference_premium) > 0.005:
        raise ValueError(
            f"ISWL is a fixed-premium plan: a premium of {requested:,.2f} is not a whole number "
            f"of billed premiums ({reference_premium:,.2f}). Additional or partial ISWL premiums "
            "are not supported.")
    billed = basis.billed_per_payment(month_date)
    net = basis.net_per_payment(rate_year)
    fee = basis.fee_modal
    benefit = basis.benefit_premium_per_payment(month_date)
    return ISWLPremiumSplit(
        payments=payments,
        gross_premium=round_cents(Decimal(str(billed)) * payments),
        net_premium=round_cents(Decimal(str(net)) * payments),
        premium_load=round_cents((Decimal(str(billed)) - Decimal(str(net)) - Decimal(str(fee))
                                  - Decimal(str(benefit))) * payments),
        policy_fee=round_cents(Decimal(str(fee)) * payments),
        benefit_premium=round_cents(Decimal(str(benefit)) * payments),
    )


# -- plan and cell resolution ------------------------------------------------------

def _plan(reader: SchemaReader, plancode: str, company_code: str) -> Tuple[PlanDef, str]:
    plan, note = resolve_plan(reader.plan_defs(plancode), company_code)
    if plan is None:
        detail = f" ({note})" if note else ""
        raise RateLookupError(f"ISWL plancode {plancode} is not loaded in UL_Rates schema rates{detail}.")
    if plan.product_family != PRODUCT_FAMILY_ISWL:
        raise RateLookupError(
            f"Plancode {plancode} is {plan.product_family or 'unclassified'} in schema rates "
            "PLAN_DEF, not ISWL.")
    return plan, note


def _fact(plan: PlanDef, name: str):
    return dict(plan.facts).get(name)


def _validate_plan_facts(plan: PlanDef, config: PlancodeConfig, single_premium: bool = False) -> None:
    rules = str(_fact(plan, "PREMLOAD_RULES") or "").strip()
    # A single-premium policy pays no further premium, so its load rules never apply.
    if rules != VERIFIED_PREMLOAD_RULES and not single_premium:
        raise RateLookupError(
            f"{plan.plancode} premium load rules {rules or '(blank)'} are not the verified ISWL "
            f"rule {VERIFIED_PREMLOAD_RULES} (rule 4 only).")
    maturity = _fact(plan, "MATURITY_AGE")
    cease = _fact(plan, "PREMIUM_CEASE_AGE")
    if maturity is None or cease is None:
        raise RateLookupError(f"{plan.plancode} PLAN_DEF has no MATURITY_AGE/PREMIUM_CEASE_AGE.")
    if int(cease) != int(maturity):
        raise RateLookupError(
            f"{plan.plancode} premiums cease at age {cease}, before maturity {maturity}; "
            "limited-pay ISWL is not supported.")
    if (config.maturity_age, config.premium_cease_age) != (int(maturity), int(cease)):
        raise RateLookupError(
            f"{plan.plancode} has an illustration age override (maturity {config.maturity_age}, "
            f"premium cease {config.premium_cease_age}; PLAN_DEF {maturity}/{cease}); the ISWL "
            "guaranteed cash values run to the PLAN_DEF maturity, so the override is not supported.")
    vpu = _fact(plan, "VALUE_PER_UNIT")
    if vpu is not None and Decimal(str(vpu)) != Decimal("1000"):
        raise RateLookupError(f"{plan.plancode} VALUE_PER_UNIT is {vpu}, not 1000.")


def _rate_key(reader: SchemaReader, plan: PlanDef, policy: IllustrationPolicyData, segment) -> RateKey:
    spec, note = band_for_amount(
        reader.plan_bands(plan.company, plan.plancode), policy.issue_date, segment.face_amount)
    if spec is None:
        raise RateLookupError(f"{plan.plancode} has no rate band for the base coverage: {note}.")
    sex = rates_sex(segment.rate_sex or policy.rate_sex)
    rate_class = str(segment.rate_class or policy.rate_class or "").strip().upper()
    return RateKey(sex, rate_class, spec.band, str(policy.issue_state or "").strip().upper())


def _cell(rows: Sequence[CellAssignment], rate_type: str, key: RateKey, plancode: str,
          notes: List[str]) -> CellAssignment:
    assignment, cell_notes = choose_cell(rows, rate_type, key)
    if assignment is None:
        detail = "; ".join(cell_notes) or "no cell is loaded"
        raise RateLookupError(f"{plancode} has no {rate_type} rate in schema rates ({detail}).")
    if cell_notes:
        notes.append(f"{rate_type}: {'; '.join(cell_notes)}")
    return assignment


def _schedule(
    reader: SchemaReader, assignment: CellAssignment, scale: str, *, issue_age: int,
    issue_date: date, years: int, calendar: bool, label: str, zero_tail: bool = False,
) -> List:
    """1-indexed schedule by policy year. Calendar-dated rates use the window in
    effect on each policy year's start; issue-dated rates the one on the issue date.
    ``zero_tail`` lets a schedule that has run off to zero (surrender charges) end
    early; its remaining years are zero."""
    windows = sorted((w for w in reader.schedule_windows(assignment.schedule_id) if w.scale == scale),
                     key=lambda w: w.effective_from)
    if not windows:
        raise RateLookupError(f"{label} has no scale {scale} schedule in schema rates.")
    set_ids = tuple(sorted({w.rate_set_id for w in windows}))
    sets = reader.rate_sets(set_ids)
    values = reader.rate_values(set_ids, issue_age)
    schedule: List = [None]
    for year in range(1, years + 1):
        on = issue_date + relativedelta(years=year - 1) if calendar else issue_date
        window = next((w for w in windows if w.covers(on)), None)
        if window is None:
            raise RateLookupError(f"{label} scale {scale}: no schedule window covers {on:%m/%d/%Y}.")
        info = sets.get(window.rate_set_id)
        if info is None:
            raise RateLookupError(f"{label} scale {scale}: rate set {window.rate_set_id} is missing.")
        rate = rate_at(info.grain, values.get(window.rate_set_id, {}), issue_age, year)
        if rate is None and zero_tail and len(schedule) > 1 and schedule[-1] == 0.0:
            schedule.append(0.0)
            continue
        if rate is None:
            raise RateLookupError(f"{label} scale {scale} has no rate for policy year {year} "
                                  f"(issue age {issue_age}).")
        schedule.append(float(rate))
    return schedule


def _single(reader: SchemaReader, assignment: CellAssignment, scale: str, *, issue_age: int,
            issue_date: date, label: str) -> float:
    return _schedule(reader, assignment, scale, issue_age=issue_age, issue_date=issue_date,
                     years=1, calendar=False, label=label)[1]


def _plan_rate(reader: SchemaReader, plan: PlanDef, rate_type: str, state: str) -> Optional[tuple]:
    rows = [a for a in reader.plan_assignments(plan.company, plan.plancode)
            if a.rate_type == rate_type and a.scale == "G" and a.state in (state, "**")]
    if not rows:
        return None
    chosen = min(rows, key=lambda a: a.state != state)
    ids = (chosen.rate_set_id,)
    info = reader.rate_sets(ids).get(chosen.rate_set_id)
    return (info.grain if info else "", reader.rate_values(ids, None).get(chosen.rate_set_id, {}))


def _gint_schedule(reader, plan, state: str, years: int) -> List:
    found = _plan_rate(reader, plan, "GINT", state)
    if found is None:
        raise RateLookupError(f"{plan.plancode} has no GINT in schema rates.")
    grain, values = found
    schedule: List = [None]
    for year in range(1, years + 1):
        rate = rate_at(grain, values, 0, year)
        if rate is None:
            raise RateLookupError(f"{plan.plancode} GINT has no rate for policy year {year}.")
        schedule.append(float(rate))
    return schedule


def _mode_factor_row(reader, plan: PlanDef, family: str, mode: str):
    rows = [m for m in reader.modal_factors(plan.company, plan.plancode)
            if m.mode == mode and not m.market_org]
    exact = [m for m in rows if m.billing_form == family]
    rows = exact or [m for m in rows if m.billing_form == "*"]   # "*" = every bill form
    if len(rows) != 1:
        raise RateLookupError(
            f"{plan.plancode} has {len(rows)} PLAN_MODEFACT rows for {family} mode {mode}; "
            "the ISWL premium needs exactly one.")
    row = rows[0]
    problems = [
        f"{name}={value!r}" for name, value in (
            ("POLICY_FEE_RULE", row.policy_fee_rule), ("MULTIPLY_ORDER", row.multiply_order),
            ("RATING_ORDER", row.rating_order), ("ROUNDING_RULE", row.rounding_rule),
        ) if str(value or "").strip() != VERIFIED_RULES[name]
    ]
    if Decimal(str(row.collection_fee or 0)) != 0:
        problems.append(f"COLLECTION_FEE={row.collection_fee}")
    if str(row.policy_fee_add or "").strip() not in POLICY_FEE_ADD_MODES:
        problems.append(f"POLICY_FEE_ADD={row.policy_fee_add!r}")
    if problems:
        raise RateLookupError(f"{plan.plancode} unverified mode premium rules: " + ", ".join(problems))
    return row


def _ceasing_items(policy: IllustrationPolicyData, prem_factor: float) -> List[ISWLItemPremium]:
    anchor = policy.valuation_date
    items: List[ISWLItemPremium] = []
    factor = Decimal(str(prem_factor))
    for ben in policy.benefits:
        if not ben.is_active or ben.cease_date is None or (anchor and ben.cease_date <= anchor):
            continue
        per_unit = ben.coi_rate or 0.0
        if per_unit <= 0:
            continue
        rating = ben.rating_factor if ben.rating_factor and ben.rating_factor > 0 else 1.0
        annual = Decimal(str(ben.units)) * Decimal(str(per_unit)) * Decimal(str(rating))
        items.append(ISWLItemPremium(
            f"Benefit {ben.benefit_type}{ben.benefit_subtype}", ben.cease_date,
            float(annual), round_cents(annual * factor)))
    for rider in policy.riders:
        cease = rider.maturity_date
        if not rider.is_active or cease is None or (anchor and cease <= anchor):
            continue
        per_unit = rider.premium_rate or 0.0
        if per_unit <= 0:
            continue
        annual = Decimal(str(rider.units)) * Decimal(str(per_unit))
        items.append(ISWLItemPremium(
            f"Rider {rider.plancode}", cease, float(annual), round_cents(annual * factor)))
    return items


def _surrender_charges(reader, plan: PlanDef, base_rows, key: RateKey, years: int,
                       notes: List[str], common: dict, company: str = "") -> Tuple[List, List]:
    """Surrender charges as ``(per-unit schedule, fraction-of-AV schedule)`` by policy
    year; the unused one is all zero / empty.

    A plan whose ``PLAN_DEF`` names no surrender charge rules (``SCR_RULES``
    blank/zero) has none. Rule 5 alone on a verified CKULTB04 table reads the schema
    ``SCR_PCT`` percentages of the account value; every other rule set requires the
    dollar-per-unit ``SCR`` schedule.
    """
    rules = str(_fact(plan, "SCR_RULES") or "").strip()
    no_per_unit = [None] + [0.0] * years
    if not rules.strip("0"):
        notes.append(f"{plan.plancode} PLAN_DEF SCR_RULES {rules or '(blank)'}: no surrender charge.")
        return no_per_unit, []
    if "5" not in rules:
        return _schedule(reader, _cell(base_rows, "SCR", key, plan.plancode, notes), "G",
                         years=years, calendar=False, label=f"{plan.plancode} SCR", zero_tail=True,
                         **common), []
    return no_per_unit, _rule_5_percentages(reader, plan, rules, base_rows, key, years, notes, common,
                                            company)


def _rule_5_percentages(reader, plan: PlanDef, rules: str, base_rows, key: RateKey, years: int,
                        notes: List[str], common: dict, company: str = "") -> List:
    """Rule-5 ``SCR_PCT`` schedule (fractions of the account value) by policy year."""
    if rules.rstrip("0") != "5":
        raise RateLookupError(
            f"{plan.plancode} PLAN_DEF SCR_RULES {rules}: rule 5 combined with another "
            "surrender charge rule is not supported.")
    if str(company or "").strip() in GRADED_RULE_5_COMPANIES:
        raise RateLookupError(
            f"{plan.plancode} rule 5 surrender charges for company {company}: CyberLife grades the "
            "CKULTB04 percentage monthly between policy years, which is not modelled.")
    table = str(_fact(plan, "SCR_TABLE") or "").strip()
    if table not in VERIFIED_PCT_OF_AV_SCR_TABLES:
        raise RateLookupError(
            f"{plan.plancode} rule 5 surrender charges use CKULTB04 table {table or '(blank)'}, "
            "whose free-withdrawal percentage and flat charge are not verified "
            f"(verified: {', '.join(VERIFIED_PCT_OF_AV_SCR_TABLES)}).")
    if any(a.rate_type == "SCR" for a in base_rows):
        raise RateLookupError(
            f"{plan.plancode} is surrender charge rule 5 but schema rates loads both dollar SCR "
            "and SCR_PCT; which one CyberLife charges is ambiguous.")
    label = f"{plan.plancode} SCR_PCT"
    schedule = _schedule(reader, _cell(base_rows, "SCR_PCT", key, plan.plancode, notes), "G",
                         years=years, calendar=False, label=label, zero_tail=True, **common)
    if any(not 0.0 <= pct <= 1.0 for pct in schedule[1:]):
        raise RateLookupError(f"{label} is not a fraction between 0 and 1.")
    notes.append(f"Surrender charge: rule 5, SCR_PCT x account value (CKULTB04 table {table}).")
    return schedule


def _cash_value_schedule(reader, plan: PlanDef, base_rows, key: RateKey, segment, years: int,
                         notes: List[str]) -> List[float]:
    """Tabular guaranteed cash value per unit by duration 0..maturity (schema ``CV``).

    ``CV`` is keyed by sub-series; the plan's ``PLAN_SUBSERIES`` maps the rate sex and
    class to it. The endowment value at the maturity duration (the value per unit)
    is used when the table stops at the last policy year.
    """
    subseries = reader.plan_subseries(plan.company, plan.plancode)
    assignment, cell_notes = choose_cell(base_rows, "CV", key, subseries)
    if assignment is None:
        detail = "; ".join(cell_notes) or "no cell is loaded"
        raise RateLookupError(f"{plan.plancode} has no guaranteed cash values (CV) in schema rates ({detail}).")
    windows = [w for w in reader.schedule_windows(assignment.schedule_id)
               if w.scale == "G" and w.covers(segment.issue_date)]
    if len(windows) != 1:
        raise RateLookupError(f"{plan.plancode} CV has {len(windows)} schedules on the issue date.")
    set_id = windows[0].rate_set_id
    values = reader.rate_values((set_id,), segment.issue_age).get(set_id, {})
    schedule: List[float] = []
    for duration in range(0, years + 1):
        rate = values.get((segment.issue_age, duration))
        if rate is None and duration == years:
            schedule.append(float(segment.vpu or 1000.0))
            notes.append(f"CV at maturity (duration {years}) is the endowment value per unit.")
            break
        if rate is None:
            raise RateLookupError(f"{plan.plancode} CV has no value for duration {duration} "
                                  f"(issue age {segment.issue_age}).")
        schedule.append(float(rate))
    return schedule


def _year_value(schedule: Sequence, year: int, label: str) -> float:
    if not schedule or len(schedule) < 2:
        raise ValueError(f"ISWL {label} schedule is empty.")
    index = min(max(int(year), 1), len(schedule) - 1)
    return float(schedule[index])


# -- public loaders ----------------------------------------------------------------

def load_iswl_rates(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    coi_scale: int = 1,
    expense_scale: int = 1,
    *,
    repo=None,
) -> IllustrationRates:
    """All projection rates for an ISWL policy from schema ``rates``.

    ``coi_scale`` 1/0 selects the current (C) or guaranteed (G) COI; ``expense_scale``
    the current or guaranteed premium load. ``repo`` replaces the live
    ``RatesSchemaRepository`` (tests).
    """
    if not config.is_iswl:
        raise ValueError(f"{config.plancode} is not an ISWL plancode.")
    base_segments = [s for s in policy.segments if s.is_base]
    if len(base_segments) != 1:
        raise RateLookupError(
            f"ISWL illustrations need exactly one base coverage phase; this policy has "
            f"{len(base_segments)}.")
    segment = base_segments[0]
    if policy.issue_date is None or segment.issue_date is None:
        raise RateLookupError("ISWL rates need the base coverage issue date.")
    with open_schema_reader(repo) as reader:
        return _load(reader, policy, config, segment, coi_scale, expense_scale)


def _load(reader: SchemaReader, policy, config, segment, coi_scale: int, expense_scale: int):
    plan, plan_note = _plan(reader, policy.plancode, policy.company_code)
    if not policy.is_cvat and config.corridor_by_age is None:
        # Without CORR the death benefit would silently drop its 7702/pre-TEFRA corridor
        # (F12S2N00 N8620667: AV 106,332.58 on a 44,449 face; CyberLife MD 28.89, 0 without).
        raise RateLookupError(
            f"{plan.plancode} has no CORR corridor factors in UL_Rates schema rates; the "
            f"{policy.def_of_life_ins or 'pre-TEFRA'} death benefit corridor cannot be applied.")
    single_premium = policy.is_single_premium
    _validate_plan_facts(plan, config, single_premium)
    notes: List[str] = [f"Plan: {plan_note}"] if plan_note else []
    key = _rate_key(reader, plan, policy, segment)
    base_rows = [a for a in reader.cell_assignments(plan.company, plan.plancode) if not a.benefit]
    years = config.maturity_age - segment.issue_age
    common = {"issue_age": segment.issue_age, "issue_date": segment.issue_date}

    coi_label = f"{plan.plancode} COI"
    annual_coi = _schedule(
        reader, _cell(base_rows, "COI", key, plan.plancode, notes), "C" if coi_scale == 1 else "G",
        years=years, calendar=True, label=coi_label, **common)
    if config.coi_rate_basis == COI_RATE_BASIS_MONTHLY:
        # CKDRECUL DULCVCRU 2: the IAF COI is already a monthly rate per $1,000.
        coi = [None] + list(annual_coi[1:])
        notes.append(f"{plan.plancode} COI rates are monthly (COI_RateBasis Monthly, DULCVCRU 2).")
    else:
        coi = [None] + [rate / MONTHS_PER_YEAR for rate in annual_coi[1:]]
    scr, scr_pct = _surrender_charges(reader, plan, base_rows, key, years, notes, common,
                                      policy.company_code)
    cash_values = _cash_value_schedule(reader, plan, base_rows, key, segment, years, notes)
    state = key.state
    gint = _gint_schedule(reader, plan, state, years)
    if single_premium:
        notes.append(
            f"Single premium (premium pay status 42): no premium is due, so the premium load "
            f"(PLAN_DEF PREMLOAD_RULES {_fact(plan, 'PREMLOAD_RULES') or 'blank'}), PREM and "
            "PLAN_MODEFACT are not used.")
        basis = _single_premium_basis(plan, plan_note, policy, segment, notes, cash_values, scr_pct)
    else:
        basis = _premium_paying_basis(
            reader, plan, plan_note, policy, segment, base_rows, key, years, expense_scale,
            notes, common, cash_values, scr_pct)
    return IllustrationRates(
        coi=coi,
        segment_coi={segment.coverage_phase: coi},
        scr=scr,
        segment_scr={segment.coverage_phase: scr},
        gint=gint,
        coi_scale=coi_scale,
        expense_scale=expense_scale,
        iswl=basis,
    )


def _single_premium_basis(plan, plan_note, policy, segment, notes, cash_values, scr_pct) -> ISWLRateBasis:
    """Rate basis of a single-premium ISWL: no premium is billed again."""
    return ISWLRateBasis(
        plan_company=plan.company,
        plan_note=plan_note,
        units=float(segment.units),
        base_premium_per_unit=0.0,
        load_pct=[None, 0.0],
        net_premium_per_unit=[None, 0.0],
        billing_frequency=int(policy.billing_frequency or MONTHS_PER_YEAR),
        mode="",
        bill_form_family="",
        prem_factor=0.0,
        fee_factor=0.0,
        policy_fee_annual=0.0,
        billed_premium=0.0,
        anchor_date=policy.valuation_date,
        notes=notes,
        issue_date=segment.issue_date,
        cash_value_per_unit=cash_values,
        surrender_charge_pct=scr_pct,
        single_premium=True,
    )


def _premium_paying_basis(reader, plan, plan_note, policy, segment, base_rows, key, years,
                          expense_scale, notes, common, cash_values, scr_pct) -> ISWLRateBasis:
    """Rate basis of a premium-paying ISWL (premium load rule 4)."""
    load_pct = _schedule(
        reader, _cell(base_rows, "PREMLOAD_PCT", key, plan.plancode, notes),
        "C" if expense_scale == 1 else "G", years=years, calendar=True,
        label=f"{plan.plancode} PREMLOAD_PCT", **common)
    prem = _single(reader, _cell(base_rows, "PREM", key, plan.plancode, notes), "G",
                   label=f"{plan.plancode} PREM", **common)
    stored = segment.premium_rate
    if stored and abs(stored - prem) > 0.005:
        notes.append(
            f"Net premium uses the policy's stored premium per unit {stored:.2f}; the schema PREM "
            f"at issue age {segment.issue_age} is {prem:.2f}.")
    base_rate = stored or prem

    try:
        family = factor_family(policy.bill_form_code)
        mode = billing_mode(policy.billing_frequency)
    except ModalPremiumError as exc:
        raise RateLookupError(f"ISWL premium: {exc}") from exc
    row = _mode_factor_row(reader, plan, family, mode)
    prem_factor = 1.0 if mode == "A" else float(row.prem_factor)
    fee_factor = 1.0 if mode == "A" else float(row.fee_factor)
    fee_added = mode in POLICY_FEE_ADD_MODES[str(row.policy_fee_add).strip()]
    net_per_unit = [None] + [
        round_cents((Decimal(1) - Decimal(str(pct))) * Decimal(str(base_rate))) for pct in load_pct[1:]
    ]
    return ISWLRateBasis(
        plan_company=plan.company,
        plan_note=plan_note,
        units=float(segment.units),
        base_premium_per_unit=base_rate,
        load_pct=load_pct,
        net_premium_per_unit=net_per_unit,
        billing_frequency=int(policy.billing_frequency),
        mode=mode,
        bill_form_family=family,
        prem_factor=prem_factor,
        fee_factor=fee_factor,
        policy_fee_annual=float(row.policy_fee_annual) if fee_added else 0.0,
        billed_premium=float(policy.modal_premium or 0.0),
        anchor_date=policy.valuation_date,
        ceasing_items=_ceasing_items(policy, prem_factor),
        notes=notes,
        schema_premium_per_unit=prem,
        issue_date=segment.issue_date,
        cash_value_per_unit=cash_values,
        surrender_charge_pct=scr_pct,
    )


def iswl_recorded_credited_rate(bucket_rates: Sequence[Tuple[float, float]], guaranteed_rate: float) -> float:
    """The rate CyberLife credits the policy's current fixed-fund buckets.

    ``bucket_rates`` holds ``(value, annual percent)`` for each current, unimpaired
    bucket. Buckets crediting different rates give their value-weighted average.
    """
    rates = [(float(value), float(pct) / 100.0) for value, pct in bucket_rates if pct is not None]
    if not rates:
        raise RateLookupError(
            "ISWL current interest: schema rates has no declared rate for this plan and the "
            "policy has no current fund bucket rate.")
    distinct = {rate for _value, rate in rates}
    if len(distinct) == 1:
        rate = distinct.pop()
    else:
        total = sum(value for value, _rate in rates)
        if total <= 0:
            raise RateLookupError("ISWL fund buckets credit different rates and hold no value to weight them.")
        rate = sum(value * rate for value, rate in rates) / total
    return max(rate, float(guaranteed_rate))


def iswl_current_credited_rate(
    company_code: str, plancode: str, as_of: date, guaranteed_rate: float, *, repo=None,
) -> Optional[float]:
    """Current declared ISWL crediting rate on ``as_of``: the latest current-scale
    new-money (``CINT_NEW``) and rollover (``CINT_ROLL``) fixed-fund rates, floored at
    the guaranteed rate. ``None`` when the plan has no fixed-fund rates loaded.

    The engine credits one rate to the whole account value, so a new-money rate that
    differs from the rollover rate on ``as_of`` raises instead of being blended.
    """
    with open_schema_reader(repo) as reader:
        plan, _note = _plan(reader, plancode, company_code)
        funds = [a for a in reader.fund_assignments(plan.company, plancode) if a.fund_type != "INDEX"]
        if not funds:
            return None
        rates = reader.fund_rates(tuple(sorted({a.fund_key for a in funds})))
    latest: Dict[str, Tuple[date, float]] = {}
    for rate in rates:
        if rate.scale != "C" or rate.rate_type not in CURRENT_INTEREST_RATE_TYPES or rate.rate_start > as_of:
            continue
        seen = latest.get(rate.rate_type)
        if seen is None or rate.rate_start > seen[0]:
            latest[rate.rate_type] = (rate.rate_start, float(rate.rate))
    if not latest:
        raise RateLookupError(
            f"{plancode} has no current-scale CINT_NEW/CINT_ROLL rate on or before {as_of:%m/%d/%Y}.")
    declared = {value for _start, value in latest.values()}
    if len(declared) > 1:
        detail = ", ".join(f"{name} {value:.4%}" for name, (_s, value) in sorted(latest.items()))
        raise RateLookupError(
            f"{plancode} new-money and rollover rates differ on {as_of:%m/%d/%Y} ({detail}); "
            "ISWL interest buckets are not modelled.")
    return max(declared.pop(), float(guaranteed_rate))
