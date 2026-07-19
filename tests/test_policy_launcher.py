"""Taskbar policy launcher + PolView "Open in Illustrator" wiring (headless Qt).

Typing a policy number in the taskbar's compact bar and clicking PolView / ABR
Quote / Illustration must open that app with the policy already loaded, routed
through each app's existing Get/Retrieve path. An empty policy field must leave
today's plain-open behavior untouched. PolView's header "Open in Illustrator"
button funnels the current policy through the same illustration launcher and is
inert until a policy is loaded.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.abrquote.ui.abr_window import ABRQuoteWindow
from suiteview.illustration.ui.main_window import IllustrationWindow
from suiteview.polview.ui.main_window import GetPolicyWindow
from suiteview.taskbar_launcher.suiteview_taskbar import SuiteViewTaskbar

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


# ── Illustration window: initial_policy drives the Get path ───────────


def test_illustration_initial_policy_calls_load_policy(monkeypatch):
    _app()
    calls = []
    monkeypatch.setattr(
        IllustrationWindow, "load_policy",
        lambda self, policy, region="CKPR", company_code="": calls.append(
            (policy, region, company_code)),
    )
    win = IllustrationWindow(initial_policy="E0213651", initial_region="CKMO",
                             initial_company="04")
    assert calls == [("E0213651", "CKMO", "04")]
    win.close()


def test_illustration_no_initial_policy_does_not_load(monkeypatch):
    _app()
    calls = []
    monkeypatch.setattr(
        IllustrationWindow, "load_policy",
        lambda self, *a, **kw: calls.append((a, kw)),
    )
    win = IllustrationWindow()
    assert calls == []
    win.close()


def test_illustration_load_policy_routes_through_lookup_bar():
    _app()
    win = IllustrationWindow()
    fired = []
    win.lookup_bar._on_get_policy = lambda: fired.append(True)
    win.load_policy("E0213651", region="CKMO", company_code="04")
    assert win.lookup_bar.region_input.text() == "CKMO"
    assert win.lookup_bar.company_input.text() == "04"
    assert win.lookup_bar.policy_input.text() == "E0213651"
    assert fired == [True]
    win.close()


# ── ABR window: initial_policy drives the Retrieve path ───────────────


def _mute_abr_onedrive_warning(monkeypatch):
    """OutputPanel pops a MODAL missing-OneDrive warning on machines without
    the synced folder — silence it so window construction can't block."""
    from suiteview.abrquote.ui.output_panel import OutputPanel

    monkeypatch.setattr(OutputPanel, "_check_onedrive_sync", lambda self: None)


def test_abr_initial_policy_calls_load_policy(monkeypatch):
    _app()
    _mute_abr_onedrive_warning(monkeypatch)
    calls = []
    monkeypatch.setattr(
        ABRQuoteWindow, "load_policy",
        lambda self, policy, region="CKPR", company_code="": calls.append(
            (policy, region, company_code)),
    )
    win = ABRQuoteWindow(initial_policy="E0008145")
    assert calls == [("E0008145", "CKPR", "")]
    win.close()


def test_abr_load_policy_routes_through_policy_panel(monkeypatch):
    _app()
    _mute_abr_onedrive_warning(monkeypatch)
    win = ABRQuoteWindow()
    steps, loaded = [], []
    win._set_step = lambda s: steps.append(s)
    win.policy_panel.load_policy = lambda p: loaded.append(p)
    win.load_policy("E0008145", region="CKMO", company_code="04")
    # Region/company are ignored (ABR is always CKPR, company auto-detected),
    # but the window returns to Step 1 and hands the policy to the panel.
    assert steps == [0]
    assert loaded == ["E0008145"]
    win.close()


def test_abr_load_policy_ignores_blank(monkeypatch):
    _app()
    _mute_abr_onedrive_warning(monkeypatch)
    win = ABRQuoteWindow()
    loaded = []
    win.policy_panel.load_policy = lambda p: loaded.append(p)
    win.load_policy("   ")
    assert loaded == []
    win.close()


# ── PolView header "Open in Illustrator" button ───────────────────────


def test_polview_illustrator_button_disabled_without_policy():
    _app()
    win = GetPolicyWindow(enable_policy_list=False)
    assert win.open_illustrator_btn.isEnabled() is False
    assert win.open_illustrator_btn.toolTip() == "Open this policy in the Illustrator"
    win.close()


def test_polview_open_in_illustrator_noop_without_policy():
    _app()
    win = GetPolicyWindow(enable_policy_list=False)
    launched = []
    win.set_illustration_launcher(
        lambda policy, region, company: launched.append((policy, region, company)))
    win._current_policy = None
    win._open_in_illustrator()
    assert launched == []
    win.close()


def test_polview_open_in_illustrator_launches_current_policy():
    _app()
    win = GetPolicyWindow(enable_policy_list=False)
    launched = []
    win.set_illustration_launcher(
        lambda policy, region, company: launched.append((policy, region, company)))
    win._current_policy = "E0213651"
    win._current_region = "CKMO"
    win._policy_info = {"CompanyCode": "04"}
    win._open_in_illustrator()
    assert launched == [("E0213651", "CKMO", "04")]
    win.close()


# ── Taskbar compact-bar pass-through ──────────────────────────────────


class _FakeInput:
    def __init__(self, text=""):
        self._text = text

    def text(self):
        return self._text


class _FakeCombo:
    def __init__(self, value="CKPR"):
        self._value = value

    def currentText(self):
        return self._value


class _FakeWindow:
    """Records the policy handed to a launched app window."""

    def __init__(self):
        self.loaded = []

    def load_policy(self, policy, region="CKPR", company_code=""):
        self.loaded.append((policy, region, company_code))


def _bare_taskbar(policy="", region="CKPR"):
    """A SuiteViewTaskbar with only the compact-bar surface the launch
    handlers touch — built via __new__ to skip the heavy Win32/UI __init__."""
    bar = SuiteViewTaskbar.__new__(SuiteViewTaskbar)
    bar._is_compact_mode = True
    bar.compact_policy_input = _FakeInput(policy)
    bar.compact_region_combo = _FakeCombo(region)
    bar.abrquote_window = None
    bar.illustration_window = None
    bar._bring_to_front = lambda w: None
    return bar


def test_taskbar_illustration_button_passes_typed_policy():
    _app()
    bar = _bare_taskbar(policy="E0213651", region="CKMO")
    win = _FakeWindow()

    def _open():
        bar.illustration_window = win

    bar._open_illustration = _open
    bar._illustration_btn_clicked()
    assert win.loaded == [("E0213651", "CKMO", "")]


def test_taskbar_illustration_button_empty_policy_is_plain_open():
    _app()
    bar = _bare_taskbar(policy="")
    win = _FakeWindow()
    opened = []

    def _open():
        opened.append(True)
        bar.illustration_window = win

    bar._open_illustration = _open
    bar._illustration_btn_clicked()
    assert opened == [True]        # window still opened...
    assert win.loaded == []        # ...but no policy pushed in


def test_taskbar_abr_button_passes_typed_policy():
    _app()
    bar = _bare_taskbar(policy="E0008145")
    win = _FakeWindow()

    def _open():
        bar.abrquote_window = win

    bar._open_abrquote = _open
    bar._abrquote_btn_clicked()
    assert win.loaded == [("E0008145", "CKPR", "")]


def test_taskbar_abr_button_empty_policy_is_plain_open():
    _app()
    bar = _bare_taskbar(policy="")
    win = _FakeWindow()
    opened = []

    def _open():
        opened.append(True)
        bar.abrquote_window = win

    bar._open_abrquote = _open
    bar._abrquote_btn_clicked()
    assert opened == [True]
    assert win.loaded == []


def test_taskbar_polview_with_policy_uses_load_policy():
    _app()
    bar = _bare_taskbar(policy="E0213651", region="CKMO")
    win = _FakeWindow()
    bar._get_polview_window = lambda: win
    bar._open_polview_with_policy()
    # Company left blank so PolView auto-detects it.
    assert win.loaded == [("E0213651", "CKMO", "")]


def test_taskbar_polview_empty_policy_does_nothing():
    _app()
    bar = _bare_taskbar(policy="")
    called = []
    bar._get_polview_window = lambda: called.append(True)
    bar._open_polview_with_policy()
    assert called == []


def test_taskbar_launch_illustration_with_policy_reuses_window():
    """PolView's 'Open in Illustrator' funnels through this shared launcher."""
    _app()
    bar = _bare_taskbar()
    win = _FakeWindow()

    def _open():
        bar.illustration_window = win

    bar._open_illustration = _open
    bar._launch_illustration_with_policy("E0213651", region="CKMO",
                                         company_code="04")
    assert win.loaded == [("E0213651", "CKMO", "04")]
