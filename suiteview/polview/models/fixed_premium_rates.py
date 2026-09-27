"""Fixed-premium rate views (ISWL and traditional Whole Life) for PolView Rates.

Sources, all read through ``suiteview.core.rates.Rates`` under the policy's
CyberLife rate-file user (``cyberlife_rate_user``):

* ``WL_RATE_PREM`` - IAF premium cells. Type N is the annual premium per unit;
  PLAN_OPTION ``**`` is the base plan and other options are rider premiums
  keyed by benefit type + subtype (``10`` = benefit 1/0 waiver of premium).
* ``POINT_MODEFACT`` -> ``RATE_MODEFACT`` - mode factors and the policy fee.

Missing sources are reported in the matrices themselves, never as zeros.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from suiteview.core.modal_premium import (
    MODE_LABELS, ModalPremiumError, billing_mode, calculate_modal_premium,
    describe_bill_form, factor_family, fee_label, unverified_rules,
)
from suiteview.core.rates import WL_PREMIUM_RATE_TYPES

if TYPE_CHECKING:
    from .policy_information import PolicyInformation

BASE_OPTION = "**"
SEX_LABELS = {"1": "Male", "2": "Female", "3": "Unisex"}


@dataclass
class PremiumItem:
    """One premium-paying piece of a policy: a coverage or a benefit."""
    label: str
    plancode: str
    option: str
    issue_age: Optional[int]
    issue_date: Optional[date]
    units: Optional[Decimal]
    stored_rate: Optional[Decimal]
    active: bool
    status: str
    sex: str
    rateclass: str
    substandard: str = ""
    rate_row: Optional[Dict[str, Any]] = None
    reason: str = ""
    lookup: Dict[str, Any] = field(default_factory=dict)

    @property
    def rate(self) -> Optional[Decimal]:
        return self.rate_row["RATE"] if self.rate_row else None

    @property
    def annual_premium(self) -> Optional[Decimal]:
        if self.rate is None or self.units is None:
            return None
        return self.rate * self.units

    @property
    def check(self) -> str:
        if self.rate is None:
            return ""
        if self.stored_rate is None:
            return "No stored rate"
        return "Match" if self.stored_rate == self.rate else f"Differs (stored {self.stored_rate})"


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, date):
        return value.strftime("%m/%d/%Y")
    if isinstance(value, Decimal):
        return _rate(value)
    return value


def _rate(value: Decimal) -> str:
    """Stored decimal(19,8) cells without padding zeros (at least two places)."""
    text = f"{value:f}"
    if "." in text:
        whole, fraction = text.split(".")
        fraction = fraction.rstrip("0").ljust(2, "0")
        text = f"{whole}.{fraction}"
    return text


def _money(value: Optional[Decimal]) -> str:
    return "" if value is None else f"{value.quantize(Decimal('0.01')):,.2f}"


def _as_of(policy: "PolicyInformation") -> date:
    return policy.values.valuation_date or date.today()


def _matrix(columns: List[str], metadata: List[tuple], body: List[list]) -> List[List]:
    """Left RateFields/RateInfo metadata block beside a body, the house layout."""
    width = len(columns) - 2
    matrix = [["RateFields", "RateInfo", *columns[2:]]]
    for row in range(max(len(metadata), len(body))):
        fields = list(metadata[row]) if row < len(metadata) else ["", ""]
        values = body[row] if row < len(body) else [""] * width
        matrix.append([*fields, *[_cell(v) for v in values]])
    return matrix


def select_premium_row(rows: List[Dict[str, Any]], option: str, sex: str, rateclass: str):
    """The single type-N IAF cell for an option, sex and rate class.

    An exact rate class wins; otherwise IAF rate class ``0`` (class-independent,
    as printed for rider premiums). Several remaining cells (bands, duration
    codes or scale windows) are ambiguous and are not chosen for the user.
    Returns ``(row, reason)``.
    """
    candidates = [r for r in rows if r["RATE_TYPE"] == "N" and r["PLAN_OPTION"] == option]
    if not candidates:
        return None, f"No WL_RATE_PREM premium (type N) for option {option}"
    by_sex = [r for r in candidates if r["SEX"] == sex]
    if not by_sex:
        found = ", ".join(sorted({r["SEX"] for r in candidates}))
        return None, f"No WL_RATE_PREM premium for sex {sex or '(blank)'} (loaded: {found})"
    matched = _premium_rateclass_matches(by_sex, rateclass)
    if not matched:
        found = ", ".join(sorted({r["RATECLASS"] for r in by_sex}))
        return None, f"No WL_RATE_PREM premium for rate class {rateclass or '(blank)'} (loaded: {found})"
    return _single_premium_row(matched)


def _premium_rateclass_matches(rows: List[Dict[str, Any]], rateclass: str) -> List[Dict[str, Any]]:
    matched = [row for row in rows if rateclass and row["RATECLASS"] == rateclass]
    return matched or [row for row in rows if row["RATECLASS"] == "0"]


def _single_premium_row(rows: List[Dict[str, Any]]):
    if len(rows) == 1:
        return rows[0], ""
    if len(rows) > 1:
        ids = ", ".join(f"{r['PREMIUM_IDENTIFIER']}@{r['SCALE_START']}" for r in rows)
        return None, f"Ambiguous: {len(rows)} premium cells ({ids}); not selected"
    return None, ""


def _coverage_substandard(cov, as_of: date) -> str:
    notes = []
    if cov.table_rating and (cov.table_cease_date is None or cov.table_cease_date > as_of):
        notes.append(f"table {cov.table_rating_code or cov.table_rating}")
    if cov.flat_extra and cov.flat_extra > 0 and (cov.flat_cease_date is None or cov.flat_cease_date > as_of):
        notes.append(f"flat {cov.flat_extra}")
    return ", ".join(notes)


def premium_items(policy: "PolicyInformation", cov_index: Optional[int] = None) -> List[PremiumItem]:
    """Coverages and their benefits with the IAF premium each would use.

    ``cov_index`` limits the list to one coverage (1-based) and its benefits.
    """
    as_of = _as_of(policy)
    coverages = policy.coverages.get_coverages()
    indexes = [cov_index] if cov_index else range(1, len(coverages) + 1)
    lookups: Dict[tuple, Dict[str, Any]] = {}
    items: List[PremiumItem] = []

    def lookup(plancode, age, issue_date):
        key = (plancode, age, issue_date)
        if key not in lookups:
            lookups[key] = policy.rates.rates_wl_premium(plancode, age, issue_date)
        return lookups[key]

    def resolve(item: PremiumItem):
        if item.issue_age is None:
            item.reason = "Missing issue age"
            return
        item.lookup = lookup(item.plancode, item.issue_age, item.issue_date)
        if not item.lookup["rows"]:
            if item.lookup["versions"]:
                item.reason = (f"No WL_RATE_PREM IAF version for {item.plancode} "
                               f"effective by {_cell(item.issue_date)}")
            else:
                item.reason = (f"Not loaded: no WL_RATE_PREM rows for {item.plancode}, "
                               f"user {policy.rates.cyberlife_rate_user_code}, age {item.issue_age}")
            return
        item.rate_row, item.reason = select_premium_row(
            item.lookup["rows"], item.option, item.sex, item.rateclass)

    for index in indexes:
        cov = coverages[index - 1]
        sex, rateclass = policy.rates.cov_rate_sex_code(index), policy.rates.renewal_cov_rateclass_by_cov(index)
        active = policy.coverages._coverage_is_active(cov, as_of)
        cov_item = PremiumItem(
            label=f"Cov {index:02d} base", plancode=cov.plancode, option=BASE_OPTION,
            issue_age=cov.issue_age, issue_date=cov.issue_date, units=cov.units,
            stored_rate=cov.annual_premium_per_unit, active=active,
            status="Active" if active else "Not active", sex=sex, rateclass=rateclass,
            substandard=_coverage_substandard(cov, as_of),
        )
        resolve(cov_item)
        items.append(cov_item)
        for ben_number, ben in enumerate(policy.benefits.get_benefits(), start=1):
            if ben.cov_pha_nbr != cov.cov_pha_nbr:
                continue
            ceased = ben.cease_date is not None and ben.cease_date <= as_of
            ben_active = active and not ceased
            status = ("Ceased " + ben.cease_date.strftime("%m/%d/%Y")) if ceased else (
                "Active" if ben_active else "Coverage not active")
            rating = ben.rating_factor
            ben_item = PremiumItem(
                label=f"Ben {ben_number:02d} ({ben.benefit_type_cd}/{ben.benefit_subtype_cd})",
                plancode=cov.plancode, option=f"{ben.benefit_type_cd}{ben.benefit_subtype_cd}",
                issue_age=ben.issue_age, issue_date=ben.issue_date or cov.issue_date,
                units=ben.units, stored_rate=ben.coi_rate, active=ben_active, status=status,
                sex=sex, rateclass=rateclass,
                substandard=f"rating factor {rating}" if rating not in (None, 0, 1) else "",
            )
            resolve(ben_item)
            items.append(ben_item)
    return items


def build_premium_rate_matrix(policy: "PolicyInformation", cov_index: int) -> List[List]:
    """IAF premium rates for a coverage (base plus its benefits), per unit."""
    items = premium_items(policy, cov_index)
    base = items[0]
    lookup = base.lookup
    first = lookup["rows"][0] if lookup.get("rows") else {}
    columns = ["RateFields", "RateInfo", "Item", "Option", "Type", "Description", "Issue Age",
               "Identifier", "Scale Start", "Scale Stop", "Rate", "Units", "Annual Premium",
               "Stored Rate", "Check", "Status"]
    metadata = [
        ("Policy", policy.policy_number), ("Cov Index", cov_index), ("Plancode", base.plancode),
        ("Source", "WL_RATE_PREM"),
        ("Rate User", f"{policy.rates.cyberlife_rate_user_code} (company {policy.company_code})"),
        ("IAF Version", (lookup.get("iaf_version") or "(blank)") if lookup.get("rows") else "Not loaded"),
        ("IAF Effective", _cell(lookup.get("effective_date")) if lookup.get("rows") else "Not loaded"),
        ("Issue Date", _cell(base.issue_date)), ("Issue Age", _cell(base.issue_age)),
        ("Sex", f"{base.sex} ({SEX_LABELS.get(base.sex, 'Unknown')})"),
        ("Rateclass", base.rateclass or "(blank)"),
        ("Value per Unit", _cell(first.get("VALUE_PER_UNIT")) if first else "Not loaded"),
        ("Pay Age", f"{first['PAY_AGE']} (use {first['PAY_AGE_USE']})" if first else "Not loaded"),
        ("ME Age", f"{first['ME_AGE']} (use {first['ME_AGE_USE']})" if first else "Not loaded"),
        (" ", " "), ("Rates are annual", "per unit"),
        ("Stored cov rate", "ANN_PRM_UNT_AMT"), ("Stored ben rate", "BNF_ANN_PPU_AMT"),
        ("Substandard is not", "included in rates"),
    ]
    body = []
    for item in items:
        row = item.rate_row
        if row is None:
            body.append([item.label, item.option, "N", WL_PREMIUM_RATE_TYPES["N"], item.issue_age,
                         "", "", "", item.reason, _cell(item.units), "", _cell(item.stored_rate),
                         "", item.status])
            continue
        body.append([item.label, item.option, row["RATE_TYPE"], WL_PREMIUM_RATE_TYPES["N"],
                     item.issue_age, row["PREMIUM_IDENTIFIER"], row["SCALE_START"],
                     row["SCALE_STOP"] or "", row["RATE"], item.units,
                     _money(item.annual_premium), _cell(item.stored_rate), item.check,
                     item.status + (f"; substandard {item.substandard} not included"
                                    if item.substandard else "")])
    # The base plan's other printed cells (target, COI) for this insured.
    for row in lookup.get("rows", []):
        if (row["PLAN_OPTION"] != BASE_OPTION or row["RATE_TYPE"] == "N"
                or row["SEX"] != base.sex or row["RATECLASS"] not in (base.rateclass, "0")):
            continue
        body.append([base.label, BASE_OPTION, row["RATE_TYPE"],
                     WL_PREMIUM_RATE_TYPES.get(row["RATE_TYPE"], f"Type {row['RATE_TYPE']}"),
                     base.issue_age, row["PREMIUM_IDENTIFIER"], row["SCALE_START"],
                     row["SCALE_STOP"] or "", row["RATE"], "", "", "", "", "As printed on the IAF"])
    return _matrix(columns, metadata, body)


def _modal_policy_blockers(policy: "PolicyInformation") -> List[str]:
    status = policy.status.premium_pay_status_code.strip()
    if status in ("44", "45"):
        return ["Policy is on ETI/RPU: no fixed premium is billed"]
    return []


def _modal_premium_rows(items: List[PremiumItem]) -> tuple[List[list], List[str], Decimal, List[str]]:
    body: List[list] = []
    blockers: List[str] = []
    annual = Decimal("0")
    substandard: List[str] = []
    for item in items:
        if not item.active:
            body.append(["Premium", item.label, _cell(item.units), _cell(item.rate), "",
                         f"{item.status}: excluded"])
            continue
        if item.rate is None:
            blockers.append(f"{item.label}: {item.reason}")
            body.append(["Premium", item.label, _cell(item.units), "Not loaded", "", item.reason])
            continue
        if item.units is None:
            blockers.append(f"{item.label}: missing units")
            body.append(["Premium", item.label, "", item.rate, "", "Missing units"])
            continue
        if item.substandard:
            substandard.append(f"{item.label} {item.substandard}")
        annual += item.annual_premium
        body.append(["Premium", item.label, item.units, item.rate, _money(item.annual_premium),
                     f"{item.option} x units"])
    if items and not blockers:
        body.append(["Annual", "Annual premium", "", "", _money(annual), "Sum of active items"])
    return body, blockers, annual, substandard


def _modal_lookup_blockers(plancode: str, lookup: Dict[str, Any]) -> List[str]:
    if lookup["index"] is None:
        return [f"Not loaded: no POINT_MODEFACT pointer for plancode {plancode}"]
    if lookup["factors"] is None:
        return [f"Not loaded: mode premium table {lookup['index']} is not in RATE_MODEFACT"]
    return []


def _modal_mode_and_family(policy: "PolicyInformation", blockers: List[str]):
    frequency = policy.billing.billing_frequency
    nsd = policy.billing.non_standard_mode_code
    form = policy.billing.bill_form_code
    try:
        return billing_mode(frequency, nsd), factor_family(form), form
    except ModalPremiumError as exc:
        blockers.append(str(exc))
        return None, None, form


def _append_modal_rule_blockers(factors: Optional[Dict[str, Any]], blockers: List[str]) -> None:
    if factors is None:
        return
    problems = unverified_rules(factors)
    if problems:
        blockers.append("Unverified mode premium rules: " + ", ".join(problems))


def _modal_result(annual: Decimal, factors, form: str, mode, blockers: List[str]):
    if blockers:
        return None
    try:
        return calculate_modal_premium(annual, factors, form, mode)
    except ModalPremiumError as exc:
        blockers.append(str(exc))
        return None


def _append_modal_rows(body: List[list], annual: Decimal, result, mode, family, blockers: List[str]) -> None:
    if result is None:
        body.append(["Modal", "Calculated modal premium", "", "", "Not calculated",
                     "; ".join(blockers)])
        return
    suffix = "" if mode == "A" else f"{mode}"
    body.append(["Mode factor", f"{family}{suffix}" if suffix else "Annual (1.0)", "",
                 result.factor, _money(result.premium),
                 f"round({_money(annual)} x {result.factor}, 2)"])
    body.append(["Policy fee", f"{family}{suffix}_FEE" if suffix else "Annual (1.0)", "",
                 result.fee_factor, _money(result.fee),
                 f"round({_money(result.policy_fee)} x {result.fee_factor}, 2)"])
    body.append(["Modal", "Calculated modal premium", "", "", _money(result.total), ""])


def _append_modal_difference(
    body: List[list],
    stored: Optional[Decimal],
    result,
    substandard: List[str],
) -> None:
    body.append(["Stored", "LH_BAS_POL.POL_PRM_AMT", "", "", _money(stored), ""])
    if result is None or stored is None:
        return
    difference = stored - result.total
    note = "Match" if difference == 0 else "Differs"
    if substandard:
        note += "; substandard not included (" + ", ".join(substandard) + ")"
    body.append(["Difference", "Stored - calculated", "", "", _money(difference), note])


def _mode_text(mode, frequency, nsd: str) -> str:
    if not mode:
        return f"PMT_FQY_PER {frequency}"
    nsd = nsd or ""
    return (
        f"{MODE_LABELS[mode]} (PMT_FQY_PER {frequency}"
        + (f", NSD_MD_CD {nsd}: monthly premium" if nsd.strip() else "")
        + ")"
    )


def _modal_metadata(policy: "PolicyInformation", plancode: str, as_of: date,
                    mode, lookup: Dict[str, Any]) -> List[tuple]:
    factors = lookup["factors"]
    metadata = [
        ("Policy", policy.policy_number), ("Plancode", plancode), ("As of", _cell(as_of)),
        ("Mode", _mode_text(mode, policy.billing.billing_frequency, policy.billing.non_standard_mode_code)),
        ("Bill Form", describe_bill_form(policy.billing.bill_form_code)),
        ("Rate User", f"{policy.rates.cyberlife_rate_user_code} (company {policy.company_code})"),
        ("Premiums", "WL_RATE_PREM (N)"),
        ("Factors", lookup["index"] or "No POINT_MODEFACT pointer"),
    ]
    if factors is None:
        metadata.append(("RATE_MODEFACT", "Not loaded"))
    else:
        metadata += [
            ("Policy Fee", f"{factors['POLICY_FEE']:.2f} annual"),
            ("Fee Added", fee_label(factors["POLICY_FEE_ADD"])),
            ("Fee Rule", factors["POLICY_FEE_RULE"]),
            ("Collection Fee", f"{factors['COLLECTION_FEE']:.2f} (add {factors['COLLECTION_FEE_ADD']})"),
            ("Multiply Order", factors["MULTIPLY_ORDER"]), ("Rating Order", factors["RATING_ORDER"]),
            ("Rounding Rule", factors["ROUNDING_RULE"]),
            (" ", " "), ("Factors S/Q/M", " "),
            ("DIR", " / ".join(str(factors[f"DIR{m}"]) for m in "SQM")),
            ("DIR fee", " / ".join(str(factors[f"DIR{m}_FEE"]) for m in "SQM")),
            ("PAC", " / ".join(str(factors[f"PAC{m}"]) for m in "SQM")),
            ("PAC fee", " / ".join(str(factors[f"PAC{m}_FEE"]) for m in "SQM")),
            (" ", " "),
            ("User / Table", f"{factors['USER_CODE']} / {factors['MODE_PREM_TABLE']}"),
            ("DIR tables", f"factor {factors['DIR_FACTOR_TABLE']}, fee {factors['DIR_FEE_FACTOR_TABLE']}"),
            ("PAC tables", f"factor {factors['PAC_FACTOR_TABLE']}, fee {factors['PAC_FEE_FACTOR_TABLE']}"),
            ("Rules table", factors["RULES_TABLE"]), ("Factor source", factors["FACTOR_SOURCE"]),
        ]
    return metadata


def build_modal_premium_matrix(policy: "PolicyInformation") -> List[List]:
    """Annual premium from IAF rates, mode factors, policy fee and POL_PRM_AMT."""
    as_of = _as_of(policy)
    plancode = policy.coverages.cov_plancode(1)
    stored = policy.billing.modal_premium
    columns = ["RateFields", "RateInfo", "Line", "Item", "Units", "Rate", "Amount", "Note"]
    blockers = _modal_policy_blockers(policy)
    items = premium_items(policy) if not blockers else []
    body, premium_blockers, annual, substandard = _modal_premium_rows(items)
    blockers.extend(premium_blockers)

    lookup = policy.rates.rates_modal_factors()
    factors = lookup["factors"]
    blockers.extend(_modal_lookup_blockers(plancode, lookup))
    mode, family, form = _modal_mode_and_family(policy, blockers)
    _append_modal_rule_blockers(factors, blockers)
    result = _modal_result(annual, factors, form, mode, blockers)
    _append_modal_rows(body, annual, result, mode, family, blockers)
    _append_modal_difference(body, stored, result, substandard)
    metadata = _modal_metadata(policy, plancode, as_of, mode, lookup)
    return _matrix(columns, metadata, body)
