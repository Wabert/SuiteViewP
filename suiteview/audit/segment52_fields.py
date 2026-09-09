"""Requested application/conversion fields on the 52-G user segment."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Segment52Field:
    name: str
    label: str
    kind: Literal["date", "decimal", "integer", "text"]


# Column names verified against live CKPR metadata (2026-09-08).
# These are policy user fields, not the similarly named TH_USER_PDF rules.
SEGMENT52_FIELDS = (
    Segment52Field("APP_RECEIVED_DATE", "Application received date", "date"),
    Segment52Field("SRC_CONV_EXP_DT", "Source conversion expiry date", "date"),
    Segment52Field("SOURCE_PLAN_CODE", "Source plan code", "text"),
    Segment52Field("SOURCE_PLAN_EFF_DATE", "Source plan effective date", "date"),
    Segment52Field("SOURCE_ISSUE_DATE", "Source issue date", "date"),
    Segment52Field("SOURCE_FACE_AMT", "Source face amount", "decimal"),
    Segment52Field("SOURCE_CNV_CREDIT_IND", "Source conversion credit indicator", "text"),
    Segment52Field("CONV_CREDIT_AMT", "Conversion credit amount", "decimal"),
    Segment52Field("CONV_CREDIT_PERIOD", "Conversion credit period", "integer"),
    Segment52Field("CONV_TO_TRM_PERIOD", "Conversion to term period", "integer"),
    Segment52Field("CONV_FACE_AMT", "Conversion face amount", "decimal"),
)
