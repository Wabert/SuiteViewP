"""
Join suggestions for the Visual Query canvas.

Knowing *which* fields connect two tables is the hardest step for someone who
doesn't write SQL, and most of the answers are already known:

* **CyberLife tables** share the full policy key — ``CK_SYS_CD``, ``CK_CMP_CD``,
  ``TCH_POL_ID`` (plus ``COV_PHA_NBR`` when both are coverage-level). Joining on
  ``TCH_POL_ID`` alone can silently match the wrong company, so the whole key is
  always suggested together.
* **Policy lists and file datasets** use business names: a ``PolicyId`` /
  ``Policy Number`` column matches ``CK_POLICY_NBR``, a ``Company`` column
  matches ``CK_CMP_CD`` and so on.
* Otherwise, identically named key-like columns (``...ID``, ``...NBR``,
  ``...CODE``) are suggested.

Suggestions are only offered, never applied: the canvas draws them as dashed
lines for the user to accept or dismiss. Pure Python, no Qt.
"""
from __future__ import annotations

from suiteview.audit.policy_list import (
    COMPANY_ALIASES,
    POLICY_ALIASES,
    SYSTEM_ALIASES,
    normalize_name,
)

KIND_DATABASE = "database"
KIND_FILE = "file"
KIND_LIST = "list"

POLICY_KEY = ("CK_SYS_CD", "CK_CMP_CD", "TCH_POL_ID")
COVERAGE_KEY = "COV_PHA_NBR"
_KEY_SUFFIXES = ("id", "nbr", "num", "number", "no", "key", "code", "cd")

# Role → aliases, in the order the keys are suggested.
_ROLES = (
    ("policy", POLICY_ALIASES),
    ("company", COMPANY_ALIASES),
    ("system", SYSTEM_ALIASES),
)


def _by_upper(columns: list[str]) -> dict[str, str]:
    return {str(col).strip().upper(): col for col in columns}


def _role_column(columns: list[str], aliases: frozenset[str]) -> str | None:
    for col in columns:
        if normalize_name(col) in aliases:
            return col
    return None


def suggest_join_keys(
    left_columns: list[str], left_kind: str,
    right_columns: list[str], right_kind: str,
) -> list[tuple[str, str]]:
    """Likely (left column, right column) key pairs, or [] when nothing fits."""
    if not left_columns or not right_columns:
        return []
    left_up, right_up = _by_upper(left_columns), _by_upper(right_columns)
    database_pairs = _database_policy_pairs(left_up, right_up, left_kind, right_kind)
    if database_pairs:
        return database_pairs
    role_pairs = _role_pairs(left_columns, right_columns)
    if role_pairs:
        return role_pairs
    return _matching_key_pairs(left_columns, right_columns)


def _database_policy_pairs(
    left_up: dict[str, str],
    right_up: dict[str, str],
    left_kind: str,
    right_kind: str,
) -> list[tuple[str, str]]:
    if left_kind == KIND_DATABASE and right_kind == KIND_DATABASE:
        if "TCH_POL_ID" in left_up and "TCH_POL_ID" in right_up:
            keys = [k for k in POLICY_KEY if k in left_up and k in right_up]
            if COVERAGE_KEY in left_up and COVERAGE_KEY in right_up:
                keys.append(COVERAGE_KEY)
            return [(left_up[k], right_up[k]) for k in keys]
    return []


def _role_pairs(left_columns: list[str], right_columns: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for role, aliases in _ROLES:
        left = _role_column(left_columns, aliases)
        right = _role_column(right_columns, aliases)
        if left and right:
            pairs.append((left, right))
        elif role == "policy":
            break  # company / system alone would match far too many rows
    if pairs:
        return pairs
    return []


def _matching_key_pairs(left_columns: list[str], right_columns: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    right_norm = {normalize_name(col): col for col in right_columns}
    for col in left_columns:
        norm = normalize_name(col)
        if norm and norm.endswith(_KEY_SUFFIXES) and norm in right_norm:
            pairs.append((col, right_norm[norm]))
    return pairs


def suggest_canvas_joins(
    tables: list[str],
    columns: dict[str, list[str]],
    kinds: dict[str, str],
    joined_pairs: set[frozenset[str]],
    dismissed_pairs: set[frozenset[str]],
) -> list[tuple[str, str, list[tuple[str, str]]]]:
    """One suggestion for every canvas table not yet joined to anything.

    Each unjoined table gets its best partner: a table already in the join
    graph first, then the one sharing the most keys, then the earliest placed.
    Returns ``(left table, right table, [(left col, right col), ...])``.
    """
    joined = {table for pair in joined_pairs for table in pair}
    suggestions: list[tuple[str, str, list[tuple[str, str]]]] = []
    offered: set[frozenset[str]] = set()
    for table in tables:
        if table in joined:
            continue
        best = None
        for index, other in enumerate(tables):
            pair = frozenset((table, other))
            if other == table or pair in dismissed_pairs or pair in offered:
                continue
            keys = suggest_join_keys(columns.get(other, []), kinds.get(other, ""),
                                     columns.get(table, []), kinds.get(table, ""))
            if not keys:
                continue
            score = (other in joined, len(keys), -index)
            if best is None or score > best[0]:
                best = (score, other, keys)
        if best is not None:
            _score, other, keys = best
            offered.add(frozenset((table, other)))
            suggestions.append((other, table, keys))
    return suggestions
