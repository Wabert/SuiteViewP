"""A line of an in-force check: CyberLife's value on the record against SuiteView's own.

Shared by the par whole life and indeterminate premium term In-force Check pages.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

TOLERANCE = 0.005


@dataclass(frozen=True)
class CheckLine:
    area: str
    item: str
    cyberlife: Optional[float]
    calculated: Optional[float]
    status: str                  # match / differs / info
    detail: str = ""

    @property
    def difference(self) -> Optional[float]:
        if self.cyberlife is None or self.calculated is None:
            return None
        return round(self.calculated - self.cyberlife, 6)


def check_line(area: str, item: str, cyberlife, calculated, detail: str = "", tolerance: float = TOLERANCE) -> CheckLine:
    """``match`` within ``tolerance``, ``differs`` beyond it, ``info`` when either side is missing."""
    if cyberlife is None or calculated is None:
        return CheckLine(area, item, cyberlife, calculated, "info", detail)
    status = "match" if abs(float(calculated) - float(cyberlife)) < tolerance else "differs"
    return CheckLine(area, item, float(cyberlife), float(calculated), status, detail)


def _amount(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:,.4f}".rstrip("0").rstrip(".")


def rate_check_notice(checks: Sequence[CheckLine], error: str = "", shown: int = 3) -> str:
    """The load-time warning (like UL's monthly deduction check) when any in-force check
    differs from CyberLife or the checks could not run; "" when everything matches."""
    if error:
        return f"In-force rate check could not run: {error}"
    differs = [c for c in checks if c.status == "differs"]
    if not differs:
        return ""
    lines = [f"In-force rate check mismatch: {len(differs)} of {len(checks)} checks differ from "
             "CyberLife. Confirm the rates before illustrating (see the In-force Check tab)."]
    lines += [f"{c.area}: {c.item} - CyberLife {_amount(c.cyberlife)} vs calculated {_amount(c.calculated)}"
              for c in differs[:shown]]
    if len(differs) > shown:
        lines.append(f"... and {len(differs) - shown} more.")
    return "\n".join(lines)
