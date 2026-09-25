"""Field-by-field comparison of two loaded policies' DB2 records.

Typical uses: the same policy in production vs. a test region after a test
run, a policy before vs. after a transaction, or two policies that should be
set up alike. Only tables already loaded for *both* policies are compared;
nothing is queried. Rows are paired by their natural key columns when the
counts match; otherwise the extra/missing rows are listed explicitly.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

# Columns that identify the policy itself and always differ between policies.
IDENTITY_COLUMNS = frozenset({"CK_SYS_CD", "CK_CMP_CD", "TCH_POL_ID", "CK_POLICY_NBR"})

# Columns that order multi-row tables (paired in this order when present).
KEY_HINTS = (
    "COV_PHA_NBR", "PRS_CD", "PRS_SEQ_NBR", "SPM_BNF_TYP_CD", "SPM_BNF_SBY_CD",
    "FND_ID_CD", "TAR_TYP_CD", "PRM_RT_TYP_CD", "SEG_IDX_NBR", "SVPY_YR_NBR",
    "MVRY_DT", "ASOF_DT", "SEQ_NO", "EFF_DT",
)


@dataclass(frozen=True)
class Difference:
    table: str
    row: str
    column: str
    first: str
    second: str


def _text(value) -> str:
    if value is None:
        return "NULL"
    return str(value).strip()


def _rows(data: dict, skip: frozenset) -> tuple[list[str], list[dict]]:
    columns = [c for c in data["columns"] if c not in skip]
    rows = [
        {c: _text(v) for c, v in zip(data["columns"], row) if c not in skip}
        for row in data["rows"]
    ]
    return columns, rows


def _key_columns(columns: Iterable[str]) -> list[str]:
    present = set(columns)
    return [c for c in KEY_HINTS if c in present]


def compare_policies(first: dict, second: dict, *, ignore_identity: bool = True,
                     tables: Iterable[str] | None = None) -> list[Difference]:
    """Differences between two ``cached_tables()`` maps."""
    skip = IDENTITY_COLUMNS if ignore_identity else frozenset()
    names = sorted(set(first) & set(second)) if tables is None else sorted(tables)
    differences: list[Difference] = []
    for table in names:
        if table not in first or table not in second:
            continue
        cols_a, rows_a = _rows(first[table], skip)
        cols_b, rows_b = _rows(second[table], skip)
        columns = list(dict.fromkeys(cols_a + cols_b))
        keys = _key_columns(columns)

        def label(row, index):
            if keys:
                return ", ".join(f"{k}={row.get(k, '')}" for k in keys)
            return f"row {index + 1}"

        if len(rows_a) == len(rows_b):
            order = lambda row: tuple(row.get(k, "") for k in keys) if keys else ()
            if keys:
                rows_a = sorted(rows_a, key=order)
                rows_b = sorted(rows_b, key=order)
            for index, (row_a, row_b) in enumerate(zip(rows_a, rows_b)):
                for column in columns:
                    a, b = row_a.get(column, "(absent)"), row_b.get(column, "(absent)")
                    if a != b:
                        differences.append(Difference(table, label(row_a, index), column, a, b))
            continue

        differences.append(Difference(table, "(row count)", "rows", str(len(rows_a)), str(len(rows_b))))
        signature = lambda row: tuple(row.get(c, "") for c in columns)
        count_a, count_b = Counter(map(signature, rows_a)), Counter(map(signature, rows_b))
        for index, row in enumerate(rows_a):
            sig = signature(row)
            if count_b[sig] > 0:
                count_b[sig] -= 1
                continue
            differences.append(Difference(table, label(row, index), "(whole row)", "present", "missing"))
        count_b = Counter(map(signature, rows_b))
        for index, row in enumerate(rows_b):
            sig = signature(row)
            if count_a[sig] > 0:
                count_a[sig] -= 1
                continue
            differences.append(Difference(table, label(row, index), "(whole row)", "missing", "present"))
    return differences


def only_in(first: dict, second: dict) -> tuple[list[str], list[str]]:
    """Loaded tables that have rows for only one of the policies."""
    has_rows = lambda m, t: bool(m[t]["rows"])
    a = sorted(t for t in first if t not in second and has_rows(first, t))
    b = sorted(t for t in second if t not in first and has_rows(second, t))
    return a, b
