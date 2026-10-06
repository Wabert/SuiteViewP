"""Plan minimum face on requested face decreases (Robert Haessly, 10/6/2026).

A requested specified-amount decrease, or the face reduction of a DB option A->B
change, may not take the specified amount below the plan's minimum face
(``PlancodeConfig.min_face_after_wd``: CyberLife PDF DBSMIAMT, DBSMIUSE 2). A larger
decrease is limited to the minimum and reported in the run status. A policy already
below the minimum keeps its face; it cannot go lower.

Applies only when the minimum is evidenced (``PlancodeConfig.min_face_evidenced``);
the 58 in-scope plans on the unevidenced 25,000 default take no decrease minimum
until Robert rules on them. Withdrawals keep their own cap
(``withdrawal_handler``: SA - (minimum + fee) under DBO A) on every plan.

An ABR partial acceleration is a benefit payment, not an elective decrease; its
change carries ``PLAN_MINIMUM_EXEMPT_KEY`` and is never limited.
"""
from __future__ import annotations

from typing import Iterable, List, Optional

PLAN_MINIMUM_EXEMPT_KEY = "plan_minimum_exempt"

# Face / DBO change detail keys set on the month a decrease is limited.
FACE_MIN_LIMITED_KEY = "Decrease Limited To Min Face"
FACE_MIN_KEY = "Plan Min Face"
FACE_MIN_REQUESTED_KEY = "Requested Decrease"
FACE_MIN_APPLIED_KEY = "Applied Decrease"

_EPS = 1e-6


def decrease_floor(config, face_before: float, metadata: Optional[dict] = None) -> Optional[float]:
    """Lowest specified amount a requested decrease may reach; None = no minimum.

    ``min(plan minimum, face_before)``: a policy already below the minimum keeps its
    face.
    """
    if not getattr(config, "min_face_evidenced", False):
        return None
    if (metadata or {}).get(PLAN_MINIMUM_EXEMPT_KEY):
        return None
    return min(float(config.min_face_after_wd), float(face_before))


def limited_decrease(config, face_before: float, decrease: float,
                     metadata: Optional[dict] = None) -> float:
    """``decrease`` limited so the face stays at or above ``decrease_floor``."""
    floor = decrease_floor(config, face_before, metadata)
    if floor is None or decrease <= 0.0:
        return decrease
    return max(0.0, min(decrease, float(face_before) - floor))


def record_limit(detail: dict, config, requested: float, applied: float) -> None:
    """Flag a limited decrease on a face/DBO change detail dict."""
    detail[FACE_MIN_LIMITED_KEY] = True
    detail[FACE_MIN_KEY] = float(config.min_face_after_wd)
    detail[FACE_MIN_REQUESTED_KEY] = float(requested)
    detail[FACE_MIN_APPLIED_KEY] = float(applied)


def min_face_notices(states: Iterable) -> List[str]:
    """Run-status notices for every month a face decrease was limited."""
    notices: List[str] = []
    for state in states or ():
        for attr, what in (("face_change_detail", "Face decrease"),
                           ("dbo_change_detail", "DB option change face decrease")):
            detail = getattr(state, attr, None) or {}
            if not detail.get(FACE_MIN_LIMITED_KEY):
                continue
            when = getattr(state, "date", None)
            stamp = when.strftime("%m/%d/%Y") if when is not None else "?"
            notices.append(
                f"{what} on {stamp} limited to the plan minimum face "
                f"${detail[FACE_MIN_KEY]:,.0f}: requested decrease ${detail[FACE_MIN_REQUESTED_KEY]:,.2f}, "
                f"applied ${detail[FACE_MIN_APPLIED_KEY]:,.2f}")
    return notices
