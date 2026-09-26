"""Render the PolicyInformation FieldSpec registry to Markdown."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from suiteview.polview.models.policy_fields import FIELD_SPECS


def main() -> None:
    path = Path("docs") / "polview" / "POLICY_FIELDS.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# PolicyInformation field registry",
        "",
        "Generated from `suiteview.polview.models.policy_fields.FIELD_SPECS`.",
        "Do not hand-edit table rows; update the registry and re-run this script.",
        "",
        "| Property | Table | Column | Converter | Default | Applies to | Required |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
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
