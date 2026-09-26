"""Startup options and entry-point delegation tests."""

from __future__ import annotations

from suiteview.startup import StartupOptions


def test_startup_options_default_and_local_identities():
    live = StartupOptions()
    assert live.local_data is False
    assert live.title == "SuiteView"
    assert live.mutex_name == "SuiteView_SingleInstance_Mutex"
    assert live.app_user_model_id == "SuiteView.FileExplorer.1"
    assert live.crash_log_name == "suiteview_crash.log"

    local = StartupOptions(local_data=True)
    assert local.title == "SuiteView (LOCAL DATA)"
    assert local.mutex_name == "SuiteView_Local_SingleInstance_Mutex"
    assert local.app_user_model_id == "SuiteView.LocalData.1"
    assert local.crash_log_name == "suiteview_local_crash.log"


def test_entrypoint_options_without_event_loop():
    import scripts.run_suiteview as script_entry
    import suiteview.main as package_entry

    package_options = package_entry.build_options()
    assert package_options.title == "SuiteView"
    assert package_options.crash_log_name == "crash.log"

    live_script = script_entry.build_options()
    assert live_script.title == "SuiteView"
    assert live_script.mutex_name == "SuiteView_SingleInstance_Mutex"
    assert live_script.crash_log_name == "suiteview_crash.log"

    local_script = script_entry.build_options(local_data=True)
    assert local_script.title == "SuiteView (LOCAL DATA)"
    assert local_script.mutex_name == "SuiteView_Local_SingleInstance_Mutex"
    assert local_script.crash_log_name == "suiteview_local_crash.log"


def test_entrypoint_main_delegates_without_event_loop(monkeypatch):
    import scripts.run_suiteview as script_entry
    import suiteview.main as package_entry

    called = []

    def fake_run(options):
        called.append(options)
        return 17

    monkeypatch.setattr(package_entry, "run_suiteview", fake_run)
    assert package_entry.main() == 17
    assert called[-1].crash_log_name == "crash.log"

    monkeypatch.setattr(script_entry, "run_suiteview", fake_run)
    assert script_entry.main(local_data=True) == 17
    assert called[-1].local_data is True
    assert called[-1].title == "SuiteView (LOCAL DATA)"
