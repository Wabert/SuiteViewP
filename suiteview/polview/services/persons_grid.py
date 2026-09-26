"""Persons-tab view model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import platform
from typing import Callable

US_DATE_FMT = "%#m/%d/%Y" if platform.system() == "Windows" else "%-m/%d/%Y"


def _format_date(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime(US_DATE_FMT)
    text = str(value).strip()
    if text in ("", "None", "Null", "0"):
        return ""
    try:
        if len(text) >= 10 and "-" in text:
            return datetime.strptime(text[:10], "%Y-%m-%d").strftime(US_DATE_FMT)
    except ValueError:
        pass
    return text


PERSON_CODES = {
    "00": "Primary Insured",
    "01": "Joint insured",
    "10": "Owner",
    "20": "Payor",
    "30": "Beneficiary",
    "40": "Spouse",
    "50": "Dependent",
    "60": "Other",
    "70": "Assignee",
    "A0": "Power of attorney",
    "A1": "Financial advisor",
    "A2": "Third party administrator (TPA)",
    "A3": "Certified public accountant (CPA)",
    "A4": "Plan sponsor",
    "A5": "Conservator",
    "A6": "Domestic partner",
    "A7": "Legal guardian",
    "A8": "Trustee",
}


def _first_name(person: dict, names: dict) -> str:
    first = names.get("CK_FST_NM", "") or person.get("FST_NM", person.get("CK_FST_NM", ""))
    return str(first).strip() if first else ""


def _last_name(person: dict, names: dict) -> str:
    last = names.get("CK_LST_NM", "") or person.get("LST_NM", person.get("CK_LST_NM", ""))
    return str(last).strip() if last else ""


def _suffix(person: dict, names: dict) -> str:
    suffix = names.get("CK_NM_SFX", "") or person.get("NM_SFX", person.get("CK_NM_SFX", ""))
    return str(suffix).strip() if suffix else ""


PERSON_VALUE_GETTERS: dict[str, Callable[[dict, dict], str]] = {
    "Effective Date": lambda person, _names: _format_date(person.get("EFF_DT")),
    "Person Code": lambda person, _names: str(person.get("PRS_CD", "")),
    "Description": lambda person, _names: PERSON_CODES.get(str(person.get("PRS_CD", "")), str(person.get("PRS_CD", ""))),
    "Sequence": lambda person, _names: str(person.get("PRS_SEQ_NBR", "")),
    "Gender": lambda person, _names: str(person.get("GENDER_CD", "")),
    "Class": lambda person, _names: str(person.get("OCP_CLS_CD", "")),
    "BirthDay": lambda person, _names: _format_date(person.get("BIR_DT")),
    "First Name": _first_name,
    "Last Name": _last_name,
    "Suffix": _suffix,
    "OwnerCode": lambda person, _names: "Owner" if str(person.get("OWN_CD", "")).strip() == "A" else "",
}


ROW_LABELS = tuple(PERSON_VALUE_GETTERS)


@dataclass(frozen=True)
class PersonsGrid:
    headers: list[str]
    rows: list[list[str]]


def build_persons_grid(persons: list[dict], names_list: list[dict]) -> PersonsGrid:
    """Build the transposed Persons grid."""
    headers = ["Data Type"] + [f"Person {index + 1}" for index in range(len(persons))]
    names_data = {index: names for index, names in enumerate(names_list)}
    rows = []
    for label in ROW_LABELS:
        getter = PERSON_VALUE_GETTERS[label]
        rows.append([label] + [
            getter(person, names_data.get(index, {}))
            for index, person in enumerate(persons)
        ])
    return PersonsGrid(headers, rows)
