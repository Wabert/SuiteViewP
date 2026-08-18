"""ABR Quote — "Explanation of Benefit" content builder.

This module is the single source of truth for the customer-facing explanation of
how an Accelerated Death Benefit (ABR) offer is calculated. The same structured
document is rendered two ways:

    * ``explanation_to_html(doc)`` — for the on-screen Resources panel.
    * ``explanation_to_docx(doc, out_path)`` — for the "Export to Word" button.

The explanation is written to comprehensively answer the kind of detailed,
itemized disclosure request a policyholder (or their attorney) may send, while
staying inside the boundary of what the company will disclose:

    * DISCLOSED — the calculation method, the published *industry base* mortality
      table, the discount/interest basis, and every dollar amount and deduction
      in the offer (the ABR disclosure statement contemplated by the NAIC
      Accelerated Benefits Model Regulation #620 and good-faith claims practice).
    * NOT DISCLOSED — the individualized *modified* mortality table, the specific
      multipliers/debits, and the medical-director underwriting methodology,
      which are proprietary and confidential actuarial/underwriting work product.
      The actuarial method itself is on file with the Department of Insurance.

Where a precise value from the current quote is available it is injected;
otherwise a ``[Bracketed Placeholder]`` is emitted so the document can be
completed by hand for an ad-hoc request.

NOTE FOR MAINTAINERS: This is customer-facing legal/compliance language. Wording
changes should be cleared with Legal/Compliance and Actuarial before release.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Union

from ..models.abr_data import ABRPolicyData, ABRQuoteResult, MedicalAssessment

# ── Facts used in the explanation, sourced from the ABR forms and memoranda ──
# See docs/ABRQuote/. Form numbers and filing references are intentionally kept
# out of the customer-facing wording (this is a plain-language explanation, not
# a contract citation), but are noted here for maintainers.

# Chronic and Critical riders: the underlying standard-risk table is a 75%
# multiple of the 2008 VBT, then modified with an individualized table rating
# and/or flat extra derived from the health evaluation.
BASE_TABLE_CHRONIC_CRITICAL = (
    "a 75% multiple of the 2008 Valuation Basic Table (VBT), a standard industry "
    "mortality table that reflects sex and smoking status (Male/Female, "
    "Smoker/Nonsmoker)"
)
# Terminal rider: a mortality table for terminally ill insureds.
BASE_TABLE_TERMINAL = (
    "a mortality table for terminally ill insureds, under which the chance of "
    "death is 500 per 1,000 (50%) in each policy year"
)
MORTALITY_SOURCE = "the 2008 VBT is published by the Society of Actuaries"
MORTALITY_IMPROVEMENT_TEXT = "1% per year, up to attained age 105"
INTEREST_RATE_RULE = (
    "based on the Moody's Corporate Bond Yield Average \u2014 the same published "
    "index we use to set the maximum policy loan interest rate on the policy. We "
    "apply that same rate here to bring the future death benefit into today's "
    "dollars"
)
ADMIN_CHARGE_DEFAULT = 250.0
ADMIN_CHARGE_MAX = 500.0
PLACEHOLDER = "[to be completed]"

# Company letterhead / contact block (from the reference claims letter).
LETTERHEAD = [
    "AMERICAN NATIONAL INSURANCE COMPANY",
    "Life Insurance & Annuity Claims Department   P.O. Box 10466, Springfield, MO 65808-0466",
    "TEL: (800) 615-7372    FAX: (281) 538-6757",
]
CONTACT_PHONE = "(800) 615-7372"

# Rider-type → human-readable label (no form numbers in customer-facing text).
_RIDER_LABELS = {
    "terminal": "terminal illness",
    "chronic": "chronic illness",
    "critical": "critical illness",
}


# ── Structured document model ───────────────────────────────────────────────
@dataclass
class Para:
    """A body paragraph."""
    text: str
    bold: bool = False
    italic: bool = False


@dataclass
class Bullets:
    """A bulleted list."""
    items: List[str] = field(default_factory=list)


@dataclass
class WorksheetRow:
    label: str
    value: str
    emphasis: bool = False


@dataclass
class Worksheet:
    """A two-column label/value calculation worksheet."""
    rows: List[WorksheetRow] = field(default_factory=list)


@dataclass
class Note:
    """A set-apart callout (used for confidentiality / boundary statements)."""
    text: str


Block = Union[Para, Bullets, Worksheet, Note]


@dataclass
class Section:
    heading: str
    blocks: List[Block] = field(default_factory=list)


@dataclass
class ExplanationDoc:
    title: str
    subtitle: str
    sections: List[Section] = field(default_factory=list)
    # Letter framing (claims-letter format). When these are populated the
    # document renders as a formal letter rather than a titled report.
    letterhead: List[str] = field(default_factory=list)
    letter_date: str = ""
    recipient: List[str] = field(default_factory=list)
    re_lines: List[str] = field(default_factory=list)
    salutation: str = ""
    closing: str = ""
    signer: str = ""
    signer_title: str = ""
    cc_lines: List[str] = field(default_factory=list)


# ── Formatting helpers ──────────────────────────────────────────────────────
def _money(value: Optional[float]) -> str:
    if value is None:
        return PLACEHOLDER
    try:
        return f"${value:,.2f}"
    except (TypeError, ValueError):
        return PLACEHOLDER


def _pct(value: Optional[float], decimals: int = 2) -> str:
    if value is None:
        return PLACEHOLDER
    try:
        return f"{value * 100:.{decimals}f}%"
    except (TypeError, ValueError):
        return PLACEHOLDER


def _rate_pct(value: Optional[float], decimals: int = 3) -> str:
    """A rate already expressed as a fraction (e.g. 0.0545) → '5.450%'."""
    if not value:
        return PLACEHOLDER
    try:
        return f"{value * 100:.{decimals}f}%"
    except (TypeError, ValueError):
        return PLACEHOLDER


def _fmt_date(d: Optional[date]) -> str:
    return d.strftime("%B %d, %Y") if d else PLACEHOLDER


# ── Builder ─────────────────────────────────────────────────────────────────
def build_explanation(
    policy: Optional[ABRPolicyData] = None,
    result: Optional[ABRQuoteResult] = None,
    assessment: Optional[MedicalAssessment] = None,
    level_annual_premium: Optional[float] = None,
    eligible_db_override: Optional[float] = None,
) -> ExplanationDoc:
    """Build the Accelerated Benefit explanation as a formal claims letter.

    All arguments are optional. When a quote object is missing, its values are
    rendered as ``[to be completed]`` placeholders so the document remains a
    usable template for a manual response.

    ``level_annual_premium`` is the user-entered UL annual level premium (used to
    fund the coverage to maturity); when provided for a UL-type product, the
    letter explains how the future premiums were determined.

    ``eligible_db_override`` is the user-entered Eligible Death Benefit (e.g.
    Option B policies where the death benefit is face plus account value). When
    it differs from the quoted eligible DB, all dollar figures are rescaled
    proportionally — the same way the on-screen Full Acceleration recalc does.
    The letter always presents a full acceleration of that amount.
    """
    p = policy
    r = result

    policy_number = (p.policy_number if p and p.policy_number else PLACEHOLDER)
    quote_date = _fmt_date(r.quote_date if r else None)
    insured_name = (p.insured_name.strip() if p and p.insured_name else "")

    # ── Rider type drives the mortality basis and wording ──────────────
    rider_key = ""
    if assessment and assessment.rider_type:
        rider_key = assessment.rider_type.strip().lower()
    is_terminal = rider_key.startswith("terminal")
    is_chronic = rider_key.startswith("chronic")
    is_critical = rider_key.startswith("critical")
    rider_label = _RIDER_LABELS.get(
        "terminal" if is_terminal else
        "chronic" if is_chronic else
        "critical" if is_critical else "", "",
    )

    # ── UL-type products fund to maturity with a level annual premium ──
    is_ul = bool(p and p.product_type and
                 p.product_type.upper() in ("UL", "IUL", "VUL", "ISWL"))
    is_term = bool(p and p.product_type and p.product_type.upper() == "TERM")

    # ── Derived amounts for the worksheet (always full acceleration) ───
    eligible_db = r.full_eligible_db if r else None
    admin_fee = (r.full_admin_fee if r and r.full_admin_fee else ADMIN_CHARGE_DEFAULT)
    loan_repay = r.full_loan_repayment if r else None
    payable = r.full_accelerated_benefit if r else None  # greater of calc & surrender
    surrender = r.full_surrender_value if r else None
    pv_benefits = r.apv_fb if r else None
    pv_premiums = r.apv_fp if r else None
    pv_dividends = r.apv_fd if r else None
    interest_rate = r.abr_interest_rate if r else None

    # User-entered Eligible Death Benefit — rescale everything proportionally,
    # the same way the on-screen Full Acceleration recalc does.
    overridden = bool(
        r and eligible_db_override and eligible_db
        and abs(eligible_db_override - eligible_db) >= 0.01
    )
    if overridden:
        ratio = eligible_db_override / eligible_db
        eligible_db = eligible_db_override
        loan_repay = round(loan_repay * ratio, 2) if loan_repay else loan_repay
        surrender = round(surrender * ratio, 2) if surrender else surrender
        pv_benefits = (pv_benefits or 0.0) * ratio
        pv_premiums = (pv_premiums or 0.0) * ratio
        pv_dividends = (pv_dividends or 0.0) * ratio
    accelerated_amount = eligible_db  # full acceleration is the standard quote

    # Value today of the accelerated benefit = PVFB - PVFP + PVFDivs, then the
    # calculated benefit is that net present value less the admin fee and any
    # policy loan. Computed here so the worksheet reconciles exactly on the page.
    net_pv = None
    calc_benefit = None
    if r:
        net_pv = (pv_benefits or 0.0) - (pv_premiums or 0.0) + (pv_dividends or 0.0)
        calc_benefit = round(net_pv - admin_fee - (loan_repay or 0.0), 2)
    if overridden and calc_benefit is not None:
        payable = round(max(max(0.0, calc_benefit), surrender or 0.0), 2)

    # Actuarial discount (rider definition: amount accelerated minus its value
    # today), stated explicitly as a worksheet line.
    discount = (None if overridden else (r.full_actuarial_discount if r else None))
    if discount is None and accelerated_amount is not None and net_pv is not None:
        discount = round(accelerated_amount - net_pv, 2)
    accel_pct = (accelerated_amount / eligible_db
                 if accelerated_amount and eligible_db else None)

    doc = ExplanationDoc(
        title="How Your Accelerated Benefit Was Determined",
        subtitle=(
            f"Policy {policy_number}"
            + (f"   \u2022   Accelerated benefit for {rider_label}" if rider_label else "")
            + (f"   \u2022   Prepared {quote_date}" if r else "")
        ),
        letterhead=list(LETTERHEAD),
        letter_date=(quote_date if r else PLACEHOLDER),
        recipient=[
            insured_name if insured_name else "[Policyholder Name]",
            "[Street Address]",
            "[City, State  ZIP]",
        ],
        re_lines=[f"RE:  Accelerated Benefit    Policy: {policy_number}"],
        salutation=(f"Dear {insured_name}:" if insured_name
                    else "Dear [Policyholder Name]:"),
        closing="Sincerely,",
        signer="[Claims Specialist Name]",
        signer_title="Claims Specialist",
        cc_lines=["cc:  Agent \u2013 [Agent Name]"],
    )

    # ── Letter body (claims-letter flow with short section headings) ────

    # Opening — state the letter's purpose.
    doc.sections.append(Section("", [
        Para(
            "This letter responds to your questions regarding the Accelerated "
            "Benefit available under your policy and explains how the benefit "
            "amount was determined."
        ),
        Para(
            "The calculation involves several actuarial components. The "
            "sections below describe each of them and show the figures used in "
            "this determination."
        ),
    ]))

    # Why qualifying ≠ amount — the heart of the explanation.
    why_blocks: List[Block] = [
        Para(
            "The Accelerated Death Benefit Rider is not a disability or "
            "income-replacement benefit. It is an early payment of the policy's "
            "death benefit: when the rider's eligibility conditions are met, a "
            "portion of the death benefit that would otherwise be paid in the "
            "future can be paid now, reduced by an actuarial discount that "
            "reflects how early it is being paid."
        ),
    ]
    if not is_terminal:
        why_blocks.append(Para(
            "Eligibility and amount are therefore determined by different "
            "things. Eligibility depends on the condition described in the "
            "rider. The amount, however, depends on how significantly the "
            "insured's condition affects expected mortality — the likelihood "
            "and timing of death — because that is what determines how early "
            "the death benefit is being paid. Some conditions profoundly "
            "affect daily functioning (morbidity) while having only a modest "
            "effect on expected mortality. In those situations the "
            "rider's conditions for making a claim are met, but the actuarial "
            "value of paying the death benefit early is small."
        ))
    why_blocks.append(Para(
        "The sooner the death benefit is expected to be paid, the less it "
        "must be reduced for being paid early, and the larger the amount that "
        "can be advanced today. Conversely, when expected mortality changes "
        "only modestly, the benefit is expected further in the future, a "
        "larger reduction applies, and the accelerated amount is smaller."
    ))
    doc.sections.append(Section(
        "Why qualifying for the benefit does not itself determine the amount",
        why_blocks,
    ))

    # Eligibility + the modified mortality table.
    if is_terminal:
        mortality_blocks = [
            Para(
                "As part of the accelerated benefit calculation, we use a mortality "
                f"table built for terminally ill insureds \u2014 {BASE_TABLE_TERMINAL}. "
                "This table reflects a condition expected to significantly affect "
                "mortality, and it is what drives the present-value calculation "
                "described below."
            ),
        ]
    else:
        mortality_blocks = [
            Para(
                "As part of the accelerated benefit calculation, underwriting "
                "factors are applied to a standard industry mortality table to "
                "develop a modified mortality table specific to the insured. Based "
                "on the medical documentation we received, our Medical Director's "
                "Office reviewed the insured's condition and developed the modified "
                "mortality table used in this calculation."
            ),
            Para(
                "We begin with a standard industry mortality table \u2014 "
                f"{BASE_TABLE_CHRONIC_CRITICAL} ({MORTALITY_SOURCE}) \u2014 and "
                f"apply a mortality-improvement adjustment of "
                f"{MORTALITY_IMPROVEMENT_TEXT}. Our Medical Director's Office then "
                "adjusts that table to reflect the insured's specific condition. "
                "This modified mortality table is the primary driver of the "
                "calculation: it sets the year-by-year likelihood of the claim, "
                "which in turn determines the present value of the future death "
                "benefit and the future premiums."
            ),
        ]
    doc.sections.append(Section(
        "The mortality basis used in the calculation", mortality_blocks))

    # Under the terms of the rider — deductions and discount factors.
    doc.sections.append(Section(
        "The rider provisions that govern the calculation", [
        Para(
            "Under the terms of the rider, the Accelerated Death Benefit equals "
            "the portion of the Eligible Death Benefit requested, less the "
            "following deductions:"
        ),
        Bullets([
            "The actuarial discount (see details below);",
            f"An administrative charge (currently ${admin_fee:,.0f}, "
            f"not to exceed ${ADMIN_CHARGE_MAX:,.0f}); and,",
            "Any outstanding policy debt, if the qualifying insured is "
            "also the base policy insured.",
        ]),
        Para(
            "The Accelerated Death Benefit for the base policy insured will never "
            "be less than the cash surrender value of the base policy, if any."
        ),
        Para("A copy of the rider is available to you at any time on request."),
    ]))

    # The actuarial-discount explanation (brief, approved wording).
    pv_blocks: List[Block] = [
        Para(
            "The actuarial discount is the Eligible Death Benefit less the "
            "value today — the present value — of the benefit being "
            "accelerated:"
        ),
        Para("Actuarial Discount  =  Eligible Death Benefit  \u2212  Value Today",
             bold=True),
        Para(
            "The value today is built from three present-value components:"
        ),
        Bullets([
            "Present Value of Future Benefits (PVFB) \u2014 today's value of the "
            "death benefit that would otherwise be paid in the future.",
            "Present Value of Future Premiums (PVFP) \u2014 today's value of the "
            "future premiums needed to keep this policy in force to maturity.",
            "Present Value of Future Dividends (PVFDivs) \u2014 today's value of "
            "any future dividends the policy would have paid (zero for policies "
            "that do not pay dividends).",
        ]),
        Para("Value Today  =  PVFB  \u2212  PVFP  +  PVFDivs", bold=True),
        Para(
            "In plain terms: we start with today's value of the future death "
            "benefit, subtract today's value of the future premiums that would "
            "have been required to keep it in force, and add back today's value of "
            "any future dividends. From the value today we then subtract the "
            "administrative fee and any outstanding policy debt to arrive at "
            "the amount payable — subject to the cash-surrender-value minimum "
            "described above."
        ),
    ]
    if is_ul:
        lvl = (level_annual_premium if level_annual_premium
               else None)
        lvl_text = _money(lvl) if lvl else "[Annual Level Premium]"
        pv_blocks.append(Para(
            "For this universal life policy, the future premiums are "
            "determined by calculating a level annual premium that keeps the "
            "policy in force to maturity, using the same interest rate applied "
            "elsewhere in this calculation. For this quote, that annual "
            f"premium was determined to be {lvl_text}."
        ))
    elif is_term:
        pv_blocks.append(Para(
            "For this term policy, no separate premium calculation is needed: "
            "the future premiums used in this calculation are the premiums "
            "already scheduled under the policy's premium schedule for the "
            "remainder of the term."
        ))
    doc.sections.append(Section("How the actuarial discount is calculated", pv_blocks))

    # Interest rate (Moody's basis + the rider's contractual cap).
    doc.sections.append(Section("The interest rate", [
        Para(
            "Because a future benefit is being paid early, an interest rate is "
            "used to express future amounts in today's dollars. For this "
            f"calculation the rate is {_rate_pct(interest_rate)}, "
            f"{INTEREST_RATE_RULE}. Under the rider, this rate may not exceed "
            "the greater of the yield on 90-day Treasury Bills on the election "
            "date or the maximum adjustable policy loan interest rate allowed "
            "by law."
        ),
    ]))

    # The numbers.
    doc.sections.append(Section("Summary of this calculation", [
        Para(
            "The figures behind this determination are summarized below. They "
            "show the key present-value components and how the accelerated "
            "benefit follows from them:"
        ),
        Worksheet([
            WorksheetRow("Eligible Death Benefit", _money(eligible_db)),
            WorksheetRow("Portion requested for acceleration",
                         _pct(accel_pct, 1) if accel_pct is not None else PLACEHOLDER),
            WorksheetRow("Death benefit being accelerated", _money(accelerated_amount)),
            WorksheetRow("Present Value of Future Benefits (PVFB)", _money(pv_benefits)),
            WorksheetRow("Less: Present Value of Future Premiums (PVFP)", _money(pv_premiums)),
            WorksheetRow("Plus: Present Value of Future Dividends (PVFDivs)", _money(pv_dividends)),
            WorksheetRow("Value today of the accelerated benefit", _money(net_pv)),
            WorksheetRow("Actuarial discount (amount accelerated \u2212 value today)",
                         _money(discount)),
            WorksheetRow("Less: Administrative Fee", _money(admin_fee)),
            WorksheetRow("Less: outstanding policy loan, if any", _money(loan_repay)),
            WorksheetRow("Calculated accelerated benefit", _money(calc_benefit)),
            WorksheetRow("Policy's current cash surrender value", _money(surrender)),
            WorksheetRow("Accelerated benefit payable (the greater of the two above)",
                         _money(payable), emphasis=True),
        ]),
    ]))

    # A note on the information in this letter (cooperative confidentiality).
    doc.sections.append(Section("A note about the information in this letter", [
        Para(
            "A few items \u2014 the individualized modified mortality table, the "
            "specific rating factors, and the internal medical evaluations "
            "behind them \u2014 are kept confidential in the claim file. We handle "
            "them this way to protect the insured's health information, which "
            "these documents reflect throughout, and because they are part of "
            "our internal underwriting and actuarial work. Please know this is "
            "not meant to withhold anything you need to understand the benefit: "
            "the summary above contains every figure used to arrive at the "
            "amount offered, and the actuarial methodology for this rider is on "
            "file with the insurance regulator as part of the approved form "
            "filing."
        ),
    ]))

    # Additional information (brief, service-oriented; avoids inviting disputes).
    doc.sections.append(Section("Additional medical information", [
        Para(
            "Our goal is for the determination to reflect a complete picture of "
            "the insured's health. If there is additional medical information "
            "you would like us to consider, you are welcome to send it to us, "
            "and we will review it."
        ),
    ]))

    # Required notices (NAIC Model Reg #620 §6.D).
    doc.sections.append(Section("", [
        Note(
            "Important notices: Depending on your circumstances, an accelerated "
            "death benefit may be fully or partially excludable from income "
            "under federal tax law (Section 101(g) of the Internal Revenue "
            "Code). Because individual situations vary and the exclusions are "
            "subject to limits, we recommend reviewing the tax treatment with a "
            "personal tax advisor before accepting the benefit. Receipt of an "
            "accelerated benefit may also affect eligibility for means-tested "
            "government programs such as Medicaid or Supplemental Security "
            "Income (SSI); the agency that administers the program can confirm "
            "how a payment would be treated."
        ),
    ]))

    # Close.
    doc.sections.append(Section("", [
        Para(
            "If you have questions about this determination or would like to "
            f"discuss it further, please contact our office at {CONTACT_PHONE}."
        ),
    ]))

    return doc


# ── HTML rendering (on-screen panel) ────────────────────────────────────────
def explanation_to_html(doc: ExplanationDoc) -> str:
    """Render an ExplanationDoc to a styled HTML fragment for QTextEdit."""
    crimson = "#8B1A2A"
    crimson_dark = "#5C0A14"
    slate = "#4A6FA5"
    gray = "#333"
    parts: List[str] = []

    # ── Letter header (letterhead, date, recipient, RE, salutation) ────
    if doc.letterhead:
        parts.append(
            f'<div style="text-align:center;color:{crimson_dark};'
            f'border-bottom:1px solid {slate};padding-bottom:6px;margin-bottom:10px;">'
        )
        for i, line in enumerate(doc.letterhead):
            weight = "font-weight:bold;font-size:13px;" if i == 0 else "font-size:10px;"
            parts.append(f'<div style="{weight}">{line}</div>')
        parts.append("</div>")
    if doc.letter_date:
        parts.append(f'<p style="margin:8px 0;color:{gray};">{doc.letter_date}</p>')
    if doc.recipient:
        parts.append('<div style="margin:8px 0;line-height:1.3;color:%s;">' % gray)
        for line in doc.recipient:
            parts.append(f'<div>{line}</div>')
        parts.append("</div>")
    for line in doc.re_lines:
        parts.append(
            f'<p style="margin:8px 0;font-weight:bold;color:{crimson_dark};">{line}</p>'
        )
    if doc.salutation:
        parts.append(f'<p style="margin:8px 0;color:{gray};">{doc.salutation}</p>')

    # Title/subtitle only shown when there's no letter framing.
    if not doc.letterhead:
        parts.append(
            f'<h2 style="color:{crimson_dark};margin:0 0 2px 0;">{doc.title}</h2>'
        )
        parts.append(
            f'<div style="color:{slate};font-size:11px;margin:0 0 12px 0;">'
            f'{doc.subtitle}</div>'
        )
    for sec in doc.sections:
        if sec.heading:
            parts.append(
                f'<h3 style="color:{crimson};margin:14px 0 4px 0;">{sec.heading}</h3>'
            )
        for block in sec.blocks:
            if isinstance(block, Para):
                style = "margin:4px 0;line-height:1.4;"
                if block.bold:
                    style += "font-weight:bold;"
                if block.italic:
                    style += "font-style:italic;color:#444;"
                parts.append(f'<p style="{style}">{block.text}</p>')
            elif isinstance(block, Bullets):
                parts.append('<ul style="margin:4px 0 4px 18px;line-height:1.4;">')
                for item in block.items:
                    parts.append(f"<li>{item}</li>")
                parts.append("</ul>")
            elif isinstance(block, Worksheet):
                parts.append(
                    '<table cellspacing="0" cellpadding="4" '
                    'style="border-collapse:collapse;margin:6px 0;width:100%;">'
                )
                for row in block.rows:
                    lbl_style = "border-bottom:1px solid #ddd;"
                    val_style = "border-bottom:1px solid #ddd;text-align:right;"
                    if row.emphasis:
                        lbl_style = (
                            f"border-top:2px solid {crimson};font-weight:bold;"
                            f"color:{crimson_dark};"
                        )
                        val_style = (
                            f"border-top:2px solid {crimson};font-weight:bold;"
                            f"text-align:right;color:{crimson_dark};"
                        )
                    parts.append(
                        f'<tr><td style="{lbl_style}">{row.label}</td>'
                        f'<td style="{val_style}">{row.value}</td></tr>'
                    )
                parts.append("</table>")
            elif isinstance(block, Note):
                parts.append(
                    f'<div style="margin:8px 0;padding:8px 10px;'
                    f'background:#F3E6E8;border-left:3px solid {crimson};'
                    f'font-style:italic;color:#333;line-height:1.4;">'
                    f'{block.text}</div>'
                )

    # ── Closing / signature / cc ───────────────────────────────────────
    if doc.closing:
        parts.append(f'<p style="margin:14px 0 2px 0;color:{gray};">{doc.closing}</p>')
    if doc.signer:
        parts.append(
            f'<div style="margin:2px 0;color:{gray};">{doc.signer}</div>'
        )
    if doc.signer_title:
        parts.append(
            f'<div style="margin:0 0 8px 0;color:{gray};">{doc.signer_title}</div>'
        )
    for line in doc.cc_lines:
        parts.append(f'<div style="margin:2px 0;color:{gray};font-size:10px;">{line}</div>')
    return "".join(parts)


# ── Word rendering (export) ─────────────────────────────────────────────────
def explanation_to_docx(doc: ExplanationDoc, out_path: str) -> str:
    """Render an ExplanationDoc to a professional .docx file at ``out_path``.

    Returns the path written. Raises ImportError if python-docx is unavailable.
    """
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    crimson = RGBColor(0x8B, 0x1A, 0x2A)
    crimson_dark = RGBColor(0x5C, 0x0A, 0x14)
    slate = RGBColor(0x4A, 0x6F, 0xA5)
    gray = RGBColor(0x33, 0x33, 0x33)

    document = Document()

    # 0.5-inch margins all around.
    for section in document.sections:
        section.top_margin = Inches(0.5)
        section.bottom_margin = Inches(0.5)
        section.left_margin = Inches(0.5)
        section.right_margin = Inches(0.5)

    # Base style
    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)

    is_letter = bool(doc.letterhead)

    if is_letter:
        # ── Letterhead (centered) ──────────────────────────────────────
        for i, line in enumerate(doc.letterhead):
            lp = document.add_paragraph()
            lp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            lp.paragraph_format.space_after = Pt(0)
            lrun = lp.add_run(line)
            lrun.bold = (i == 0)
            lrun.font.size = Pt(13 if i == 0 else 8.5)
            lrun.font.color.rgb = crimson_dark if i == 0 else gray
        # spacer
        document.add_paragraph()
        # Date
        dp = document.add_paragraph()
        dp.add_run(doc.letter_date).font.color.rgb = gray
        # Recipient
        for line in doc.recipient:
            rp = document.add_paragraph()
            rp.paragraph_format.space_after = Pt(0)
            rp.add_run(line).font.color.rgb = gray
        document.add_paragraph()
        # RE line(s)
        for line in doc.re_lines:
            rep = document.add_paragraph()
            rerun = rep.add_run(line)
            rerun.bold = True
            rerun.font.color.rgb = crimson_dark
        # Salutation
        if doc.salutation:
            sp = document.add_paragraph()
            sp.add_run(doc.salutation).font.color.rgb = gray
    else:
        # Title / subtitle (report format)
        title_p = document.add_paragraph()
        run = title_p.add_run(doc.title)
        run.bold = True
        run.font.size = Pt(17)
        run.font.color.rgb = crimson_dark
        sub_p = document.add_paragraph()
        sub_run = sub_p.add_run(doc.subtitle.replace("\u2022", "|"))
        sub_run.font.size = Pt(10)
        sub_run.font.color.rgb = slate

    for sec in doc.sections:
        if sec.heading:
            head_p = document.add_paragraph()
            head_p.space_before = Pt(10)
            head_run = head_p.add_run(sec.heading)
            head_run.bold = True
            head_run.font.size = Pt(12.5)
            head_run.font.color.rgb = crimson

        for block in sec.blocks:
            if isinstance(block, Para):
                para = document.add_paragraph()
                run = para.add_run(block.text)
                run.bold = block.bold
                run.italic = block.italic
                if block.italic:
                    run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
            elif isinstance(block, Bullets):
                for item in block.items:
                    document.add_paragraph(item, style="List Bullet")
            elif isinstance(block, Worksheet):
                table = document.add_table(rows=0, cols=2)
                table.style = "Light List Accent 1"
                table.autofit = True
                for row in block.rows:
                    cells = table.add_row().cells
                    lbl_run = cells[0].paragraphs[0].add_run(row.label)
                    val_para = cells[1].paragraphs[0]
                    val_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    val_run = val_para.add_run(row.value)
                    if row.emphasis:
                        lbl_run.bold = True
                        val_run.bold = True
                        lbl_run.font.color.rgb = crimson_dark
                        val_run.font.color.rgb = crimson_dark
            elif isinstance(block, Note):
                para = document.add_paragraph()
                para.paragraph_format.left_indent = Inches(0.2)
                run = para.add_run(block.text)
                run.italic = True
                run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

    # ── Closing / signature / cc ───────────────────────────────────────
    if doc.closing:
        document.add_paragraph()
        cp = document.add_paragraph()
        cp.paragraph_format.space_after = Pt(0)
        cp.add_run(doc.closing).font.color.rgb = gray
    if doc.signer:
        document.add_paragraph()  # room for a signature
        sgn = document.add_paragraph()
        sgn.paragraph_format.space_after = Pt(0)
        sgn.add_run(doc.signer).font.color.rgb = gray
    if doc.signer_title:
        tp = document.add_paragraph()
        tp.paragraph_format.space_after = Pt(0)
        tp.add_run(doc.signer_title).font.color.rgb = gray
    if doc.cc_lines:
        document.add_paragraph()
        for line in doc.cc_lines:
            ccp = document.add_paragraph()
            ccp.paragraph_format.space_after = Pt(0)
            ccrun = ccp.add_run(line)
            ccrun.font.size = Pt(9)
            ccrun.font.color.rgb = gray

    document.save(out_path)
    return out_path
