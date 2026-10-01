"""Joint survivor (second-to-die) UL COI - VP/MS JSURVCOI, company 26 (FFL) path.

CyberLife does not charge an IAF COI on the FFL "Estate Advantage" / "Estate
Protector" joint plans (N91*, B11*, N71*). It calls the VP/MS model JSURVCOI
(CKVPT050, key FFLJNT) every policy year, blending both insureds' single-life
rates by the independent-lives last-survivor formula (not Frasier).

The single-life inputs are UL_Rates schema ``rates`` rate type ``JS_Q`` (annual
probability per $1, already rounded to 5 decimals as the model uses it) and the
plan rules are ``rates.PLAN_ATTR`` ``JS_*`` attributes. Rate lookups live in
:class:`suiteview.core.joint_survivor_rates.JointSurvivorRateSource`; this module is the pure calculation, ported
from ``Cyberlife_Rates\\Rates_Database\\scripts\\joint_survivor_coi.py``
(verified against 231 in-force CKPR phases, 9/28/2026).

Every intermediate is rounded exactly like the model; see :func:`vround`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

MONTHLY_EXPONENT = 0.083333333      # the model's exact exponent, not 1/12
COI_CAP = 83.3333333                # monthly COI cap per $1,000
EXACT_TOLERANCE = 5e-7              # half a unit in the 5th decimal


class JointSurvivorError(ValueError):
    """Joint survivor inputs or plan rules are missing or inconsistent."""


def vround(value: float, places: int) -> float:
    """VP/MS F_Round: half away from zero on the number as text (15 significant digits).

    The model rounds ``ROUND(n*10^d & "")``; converting to 15 significant digits
    first reproduces more in-force rates than Python's shortest repr (215 vs 212).
    """
    if value == 0:
        return 0.0
    quantum = Decimal(1).scaleb(-places)
    return float(Decimal(format(value, ".15g")).quantize(quantum, rounding=ROUND_HALF_UP))


def ymd(value: date) -> int:
    return value.year * 10000 + value.month * 100 + value.day


def anniversary_year(date_ymd: int, issue_ymd: int) -> int:
    """f_anniversary: policy years from issue to the anniversary on or after a date."""
    return math.ceil(0.0001 * (date_ymd - issue_ymd))


@dataclass(frozen=True)
class Insured:
    """One life: rate sex (M/F), rate class and issue age at the coverage phase."""

    sex: str
    rate_class: str
    issue_age: int


@dataclass(frozen=True)
class Rating:
    """One extra-life rating (LH_SST_XTR_CRG) in the model's terms."""

    person: str                 # "00" primary, "01" joint
    type_code: str              # "0" percent, "1"/"3" table, "2"/"4" flat
    table_code: str = ""
    percent: float = 0.0        # e.g. 150 for 150%
    flat_per_1000: float = 0.0  # annual flat extra per $1,000
    effective_year: int = 0     # anniversary_year(effective date)
    cease_year: int = 999       # anniversary_year(cease date)

    def active(self, year: int) -> bool:
        return self.effective_year < year <= self.cease_year

    @property
    def description(self) -> str:
        years = f"yrs {self.effective_year + 1}-{self.cease_year}"
        if self.type_code in ("1", "3"):
            return f"Table {self.table_code} ({years})"
        if self.type_code in ("2", "4"):
            return f"Flat {self.flat_per_1000:.2f}/1000 ({years})"
        if self.type_code == "0":
            return f"{self.percent:g}% ({years})"
        return f"Type {self.type_code} ({years})"


def _yes_no(attrs: Mapping[str, str], name: str) -> bool:
    value = (attrs.get(name) or "").strip().upper()
    if value not in ("Y", "N"):
        raise JointSurvivorError(f"PLAN_ATTR {name} must be Y or N, found {attrs.get(name)!r}")
    return value == "Y"


@dataclass(frozen=True)
class JointRules:
    """Plan rules of the company-26 JSURVCOI path (rates.PLAN_ATTR JS_*)."""

    table_pct: Mapping[str, float]
    cap_curr_at_guar: bool = False    # JS_CAP_CURR_AT_GUAR (B11)
    zero_guar_at_q1: bool = False     # JS_ZERO_GUAR_AT_Q1 (B11/N71)
    zero_curr_at_q0: bool = True      # JS_ZERO_CURR_AT_Q0
    flat_factor: float = 0.012        # JS_FLAT_FACTOR

    @classmethod
    def from_plan_attributes(cls, attrs: Mapping[str, str]) -> "JointRules":
        """Build the rules from PLAN_ATTR; every rule must be stated explicitly."""
        if (attrs.get("LIVES") or "").strip() != "3":
            raise JointSurvivorError("PLAN_ATTR LIVES is not 3: not a joint survivor plan")
        table_text = (attrs.get("JS_TABLE_PCT") or "").strip()
        if not table_text:
            raise JointSurvivorError("PLAN_ATTR JS_TABLE_PCT is missing")
        table_pct: Dict[str, float] = {}
        for part in table_text.split(";"):
            code, sep, value = part.partition("=")
            if not sep:
                raise JointSurvivorError(f"PLAN_ATTR JS_TABLE_PCT entry {part!r} is not CODE=multiplier")
            table_pct[code.strip()] = float(value)
        flat = (attrs.get("JS_FLAT_FACTOR") or "").strip()
        if not flat:
            raise JointSurvivorError("PLAN_ATTR JS_FLAT_FACTOR is missing")
        return cls(
            table_pct=table_pct,
            cap_curr_at_guar=_yes_no(attrs, "JS_CAP_CURR_AT_GUAR"),
            zero_guar_at_q1=_yes_no(attrs, "JS_ZERO_GUAR_AT_Q1"),
            zero_curr_at_q0=_yes_no(attrs, "JS_ZERO_CURR_AT_Q0"),
            flat_factor=float(flat),
        )


def rated_q(base: float, primary_base: float, person: str, year: int,
            ratings: Sequence[Rating], rules: JointRules) -> float:
    """f_QX / f_QY: one life's single-life rate with its active extras."""
    active = [r for r in ratings if r.person == person and r.active(year)]
    pct = 0.0
    for r in active:
        if r.type_code == "0":
            pct += 0.01 * r.percent - 1
        elif r.type_code in ("1", "3"):
            code = r.table_code.strip()
            if code not in rules.table_pct:
                raise JointSurvivorError(f"Table rating {code!r} is not in PLAN_ATTR JS_TABLE_PCT")
            pct += rules.table_pct[code] - 1
    flat = sum(rules.flat_factor * r.flat_per_1000 for r in active if r.type_code in ("2", "4"))
    # Model quirk: flats on either life are tested against the PRIMARY's base rate.
    return min(1.0, base * (1 + pct) + (flat if primary_base > 0 else 0.0))


# Extra types that multiply a life's base rate (percent or table); flats (2/4) add.
MULTIPLE_RATING_TYPES = ("0", "1", "3")


def active_table_code(ratings: Sequence[Rating], person: str, year: int) -> str:
    """The table rating ``person`` in policy ``year``: "0" when standard, the
    JS_TABLE_PCT code of a single active table, "" for a percent rating or
    several multiple ratings at once."""
    active = [r for r in ratings
              if r.person == person and r.type_code in MULTIPLE_RATING_TYPES and r.active(year)]
    if not active:
        return "0"
    if len(active) == 1 and active[0].type_code in ("1", "3"):
        return active[0].table_code
    return ""


def ratings_with_table(ratings: Sequence[Rating], person: str, table_code: str,
                       from_year: int) -> List[Rating]:
    """``person``'s percent/table ratings replaced by ``table_code`` after policy year ``from_year``.

    Ratings in force cease at ``from_year``; ones starting later are dropped;
    flat extras and the other life's ratings are kept. ``table_code`` "0" is
    standard (no new rating).
    """
    out: List[Rating] = []
    for rating in ratings:
        if rating.person == person and rating.type_code in MULTIPLE_RATING_TYPES:
            if rating.effective_year >= from_year:
                continue
            if rating.cease_year > from_year:
                rating = replace(rating, cease_year=from_year)
        out.append(rating)
    if table_code != "0":
        out.append(Rating(person, "1", table_code, effective_year=from_year, cease_year=999))
    return out


@dataclass(frozen=True)
class JointYear:
    """One policy year of the joint calculation, before the plan rules."""

    year: int
    qx: float           # primary rated annual q
    qy: float           # joint rated annual q
    tpx: float
    tpy: float
    tpxy: float
    tqxy: float
    monthly_p: float
    coi: float          # monthly per $1,000, capped


def joint_years(base_x: Sequence[float], base_y: Sequence[float],
                ratings: Sequence[Rating], rules: JointRules) -> List[JointYear]:
    """Independent-lives last survivor for years 1..n, every step rounded to 9 decimals."""
    if len(base_x) != len(base_y):
        raise JointSurvivorError("Both insureds need the same number of single-life rates")
    tpx = tpy = tpxy_prev = 1.0
    out = []
    for t, (sx, sy) in enumerate(zip(base_x, base_y), start=1):
        qx = rated_q(sx, sx, "00", t, ratings, rules)
        qy = rated_q(sy, sx, "01", t, ratings, rules)
        tpx = 0.0 if qx == 0 else vround(tpx * (1 - qx), 9)
        tpy = 0.0 if qy == 0 else vround(tpy * (1 - qy), 9)
        tpxy = vround(tpx + tpy - tpx * tpy, 9)
        tqxy = vround(1 - (0.0 if tpxy_prev == 0 else tpxy / tpxy_prev), 9)
        monthly_p = vround((1 - tqxy) ** MONTHLY_EXPONENT, 9)
        coi = min(vround(1000 * (1 - monthly_p), 5), COI_CAP)
        out.append(JointYear(t, qx, qy, tpx, tpy, tpxy, tqxy, monthly_p, coi))
        tpxy_prev = tpxy
    return out


@dataclass(frozen=True)
class JointSchedule:
    """Blended monthly joint COI per $1,000 by policy year, current and guaranteed."""

    current: Tuple[float, ...]
    guaranteed: Tuple[float, ...]
    current_years: Tuple[JointYear, ...]
    guaranteed_years: Tuple[JointYear, ...]


def joint_schedule(base: Mapping[str, Tuple[Sequence[float], Sequence[float]]],
                   ratings: Sequence[Rating], rules: JointRules) -> JointSchedule:
    """Current and guaranteed joint COI from both insureds' unrated JS_Q.

    ``base`` maps scale "C"/"G" to (primary rates, joint rates) for years 1..n.
    The guaranteed series is always needed: B11 caps current at guaranteed.
    """
    guar = joint_years(*base["G"], ratings, rules)
    curr = joint_years(*base["C"], ratings, rules)
    if len(guar) != len(curr):
        raise JointSurvivorError("Current and guaranteed JS_Q cover different horizons")
    g_out: List[float] = []
    c_out: List[float] = []
    for i, (g, c) in enumerate(zip(guar, curr)):
        qx_g_prev = guar[i - 1].qx if i else 0.0
        g_rate = 0.0 if rules.zero_guar_at_q1 and g.qx == 1 and qx_g_prev == 1 else vround(g.coi, 5)
        g_out.append(g_rate)
        if rules.zero_curr_at_q0 and c.qx == 0:
            c_out.append(0.0)
        elif rules.cap_curr_at_guar:
            c_out.append(min(g_rate, vround(c.coi, 5)))
        else:
            c_out.append(vround(c.coi, 5))
    return JointSchedule(tuple(c_out), tuple(g_out), tuple(curr), tuple(guar))


def joint_monthly_coi(base: Mapping[str, Tuple[Sequence[float], Sequence[float]]], charge: str,
                      ratings: Sequence[Rating], rules: JointRules) -> List[float]:
    """Monthly joint COI per $1,000 for years 1..n on scale "C" or "G"."""
    schedule = joint_schedule(base, ratings, rules)
    if charge == "C":
        return list(schedule.current)
    if charge == "G":
        return list(schedule.guaranteed)
    raise JointSurvivorError(f"Charge type must be C or G, not {charge!r}")


def compare_stored_rate(schedule: Sequence[float], year: int,
                        stored: Optional[float]) -> Tuple[str, str]:
    """Compare CyberLife's stored current rate with the calculated year.

    Returns ``(status, text)``; status is ``match``, ``prior_year``, ``differs``
    or ``unavailable``.
    """
    if stored is None:
        return "unavailable", "No stored CyberLife rate (RNL_RT is NULL)"
    if not 1 <= year <= len(schedule):
        return "unavailable", f"Policy year {year} is outside the calculated horizon"
    calculated = schedule[year - 1]
    if abs(calculated - stored) < EXACT_TOLERANCE:
        return "match", "Match"
    if year > 1 and abs(schedule[year - 2] - stored) < EXACT_TOLERANCE:
        return "prior_year", (f"Matches year {year - 1} (anniversary not yet processed); "
                              f"year {year} is {calculated:.5f}")
    diff = stored - calculated
    pct = f" ({diff / calculated:+.3%})" if calculated else ""
    return "differs", f"Differs by {diff:+.5f}{pct}"


# Rate types CyberLife calculates for these plans with the FFL VP/MS target
# model (CKAPTB58 calc W), which is not available; B11/N71 surrender charges
# are a percentage of that target. Not loaded in UL_Rates.
# TODO: move to rates.PLAN_ATTR (e.g. JS_VPMS_UNAVAILABLE) so new plans need no code.
_N91_VPMS = ("MTP", "CTP", "PTP")
_EP_VPMS = ("MTP", "CTP", "STP", "SCR")
VPMS_UNAVAILABLE_RATES: Dict[str, Tuple[str, ...]] = {
    **{plan: _N91_VPMS for plan in (
        "N91EMA00", "N91EMB00", "N91EAA00", "N91EAJ00", "N91EAB00", "N91EAN00")},
    **{plan: _EP_VPMS for plan in (
        "B11EP200", "B11EP400", "N71EMR00", "N71EMJ00", "N71EP100", "N71EP300")},
}
VPMS_UNAVAILABLE_TEXT = "calculated by VP/MS; not available"

_SEX = {"1": "M", "2": "F"}


def rate_sex(sex_code: str) -> str:
    """CyberLife RT_SEX_CD 1/2 -> JS_Q sex M/F; anything else is an error."""
    code = (sex_code or "").strip()
    if code in ("M", "F"):
        return code
    if code not in _SEX:
        raise JointSurvivorError(f"Unsupported joint insured sex code {sex_code!r} (expected 1 or 2)")
    return _SEX[code]


@dataclass(frozen=True)
class JointSurvivorRates:
    """Everything the PolView joint rate view shows for one coverage phase."""

    company: str
    plancode: str
    issue_date: date
    primary: Insured
    joint: Insured
    ratings: Tuple[Rating, ...]
    rules: JointRules
    attributes: Mapping[str, str]
    plan_description: str
    maturity_age: int
    horizon: int
    horizon_note: str
    js_q: Mapping[str, Tuple[Tuple[float, ...], Tuple[float, ...]]]
    schedule: JointSchedule
    as_of: date
    policy_year: int
    stored_rate: Optional[float]
    comparison_status: str
    comparison_text: str

    @property
    def calculated_current(self) -> Optional[float]:
        if 1 <= self.policy_year <= self.horizon:
            return self.schedule.current[self.policy_year - 1]
        return None

    def ratings_for(self, person: str) -> Tuple[Rating, ...]:
        return tuple(r for r in self.ratings if r.person == person)

    @property
    def vpms_unavailable(self) -> Optional[Tuple[str, ...]]:
        return VPMS_UNAVAILABLE_RATES.get(self.plancode.strip())


def _contiguous_durations(values: Mapping[int, float], label: str) -> int:
    """Largest n with durations 1..n all present; a gap before the last raises."""
    n = 0
    while n + 1 in values:
        n += 1
    if values and max(values) > n:
        raise JointSurvivorError(f"JS_Q {label} is missing duration {n + 1}")
    return n


def policy_year_on(issue: date, as_of: date) -> int:
    """Policy year (1-based) containing ``as_of`` for a phase issued on ``issue``."""
    years = as_of.year - issue.year - ((as_of.month, as_of.day) < (issue.month, issue.day))
    return years + 1


@dataclass(frozen=True)
class JointBasis:
    """One phase's plan rules, both lives' JS_Q and the joint schedule, years 1..horizon."""

    rules: JointRules
    attributes: Mapping[str, str]
    plan_description: str
    maturity_age: int
    horizon: int
    horizon_note: str
    js_q: Mapping[str, Tuple[Tuple[float, ...], Tuple[float, ...]]]
    schedule: JointSchedule


def load_joint_basis(
    rates, company: str, plancode: str, primary: Insured, joint: Insured,
    ratings: Sequence[Rating],
) -> JointBasis:
    """Look up JS_Q/PLAN_ATTR/PLAN_DEF through ``rates`` and calculate the schedule.

    ``rates`` is a :class:`suiteview.core.joint_survivor_rates.JointSurvivorRateSource`
    (PolView's ``Rates`` or RERUN's ``ULRates``). The horizon is maturity
    age minus the younger issue age, limited to the JS_Q durations loaded.
    """
    company, plancode = company.strip(), plancode.strip()
    attrs = rates.get_plan_attributes(company, plancode)
    rules = JointRules.from_plan_attributes(attrs)
    definition = rates.get_plan_definition(company, plancode)
    if not definition or definition.get("MATURITY_AGE") is None:
        raise JointSurvivorError(f"rates.PLAN_DEF has no MATURITY_AGE for {company}/{plancode}")
    maturity_age = int(definition["MATURITY_AGE"])
    younger = min(primary.issue_age, joint.issue_age)
    horizon = maturity_age - younger
    if horizon < 1:
        raise JointSurvivorError(f"Maturity age {maturity_age} is not after issue age {younger}")

    raw = {}
    for scale in ("C", "G"):
        for person, life in (("00", primary), ("01", joint)):
            values = rates.get_joint_survivor_q(
                company, plancode, scale, life.sex, life.rate_class, life.issue_age)
            label = f"{plancode} {scale} {life.sex}/{life.rate_class} age {life.issue_age}"
            available = _contiguous_durations(values, label)
            if available == 0:
                raise JointSurvivorError(f"No JS_Q rates for {label}")
            raw[(scale, person)] = (values, available)
    loaded = min(available for _, available in raw.values())
    horizon_note = f"maturity {maturity_age} - younger issue age {younger}"
    if loaded < horizon:
        horizon_note += f"; JS_Q ends at duration {loaded}"
        horizon = loaded
    js_q = {
        scale: tuple(
            tuple(raw[(scale, person)][0][t] for t in range(1, horizon + 1))
            for person in ("00", "01"))
        for scale in ("C", "G")
    }
    return JointBasis(
        rules=rules, attributes=dict(attrs),
        plan_description=str(definition.get("DESCRIPTION") or ""), maturity_age=maturity_age,
        horizon=horizon, horizon_note=horizon_note, js_q=js_q,
        schedule=joint_schedule(js_q, ratings, rules),
    )


def calculate_joint_survivor_rates(
    rates, company: str, plancode: str, issue_date: date, primary: Insured, joint: Insured,
    ratings: Sequence[Rating], as_of: date, stored_rate: Optional[float],
) -> JointSurvivorRates:
    """The phase's joint basis plus the comparison with CyberLife's stored rate."""
    basis = load_joint_basis(rates, company, plancode, primary, joint, ratings)
    year = policy_year_on(issue_date, as_of)
    status, text = compare_stored_rate(basis.schedule.current, year, stored_rate)
    return JointSurvivorRates(
        company=company.strip(), plancode=plancode.strip(), issue_date=issue_date,
        primary=primary, joint=joint, ratings=tuple(ratings), rules=basis.rules,
        attributes=basis.attributes, plan_description=basis.plan_description,
        maturity_age=basis.maturity_age, horizon=basis.horizon,
        horizon_note=basis.horizon_note, js_q=basis.js_q, schedule=basis.schedule,
        as_of=as_of, policy_year=year, stored_rate=stored_rate,
        comparison_status=status, comparison_text=text,
    )
