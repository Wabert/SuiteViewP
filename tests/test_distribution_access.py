"""The distribution builder exposes only the single role-controlled package."""

from pathlib import Path

import pytest

from scripts import build_distribution


def test_builder_help_has_no_edition_switch(monkeypatch, capsys):
    monkeypatch.setattr(build_distribution.sys, "argv", ["build_distribution", "--help"])
    with pytest.raises(SystemExit) as result:
        build_distribution.main()
    assert result.value.code == 0
    assert "--light" not in capsys.readouterr().out
    assert (Path(__file__).resolve().parents[1] / "SuiteView.spec").is_file()


def test_retired_switch_is_rejected_before_building(monkeypatch):
    monkeypatch.setattr(build_distribution.sys, "argv", ["build_distribution", "--light"])
    with pytest.raises(SystemExit) as result:
        build_distribution.main()
    assert result.value.code == 2
