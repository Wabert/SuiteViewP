"""Pytest configuration for standalone manual scripts outside ``tests/``."""

collect_ignore = [
    "scripts/test_odbc_backend.py",  # manual/live ODBC utility
]
