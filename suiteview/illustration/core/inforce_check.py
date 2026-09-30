"""A line of an in-force check: CyberLife's value on the record against SuiteView's own.

Shared by the par whole life and indeterminate premium term In-force Check pages.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

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
