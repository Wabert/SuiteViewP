"""Verify policy-number inputs are case-insensitive across the suite.

Every app looks policies up by an upper-case key, so a lower-case entry must be
folded to upper case *in the field itself* — what the user sees is what gets
queried.  This drives the real widgets with simulated typing and pasted text.

Usage:
    venv\\Scripts\\python.exe tools/app/test_policy_input_uppercase.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SUITEVIEW_LOCAL_DATA", "1")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402


def _type(widget, text: str) -> str:
    """Type *text* keystroke by keystroke and return what the field shows."""
    widget.clear()
    QTest.keyClicks(widget, text)
    return widget.text()


def _paste(widget, text: str) -> str:
    """setText() is the path taken by paste and by cross-app hand-offs."""
    widget.clear()
    widget.setText(text)
    return widget.text()


def main() -> int:
    app = QApplication(sys.argv)
    results = {}
    failures = []

    def check(name, widget, typed="u0532652ab", pasted="e0213651xy"):
        got_typed = _type(widget, typed)
        got_pasted = _paste(widget, pasted)
        entry = {"typed": got_typed, "pasted": got_pasted}
        if got_typed != typed.upper():
            failures.append(f"{name}: typed {typed!r} -> {got_typed!r}")
        if got_pasted != pasted.upper():
            failures.append(f"{name}: pasted {pasted!r} -> {got_pasted!r}")
        results[name] = entry
        widget.clear()

    from suiteview.polview.ui.widgets import PolicyLookupBar
    bar = PolicyLookupBar()
    check("polview.PolicyLookupBar.policy_input", bar.policy_input)
    check("polview.PolicyLookupBar.region_input", bar.region_input,
          typed="ckpr", pasted="ckmo")
    check("polview.PolicyLookupBar.company_input", bar.company_input,
          typed="a1", pasted="b4")

    # The lookup bar is what PolView, RERUN and the Audit hand-off all use, so
    # confirm the emitted signal payload is upper-cased too.
    emitted = []
    bar.policy_requested.connect(lambda p, r, c: emitted.append((p, r, c)))
    bar.policy_input.setText("u0532652")
    bar.region_input.setText("ckpr")
    bar.company_input.setText("a1")
    bar._on_get_policy()
    results["polview.policy_requested"] = emitted
    if emitted != [("U0532652", "CKPR", "A1")]:
        failures.append(f"policy_requested emitted {emitted!r}")

    from suiteview.abrquote.ui.policy_panel import PolicyPanel
    panel = PolicyPanel()
    check("abrquote.PolicyPanel.policy_input", panel.policy_input)

    from suiteview.polview.ui.tabs.policy_list_tab import PolicyListWindow
    plist = PolicyListWindow()
    check("polview.PolicyListWindow.policy_input", plist.policy_input)

    from suiteview.audit.tabs.policy_tab import PolicyTab
    ptab = PolicyTab()
    check("audit.PolicyTab.txt_polnum_value", ptab.txt_polnum_value)

    from suiteview.mainframe_nav.mainframe_terminal_screen import MainframeTerminalScreen
    mf = MainframeTerminalScreen()
    check("mainframe_nav.policy_input", mf.policy_input,
          typed="u0532652", pasted="e0213651")

    results["failures"] = failures
    results["all_ok"] = not failures
    print(json.dumps(results, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
