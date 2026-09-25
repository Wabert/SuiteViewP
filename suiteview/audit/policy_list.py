"""
Policy lists pasted from the clipboard — the most common query starting point.

A user copies policy numbers (usually with company codes) from a spreadsheet and
wants more data about them. This module turns the pasted text into a small
in-query table (a "policy list") whose columns join straight onto
``LH_BAS_POL``: ``PolicyNumber`` → ``CK_POLICY_NBR``, ``CompanyCode`` →
``CK_CMP_CD`` and ``SystemCode`` → ``CK_SYS_CD``. Any other pasted columns come
along unchanged so they appear beside the looked-up data.

Values are normalized the way DB2 stores them, and anything that could silently
lose a match is reported rather than guessed:

* policy numbers are trimmed and upper-cased;
* one-digit company codes regain their leading zero (Excel turns ``01`` into
  ``1``); unknown company codes are reported;
* all-digit policy numbers of different lengths are reported, because Excel
  also drops their leading zeros. Padding them is an explicit user choice.

Pure Python — no Qt — so the parsing rules are unit-testable.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

POLICY_COLUMN = "PolicyNumber"
COMPANY_COLUMN = "CompanyCode"
SYSTEM_COLUMN = "SystemCode"
KNOWN_COMPANY_CODES = ("01", "04", "06", "08", "26")
DEFAULT_LIST_NAME = "PolicyList"

# Normalized header names recognized for each role (see normalize_name).
POLICY_ALIASES = frozenset({
    "policy", "policies", "policyid", "policynumber", "policynbr", "policyno",
    "policynum", "polnbr", "polno", "polnum", "pol", "polid", "ckpolicynbr",
    "contract", "contractnumber", "contractno", "certificate",
})
COMPANY_ALIASES = frozenset({
    "company", "companycode", "companycd", "companyid", "co", "cocode", "cocd",
    "cmp", "cmpcd", "cmpcode", "ckcmpcd", "comp",
})
SYSTEM_ALIASES = frozenset({"system", "systemcode", "syscd", "syscode", "cksyscd"})

_POLICY_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-]{3,14}$")


def normalize_name(name: str) -> str:
    """Compare column names loosely: ``SLR Output[Policy Id]`` → ``policyid``."""
    text = str(name or "")
    bracket = re.findall(r"\[([^\]]*)\]", text)
    if bracket:
        text = bracket[-1]
    return re.sub(r"[^a-z0-9]", "", text.lower())


def normalize_company(value: str) -> str:
    text = str(value or "").strip().upper()
    if text.isdigit() and len(text) < 2:
        return text.zfill(2)
    return text


def parse_clipboard_text(text: str) -> list[list[str]]:
    """Split pasted text into rows of cells (tab, comma, semicolon or spaces)."""
    lines = [line for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return []
    joined = "\n".join(lines)
    if "\t" in joined:
        rows = [line.split("\t") for line in lines]
    elif "," in joined or ";" in joined:
        delimiter = "," if joined.count(",") >= joined.count(";") else ";"
        rows = list(csv.reader(io.StringIO(joined), delimiter=delimiter))
    else:
        rows = [line.split() for line in lines]
    rows = [[cell.strip() for cell in row] for row in rows]
    rows = [row for row in rows if any(row)]
    width = max((len(row) for row in rows), default=0)
    return [row + [""] * (width - len(row)) for row in rows]


def _role(name: str) -> str:
    norm = normalize_name(name)
    if norm in POLICY_ALIASES:
        return "policy"
    if norm in COMPANY_ALIASES:
        return "company"
    if norm in SYSTEM_ALIASES:
        return "system"
    return ""


def looks_like_header(rows: list[list[str]]) -> bool:
    """Whether the first pasted row holds column names rather than policies."""
    if not rows:
        return False
    first = rows[0]
    if any(_role(cell) for cell in first):
        return True
    if len(rows) < 2:
        return False
    # Names have no digits while the data below them does.
    for col, cell in enumerate(first):
        below = [row[col] for row in rows[1:] if row[col]]
        if cell and not any(ch.isdigit() for ch in cell) and below and all(
                any(ch.isdigit() for ch in value) for value in below):
            return True
    return False


def _is_company_column(values: list[str]) -> bool:
    present = [v for v in values if v]
    return bool(present) and all(
        normalize_company(v) in KNOWN_COMPANY_CODES for v in present)


def guess_columns(rows: list[list[str]], has_header: bool) -> tuple[int, int | None]:
    """(policy column, company column or None) for the pasted grid."""
    if not rows:
        return 0, None
    width = len(rows[0])
    body = rows[1:] if has_header else rows
    policy = company = None
    if has_header:
        for col, name in enumerate(rows[0]):
            role = _role(name)
            if role == "policy" and policy is None:
                policy = col
            elif role == "company" and company is None:
                company = col
    columns = [[row[col] for row in body] for col in range(width)]
    if company is None:
        company = next((col for col in range(width)
                        if col != policy and _is_company_column(columns[col])), None)
    if policy is None:
        def score(col: int) -> float:
            values = [v for v in columns[col] if v]
            if not values:
                return 0.0
            return sum(bool(_POLICY_VALUE.match(v)) for v in values) / len(values)
        candidates = [col for col in range(width) if col != company]
        policy = max(candidates, key=score) if candidates else 0
    return policy, company


@dataclass
class PolicyList:
    """A normalized policy list ready to become an in-query table."""

    columns: list[str]
    rows: list[list[str]]
    blank_policies: int = 0
    duplicates_removed: int = 0
    unknown_companies: list[str] = field(default_factory=list)
    blank_companies: int = 0
    numeric_lengths: tuple[int, int] | None = None

    @property
    def policy_count(self) -> int:
        return len(self.rows)

    def warnings(self) -> list[str]:
        notes: list[str] = []
        if self.numeric_lengths:
            shortest, longest = self.numeric_lengths
            notes.append(
                f"Some all-digit policy numbers have only {shortest} digits while others "
                f"are {longest} characters — Excel may have dropped leading zeros. Tick "
                "\"Restore leading zeros\" if they should all be the same length.")
        if self.unknown_companies:
            notes.append("Unknown company codes: " + ", ".join(self.unknown_companies[:8])
                         + (" …" if len(self.unknown_companies) > 8 else ""))
        if self.blank_companies:
            notes.append(f"{self.blank_companies} rows have no company code and "
                         "will not match a policy.")
        if COMPANY_COLUMN not in self.columns:
            notes.append("No company code column: a policy number can exist in more "
                         "than one company, so each may match several policies.")
        return notes

    def summary(self) -> str:
        parts = [f"{self.policy_count} {'policy' if self.policy_count == 1 else 'policies'}"]
        if self.duplicates_removed:
            parts.append(f"{self.duplicates_removed} duplicates removed")
        if self.blank_policies:
            parts.append(f"{self.blank_policies} blank rows skipped")
        return ", ".join(parts)


def _unique(name: str, taken: set[str]) -> str:
    base = name or "Column"
    candidate, index = base, 2
    while candidate.upper() in taken:
        candidate = f"{base}_{index}"
        index += 1
    taken.add(candidate.upper())
    return candidate


def build_policy_list(
    grid: list[list[str]],
    *,
    has_header: bool,
    policy_col: int,
    company_col: int | None,
    system_code: str = "I",
    remove_duplicates: bool = True,
    pad_numeric_to: int | None = None,
) -> PolicyList:
    """Normalize a pasted grid into PolicyNumber / CompanyCode / SystemCode + extras."""
    if not grid:
        return PolicyList(columns=[POLICY_COLUMN], rows=[])
    width = len(grid[0])
    headers = grid[0] if has_header else [f"Column{i + 1}" for i in range(width)]
    body = grid[1:] if has_header else grid

    columns = [POLICY_COLUMN]
    if company_col is not None:
        columns.append(COMPANY_COLUMN)
    if system_code:
        columns.append(SYSTEM_COLUMN)
    taken = {c.upper() for c in columns}
    extras = [col for col in range(width) if col not in (policy_col, company_col)]
    columns.extend(_unique(re.sub(r"\s+", " ", headers[col]).strip() or f"Column{col + 1}",
                           taken) for col in extras)

    result = PolicyList(columns=columns, rows=[])
    seen: set[tuple[str, str]] = set()
    unknown: list[str] = []
    numeric_lengths: set[int] = set()
    for row in body:
        policy = row[policy_col].strip().upper() if policy_col < width else ""
        if not policy:
            result.blank_policies += 1
            continue
        if pad_numeric_to and policy.isdigit():
            policy = policy.zfill(pad_numeric_to)
        if policy.isdigit():
            numeric_lengths.add(len(policy))
        company = normalize_company(row[company_col]) if company_col is not None else ""
        if company_col is not None:
            if not company:
                result.blank_companies += 1
            elif company not in KNOWN_COMPANY_CODES and company not in unknown:
                unknown.append(company)
        key = (policy, company)
        if remove_duplicates and key in seen:
            result.duplicates_removed += 1
            continue
        seen.add(key)
        values = [policy]
        if company_col is not None:
            values.append(company)
        if system_code:
            values.append(system_code)
        values.extend(row[col] for col in extras)
        result.rows.append(values)
    result.unknown_companies = unknown
    longest = max((len(row[0]) for row in result.rows), default=0)
    if numeric_lengths and (len(numeric_lengths) > 1 or min(numeric_lengths) < longest):
        result.numeric_lengths = (min(numeric_lengths), max(max(numeric_lengths), longest))
    return result


def safe_table_name(name: str, taken: set[str]) -> str:
    """A plain identifier for the list table, unique within the query."""
    clean = re.sub(r"[^A-Za-z0-9_]", "_", str(name or "").strip()) or DEFAULT_LIST_NAME
    if clean[0].isdigit():
        clean = f"L_{clean}"
    return _unique(clean, {t.upper() for t in taken})
