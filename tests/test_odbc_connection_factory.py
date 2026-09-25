from __future__ import annotations

import io
import tokenize
from pathlib import Path

from suiteview.core import odbc_utils


ROOT = Path(__file__).resolve().parents[1]
SUITEVIEW = ROOT / "suiteview"

def _uses_direct_pyodbc_connect(path: Path) -> bool:
    tokens = [
        token
        for token in tokenize.generate_tokens(
            io.StringIO(path.read_text(encoding="utf-8")).readline
        )
        if token.type not in {tokenize.ENCODING, tokenize.NL, tokenize.NEWLINE}
    ]
    for index in range(len(tokens) - 4):
        if (
            tokens[index].string == "pyodbc"
            and tokens[index + 1].string == "."
            and tokens[index + 2].string == "connect"
            and tokens[index + 3].string == "("
        ):
            return True
    return False


def test_non_core_code_uses_odbc_connection_factory():
    offenders = []
    for path in SUITEVIEW.rglob("*.py"):
        if "core" in path.relative_to(SUITEVIEW).parts:
            continue
        if _uses_direct_pyodbc_connect(path):
            offenders.append(path.relative_to(ROOT).as_posix())

    assert offenders == []


def test_connect_dsn_passes_explicit_options(monkeypatch):
    calls = []
    connection = object()

    def connect(connection_string, **kwargs):
        calls.append((connection_string, kwargs))
        return connection

    monkeypatch.setattr(odbc_utils.pyodbc, "connect", connect)

    assert odbc_utils.connect_dsn(
        "UL_Rates", autocommit=False, timeout=None, readonly=True,
    ) is connection
    assert calls == [
        ("DSN=UL_Rates", {"autocommit": False, "readonly": True})
    ]
