"""Pure summary/clipboard rendering for ABR quotes."""

from __future__ import annotations

from ..models.abr_data import ABRPolicyData, ABRQuoteResult, MedicalAssessment


def fmt_money(amount: float) -> str:
    """Format money exactly as the ABR email summary expects."""
    if amount < 0:
        return f"(${abs(amount):,.2f})"
    return f"${amount:,.2f}"


def _time_in_force(policy: ABRPolicyData) -> str:
    total_months = (policy.policy_year - 1) * 12 + policy.policy_month
    years, months = total_months // 12, total_months % 12
    if years and months:
        return f"{years} years, {months} months"
    if years:
        return f"{years} years"
    return f"{months} months"


def _substandard_text(assessment: MedicalAssessment) -> str:
    if assessment.rider_type == "Terminal":
        return "50% mortality each year"
    sub_parts = []
    if (
        assessment.use_five_year
        and assessment.use_ten_year
        and (
            assessment.derived_table_rating_5yr > 0
            or assessment.derived_table_rating_10yr > 0
        )
    ):
        if assessment.derived_table_rating_5yr > 0:
            sub_parts.append(
                f"Table {assessment.derived_table_rating_5yr:.2f} (yrs 1-5)"
            )
        if assessment.derived_table_rating_10yr > 0:
            sub_parts.append(
                f"Table {assessment.derived_table_rating_10yr:.2f} (yrs 6-10)"
            )
    elif assessment.derived_table_rating > 0:
        sub_parts.append(f"Table {assessment.derived_table_rating:.2f}")
    if assessment.use_increased_decrement and assessment.direct_increased_decrement > 0:
        sub_parts.append(
            f"ID {assessment.direct_increased_decrement:.0f}% "
            f"(yr {assessment.incr_decrement_start_year}-"
            f"{assessment.incr_decrement_stop_year})"
        )
    return "  |  ".join(sub_parts) if sub_parts else "None"


def build_summary_sections(
    policy: ABRPolicyData | None,
    result: ABRQuoteResult | None,
    assessment: MedicalAssessment | None,
) -> list[tuple[str, list[tuple[str, str]]]]:
    """Collect label/value pairs grouped by titled summary section."""
    sections: list[tuple[str, list[tuple[str, str]]]] = []
    sec1: list[tuple[str, str]] = []
    if result:
        sec1.append((
            "Quote Date:",
            result.quote_date.strftime("%m/%d/%Y") if result.quote_date else "—",
        ))
    if policy:
        sec1.append(("Policy Number:", policy.policy_number))
    if result:
        sec1.append(("Product:", result.plan_description or (policy.plan_code if policy else "—")))
    if assessment:
        sec1.append(("Acceleration:", assessment.rider_type))
    if sec1:
        sections.append(("Policy", sec1))

    if policy:
        sections.append(("Coverage", [
            ("Issue Age:", str(policy.issue_age)),
            ("Issue Date:", policy.issue_date.strftime("%m/%d/%Y") if policy.issue_date else "—"),
            ("Time in Force:", _time_in_force(policy)),
        ]))

    sec3: list[tuple[str, str]] = []
    if policy:
        sec3.append(("Attained Age:", str(policy.attained_age)))
    if assessment:
        sec3.extend([
            ("5 Yr. Survival Rate:", f"{assessment.computed_survival_5yr * 100:.1f}%"),
            ("10 Yr. Survival Rate:", f"{assessment.computed_survival_10yr * 100:.1f}%"),
            ("Life Expectancy in Years:", f"{assessment.computed_le:.1f}"),
            ("Substandard to achieve mortality:", _substandard_text(assessment)),
        ])
    if sec3:
        sections.append(("Assessment", sec3))

    sec4: list[tuple[str, str]] = []
    if result:
        full_benefit = max(result.full_accel_benefit, 0)
        full_ratio = result.full_benefit_ratio if result.full_accel_benefit >= 0 else 0.0
        sec4.append(("Calculated Benefit:", fmt_money(full_benefit)))
        sec4.append(("Benefit Ratio (Accl Ben/Full DB):", f"{full_ratio * 100:.2f}%"))
        if result.full_surrender_value > 0:
            sec4.append(("Surrender Value:", fmt_money(result.full_surrender_value)))
            sec4.append(("Accelerated Benefit:", fmt_money(result.full_accelerated_benefit)))
    sec4.append(("Reinsurers:", policy.reinsurers if policy and policy.reinsurers else "(none)"))
    if sec4:
        sections.append(("Result", sec4))

    if result and result.messages:
        sections.append(("Warnings", [("", f"• {msg}") for msg in result.messages]))
    return sections


def build_clipboard_html(sections: list[tuple[str, list[tuple[str, str]]]]) -> str:
    """Build HTML table for Outlook/email clients."""
    hdr_bg = "#5C0A14"
    hdr_fg = "#FFFFFF"
    sec_bg = "#F2E6E8"
    sec_fg = "#5C0A14"
    label_fg = "#4A5568"
    value_fg = "#1A202C"
    border_c = "#D4A0A8"

    html = (
        '<html><head><meta charset="utf-8"></head><body>'
        '<table style="border-collapse:collapse; font-family:Calibri,Arial,sans-serif;'
        f' font-size:11pt; border:1px solid {border_c}; min-width:420px;">'
        f'<tr><td colspan="2" style="background:{hdr_bg}; color:{hdr_fg};'
        ' font-weight:bold; font-size:13pt; padding:8px 12px;">ABR Quote Summary</td></tr>'
    )
    for title, pairs in sections:
        html += (
            f'<tr><td colspan="2" style="background:{sec_bg}; color:{sec_fg};'
            f' font-weight:bold; font-size:10pt; padding:5px 12px;'
            f' border-top:1px solid {border_c}; border-bottom:1px solid {border_c};">{title}</td></tr>'
        )
        is_warn = title == "Warnings"
        for label, value in pairs:
            val_color = "#CC0000" if is_warn else value_fg
            val_align = "left" if is_warn else "right"
            html += (
                f'<tr>'
                f'<td style="padding:3px 12px; color:{label_fg}; white-space:nowrap;'
                f' border-bottom:1px solid #EDF2F7;">{label}</td>'
                f'<td style="padding:3px 12px; font-weight:bold; color:{val_color};'
                f' text-align:{val_align}; white-space:nowrap;'
                f' border-bottom:1px solid #EDF2F7;">{value}</td>'
                f'</tr>'
            )
    html += '</table></body></html>'
    return html


def build_clipboard_text(sections: list[tuple[str, list[tuple[str, str]]]]) -> str:
    """Build plain-text fallback for non-HTML targets."""
    all_pairs = [pair for _, pairs in sections for pair in pairs]
    label_w = max((len(label) for label, _ in all_pairs), default=0)
    value_w = max((len(value) for _, value in all_pairs), default=0)
    total_w = label_w + value_w + 4

    lines: list[str] = []
    lines.append("ABR Quote Summary")
    lines.append("=" * total_w)
    for title, pairs in sections:
        lines.append("")
        if title:
            lines.append(f"— {title} —")
        is_warn = title == "Warnings"
        for label, value in pairs:
            if is_warn:
                lines.append(f"  {label:<{label_w}}  {value}")
            else:
                lines.append(f"  {label:<{label_w}}  {value:>{value_w}}")
    return "\n".join(lines)


def render_quote_summary(
    policy: ABRPolicyData | None,
    result: ABRQuoteResult | None,
    assessment: MedicalAssessment | None,
) -> tuple[list[tuple[str, list[tuple[str, str]]]], str, str]:
    """Return sections, HTML and text for an ABR quote summary."""
    sections = build_summary_sections(policy, result, assessment)
    return sections, build_clipboard_html(sections), build_clipboard_text(sections)
