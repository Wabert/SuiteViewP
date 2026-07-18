"""Drive a real local policy through a guideline recalc and verify the new
Values-tab "TEFRA/TAMRA Recalc" group end to end.

Uses local SQLite data (SUITEVIEW_LOCAL_DATA=1) so it runs offline. Applies a
specified-amount change at a future date — which re-solves the 7702 guideline
premiums — then (a) prints the captured before/after GLP & GSP detail and
(b) renders the IllustrationValuesTab "TEFRA/TAMRA Recalc" group to a PNG (the
recalc summary, plus the first recalc's detail page when one exists).

Usage (single JSON arg):
    venv\\Scripts\\python.exe tools/check_guideline_recalc.py '<json>'

    {"policy":"U0688012","region":"CKPR","company":"01","months":36,
     "change":{"kind":"face_amount","date":"2027-05-09","value":50000},
     "png":"/tmp/guideline_recalc.png"}

If "change" is omitted a face decrease to half the current specified amount is
applied at the first anniversary after the valuation date.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run(cmd: dict) -> dict:
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet, PolicyChangeEvent, PolicyChangeKind,
    )

    policy = cmd["policy"]
    region = cmd.get("region", "CKPR")
    company = cmd.get("company")
    months = int(cmd.get("months", 36))

    clear_cache()
    policy_data = build_illustration_data(policy, region=region, company_code=company)

    change = cmd.get("change")
    if change:
        kind = (PolicyChangeKind.FACE_AMOUNT if change["kind"] == "face_amount"
                else PolicyChangeKind.DB_OPTION)
        value = float(change["value"]) if change["kind"] == "face_amount" else change["value"]
        eff = datetime.date.fromisoformat(change["date"])
    else:
        kind = PolicyChangeKind.FACE_AMOUNT
        value = round(policy_data.total_face / 2.0, 2)
        val = policy_data.valuation_date or policy_data.issue_date
        eff = datetime.date(val.year + 1, val.month, val.day)

    future_inputs = IllustrationInputSet(policy_changes=[
        PolicyChangeEvent(kind=kind, effective_date=eff, value=value),
    ])

    states = IllustrationEngine().project(
        policy_data, months=months, future_inputs=future_inputs)

    first = next((s.guideline_recalc for s in states if s.guideline_recalc), None)
    detail = None
    if first:
        detail = {k: (v.isoformat() if isinstance(v, datetime.date) else v)
                  for k, v in first.items()}

    png = cmd.get("png")
    png_written = None
    if png:
        png_written = _render_recalc_page(policy_data, states, png)

    return {
        "policy": policy,
        "plancode": policy_data.plancode,
        "valuation_date": str(policy_data.valuation_date),
        "base_total_face": policy_data.total_face,
        "change": {"kind": kind.value, "date": eff.isoformat(), "value": value},
        "months": months,
        "recalc_found": detail is not None,
        "guideline_recalc": detail,
        "png": png_written,
    }


def _render_recalc_page(policy_data, states, png_path: str) -> str:
    """Build the real Values tab headless and grab the TEFRA/TAMRA Recalc group.

    Saves the recalc summary to ``png_path``; when at least one recalc exists,
    also saves the first recalc's before/after detail page alongside it
    (``<png>`` → ``<png stem>_detail<suffix>``).
    """
    from PyQt6.QtWidgets import QApplication
    from suiteview.illustration.ui.values_tab import IllustrationValuesTab

    app = QApplication.instance() or QApplication([])
    tab = IllustrationValuesTab()
    tab.resize(1240, 820)
    tab.display_projection(policy_data, states, months=len(states))
    # Switch the content stack to the new group, exactly like a navigator click.
    tab.content_stack.setCurrentWidget(tab.recalc_view)
    tab.recalc_view.resize(1240, 800)

    out = Path(png_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tab.recalc_view.show_summary()
    app.processEvents()
    tab.recalc_view.grab().save(str(out))
    if tab.recalc_view.detail_views:
        tab.recalc_view.show_date(0)
        app.processEvents()
        detail_out = out.with_name(f"{out.stem}_detail{out.suffix}")
        tab.recalc_view.grab().save(str(detail_out))
    app.processEvents()
    return str(out)


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "missing JSON arg"}))
        sys.exit(1)
    # default=str: recalc detail nests dates (7-pay window/solve dates).
    print(json.dumps(run(json.loads(sys.argv[1])), indent=1, default=str))


if __name__ == "__main__":
    main()
