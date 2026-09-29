"""The PolView policy badge strip, shared with RERUN."""

from __future__ import annotations

import os
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.polview.models.policy_data import CachedReadError
from suiteview.polview.services import policy_insights
from suiteview.polview.services.policy_insights import (
    INFO, OK, Chip, PolicySummary, _Reader,
)
from suiteview.polview.ui.policy_summary_strip import (
    POLVIEW_STRIP_THEME, PolicySummaryStrip, StripTheme, chip_style,
)


_QT_APP = None


@pytest.fixture
def app(monkeypatch, tmp_path):
    global _QT_APP
    monkeypatch.setenv("SUITEVIEW_PROFILE_DIR", str(tmp_path / "profile"))
    from suiteview.core import access_control

    monkeypatch.setattr(access_control, "guard_app_access", lambda _code: None)
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _unprefetched_policy():
    @contextmanager
    def guard():
        raise CachedReadError("not prefetched")
        yield  # pragma: no cover

    return SimpleNamespace(cached_reads_only=guard, plancode="B11EP200")


def test_live_reads_skip_the_prefetch_guard():
    policy = _unprefetched_policy()
    cached = _Reader(policy)
    assert cached.get("plancode") is None and cached.pending == ["plancode"]
    live = _Reader(policy, live=True)
    assert live.get("plancode") == "B11EP200" and live.pending == []


def test_strip_theme_changes_the_frame_but_never_the_badges(app):
    polview = PolicySummaryStrip()
    rerun = PolicySummaryStrip(theme=StripTheme(border="#5E35A5", text="#2A1458", hover_bg="#EDE7F6"))
    assert POLVIEW_STRIP_THEME.border in polview.styleSheet()
    assert "#5E35A5" in rerun.styleSheet() and POLVIEW_STRIP_THEME.border not in rerun.styleSheet()
    assert "#2A1458" in rerun.copy_button.styleSheet()
    summary = _summary()
    for strip in (polview, rerun):
        strip.set_summary(summary)
        label = strip._chip_labels["status"]
        assert label.styleSheet() == chip_style(OK)
    assert polview.chip_texts() == rerun.chip_texts() == ["22 Premium Paying", "Joint Second to Die"]


def _summary() -> PolicySummary:
    return PolicySummary(
        policy_number="000335148", company_code="26", company_name="FFL", region="CKPR",
        system_code="I", plancode="B11EP200",
        chips=(Chip("status", "22 Premium Paying", OK), Chip("joint", "Joint Second to Die", INFO)))


def test_rerun_window_shows_the_policy_badges_under_the_lookup_bar(app, monkeypatch):
    from suiteview.illustration.ui import main_window
    from suiteview.illustration.ui.main_window import IllustrationWindow

    calls = []

    def fake_summary(policy, today=None, *, live_reads=False):
        calls.append(live_reads)
        return _summary()

    monkeypatch.setattr(main_window, "build_policy_summary", fake_summary)
    window = IllustrationWindow()
    try:
        strip = window.summary_strip
        layout = window.lookup_bar.parentWidget().layout()
        assert layout.indexOf(strip.parentWidget()) == layout.indexOf(window.lookup_bar) + 1
        assert strip.message_label.text() == "Enter a policy number to begin"
        assert not strip.copy_button.isEnabled()

        window._policy = SimpleNamespace(exists=True, company_code="26", policy_number="000335148")
        window._notes_store.add("26", "000335148", "Checked the joint COI")
        window._refresh_summary_strip()
        assert calls == [True]
        assert strip.chip_texts() == ["22 Premium Paying", "Joint Second to Die"]
        assert strip.suggestion_keys() == []
        assert strip.notes_button.text() == "📝 Notes (1)"

        window._copy_policy_summary()
        assert QApplication.clipboard().mimeData().text().startswith("Policy:")
        assert "000335148" in window._status_label.text()

        def broken(policy, today=None, *, live_reads=False):
            raise RuntimeError("DB2 down")

        monkeypatch.setattr(main_window, "build_policy_summary", broken)
        window._refresh_summary_strip()
        assert strip.message_label.text() == "Policy badges unavailable: DB2 down"
        assert strip.summary is None
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_summary_builder_forwards_live_reads(monkeypatch):
    seen = []
    real = policy_insights._Reader

    class Spy(real):
        def __init__(self, policy, live=False):
            seen.append(live)
            super().__init__(policy, live)

    monkeypatch.setattr(policy_insights, "_Reader", Spy)
    policy = SimpleNamespace(policy_number="X", company_code="01")
    policy_insights.build_policy_summary(policy, live_reads=True)
    assert seen and all(seen)
