"""Recognise pasted policy references such as ``CKPR - 01 - U0613620``.

Users copy policy identities from everywhere: PolView's own header, policy
support folder names (``01_13034048``), spreadsheets, emails and CyberLife's
technical policy ID (``E0008145  QXXX``). ``parse_policy_reference`` splits such
text into region, company and policy number so the lookup fields can be filled
in one paste.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from suiteview.core.db2_constants import REGION_DSN_MAP

COMPANY_CODES = ("01", "04", "06", "08", "26")
_SEPARATORS = re.compile(r"[\s,;/|_\-·•:()\[\]]+")


@dataclass(frozen=True)
class PolicyReference:
    policy: str
    company: str = ""
    region: str = ""


def has_separator(text: str) -> bool:
    return bool(_SEPARATORS.search((text or "").strip()))


def parse_policy_reference(text: str) -> Optional[PolicyReference]:
    """Return the reference in *text*, or ``None`` if no policy number is found."""
    tokens = [t for t in _SEPARATORS.split((text or "").strip().upper()) if t]
    if not tokens:
        return None
    region = company = policy = ""
    for token in tokens:
        if not region and token in REGION_DSN_MAP:
            region = token
        elif not company and token in COMPANY_CODES:
            company = token
        elif not policy and len(token) >= 5 and any(ch.isdigit() for ch in token):
            policy = token
    if not policy:
        return None
    return PolicyReference(policy, company, region)
