"""Pytest configuration for SuiteView.

A few files under ``tests/`` and ``scripts/`` are standalone *manual* scripts: they build a
window and call ``app.exec()`` at import time, not inside a test function. When
pytest collects them the blocking event loop stalls the entire run (and the
trailing ``sys.exit`` aborts collection with an INTERNALERROR). Exclude them
here so pytest runs the real, headless test modules cleanly.

Run a manual script directly for a visual check, e.g.:
    venv\\Scripts\\python.exe tests\\test_checkbox_list.py
"""
import os

# Standalone scripts that do work at import (Qt event loop, or live-connection
# lookups) — manual debug scripts, not pytest modules.
collect_ignore = [
    "tests/test_checkbox_list.py",   # module-level app.exec()
    "tests/test_ui_display.py",      # module-level app.exec()
    "tests/test_connection.py",      # hits get_connection(1) at import (None on minipc)
    "scripts/test_expand_input.py",  # module-level app.exec()
    "scripts/test_gal_cache.py",     # manual/live Outlook utility
    "scripts/test_odbc_backend.py",  # manual/live ODBC utility
]

# Office/COM-backed scripts can start Outlook at import time. Keep full pytest
# deterministic by making those manual/live checks opt-in.
if os.environ.get("SUITEVIEW_RUN_OUTLOOK_TESTS") != "1":
    collect_ignore += [
        "tests/test_find_email.py",
        "tests/test_outlook_scan.py",
        "tests/test_sender_properties.py",
        "tests/test_attachments.py",
    ]
