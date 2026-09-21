"""Verify native PolView progressive loading read-only, using an isolated profile."""

import argparse
import cProfile
import json
import os
from pathlib import Path
import pstats
import sys
from contextlib import ExitStack
from tempfile import TemporaryDirectory
from threading import get_ident
from time import perf_counter
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def profile_rows(profiler):
    return [
        {"function": f"{Path(key[0]).name}:{key[1]}:{key[2]}",
         "calls": value[1], "own_seconds": value[2], "cumulative_seconds": value[3]}
        for key, value in sorted(
            pstats.Stats(profiler).stats.items(), key=lambda entry: entry[1][3], reverse=True,
        )[:40]
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--company", default="")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--all-tabs", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--profile-construction", action="store_true")
    parser.add_argument("--profile-load", action="store_true")
    parser.add_argument("--compare-warm", action="store_true")
    parser.add_argument("--expect-surrender-unavailable", action="store_true")
    parser.add_argument("--expect-surrender-reason")
    args = parser.parse_args()
    if args.expect_surrender_unavailable and not args.all_tabs:
        parser.error("--expect-surrender-unavailable requires --all-tabs")
    if args.expect_surrender_reason and not args.expect_surrender_unavailable:
        parser.error("--expect-surrender-reason requires --expect-surrender-unavailable")
    report = {"timings": [], "table_reads": [], "connections": [], "ui_errors": []}
    started = perf_counter()
    with TemporaryDirectory(prefix="suiteview-polview-profile-") as profile:
        os.environ["SUITEVIEW_PROFILE_DIR"] = profile
        import pyodbc
        from PyQt6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from suiteview.core.policy_service import clear_cache, get_policy_info
        from suiteview.polview.models.policy_data import PolicyData
        from suiteview.polview.services.policy_prefetch import PolicyLoadSession
        from suiteview.polview.ui import main_window

        report["import_seconds"] = perf_counter() - started
        app = QApplication.instance() or QApplication([])
        gui_thread = get_ident()
        phase = "first"
        heartbeat_times = []
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: heartbeat_times.append(perf_counter()))
        original_connect = pyodbc.connect
        original_ensure = PolicyData._ensure_table_loaded
        original_initial = PolicyLoadSession.load_initial

        def dialog(_parent, title, message, *unused):
            report["ui_errors"].append(f"{title}: {message}")
            return QMessageBox.StandardButton.Ok

        def odbc_error(_parent, dsn, error_detail=""):
            report["ui_errors"].append(f"{dsn}: {error_detail}")

        def track_connect(*pos, **kw):
            start = perf_counter()
            try:
                return original_connect(*pos, **kw)
            finally:
                report["connections"].append({
                    "phase": phase, "gui_thread": get_ident() == gui_thread,
                    "seconds": perf_counter() - start,
                })

        def track_table(data, table):
            cached = table in data._table_cache
            start = perf_counter()
            try:
                return original_ensure(data, table)
            finally:
                if not cached:
                    report["table_reads"].append({
                        "phase": phase, "table": table,
                        "seconds": perf_counter() - start,
                        "failed": table in data._table_errors,
                        "gui_thread": get_ident() == gui_thread,
                    })

        def profile_initial(session):
            profiler = cProfile.Profile()
            profiler.enable()
            try:
                return original_initial(session)
            finally:
                profiler.disable()
                report[f"{phase}_load_profile"] = profile_rows(profiler)

        def timed(stage, method):
            def invoke(*pos, **kw):
                start = perf_counter()
                try:
                    return method(*pos, **kw)
                finally:
                    report["timings"].append({
                        "phase": phase, "stage": stage,
                        "gui_thread": get_ident() == gui_thread,
                        "seconds": perf_counter() - start,
                    })
            return invoke

        def wait_until(predicate, timeout_ms=120000):
            loop = QEventLoop()
            poll = QTimer()
            poll.setInterval(10)
            poll.timeout.connect(lambda: loop.quit() if predicate() else None)
            timeout = QTimer()
            timeout.setSingleShot(True)
            timeout.timeout.connect(loop.quit)
            poll.start()
            timeout.start(timeout_ms)
            if not predicate():
                loop.exec()
            poll.stop()
            timeout.stop()
            if not predicate():
                raise TimeoutError("PolView did not finish within the verification timeout.")

        def screenshot(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            if not window.grab().save(str(path), "PNG"):
                raise RuntimeError(f"Cannot save screenshot: {path}")

        window = None
        with ExitStack() as patches:
            for name in ("warning", "critical", "information"):
                patches.enter_context(patch.object(QMessageBox, name, dialog))
            patches.enter_context(patch.object(main_window, "_show_odbc_warning", odbc_error))
            patches.enter_context(patch.object(PolicyData, "_ensure_table_loaded", track_table))
            patches.enter_context(patch.object(pyodbc, "connect", track_connect))
            if args.profile_load:
                patches.enter_context(patch.object(PolicyLoadSession, "load_initial", profile_initial))
            try:
                start = perf_counter()
                profiler = cProfile.Profile() if args.profile_construction else None
                if profiler:
                    profiler.enable()
                try:
                    window = main_window.GetPolicyWindow()
                finally:
                    if profiler:
                        profiler.disable()
                        report["construction_profile"] = profile_rows(profiler)
                report["construction_seconds"] = perf_counter() - start
                for stage, (tab, _title) in window._stage_tabs.items():
                    loader = getattr(tab, "load_data_from_policy", None)
                    if loader is not None:
                        patches.enter_context(patch.object(
                            tab, "load_data_from_policy", timed(stage, loader),
                        ))
                start = perf_counter()
                window.load_policy(args.policy, args.region, args.company)
                report["request_return_seconds"] = perf_counter() - start
                window.show()
                app.processEvents()
                report["shell_visible_seconds"] = perf_counter() - start
                timer.start()
                if args.screenshot:
                    screenshot(args.screenshot.with_stem(args.screenshot.stem + "-loading"))
                wait_until(lambda: window._policy is not None or not window._loader.busy)
                report["initial_load_seconds"] = perf_counter() - start
                report["initial_table_reads"] = len(report["table_reads"])
                if window._policy is None:
                    raise RuntimeError(window._status_label.text())
                wait_until(lambda: not window._loader.busy)
                report["background_complete_seconds"] = perf_counter() - start
                if args.all_tabs:
                    for tab, _title in window._stage_tabs.values():
                        if window.tabs.indexOf(tab) >= 0:
                            window.tabs.setCurrentWidget(tab)
                            app.processEvents()
                    window.tabs.setCurrentWidget(
                        window.advprod_tab if args.expect_surrender_unavailable
                        else window.coverages_tab
                    )
                    app.processEvents()
                timer.stop()
                gaps = [b - a for a, b in zip(heartbeat_times, heartbeat_times[1:])]
                report["gui_heartbeat_count"] = len(heartbeat_times)
                report["max_gui_heartbeat_gap_seconds"] = max(gaps, default=0.0)
                if args.screenshot:
                    screenshot(args.screenshot)
                report["tab_states"] = dict(window._tab_states)
                report["checks"] = {
                    "nonblocking_request": report["request_return_seconds"] < 0.2,
                    "gui_heartbeat_active": len(heartbeat_times) >= 5,
                    "gui_heartbeat_gap_under_half_second": max(gaps, default=0.0) < 0.5,
                    "no_gui_database_connections": not any(c["gui_thread"] for c in report["connections"]),
                    "no_gui_table_fetches": not any(r["gui_thread"] for r in report["table_reads"]),
                    "no_table_errors": not any(r["failed"] for r in report["table_reads"]),
                    "no_ui_errors": not report["ui_errors"],
                    "all_visible_tabs_ready": all(
                        window._tab_states[stage] == "ready"
                        for stage, (tab, _) in window._stage_tabs.items()
                        if window.tabs.indexOf(tab) >= 0
                    ),
                    "shared_policy_instance": get_policy_info(
                        window._policy.policy_number, window._policy.region,
                        window._policy.company_code, window._policy.system_code,
                    ) is window._policy,
                    "each_table_fetched_once": len(report["table_reads"]) == len({
                        read["table"] for read in report["table_reads"]
                    }),
                }
                if args.all_tabs and window._policy.is_advanced_product:
                    fields = window.advprod_tab.policy_info._fields
                    if args.expect_surrender_unavailable:
                        reason = window.advprod_tab.surrender_notice.text()
                        report["surrender_unavailable_reason"] = reason
                        report["checks"]["surrender_unavailable_explicit"] = (
                            all(fields[field].text() == "N/A"
                                and fields[field].toolTip() == reason
                                for field in ("surrender_charge", "surrender_value"))
                            and bool(reason)
                            and window.advprod_tab.surrender_notice.isVisible()
                            and bool(fields["total_av"].text())
                            and window.advprod_tab.mv_values.table._data_table.rowCount() > 0
                            and not window._load_overlays["advprod"].isVisible()
                        )
                        if args.expect_surrender_reason:
                            report["checks"]["surrender_reason_matches"] = (
                                args.expect_surrender_reason in reason
                            )
                    else:
                        report["checks"]["surrender_values_available"] = all(
                            fields[field].text() not in ("", "cannot calc", "N/A")
                            for field in ("surrender_charge", "surrender_value")
                        )
                if args.compare_warm:
                    phase = "warm"
                    window._on_all_policies_removed()
                    clear_cache()
                    previous = window._policy
                    start = perf_counter()
                    window.load_policy(args.policy, args.region, args.company)
                    wait_until(lambda: not window._loader.busy)
                    report["warm_all_data_seconds"] = perf_counter() - start
                    report["checks"]["warm_uses_fresh_policy"] = (
                        window._policy is not None and window._policy is not previous
                        and window._tab_states["coverages"] == "ready"
                    )
                report["all_ok"] = all(report["checks"].values())
            except Exception as exc:
                report["all_ok"] = False
                report["error"] = str(exc)
            finally:
                timer.stop()
                if window is not None:
                    window._loader.shutdown()
                    window.close()
                    if hasattr(window, "policy_list_window"):
                        window.policy_list_window.hide()
                        window.policy_list_window.deleteLater()
                    window.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
