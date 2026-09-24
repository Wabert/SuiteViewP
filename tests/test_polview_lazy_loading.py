"""Progressive data loading stays responsive and never paints a stale policy."""

from contextlib import nullcontext
from copy import deepcopy
from threading import Event, get_ident
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import pyodbc
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QTimer
from PyQt6.QtWidgets import QApplication, QLabel

from suiteview.polview.ui import main_window
from suiteview.polview.ui.policy_load_controller import PolicyLoadController, DETAIL_STAGES


class FakePolicy(SimpleNamespace):
    def detached_copy(self):
        return deepcopy(self)

    def merge_prefetched(self, other):
        assert self.policy_number == other.policy_number
        assert self.company_code == other.company_code

    def cached_reads_only(self):
        return nullcontext()


def policy(number="FIRST", *, advanced=True, company="01", system="I"):
    return FakePolicy(
        exists=True, available_companies=[], last_error="",
        policy_number=number, region="CKPR", company_code=company,
        system_code=system, policy_id=f"{number} TEST",
        is_advanced_product=advanced, status_description="Active",
    )


@pytest.fixture
def host(qtbot, monkeypatch, tmp_path):
    monkeypatch.setenv("SUITEVIEW_PROFILE_DIR", str(tmp_path))
    state = SimpleNamespace(
        gates={}, entered=[], calls=[], closed=[], rendered=[],
        failures={}, errors={}, policies={}, unavailable=set(), sessions=[],
    )

    class Session:
        def __init__(self, number, region, company, *, seed=None):
            self.number = number
            self.policy = seed or state.policies.get(number) or policy(number)
            state.sessions.append((number, seed))

        def _prepare(self, stage):
            state.entered.append((self.number, stage))
            gate = state.gates.get((self.number, stage))
            if gate is not None and not gate.wait(5):
                raise TimeoutError("Test worker was not released")
            state.calls.append((self.number, stage, get_ident()))
            if state.failures.get(stage, 0):
                state.failures[stage] -= 1
                raise state.errors.get(stage, RuntimeError(f"{stage} database unavailable"))
            return SimpleNamespace(
                policy=self.policy.detached_copy(), stage=stage,
                available=stage not in state.unavailable,
                payload=f"{self.number}:{stage}",
            )

        def load_initial(self):
            return self._prepare("coverages")

        def prepare(self, stage):
            return self._prepare(stage)

        def close(self):
            state.closed.append(get_ident())

    monkeypatch.setattr(
        main_window, "PolicyLoadController",
        lambda: PolicyLoadController(session_factory=Session),
    )
    monkeypatch.setattr(main_window, "cache_policy_info", Mock())
    monkeypatch.setattr(main_window, "DB2Connection", Mock())
    window = main_window.GetPolicyWindow(enable_policy_list=False)
    for stage, (tab, _title) in window._stage_tabs.items():
        if stage in ("other", "raw"):
            continue
        label = QLabel(tab)

        def populate(loaded, *extra, label=label, stage=stage):
            state.rendered.append((loaded.policy_number, stage, get_ident(), extra))
            label.setText(loaded.policy_number)

        monkeypatch.setattr(tab, "load_data_from_policy", Mock(side_effect=populate))
        tab.test_label = label
    for name in ("reset_for_new_policy", "store_connection_info",
                 "enable_rates_tab", "show_rates_tab"):
        monkeypatch.setattr(window.records_tree, name, Mock())
    window.show()
    yield window, state
    for gate in state.gates.values():
        gate.set()
    window._loader.shutdown()
    if not sip.isdeleted(window):
        window.close()
        window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def settled(qtbot, window):
    qtbot.waitUntil(lambda: not window._loader.busy, timeout=5000)


@pytest.mark.parametrize("stage", ["coverages", "policy"])
def test_communication_failure_retries_once_without_password_prompt(host, qtbot, monkeypatch, stage):
    window, state = host
    prompt = Mock()
    monkeypatch.setattr(main_window, "_show_odbc_warning", prompt)
    state.failures[stage] = 1
    state.errors[stage] = pyodbc.Error(
        "08001", "[08001] SQLCODE = -30081, TCP/IP COMMUNICATIONS ERROR\x00garbage")
    window.load_policy("FIRST")
    settled(qtbot, window)
    assert window._tab_states[stage] == "ready"
    assert sum(s == stage for _, s, _ in state.calls) == 2
    prompt.assert_not_called()
    if stage == "coverages":
        assert len(state.sessions) == 2
        assert state.closed


def test_persistent_transport_error_is_clean_and_manual_retry_remains(host, qtbot, monkeypatch):
    window, state = host
    prompt = Mock()
    monkeypatch.setattr(main_window, "_show_odbc_warning", prompt)
    state.failures["coverages"] = 2
    state.errors["coverages"] = pyodbc.Error(
        "08001", "[08001] SQLCODE = -30081, TCP/IP COMMUNICATIONS ERROR\x00garbage")
    window.load_policy("FIRST")
    settled(qtbot, window)
    assert window._tab_states["coverages"] == "failed"
    assert len(state.calls) == 2
    detail = window.tabs.tabToolTip(window.tabs.indexOf(window.coverages_tab))
    assert "-30081" in detail
    assert "reconnecting once" in detail
    assert "garbage" not in detail
    assert "password" not in detail.lower()
    prompt.assert_not_called()
    window._retry_policy_tab("coverages")
    settled(qtbot, window)
    assert window._tab_states["coverages"] == "ready"


def test_authentication_error_prompts_without_automatic_retry(host, qtbot, monkeypatch):
    window, state = host
    prompt = Mock()
    monkeypatch.setattr(main_window, "_show_odbc_warning", prompt)
    state.failures["coverages"] = 1
    state.errors["coverages"] = pyodbc.Error("28000", "[28000] Invalid password")
    window.load_policy("FIRST")
    settled(qtbot, window)
    assert len(state.calls) == 1
    prompt.assert_called_once()
    assert window._tab_states["coverages"] == "failed"


def test_initial_request_returns_immediately_and_gui_keeps_ticking(host, qtbot):
    window, state = host
    gate = state.gates[("FIRST", "coverages")] = Event()
    ticks = []
    timer = QTimer(window)
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start()
    start = perf_counter()
    window.load_policy("FIRST")
    assert perf_counter() - start < 0.15
    assert window._policy is None
    assert window._load_overlays["coverages"].isVisible()
    assert not window.records_tree.isEnabled()
    qtbot.waitUntil(lambda: len(ticks) >= 5)
    assert not state.rendered
    gate.set()
    qtbot.waitUntil(lambda: window.coverages_tab.test_label.text() == "FIRST")
    timer.stop()
    assert QApplication.overrideCursor() is None
    assert window.records_tree.isEnabled()
    assert all(thread != get_ident() for _, _, thread in state.calls)
    assert all(thread == get_ident() for _, _, thread, _ in state.rendered)


def test_details_prepare_without_selection_and_render_only_when_selected(host, qtbot):
    window, state = host
    window.load_policy("FIRST")
    settled(qtbot, window)
    assert {stage for _, stage, _ in state.calls} == {"coverages", *DETAIL_STAGES}
    assert [stage for _, stage, _, _ in state.rendered] == ["coverages"]
    for stage in DETAIL_STAGES:
        tab = window._stage_tabs[stage][0]
        window.tabs.setCurrentWidget(tab)
        window.tabs.setCurrentWidget(window.coverages_tab)
        window.tabs.setCurrentWidget(tab)
        tab.load_data_from_policy.assert_called_once()
        assert tab.test_label.text() == "FIRST"
        assert not window._load_overlays[stage].isVisible()
    for stage in ("advprod", "reinsurance"):
        tab = window._stage_tabs[stage][0]
        assert tab.load_data_from_policy.call_args.args[1] == f"FIRST:{stage}"
    main_window.DB2Connection.return_value.connect.assert_not_called()


def test_selected_tab_moves_ahead_of_other_queued_work(host, qtbot):
    window, state = host
    gate = state.gates[("FIRST", "policy")] = Event()
    window.load_policy("FIRST")
    qtbot.waitUntil(lambda: ("FIRST", "policy") in state.entered)
    window.tabs.setCurrentWidget(window.reinsurance_tab)
    assert window._load_overlays["reinsurance"].isVisible()
    gate.set()
    settled(qtbot, window)
    assert [stage for _, stage, _ in state.calls][:3] == ["coverages", "policy", "reinsurance"]
    assert window.reinsurance_tab.test_label.text() == "FIRST"


def test_switching_policies_discards_inflight_old_result(host, qtbot):
    window, state = host
    gate = state.gates[("FIRST", "reinsurance")] = Event()
    window.load_policy("FIRST")
    qtbot.waitUntil(lambda: ("FIRST", "reinsurance") in state.entered)
    window.tabs.setCurrentWidget(window.reinsurance_tab)
    window.load_policy("SECOND")
    assert window._policy is None
    gate.set()
    settled(qtbot, window)
    assert window._policy.policy_number == "SECOND"
    assert window.tabs.currentWidget() is window.coverages_tab
    window.tabs.setCurrentWidget(window.reinsurance_tab)
    assert window.reinsurance_tab.test_label.text() == "SECOND"
    assert not any(number == "FIRST" and stage == "reinsurance" for number, stage, _, _ in state.rendered)
    assert state.closed and all(thread != get_ident() for thread in state.closed)


@pytest.mark.parametrize("company", ["", "01"])
def test_first_view_of_each_policy_defaults_to_coverages(host, qtbot, company):
    window, state = host
    window.tabs.setCurrentWidget(window.policy_tab)
    window.load_policy("FIRST", company_code=company)
    settled(qtbot, window)
    assert window.tabs.currentWidget() is window.coverages_tab

    window.tabs.setCurrentWidget(window.reinsurance_tab)
    window.load_policy("SECOND", company_code=company)
    settled(qtbot, window)
    assert window.tabs.currentWidget() is window.coverages_tab
    assert window.coverages_tab.test_label.text() == "SECOND"

    window.tabs.setCurrentWidget(window.policy_tab)
    window.load_policy("FIRST", company_code=company)
    settled(qtbot, window)
    assert window.tabs.currentWidget() is window.policy_tab
    assert window.policy_tab.test_label.text() == "FIRST"


def test_new_company_for_same_policy_defaults_to_coverages(host, qtbot):
    window, state = host
    window.load_policy("FIRST", company_code="01")
    settled(qtbot, window)
    window.tabs.setCurrentWidget(window.reinsurance_tab)
    state.policies["FIRST"] = policy("FIRST", company="26")
    window.load_policy("FIRST", company_code="26")
    settled(qtbot, window)
    assert window._policy.company_code == "26"
    assert window.tabs.currentWidget() is window.coverages_tab


def test_second_lookup_cancels_first_before_initial_response(host, qtbot):
    window, state = host
    gate = state.gates[("FIRST", "coverages")] = Event()
    window.load_policy("FIRST")
    qtbot.waitUntil(lambda: ("FIRST", "coverages") in state.entered)
    window.load_policy("SECOND")
    gate.set()
    settled(qtbot, window)
    assert window._policy.policy_number == "SECOND"
    assert all(number == "SECOND" for number, _, _, _ in state.rendered)


def test_failed_page_does_not_block_coverages_or_other_pages_and_retries(host, qtbot):
    window, state = host
    state.failures["reinsurance"] = 1
    window.load_policy("FIRST")
    settled(qtbot, window)
    assert window._tab_states["coverages"] == "ready"
    assert window._tab_states["advprod"] == "ready"
    window.tabs.setCurrentWidget(window.reinsurance_tab)
    overlay = window._load_overlays["reinsurance"]
    assert overlay.isVisible() and overlay.retry_button.isVisible()
    assert "database unavailable" in overlay.message.text()
    overlay.retry_button.click()
    settled(qtbot, window)
    assert window._tab_states["reinsurance"] == "ready"
    assert window.reinsurance_tab.test_label.text() == "FIRST"
    assert not overlay.isVisible()


def test_render_failure_is_not_claimed_ready_and_can_retry(host, qtbot):
    window, state = host
    window.load_policy("FIRST")
    settled(qtbot, window)
    window.policy_tab.load_data_from_policy.side_effect = RuntimeError("Bad rendered field")
    window.tabs.setCurrentWidget(window.policy_tab)
    assert window._tab_states["policy"] == "failed"
    assert "Bad rendered field" in window._load_overlays["policy"].message.text()
    window.policy_tab.load_data_from_policy.side_effect = None
    window._load_overlays["policy"].retry_button.click()
    settled(qtbot, window)
    assert window._tab_states["policy"] == "ready"


def test_initial_failure_and_retry_are_nonmodal(host, qtbot):
    window, state = host
    state.failures["coverages"] = 1
    window.load_policy("FIRST")
    settled(qtbot, window)
    assert window._policy is None
    assert window._load_overlays["coverages"].retry_button.isVisible()
    window._load_overlays["coverages"].retry_button.click()
    settled(qtbot, window)
    assert window._policy.policy_number == "FIRST"


@pytest.mark.parametrize("origin", ["query", "rerun"])
@pytest.mark.parametrize("transport_failure", [False, True])
def test_handoff_failure_identifies_requested_policy_and_get_recovers(
    host, qtbot, origin, transport_failure,
):
    window, state = host
    window.load_policy("FIRST", company_code="01")
    settled(qtbot, window)
    state.failures["coverages"] = 2 if transport_failure else 1
    if transport_failure:
        state.errors["coverages"] = pyodbc.Error("08S01", "Host communication failed")
    if origin == "query":
        from suiteview.audit.audit_window import AuditWindow

        caller = SimpleNamespace(
            cmb_region=SimpleNamespace(currentText=lambda: "CKPR"),
            _polview_provider=lambda: window, _polview_window=None,
        )
        AuditWindow._open_polview_with_policy(caller, "SECOND", "01")
    else:
        from suiteview.illustration.ui.main_window import IllustrationWindow

        caller = SimpleNamespace(
            _current_policy="SECOND", _current_region="CKPR",
            _policy_info={"CompanyCode": "01"}, _polview_launcher=window.load_policy,
        )
        IllustrationWindow._open_in_polview(caller)
    assert "SECOND" in window.lookup_bar.policy_label.text()
    assert "FIRST" not in window.lookup_bar.policy_label.text()
    settled(qtbot, window)
    assert window._policy is None
    assert "SECOND" in window.lookup_bar.policy_label.text()
    assert not window.open_record_btn.isEnabled()
    window.lookup_bar.get_button.click()
    settled(qtbot, window)
    assert window._policy.policy_number == "SECOND"
    assert window.coverages_tab.test_label.text() == "SECOND"
    assert window.open_record_btn.isEnabled()


def test_optional_tab_checks_remove_absent_data_without_loading_on_gui(host, qtbot):
    window, state = host
    state.unavailable.update(("loans", "dividends"))
    state.policies["TRAD"] = policy("TRAD", advanced=False)
    window.load_policy("TRAD")
    settled(qtbot, window)
    for tab in (window.advprod_tab, window.loans_tab, window.dividends_tab):
        assert window.tabs.indexOf(tab) == -1
        tab.load_data_from_policy.assert_not_called()


def test_company_chooser_has_no_background_detail_queries(host, qtbot, monkeypatch):
    window, state = host
    state.policies["AMBIGUOUS"] = FakePolicy(
        exists=False, available_companies=["01", "04"], last_error="",
    )
    chooser = Mock()
    monkeypatch.setattr(window.lookup_bar, "show_company_chooser", chooser)
    window.load_policy("AMBIGUOUS")
    settled(qtbot, window)
    chooser.assert_called_once_with(["01", "04"], "AMBIGUOUS", "CKPR")
    assert [stage for _, stage, _ in state.calls] == ["coverages"]
    assert window._policy is None


def test_cached_switch_hands_worker_an_independent_snapshot(host, qtbot):
    window, state = host
    window.load_policy("FIRST")
    settled(qtbot, window)
    first = window._policy
    window.load_policy("SECOND")
    settled(qtbot, window)
    window.load_policy("FIRST", company_code="01")
    settled(qtbot, window)
    assert state.sessions[-1][1] is not first
    assert state.sessions[-1][1].policy_number == first.policy_number
    assert window.coverages_tab.test_label.text() == "FIRST"


def test_disposing_during_query_does_not_block_gui_or_deliver_results(host, qtbot):
    window, state = host
    gate = state.gates[("FIRST", "coverages")] = Event()
    window.load_policy("FIRST")
    qtbot.waitUntil(lambda: ("FIRST", "coverages") in state.entered)
    start = perf_counter()
    window._loader.dispose()
    assert perf_counter() - start < 0.1
    gate.set()
    qtbot.waitUntil(
        lambda: sip.isdeleted(window._loader._thread) or not window._loader._thread.isRunning(),
    )
    assert not state.rendered
    assert state.closed and all(thread != get_ident() for thread in state.closed)


def test_destroying_window_during_query_closes_worker_without_gui_callbacks(host, qtbot):
    window, state = host
    gate = state.gates[("FIRST", "coverages")] = Event()
    window.load_policy("FIRST")
    qtbot.waitUntil(lambda: ("FIRST", "coverages") in state.entered)
    controller = window._loader
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(window)
    assert controller._disposed
    gate.set()
    qtbot.waitUntil(lambda: bool(state.closed))
    qtbot.waitUntil(lambda: sip.isdeleted(controller))
    assert not state.rendered
    assert all(thread != get_ident() for thread in state.closed)
