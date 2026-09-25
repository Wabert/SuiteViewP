"""A chronological timeline of a policy's key dates (read from cached data).

Every event names its DB2 source. Sentinel dates (9999-12-31, 0001-01-01)
and blanks are omitted rather than shown as real events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from .policy_insights import _Reader


@dataclass(frozen=True)
class TimelineEvent:
    when: date
    label: str
    source: str
    category: str


def _as_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value if 1800 < value.year < 9999 else None
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-":
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
        return parsed if 1800 < parsed.year < 9999 else None
    return None


def _add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:  # 29 February
        return value.replace(year=value.year + years, day=28)


def build_policy_timeline(policy) -> list[TimelineEvent]:
    read = _Reader(policy)
    events: list[TimelineEvent] = []

    def add(when, label, source, category):
        parsed = _as_date(when)
        if parsed is not None:
            events.append(TimelineEvent(parsed, label, source, category))

    def bas(field):
        return read.get(f"LH_BAS_POL.{field}", lambda p: p.data_item("LH_BAS_POL", field))

    add(bas("APP_WRT_DT"), "Application written", "LH_BAS_POL.APP_WRT_DT", "Policy")
    add(bas("LST_ANV_DT"), "Last anniversary processed", "LH_BAS_POL.LST_ANV_DT", "Processing")
    add(bas("NXT_YR_END_PRC_DT"), "Next year-end processing", "LH_BAS_POL.NXT_YR_END_PRC_DT", "Processing")
    add(bas("NXT_MVRY_PRC_DT"), "Next monthliversary", "LH_BAS_POL.NXT_MVRY_PRC_DT", "Processing")
    add(bas("LST_FIN_DT"), "Last financial activity", "LH_BAS_POL.LST_FIN_DT", "Processing")
    add(bas("PRM_PAID_TO_DT"), "Premium paid to", "LH_BAS_POL.PRM_PAID_TO_DT", "Billing")
    add(bas("PRM_BILL_TO_DT"), "Premium billed to", "LH_BAS_POL.PRM_BILL_TO_DT", "Billing")
    add(bas("NXT_BIL_DT"), "Next bill", "LH_BAS_POL.NXT_BIL_DT", "Billing")
    add(bas("NXT_SCH_NOT_DT"), "Next scheduled notification", "LH_BAS_POL.NXT_SCH_NOT_DT", "Billing")
    add(bas("NXT_SCH_STT_DT"), "Next scheduled statement", "LH_BAS_POL.NXT_SCH_STT_DT", "Billing")
    add(bas("PLN_TMN_DT"), "Policy terminated", "LH_BAS_POL.PLN_TMN_DT", "Status")
    if read.get("in_grace"):
        add(read.get("grace_period_expiry_date"), "Grace period expires",
            "LH_NON_TRD_POL / LH_TRD_POL.GRA_PER_EXP_DT", "Status")

    tamra_start = _as_date(read.get("tamra_start", lambda p: p.data_item(
        "LH_TAMRA_7_PY_PER", "SVPY_PER_STR_DT")))
    if tamra_start:
        add(tamra_start, "7-pay period starts", "LH_TAMRA_7_PY_PER.SVPY_PER_STR_DT", "Tax")
        add(_add_years(tamra_start, 7), "7-pay period ends (start + 7 years)",
            "Derived from LH_TAMRA_7_PY_PER.SVPY_PER_STR_DT", "Tax")

    for cov in read.get("coverages", lambda p: p.get_coverages()) or []:
        name = f"Coverage {cov.cov_pha_nbr} ({cov.plancode})"
        add(cov.issue_date, f"{name} issued" if cov.cov_pha_nbr != 1 else f"Policy issued · {name}",
            "LH_COV_PHA.ISSUE_DT", "Coverage")
        add(getattr(cov, "maturity_date", None), f"{name} matures", "LH_COV_PHA.COV_MT_EXP_DT", "Coverage")
        add(getattr(cov, "terminate_date", None), f"{name} terminated", "LH_COV_PHA.TMN_DT", "Coverage")
        if getattr(cov, "table_rating", None):
            add(getattr(cov, "table_cease_date", None), f"{name} table rating ceases",
                "LH_SST_XTR_CRG.SST_XTR_CEA_DT", "Rating")
        if getattr(cov, "flat_extra", None):
            add(getattr(cov, "flat_cease_date", None), f"{name} flat extra ceases",
                "LH_SST_XTR_CRG.SST_XTR_CEA_DT", "Rating")
    for bnf in read.get("benefits", lambda p: p.get_benefits()) or []:
        name = f"Benefit {bnf.benefit_code} (phase {bnf.cov_pha_nbr})"
        add(getattr(bnf, "issue_date", None), f"{name} issued", "LH_SPM_BNF.BNF_ISS_DT", "Benefit")
        add(getattr(bnf, "pay_up_date", None), f"{name} pays up", "LH_SPM_BNF.BNF_PAY_UP_DT", "Benefit")
        add(bnf.cease_date, f"{name} ceases", "LH_SPM_BNF.BNF_CEA_DT", "Benefit")

    events.sort(key=lambda e: (e.when, e.label))
    return events


def relative_text(when: date, today: date) -> str:
    days = (when - today).days
    if days == 0:
        return "today"
    span = abs(days)
    if span < 60:
        text = f"{span} day{'s' if span != 1 else ''}"
    elif span < 730:
        text = f"{round(span / 30.44)} months"
    else:
        text = f"{span / 365.25:.1f} years"
    return f"in {text}" if days > 0 else f"{text} ago"
