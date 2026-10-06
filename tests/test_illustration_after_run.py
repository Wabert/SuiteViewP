"""After Run (should-do 6) and run error text (should-do 7)."""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox

import suiteview.illustration.ui.main_window as mw
from suiteview.illustration.core.business_mode import BUSINESS_MODE_ENV
from suiteview.illustration.core.rate_loader import RateLookupError
from suiteview.illustration.ui.main_window import RUN_FAILED_MESSAGE, IllustrationWindow

_QT_APP = None


@pytest.fixture
def window(monkeypatch):
    global _QT_APP
    monkeypatch.delenv(BUSINESS_MODE_ENV, raising=False)
    _QT_APP = QApplication.instance() or QApplication([])
    win = IllustrationWindow()
    yield win
    win.close()


def _result():
    return SimpleNamespace(
        abr_quote=None, policy=object(), current=[object()], scenario=None,
        guaranteed=None, report=SimpleNamespace(report=object(), guaranteed_error=None),
        lumpsum_result=None, status="Values ready", warnings=())


def test_run_lands_on_the_report_tab(window, monkeypatch):
    monkeypatch.setattr(window.values_tab, "display_projection", lambda *a, **k: None)
    monkeypatch.setattr(window.report_tab, "display_report", lambda *a, **k: None)
    window.tabs.setCurrentWidget(window.policy_tab)
    window._render_run_result(_result())
    assert window.tabs.currentWidget() is window.report_tab


def _fail_run(window, monkeypatch, exc):
    shown = []
    monkeypatch.setattr(window, "_read_run_request", lambda: SimpleNamespace(
        basis=SimpleNamespace(policy_number="UL000001")))

    def boom(request):
        raise exc

    monkeypatch.setattr(mw, "execute_run", boom)
    monkeypatch.setattr(QMessageBox, "critical",
                        lambda parent, title, text: shown.append(("critical", title, text)))
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda parent, title, text: shown.append(("warning", title, text)))
    window._on_run_values()
    return shown


def test_unexpected_run_failure_shows_business_text_and_logs_detail(window, monkeypatch, caplog):
    with caplog.at_level("ERROR", logger=mw.logger.name):
        shown = _fail_run(window, monkeypatch, KeyError("LH_COV_PHA.ANN_PRM_UNT_AMT"))
    assert shown == [("critical", "Run Values", RUN_FAILED_MESSAGE)]
    assert "ANN_PRM_UNT_AMT" not in window._status_label.text()
    assert "could not be calculated" in window._status_label.text()
    assert any("ANN_PRM_UNT_AMT" in record.getMessage() for record in caplog.records)
    assert caplog.records[-1].exc_info is not None


def test_missing_illustration_rate_message_is_kept(window, monkeypatch):
    shown = _fail_run(window, monkeypatch, RateLookupError("No COI rate for 1U143900 age 99"))
    assert shown == [("warning", "Missing Illustration Rate", "No COI rate for 1U143900 age 99")]
