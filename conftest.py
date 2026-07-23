"""Pytest configuration for standalone manual scripts outside ``tests/``."""

collect_ignore = [
    "scripts/test_expand_input.py",  # module-level app.exec()
    "scripts/test_gal_cache.py",     # manual/live Outlook utility
    "scripts/test_odbc_backend.py",  # manual/live ODBC utility
]
