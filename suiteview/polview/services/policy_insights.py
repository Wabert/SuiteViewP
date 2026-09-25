"""At-a-glance policy facts, status chips, support-tool availability and
clipboard summaries for PolView.

Everything here reads named ``PolicyInformation`` properties. In the GUI the
policy is a merged snapshot whose tables arrive progressively, so each fact is
read under its own ``cached_reads_only()`` guard: a fact whose tables have not
been prefetched yet is *pending* (``None``), never a live GUI-thread query and
never a guessed value. Genuine read errors are logged and also left pending,
because the owning tab already reports them explicitly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Optional

from suiteview.polview.models.policy_data import CachedReadError

logger = logging.getLogger(__name__)

PRODUCTION_REGION = "CKPR"
REGION_LABELS = {
    "CKMO": "MODEL",
    "CKAS": "ACCEPTANCE",
    "CKCS": "CYBERTEK",
    "CKSR": "SYSTEM",
}

# Chip tones map to colours in the UI strip.
DANGER, WARN, INFO, OK, NEUTRAL, TEST, FUN = (
    "danger", "warn", "info", "ok", "neutral", "test", "fun",
)


@dataclass(frozen=True)
class Chip:
    key: str
    text: str
    tone: str = NEUTRAL
    tooltip: str = ""


@dataclass(frozen=True)
class ToolAvailability:
    key: str
    label: str
    available: bool
    reason: str = ""


@dataclass(frozen=True)
class Suggestion:
    key: str
    text: str
    tooltip: str = ""


@dataclass(frozen=True)
class PolicySummary:
    policy_number: str
    company_code: str
    company_name: str
    region: str
    system_code: str
    plancode: Optional[str] = None
    form_number: Optional[str] = None
    product_type: Optional[str] = None
    db_option: Optional[str] = None
    total_death_benefit: Optional[Decimal] = None
    # Used to find recent policies by name; deliberately not in the copied summary.
    insured_name: Optional[str] = None
    issue_date: Optional[date] = None
    issue_age: Optional[int] = None
    attained_age: Optional[int] = None
    policy_year: Optional[int] = None
    valuation_date: Optional[date] = None
    paid_to_date: Optional[date] = None
    status_code: Optional[str] = None
    status_description: Optional[str] = None
    chips: tuple[Chip, ...] = ()
    pending: tuple[str, ...] = field(default_factory=tuple)

    @property
    def identity(self) -> str:
        parts = [self.region, self.company_code, self.policy_number]
        return " - ".join(p for p in parts if p)


class _Reader:
    """Read named properties under per-fact cached guards."""

    def __init__(self, policy):
        self.policy = policy
        self.pending: list[str] = []

    def get(self, name: str, getter: Optional[Callable[[Any], Any]] = None):
        guard = getattr(self.policy, "cached_reads_only", None)
        try:
            if guard is None:
                return getter(self.policy) if getter else getattr(self.policy, name)
            with guard():
                return getter(self.policy) if getter else getattr(self.policy, name)
        except CachedReadError:
            self.pending.append(name)
            return None
        except Exception:  # the owning tab surfaces the real error
            logger.debug("Policy summary could not read %s", name, exc_info=True)
            self.pending.append(name)
            return None


def _fmt_date(value: Optional[date]) -> str:
    return f"{value.month}/{value.day:02d}/{value.year}" if value else ""


def _fmt_money(value, cents: bool = False) -> str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"${number:,.2f}" if cents else f"${number:,.0f}"


def status_tone(code: str) -> str:
    """Colour class for a premium-paying status (PRM_PAY_STA_REA_CD)."""
    code = (code or "").strip()
    if code in ("98", "99"):
        return DANGER
    if code in ("54", "97") or code.startswith("1"):
        return WARN
    if code.startswith("2"):
        return OK
    if code.startswith(("3", "4")):
        return INFO
    return NEUTRAL


def _same_month_day(a: Optional[date], b: date) -> bool:
    return bool(a and (a.month, a.day) == (b.month, b.day))


def build_policy_summary(policy, today: Optional[date] = None) -> PolicySummary:
    """Summarise whatever is already known about *policy* (never queries)."""
    today = today or date.today()
    read = _Reader(policy)
    region = str(getattr(policy, "region", "") or "")
    company = str(getattr(policy, "company_code", "") or "")
    system = str(getattr(policy, "system_code", "") or "")

    coverages = read.get("coverages", lambda p: p.get_coverages()) or []
    base = coverages[0] if coverages else None
    status_code = read.get("premium_pay_status_code")
    status_desc = read.get("premium_pay_status_description")
    advanced = read.get("is_advanced_product")
    product_type = read.get("product_type")
    in_grace = read.get("in_grace")
    grace_expiry = read.get("grace_period_expiry_date") if in_grace else None
    valuation = read.get("valuation_date")
    paid_to = read.get("paid_to_date")
    issue_date = base.issue_date if base is not None else None
    policy_year = read.get("policy_year")

    chips: list[Chip] = []

    if region and region != PRODUCTION_REGION:
        label = REGION_LABELS.get(region, "NON-PROD")
        chips.append(Chip(
            "region", region, TEST,
            f"{region} is not production (CKPR). Values are {label.lower()} region data.",
        ))
    if system == "P":
        chips.append(Chip("pending", "Pending", WARN,
                          "Pending policy (CK_SYS_CD = 'P'), not yet inforce."))
    if status_code:
        chips.append(Chip(
            "status", f"{status_code} {status_desc or ''}".strip(), status_tone(status_code),
            f"Premium paying status {status_code} - {status_desc}\n"
            "Source: LH_BAS_POL.PRM_PAY_STA_REA_CD",
        ))
    suspense = read.get("suspense_code")
    if suspense and suspense != "0":
        chips.append(Chip(
            "suspense", read.get("suspense_description") or f"Suspense {suspense}", DANGER,
            f"Suspense code {suspense} (LH_BAS_POL.SUS_CD)",
        ))
    if in_grace:
        until = f" until {_fmt_date(grace_expiry)}" if grace_expiry else ""
        chips.append(Chip("grace", f"In Grace{until}", DANGER,
                          f"Policy is in its grace period{until}. Premium is needed to keep "
                          "coverage in force.\nSource: IN_GRA_PER_IND = 1, GRA_PER_EXP_DT"))
    mec = read.get("mec_indicator")
    if mec == "1":
        chips.append(Chip("mec", "MEC", WARN,
                          "Modified Endowment Contract (LH_TAMRA_7_PY_PER.MEC_STA_CD = 1)."))
    debt = read.get("policy_debt")
    if debt:
        chips.append(Chip("loan", f"Loan {_fmt_money(debt, cents=True)}", WARN,
                          "Total policy debt: loan principal plus accrued interest."))
    reins = read.get("reins_partner")
    reins = str(reins or "").strip()
    if reins:
        partner = "RGA" if reins == "R" else "ANICO"
        chips.append(Chip("reins", f"Reins {partner}", INFO,
                          f"Reinsurance partner code {reins} (TH_USER_GENERIC.FUZGREIN_IND)."))
    if product_type:
        kind = "Advanced" if advanced else "Traditional" if advanced is not None else ""
        product_line = read.get("product_line_description")
        chips.append(Chip(
            "product", " · ".join(p for p in (product_type, kind) if p), NEUTRAL,
            f"Product line: {product_line or 'unknown'}",
        ))
    if advanced:
        dol = str(read.get("gpt_cvat") or "").strip()
        if dol:
            chips.append(Chip("dol", dol, NEUTRAL,
                              "Definition of life insurance: GPT = Guideline Premium Test, "
                              "CVAT = Cash Value Accumulation Test"))
        standard_db = read.get("standard_death_benefit")
        corridor_db = read.get("corridor_death_benefit")
        if corridor_db is not None and standard_db is not None and corridor_db > standard_db:
            chips.append(Chip("corridor", "In Corridor", WARN,
                              "Corridor death benefit exceeds the standard death benefit."))
    lives = read.get("insured_lives_description")
    if lives and lives != "Single":
        chips.append(Chip("joint", lives, INFO, "Base coverage lives code (NBR_OF_LIVES_CD)."))

    # Traditional premium-paying policies whose paid-to has fallen behind.
    if (advanced is False and status_code and status_code.startswith("2")
            and paid_to and valuation and paid_to < valuation):
        chips.append(Chip(
            "paid_to", f"Paid to {_fmt_date(paid_to)}", WARN,
            f"Premium is paid to {_fmt_date(paid_to)}, before the valuation date "
            f"{_fmt_date(valuation)} (LH_BAS_POL.PRM_PAID_TO_DT).",
        ))

    # A little delight: anniversaries, birthdays and vintage contracts.
    if issue_date and _same_month_day(issue_date, today) and issue_date < today:
        years = today.year - issue_date.year
        chips.append(Chip("anniversary", f"🎂 {years}-year anniversary today", FUN,
                          f"Issued {_fmt_date(issue_date)}. Happy policy anniversary!"))
    birth = read.get("primary_insured_birth_date")
    if _same_month_day(birth, today):
        chips.append(Chip("birthday", "🎈 Insured's birthday", FUN,
                          "It's the primary insured's birthday today."))
    if policy_year and policy_year >= 50 and issue_date:
        chips.append(Chip("vintage", f"🏛 Vintage {issue_date.year}", FUN,
                          f"In force for {policy_year - 1}+ years. They don't make them like this anymore."))

    db_option = read.get("db_option_description") if advanced else None
    return PolicySummary(
        policy_number=str(getattr(policy, "policy_number", "") or ""),
        company_code=company,
        company_name=str(read.get("company_name") or ""),
        region=region,
        system_code=system,
        plancode=(base.plancode if base is not None else None),
        form_number=(str(getattr(base, "form_number", "") or "").strip() or None) if base else None,
        product_type=product_type,
        db_option=db_option or None,
        insured_name=read.get("primary_insured_name") or None,
        total_death_benefit=read.get("total_death_benefit"),
        issue_date=issue_date,
        issue_age=(base.issue_age if base is not None else None),
        attained_age=read.get("attained_age"),
        policy_year=policy_year,
        valuation_date=valuation,
        paid_to_date=paid_to,
        status_code=status_code,
        status_description=status_desc,
        chips=tuple(chips),
        pending=tuple(dict.fromkeys(read.pending)),
    )


def summary_rows(summary: PolicySummary) -> list[tuple[str, str]]:
    """Label/value pairs for the copied policy summary."""
    rows = [("Policy", summary.identity
             + (f" ({summary.company_name})" if summary.company_name else ""))]
    plan = " / ".join(p for p in (summary.plancode, summary.form_number) if p)
    if plan:
        rows.append(("Plan", plan + (f"  [{summary.product_type}]" if summary.product_type else "")))
    if summary.db_option:
        rows.append(("DB option", summary.db_option))
    if summary.total_death_benefit is not None:
        rows.append(("Death benefit", _fmt_money(summary.total_death_benefit)))
    if summary.issue_date:
        age = f" at age {summary.issue_age}" if summary.issue_age is not None else ""
        rows.append(("Issued", f"{_fmt_date(summary.issue_date)}{age}"))
    if summary.policy_year:
        rows.append(("Policy year", str(summary.policy_year)))
    if summary.attained_age is not None:
        rows.append(("Attained age", str(summary.attained_age)))
    if summary.valuation_date:
        rows.append(("Valuation date", _fmt_date(summary.valuation_date)))
    if summary.paid_to_date:
        rows.append(("Paid to", _fmt_date(summary.paid_to_date)))
    flags = [c.text for c in summary.chips if c.tone != FUN and c.key not in ("product", "paid_to")]
    if flags:
        rows.append(("Flags", ", ".join(flags)))
    return rows


def summary_text(summary: PolicySummary) -> str:
    """Aligned plain text (for monospaced targets: Notepad, tickets, logs)."""
    rows = summary_rows(summary)
    width = max(len(label) for label, _ in rows) + 2
    return "\n".join(f"{label + ':':<{width}}{value}" for label, value in rows)


def summary_html(summary: PolicySummary) -> str:
    """Compact two-column table that pastes cleanly into Outlook, Word and Excel."""
    from html import escape

    cells = "".join(
        "<tr>"
        f'<td style="padding:1px 14px 1px 0;font-weight:bold;color:#0A3D0A;white-space:nowrap;">'
        f"{escape(label)}</td>"
        f'<td style="padding:1px 0;">{escape(value)}</td>'
        "</tr>"
        for label, value in summary_rows(summary)
    )
    return (
        '<table style="border-collapse:collapse;font-family:Calibri,Segoe UI,sans-serif;'
        f'font-size:11pt;">{cells}</table>'
    )


def support_tool_availability(policy) -> dict[str, ToolAvailability]:
    """Which Policy Support tools apply, and why not when they do not."""
    from suiteview.polview.services.glp_exception import is_glp_exception_eligible
    from suiteview.polview.services.reinstatement import is_ul_policy

    read = _Reader(policy)
    loaded = bool(policy is not None and getattr(policy, "exists", False))
    none_loaded = "Load a policy first."
    product = read.get("product_type") if loaded else None
    glp = bool(loaded and read.get("glp", lambda p: is_glp_exception_eligible(p)))
    doli = read.get("def_of_life_ins_description") if loaded else ""
    glp_reason = (
        "Available only for UL/IUL/ISWL/SGUL/VUL policies using Guideline Premium"
        f" (this policy: {product or 'unknown'}"
        + (f", {doli}" if doli else "") + ")."
    )
    ul = bool(loaded and read.get("ul", lambda p: is_ul_policy(p)))
    rider = bool(loaded and read.get("annuity", lambda p: any(
        str(getattr(c, "plancode", "")).strip().upper() == "0699830R"
        for c in p.get_coverages())))
    return {
        "policy_support": ToolAvailability("policy_support", "Policy Support", loaded,
                                           "" if loaded else none_loaded),
        "abr": ToolAvailability("abr", "ABR", loaded, "" if loaded else none_loaded),
        "glp_exception": ToolAvailability("glp_exception", "GLP Exception", glp,
                                          "" if glp else (glp_reason if loaded else none_loaded)),
        "forecast": ToolAvailability("forecast", "Forecast", glp,
                                     "" if glp else (glp_reason if loaded else none_loaded)),
        "reinstatement": ToolAvailability(
            "reinstatement", "UL Reinstatement", ul,
            "" if ul else ("Reinstatement quotes are available only for UL, IUL and SGUL "
                           f"policies (this policy: {product or 'unknown'})."
                           if loaded else none_loaded)),
        "annuity_rider": ToolAvailability(
            "annuity_rider", "Annuity Rider", rider,
            "" if rider else ("No 0699830R annuity rider coverage on this policy."
                              if loaded else none_loaded)),
    }


def suggested_actions(policy, summary: PolicySummary,
                      tools: dict[str, ToolAvailability],
                      today: Optional[date] = None) -> tuple[Suggestion, ...]:
    """Context-aware next steps for the policy's current situation."""
    suggestions: list[Suggestion] = []
    in_grace = any(c.key == "grace" for c in summary.chips)
    if tools.get("reinstatement") and tools["reinstatement"].available:
        from suiteview.polview.services.reinstatement import reinstatement_summary

        read = _Reader(policy)
        eligibility = read.get("reinstatement", lambda p: reinstatement_summary(p, today))
        if eligibility is not None and eligibility.eligible:
            suggestions.append(Suggestion(
                "reinstatement", "Quote reinstatement",
                "Lapsed UL: open the Home Office reinstatement quote.",
            ))
    if in_grace and tools.get("glp_exception") and tools["glp_exception"].available:
        suggestions.append(Suggestion(
            "glp_exception", "GLP Exception",
            "In grace on a guideline-premium UL: solve the minimum premium to a target date.",
        ))
    if tools.get("annuity_rider") and tools["annuity_rider"].available:
        suggestions.append(Suggestion(
            "annuity_rider", "Annuity Rider", "This policy carries the 0699830R annuity rider.",
        ))
    return tuple(suggestions)
