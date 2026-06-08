"""Pytest configuration for SuiteView.

A few files under ``tests/`` are standalone *manual* Qt scripts: they build a
window and call ``app.exec()`` at import time, not inside a test function. When
pytest collects them the blocking event loop stalls the entire run (and the
trailing ``sys.exit`` aborts collection with an INTERNALERROR). Exclude them
here so ``pytest tests/`` runs the real, headless test modules cleanly.

Run a manual script directly for a visual check, e.g.:
    venv\\Scripts\\python.exe tests\\test_checkbox_list.py
"""

# Standalone scripts that do work at import (Qt event loop, or live-connection
# lookups) — manual debug scripts, not pytest modules.
collect_ignore = [
    "tests/test_checkbox_list.py",   # module-level app.exec()
    "tests/test_ui_display.py",      # module-level app.exec()
    "tests/test_connection.py",      # hits get_connection(1) at import (None on minipc)
]

# Office/COM-backed tests can't even import without pywin32 (win32com). They are
# work-laptop-only; skip them *only* when the dependency is genuinely missing so
# they still run where Office automation is available.
try:
    import win32com.client  # noqa: F401
except Exception:
    collect_ignore += [
        "tests/test_find_email.py",
        "tests/test_outlook_scan.py",
        "tests/test_sender_properties.py",
        "tests/test_attachments.py",
    ]
