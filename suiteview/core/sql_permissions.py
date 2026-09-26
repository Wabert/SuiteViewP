"""Fail-closed write-permission checks at shared SQL execution boundaries."""
from __future__ import annotations

import sqlparse
from sqlparse import tokens
from sqlparse.sql import Function, Identifier

from suiteview.core import access_control
from suiteview.core.build_env import ReadOnlyDataError


_UNSAFE_WORDS = frozenset({
    "ALTER", "ATTACH", "BACKUP", "CALL", "COMMENT", "COPY", "CREATE", "DBCC",
    "DELETE", "DENY", "DETACH", "DROP", "EXEC", "EXECUTE", "EXPORT", "GRANT",
    "IMPORT", "INSERT", "INSTALL", "INTO", "LOAD", "LOAD_EXTENSION", "MERGE",
    "NEXT", "OPENQUERY", "OPENROWSET", "OPENDATASOURCE", "PRAGMA", "REPLACE",
    "RESTORE", "REVOKE", "SET", "TRUNCATE", "UPDATE", "USE", "VACUUM",
})

_READ_FUNCTIONS = frozenset({
    "ABS", "AVG", "BIGINT", "CAST", "CEIL", "CEILING", "CHAR", "CHAR_LENGTH",
    "CHARACTER_LENGTH", "CHARINDEX", "COALESCE", "CONCAT", "CONCAT_WS", "CONVERT",
    "COUNT", "COUNT_BIG", "CURRENT_DATE", "CURRENT_TIMESTAMP", "DATE", "DATEADD",
    "DATEDIFF", "DATEDIFF_BIG", "DATENAME", "DATEPART", "DATE_TRUNC", "DAY",
    "DAYOFMONTH", "DAYOFWEEK", "DAYOFYEAR", "DAYS", "DEC", "DECIMAL", "DECODE",
    "DENSE_RANK", "DOUBLE", "EOMONTH", "EXTRACT", "FIRST_VALUE", "FLOAT", "FLOOR",
    "GETDATE", "GETUTCDATE", "IFNULL", "IIF", "INT", "INTEGER", "ISNULL", "LAG",
    "LAST_VALUE", "LEAD", "LEFT", "LEN", "LENGTH", "LISTAGG", "LOCATE", "LOWER", "LTRIM",
    "MAX", "MIN", "MOD", "MONTH", "MONTHS_BETWEEN", "NULLIF", "NVL", "POWER", "RANK", "REAL",
    "REPLACE", "RIGHT", "ROUND", "ROW_NUMBER", "RTRIM", "SIGN", "SMALLINT",
    "SQRT", "STDDEV", "STDEV", "STRING_AGG", "STRPOS", "SUBSTR", "SUBSTRING",
    "SUM", "TIME", "TIMESTAMP", "TRIM", "TRUNCATE", "TRY_CAST", "TRY_CONVERT", "UPPER",
    "VALUE", "VARCHAR", "VARCHAR_FORMAT", "WEEK", "YEAR",
})


def _read_functions_only(group) -> bool:
    for child in group.get_sublists():
        if isinstance(child, Function):
            if (child.get_name() or "").upper() not in _READ_FUNCTIONS:
                return False
            parent = child.parent
            if isinstance(parent, Identifier) and parent.get_parent_name():
                return False
        if not _read_functions_only(child):
            return False
    return True


def _is_read_query(sql: str) -> bool:
    """Allow one SELECT, including read-only CTEs; never infer from its prefix."""
    statements = sqlparse.parse(_compact_sqlparse_whitespace(sql))
    if len(statements) != 1 or statements[0].get_type() != "SELECT":
        return False
    if not _read_functions_only(statements[0]):
        return False
    return not any(_unsafe_select_token(token) for token in statements[0].flatten())


def _compact_sqlparse_whitespace(sql: str) -> str:
    compact = []
    previous_space = False
    for kind, value in sqlparse.lexer.tokenize(sql):
        space = kind in tokens.Whitespace
        if not space or not previous_space:
            compact.append(" " if space else value)
        previous_space = space
    return "".join(compact)


def _unsafe_select_token(token) -> bool:
    if token.ttype in tokens.Comment or token.ttype in tokens.Literal.String:
        return False
    if _is_allowed_function_name_token(token):
        return False
    if token.ttype in tokens.Error:
        return True
    if token.ttype in tokens.Keyword.DDL:
        return True
    if token.ttype in tokens.Keyword.DML and token.normalized != "SELECT":
        return True
    return token.value.upper() in _UNSAFE_WORDS


def _is_allowed_function_name_token(token) -> bool:
    owner = token.parent
    if isinstance(owner, Identifier):
        owner = owner.parent
    return (
        isinstance(owner, Function)
        and token.value.upper() == (owner.get_name() or "").upper()
        and token.value.upper() in _READ_FUNCTIONS
    )


def guard_query_sql(sql: str) -> None:
    """Recheck live permissions before any SQL reaches an ODBC/DuckDB cursor.

    Packaged arbitrary SQL requires both ADMIN and CanUpdateDatabase: granting
    controlled rate/registry edits must not grant access-table administration.
    Other roles may run conservative SELECT/CTE queries. Source is unrestricted.
    """
    access = access_control.get_access(refresh=True)
    if access.developer or (
        access.role_code == "ADMIN" and access.can_update_database
    ):
        return
    if not _is_read_query(sql):
        raise ReadOnlyDataError(
            "Arbitrary SQL that can modify data requires the ADMIN role and "
            "CanUpdateDatabase permission. Use the controlled rate/registry "
            "editors or a read-only SELECT query."
        )
