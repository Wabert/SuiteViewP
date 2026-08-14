"""Tests for the read-only (SuiteViewLight) edition flag in build_env."""
import importlib

import pytest

from suiteview.core import build_env


def _reload():
    return importlib.reload(build_env)


def test_not_light_from_source(monkeypatch):
    """Running from source (no frozen, no env) is the full, writable edition."""
    monkeypatch.delenv("SUITEVIEW_LIGHT", raising=False)
    monkeypatch.setattr(build_env.sys, "frozen", False, raising=False)
    assert build_env.is_light_build() is False
    assert build_env.is_data_read_only() is False


def test_env_forces_light(monkeypatch):
    """SUITEVIEW_LIGHT=1 forces the read-only edition from source."""
    monkeypatch.setenv("SUITEVIEW_LIGHT", "1")
    assert build_env.is_light_build() is True
    assert build_env.is_data_read_only() is True


def test_env_other_values_do_not_enable(monkeypatch):
    """Only the exact value "1" enables Light (mirrors SUITEVIEW_LOCAL_DATA)."""
    monkeypatch.setattr(build_env.sys, "frozen", False, raising=False)
    for val in ("0", "true", "yes", "light", ""):
        monkeypatch.setenv("SUITEVIEW_LIGHT", val)
        assert build_env.is_light_build() is False


def test_frozen_exe_name_detects_light(monkeypatch):
    """A frozen SuiteViewLight.exe is detected as the Light edition."""
    monkeypatch.delenv("SUITEVIEW_LIGHT", raising=False)
    monkeypatch.setattr(build_env.sys, "frozen", True, raising=False)
    monkeypatch.setattr(build_env.sys, "executable",
                        r"C:\dist\SuiteViewLight\SuiteViewLight.exe", raising=False)
    assert build_env.is_light_build() is True

    monkeypatch.setattr(build_env.sys, "executable",
                        r"C:\dist\SuiteView\SuiteView.exe", raising=False)
    assert build_env.is_light_build() is False


def test_guard_raises_only_when_read_only(monkeypatch):
    monkeypatch.setenv("SUITEVIEW_LIGHT", "1")
    with pytest.raises(build_env.ReadOnlyDataError):
        build_env.guard_data_writable("do a write")

    monkeypatch.delenv("SUITEVIEW_LIGHT", raising=False)
    monkeypatch.setattr(build_env.sys, "frozen", False, raising=False)
    # Should not raise in the writable edition.
    build_env.guard_data_writable("do a write")
