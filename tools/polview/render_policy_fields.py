"""Render the PolicyInformation FieldSpec registry to Markdown."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from suiteview.polview.models.policy_fields import FIELD_SPECS

SECTION_ROWS = (
    ("identity", "Policy/company/system/region identity and lookup state."),
    ("status", "Policy, suspense, premium-pay and grace status."),
    ("product", "Product family, issue state, product rules and tax-test flags."),
    ("billing", "Billing modes, bill form, premiums, fees and short-pay values."),
    ("coverages", "Coverage/rider rows, death benefits and underwriting."),
    ("benefits", "Supplemental benefit rows."),
    ("loans", "Traditional/fund loans, repayments and debt totals."),
    ("values", "Monthliversary values, fund buckets, totals, MEC/TAMRA."),
    ("targets", "MTP/GLP/GSP/GAV/NSP and target accumulators."),
    ("dividends", "Dividend options and OYT/PUA/deposit/applied rows."),
    ("persons", "Persons, insureds and addresses."),
    ("agents", "Writing/servicing agents, branch and market organization."),
    ("activity", "Policy timing and financial transactions."),
    ("rates", "Renewal-rate lookups and UL/WL/fixed-premium matrices."),
    ("support", "Support-tool export and reinstatement/reinsurance helpers."),
)


def main() -> None:
    path = Path("docs") / "polview" / "POLICY_FIELDS.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# PolicyInformation field registry",
        "",
        "Generated from `suiteview.polview.models.policy_fields.FIELD_SPECS`.",
        "Do not hand-edit table rows; update the registry and re-run this script.",
        "",
        "## Section map",
        "",
        "`PolicyInformation` is a facade returned by",
        "`suiteview.polview.services.policy_service.get_policy_info()`. Scalar",
        "registry entries below are consumed by lazy section objects.",
        "",
        "| Section | Responsibility |",
        "| --- | --- |",
    ]
    for name, description in SECTION_ROWS:
        lines.append(f"| `pi.{name}` | {description} |")
    lines.extend([
        "",
        "## Scalar FieldSpec entries",
        "",
        "| Property | Table | Column | Converter | Default | Applies to | Required |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    for spec in sorted(FIELD_SPECS, key=lambda item: (item.table, item.column, item.name)):
        default = "" if spec.default is None else str(spec.default)
        lines.append(
            "| "
            + " | ".join((
                spec.name,
                spec.table,
                spec.column,
                spec.converter,
                default,
                ", ".join(spec.applies_to),
                "yes" if spec.required else "optional",
            ))
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
