from __future__ import annotations

import re
from pathlib import Path

import pytest

from suiteview.core.sql_identifiers import (
    IdentifierCatalog,
    limit_clause,
    qualified_name,
    quote_identifier,
    top_clause,
)


ROOT = Path(__file__).resolve().parents[1]
TARGET_MODULES = (
    ROOT / "suiteview" / "core" / "schema_discovery.py",
    ROOT / "suiteview" / "ratemanager" / "whole_life" / "service.py",
    ROOT / "suiteview" / "ratemanager" / "database_loader.py",
)


def test_quote_identifier_escapes_for_sql_server():
    assert quote_identifier("A]B") == "[A]]B]"
    assert qualified_name("dbo", "Rate Table") == "[dbo].[Rate Table]"


def test_quote_identifier_escapes_for_db2():
    assert quote_identifier('A"B', "DB2") == '"A""B"'
    assert qualified_name("DB2TAB", "LH_BAS_POL", "DB2") == '"DB2TAB"."LH_BAS_POL"'


def test_identifier_catalog_rejects_unknown_names():
    catalog = IdentifierCatalog.from_tables({"KNOWN"}, {"KNOWN": {"COL"}})
    assert catalog.quote_table("KNOWN") == "[KNOWN]"
    assert catalog.quote_column("KNOWN", "COL") == "[COL]"
    with pytest.raises(ValueError):
        catalog.quote_table("OTHER")
    with pytest.raises(ValueError):
        catalog.quote_column("KNOWN", "OTHER")


def test_limit_helpers_validate_and_format():
    assert top_clause(5, "SQL_SERVER") == "TOP 5 "
    assert limit_clause(5, "DB2") == "FETCH FIRST 5 ROWS ONLY"
    assert limit_clause(5, "db2_limit") == "LIMIT 5"
    with pytest.raises(ValueError):
        limit_clause(0, "DB2")


def test_target_modules_do_not_add_inline_identifier_fstrings():
    offenders = []
    forbidden_patterns = (
        re.compile(r"""f["'][^"']*\[\{[^}]+\}\]"""),
        re.compile(r"""f["'][^"']*\{schema_name\}\.\{table_name\}"""),
    )
    for path in TARGET_MODULES:
        lines = path.read_text(encoding="utf-8").splitlines()
        text = "\n".join(lines)
        if "def _quote(" in text:
            offenders.append(f"{path.relative_to(ROOT)}: local _quote helper")
        for line_number, line in enumerate(lines, start=1):
            if not re.search(r"\b(SELECT|FROM|WHERE|JOIN|UPDATE|INSERT|DELETE)\b", line):
                continue
            for pattern in forbidden_patterns:
                match = pattern.search(line)
                if not match:
                    continue
                offenders.append(
                    f"{path.relative_to(ROOT)}:{line_number}: {match.group(0)}"
                )
    assert offenders == []
