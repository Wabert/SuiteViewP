"""Plan-level illustration facts from UL_Rates schema ``rates``.

``load_plancode`` (``plancode_config``) takes every fact below from schema ``rates``
only; the plancode table holds product rules, not these facts.

======================  ==============================================================
PlancodeConfig field    Schema source
======================  ==============================================================
product_family          ``PLAN_DEF.PRODUCT_FAMILY`` (UL and IUL -> engine ``UL``; ISWL)
maturity_age            ``PLAN_DEF.MATURITY_AGE``
premium_cease_age       ``PLAN_DEF.PREMIUM_CEASE_AGE``
cint_key                ``PLAN_DEF.CIRF_KEY``; a multi-fund IUL key (``FIXLNIUL,IUL``)
                        names the fixed account in ``PLAN_ATTR FUND_KEYS``
                        (``FIXLNIUL,IULFIX09,IULINDEX09`` -> ``IULFIX09``)
gint                    PLAN ``GINT`` (one rate for every duration)
dbd                     ``DB_DISCOUNT`` on the guaranteed (base) scale, else GINT
loan rates              PLAN ``LOAN_REG_CHG`` / ``LOAN_REG_CRD`` / ``LOAN_PREF_CHG`` /
                        ``LOAN_PREF_CRD`` (no preferred rows = no preferred loan)
safety net period       PLAN ``SNET_PERIOD`` by issue age (none = no safety net)
corridor factors        PLAN ``CORR`` by attained age, grain AA (none = no GPT corridor)
shadow_plancode         ``PLAN_ATTR SHADOW_LEGACY_PLANCODE``
======================  ==============================================================

Cell rates (EPU, MFEE, premium loads and the shadow account's scale ``S`` rates) are
read per policy by the rate loaders, not here.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Iterable, Mapping, Optional

from suiteview.core.rates_errors import RatesError
from suiteview.core.rates_schema import PlanDef, RatesSchemaRepository

# Schema PLAN_DEF.PRODUCT_FAMILY -> engine product family (PlancodeConfig.product_family).
ENGINE_FAMILIES = {"UL": "UL", "IUL": "UL", "ISWL": "ISWL"}
ALL_STATES = "**"
SHADOW_LEGACY_ATTR = "SHADOW_LEGACY_PLANCODE"
FUND_KEYS_ATTR = "FUND_KEYS"
_PLAN_TYPES = (
    "GINT", "DB_DISCOUNT", "LOAN_REG_CHG", "LOAN_REG_CRD", "LOAN_PREF_CHG", "LOAN_PREF_CRD",
    "SNET_PERIOD", "CORR",
)
# DB_DISCOUNT on these scales is the base death-benefit discount; scale S is the
# shadow account's (read by the rate loader).
_BASE_DISCOUNT_SCALES = ("C", "G")


@dataclass(frozen=True)
class PlanFacts:
    """One plancode's plan-level facts; ``None`` = the schema does not carry it."""

    plancode: str
    company: str
    schema_family: str
    description: str
    maturity_age: Optional[int]
    premium_cease_age: Optional[int]
    cirf_key: str
    fund_keys: str
    shadow_legacy_plancode: str
    gint: Optional[float]
    db_discount: Optional[float]
    loan_reg_chg: Optional[float]
    loan_reg_crd: Optional[float]
    loan_pref_chg: Optional[float]
    loan_pref_crd: Optional[float]
    snet_by_issue_age: Optional[Mapping[int, int]]
    corridor_by_age: Optional[Mapping[int, float]]

    @property
    def engine_family(self) -> str:
        family = ENGINE_FAMILIES.get(self.schema_family.upper())
        if family is None:
            raise RatesError(
                f"{self.plancode} PLAN_DEF PRODUCT_FAMILY {self.schema_family or '(blank)'} is not "
                f"an illustration product family ({', '.join(sorted(ENGINE_FAMILIES))}).")
        return family

    @property
    def cint_key(self) -> str:
        return cint_key_from(self.plancode, self.cirf_key, self.fund_keys)

    @property
    def dbd(self) -> Optional[float]:
        """Death-benefit discount rate: ``DB_DISCOUNT`` when loaded, else GINT."""
        return self.db_discount if self.db_discount is not None else self.gint


def cint_key_from(plancode: str, cirf_key: str, fund_keys: str) -> str:
    """The declared-rate fund key of a plan.

    A single ``CIRF_KEY`` is the key. CyberLife stores a multi-fund IUL plan's key as
    ``<loan fund>,<prefix>`` (``FIXLNIUL,IUL``, truncated); its fixed account is the one
    ``PLAN_ATTR FUND_KEYS`` entry, other than the loan fund, that starts with the prefix
    and is a fixed (``FIX``) fund.
    """
    parts = [p.strip() for p in str(cirf_key or "").split(",") if p.strip()]
    if len(parts) <= 1:
        return parts[0] if parts else ""
    loan_fund, prefix = parts[0], parts[1]
    funds = [f.strip() for f in str(fund_keys or "").split(",") if f.strip()]
    fixed = [f for f in funds if f != loan_fund and f.startswith(prefix) and "FIX" in f]
    if len(fixed) != 1:
        raise RatesError(
            f"{plancode} CIRF_KEY {cirf_key!r}: PLAN_ATTR FUND_KEYS {fund_keys or '(none)'} has "
            f"{len(fixed)} fixed-account funds starting {prefix!r}; exactly one is needed.")
    return fixed[0]


def _fact(plan: PlanDef, name: str):
    return dict(plan.facts).get(name)


def _int_fact(plan: PlanDef, name: str) -> Optional[int]:
    value = _fact(plan, name)
    return None if value is None or str(value).strip() == "" else int(value)


def _plan_rows(assignments, rate_type: str, scales: Iterable[str] = ("G",)):
    rows = [a for a in assignments if a.rate_type == rate_type and a.scale in tuple(scales)]
    statewide = [a for a in rows if a.state == ALL_STATES]
    if statewide or not rows:
        return statewide
    if len({a.rate_set_id for a in rows}) > 1:
        raise RatesError(
            f"{rate_type} is loaded only by state with different rate sets; the illustration "
            "needs one plan-wide rate.")
    return rows[:1]


def _one_value(plancode: str, label: str, values: Iterable[Decimal]) -> Optional[float]:
    distinct = {Decimal(str(v)) for v in values if v is not None}
    if not distinct:
        return None
    if len(distinct) > 1:
        shown = ", ".join(str(v.normalize()) for v in sorted(distinct))
        raise RatesError(f"{plancode} {label} has several rates ({shown}); the illustration uses one.")
    return float(distinct.pop())


class _Reader:
    def __init__(self, repo: RatesSchemaRepository, plan: PlanDef):
        self.repo = repo
        self.plan = plan
        self.assignments = repo.plan_assignments(plan.company, plan.plancode)
        set_ids = sorted({a.rate_set_id for a in self.assignments if a.rate_type in _PLAN_TYPES})
        self.values = repo.all_rate_values(set_ids)

    def values_of(self, rate_type: str, scales=("G",)) -> Optional[Dict[tuple, Decimal]]:
        rows = _plan_rows(self.assignments, rate_type, scales)
        if not rows:
            return None
        values = self.values.get(rows[0].rate_set_id) or {}
        return values or None

    def scalar(self, rate_type: str) -> Optional[float]:
        values = self.values_of(rate_type)
        return None if values is None else _one_value(self.plan.plancode, rate_type, values.values())

    def by_issue_age(self, rate_type: str) -> Optional[Dict[int, int]]:
        values = self.values_of(rate_type)
        if values is None:
            return None
        return {age: int(rate) for (age, _duration), rate in sorted(values.items())}

    def by_attained_age(self, rate_type: str) -> Optional[Dict[int, float]]:
        values = self.values_of(rate_type)
        if values is None:
            return None
        return {age: float(rate) for (age, _duration), rate in sorted(values.items())}

    def base_db_discount(self) -> Optional[float]:
        plan = self.plan
        found = []
        plan_values = self.values_of("DB_DISCOUNT", _BASE_DISCOUNT_SCALES)
        if plan_values:
            found.extend(plan_values.values())
        cells = [a for a in self.repo.cell_assignments_of_type(plan.company, plan.plancode, "DB_DISCOUNT")
                 if not a.benefit]
        windows = [w for w in self.repo.schedule_windows(sorted({a.schedule_id for a in cells}))
                   if w.scale in _BASE_DISCOUNT_SCALES]
        cell_values = self.repo.all_rate_values(sorted({w.rate_set_id for w in windows}))
        for values in cell_values.values():
            found.extend(values.values())
        return _one_value(plan.plancode, "DB_DISCOUNT (current/guaranteed scale)", found)


def _single_plan(plancode: str, plans) -> Optional[PlanDef]:
    if not plans:
        return None
    if len(plans) > 1:
        raise RatesError(
            f"Plancode {plancode} is loaded under companies "
            f"{', '.join(sorted(p.company for p in plans))} in UL_Rates schema rates; the "
            "illustration plan facts need one.")
    return plans[0]


def read_plan_facts(repo: RatesSchemaRepository, plancode: str) -> Optional[PlanFacts]:
    """The plancode's plan facts, or ``None`` when schema ``rates`` does not load it."""
    plancode = (plancode or "").strip().upper()
    plan = _single_plan(plancode, repo.plan_defs(plancode))
    if plan is None:
        return None
    attrs = {a.attr: a.value for a in repo.plan_attrs(plan.company, plan.plancode)}
    reader = _Reader(repo, plan)
    gint_values = reader.values_of("GINT")
    return PlanFacts(
        plancode=plan.plancode,
        company=plan.company,
        schema_family=plan.product_family,
        description=plan.description,
        maturity_age=_int_fact(plan, "MATURITY_AGE"),
        premium_cease_age=_int_fact(plan, "PREMIUM_CEASE_AGE"),
        cirf_key=str(_fact(plan, "CIRF_KEY") or "").strip(),
        fund_keys=attrs.get(FUND_KEYS_ATTR, "").strip(),
        shadow_legacy_plancode=attrs.get(SHADOW_LEGACY_ATTR, "").strip().upper(),
        gint=None if gint_values is None else _one_value(plan.plancode, "GINT", gint_values.values()),
        db_discount=reader.base_db_discount(),
        loan_reg_chg=reader.scalar("LOAN_REG_CHG"),
        loan_reg_crd=reader.scalar("LOAN_REG_CRD"),
        loan_pref_chg=reader.scalar("LOAN_PREF_CHG"),
        loan_pref_crd=reader.scalar("LOAN_PREF_CRD"),
        snet_by_issue_age=reader.by_issue_age("SNET_PERIOD"),
        corridor_by_age=reader.by_attained_age("CORR"),
    )


def load_plan_facts(plancode: str) -> Optional[PlanFacts]:
    """``read_plan_facts`` over a live UL_Rates connection (raises when unreachable)."""
    with RatesSchemaRepository() as repo:
        return read_plan_facts(repo, plancode)


def corridor_factor_at(by_age: Mapping[int, float], attained_age: int) -> float:
    """The corridor factor at an attained age; past either end of the table, the end value."""
    if attained_age in by_age:
        return float(by_age[attained_age])
    ages = sorted(by_age)
    return float(by_age[ages[0]] if attained_age < ages[0] else by_age[ages[-1]])
