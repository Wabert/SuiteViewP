"""Smoke-test the real policy screens against live policies, read-only.

For each ``POLICY[:COMPANY]`` this drives, offscreen and in an isolated profile:

* PolView: load, render every applicable tab, the timeline, and every Rates-tree
  leaf, then the Policy Support tools (tool availability, summary and
  suggestions, GLP Exception and forecast, UL Reinstatement) when they apply;
* RERUN (Illustration): load through the Get path, then Run Values;
* ABR: ``build_abr_policy`` (policy extraction only, no quote).

It records every logged error, unhandled exception and error/warning dialog, and
exits non-zero if any occurred. Nothing is written to DB2 or to the real user
profile. Usage::

    venv\\Scripts\\python.exe tools/app/smoke_policy_screens.py \\
        --policy UE215622:01 --policy 13034048:01 --output report.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class _Recorder(logging.Handler):
    """Collect ERROR+ log records and dialog/exception events per step."""

    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.events: list[dict] = []
        self.step = ""

    def emit(self, record):
        detail = record.getMessage()
        if record.exc_info:
            detail += "\n" + "".join(traceback.format_exception(*record.exc_info))[-2500:]
        self.add("log", f"{record.name}: {detail}")

    def add(self, kind: str, detail: str):
        self.events.append({"step": self.step, "kind": kind, "detail": detail})


def _pump(app, seconds: float = 0.05):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def _wait(app, predicate, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _polview(app, rec, number, company, region, timeout):
    from suiteview.polview.ui.main_window import GetPolicyWindow

    rec.step = f"{number} PolView load"
    window = GetPolicyWindow(enable_policy_list=False)
    window.show()
    window.load_policy(number, region, company)
    _wait(app, lambda: window._policy is not None or not window._loader.busy, timeout)
    _wait(app, lambda: not window._loader.busy, timeout)
    if window._policy is None:
        rec.add("result", "policy did not load")
        return window
    for stage, (tab, title) in window._stage_tabs.items():
        if stage in window._unavailable_tabs:
            continue
        rec.step = f"{number} PolView tab {title}"
        window.tabs.setCurrentWidget(tab)
        _wait(app, lambda: window._tab_states.get(stage) not in ("queued", "loading"), timeout)
        _pump(app)
        if window._tab_states.get(stage) == "failed":
            rec.add("tab-failed", window.tabs.tabToolTip(window.tabs.indexOf(tab)))
    rec.step = f"{number} PolView timeline"
    window._open_timeline()
    _pump(app)
    rec.step = f"{number} PolView rates tree"
    policy = window._policy
    from suiteview.polview.services.rate_selection import (
        SCHEMA_BENEFIT, SCHEMA_COVERAGE, SCHEMA_FIXED_FUNDS, SCHEMA_INDEX_FUNDS, SCHEMA_MODAL, SCHEMA_POLICY,
        SCHEMA_SCALES, SCHEMA_SPACE,
    )
    leaves = [(SCHEMA_COVERAGE, f"Cov {i:02d}", i) for i in range(1, policy.coverages.coverage_count + 1)]
    leaves.append((SCHEMA_SCALES, "Scales", 1))
    leaves += [(SCHEMA_BENEFIT, f"Ben {i:02d}", i) for i in range(1, policy.benefits.benefit_count + 1)]
    leaves += [(SCHEMA_POLICY, "Policy Rates", 1), (SCHEMA_FIXED_FUNDS, "Fixed Fund Rates", 1),
               (SCHEMA_INDEX_FUNDS, "Index Fund Rates", 1),
               (SCHEMA_MODAL, "Modal Factors", 1), (SCHEMA_SPACE, "Rate Space", 1)]
    leaves += [("Coverages", f"Legacy Cov {i:02d}", i) for i in range(1, policy.coverages.coverage_count + 1)]
    leaves += [("Benefits", f"Legacy Ben {i:02d}", i) for i in range(1, policy.benefits.benefit_count + 1)]
    leaves.append(("Policy", "Legacy Policy", 1))
    for category, label, index in leaves:
        rec.step = f"{number} PolView rates {label}"
        try:
            window._on_rate_selected(category, label, index)
        except Exception:
            rec.add("exception", traceback.format_exc()[-2500:])
        _pump(app)
    return window


def _policy_support(rec, number, policy):
    """Exercise the Policy Support tools on the live policy PolView loaded."""
    from datetime import date

    from dateutil.relativedelta import relativedelta

    from suiteview.polview.services import glp_exception, policy_insights, reinstatement
    from suiteview.polview.services.support_tools import build_support_tool_state

    def step(label, call):
        rec.step = f"{number} Support {label}"
        try:
            return call()
        except Exception:
            rec.add("exception", traceback.format_exc()[-2500:])
            return None

    state = step("tool state", lambda: build_support_tool_state(policy))
    tools = step("tool availability", lambda: policy_insights.support_tool_availability(policy))
    rec.add("info", f"tool state={state}; available="
            f"{ {k: v.available for k, v in (tools or {}).items()} }")
    summary = step("summary", lambda: policy_insights.build_policy_summary(policy))
    if summary is not None:
        step("suggested actions", lambda: policy_insights.suggested_actions(policy, summary, tools or {}))
    if state is not None and state.glp_eligible:
        availability = step("GLP forecast availability", lambda: glp_exception.check_forecast_availability(policy))
        if availability is not None and availability.available:
            target = (availability.policy.valuation_date or date.today()) + relativedelta(years=2)
            step("GLP exception", lambda: glp_exception.calculate_glp_exception(policy, target))
            step("support forecast", lambda: glp_exception.calculate_policy_support_forecast(
                policy, target, 100.0, "Monthly"))
        elif availability is not None:
            rec.add("info", f"GLP forecast unavailable: {availability.message}")
    if step("is UL", lambda: reinstatement.is_ul_policy(policy)):
        eligibility = step("reinstatement eligibility",
                           lambda: reinstatement.reinstatement_eligibility(policy))
        if eligibility is not None and eligibility.eligible:
            basis = step("reinstatement basis", lambda: reinstatement.load_reinstatement_basis(policy))
            if basis is not None:
                step("reinstatement quote", lambda: basis.quote(basis.default_date))
        elif eligibility is not None:
            rec.add("info", f"reinstatement not eligible: {eligibility.message}")


def _rerun(app, rec, number, company, region):
    from suiteview.illustration.ui.main_window import IllustrationWindow

    rec.step = f"{number} RERUN load"
    window = IllustrationWindow()
    window.show()
    window.load_policy(number, region, company)
    _pump(app, 0.3)
    if window._policy is None or not window._policy.exists:
        rec.add("result", "policy did not load")
        return window
    for index in range(window.tabs.count()) if hasattr(window, "tabs") else ():
        rec.step = f"{number} RERUN tab {window.tabs.tabText(index)}"
        window.tabs.setCurrentIndex(index)
        _pump(app)
    rec.step = f"{number} RERUN Run Values"
    if window.run_values_btn.isEnabled():
        window._on_run_values()
        _pump(app, 0.3)
    else:
        rec.add("result", "Run Values was disabled after load")
    return window


def _abr(rec, number, company, region):
    from datetime import date

    from suiteview.abrquote.core.abr_policy_service import build_abr_policy

    rec.step = f"{number} ABR build_abr_policy"
    try:
        build_abr_policy(number, region, company or None, as_of_date=date.today())
    except Exception:
        rec.add("exception", traceback.format_exc()[-2500:])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", action="append", required=True, help="POLICY[:COMPANY]")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--skip", action="append", default=[], choices=("polview", "rerun", "abr"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["SUITEVIEW_PROFILE_DIR"] = tempfile.mkdtemp(prefix="sv-smoke-profile-")
    os.environ.pop("SUITEVIEW_LOCAL_DATA", None)

    from PyQt6.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance() or QApplication([])
    rec = _Recorder()
    logging.getLogger().addHandler(rec)
    logging.getLogger().setLevel(logging.INFO)
    sys.excepthook = lambda *exc: rec.add("unhandled", "".join(traceback.format_exception(*exc))[-2500:])
    for name in ("critical", "warning"):
        setattr(QMessageBox, name, staticmethod(
            lambda parent, title, text, *a, _kind=name, **k: rec.add(
                f"dialog-{_kind}", f"{title}: {text}") or QMessageBox.StandardButton.Ok))
    QMessageBox.information = staticmethod(
        lambda parent, title, text, *a, **k: rec.add("dialog-info", f"{title}: {text}")
        or QMessageBox.StandardButton.Ok)

    windows = []
    for item in args.policy:
        number, _, company = item.partition(":")
        if "polview" not in args.skip:
            window = _polview(app, rec, number, company, args.region, args.timeout)
            windows.append(window)
            if window._policy is not None:
                _policy_support(rec, number, window._policy)
        if "rerun" not in args.skip:
            windows.append(_rerun(app, rec, number, company, args.region))
        if "abr" not in args.skip:
            _abr(rec, number, company, args.region)
    for window in windows:
        loader = getattr(window, "_loader", None)
        if loader is not None:
            loader.shutdown()
        window.close()
    _pump(app, 0.2)

    ignored = ("info",)
    problems = [e for e in rec.events if not e["kind"].endswith(ignored)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"policies": args.policy, "events": rec.events}, indent=1),
                           encoding="utf-8")
    for event in rec.events:
        first = event["detail"].strip().splitlines()
        print(f"[{event['kind']}] {event['step']}: {first[-1] if first else ''}"[:400])
    print(f"{len(problems)} problem event(s); report: {args.output}")
    sys.stdout.flush()
    # Skip interpreter teardown: destroying Qt objects after live ODBC
    # connections can crash the process after the report is complete.
    os._exit(1 if problems else 0)


if __name__ == "__main__":
    sys.exit(main())
