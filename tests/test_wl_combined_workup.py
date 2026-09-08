"""Mixed source kinds must form one complete reviewable Whole Life package."""

from collections import OrderedDict
import json
from unittest.mock import MagicMock

import pytest

from suiteview.ratemanager.database_loader import PackageValidationError, TableData
from suiteview.ratemanager.whole_life import service


KIND_TABLES = {
    "CVF": ("WL_RATE_CV",),
    "IAF": ("WL_RATE_PREM",),
    "Dividend": ("WL_DIV_HEADER", "WL_RATE_DIV"),
    "PUI": ("WL_RATE_PUI",),
    "NSP": ("WL_RATE_NSP",),
    "Dividend map": ("WL_DIV_PLANKEY_MAP",),
}


@pytest.fixture
def parse_kind(monkeypatch):
    def parse(kind, paths, user_code, *, infer_cvf_negatives=False):
        tables = OrderedDict(
            (name, TableData(service.TABLES[name].spec, ()))
            for name in KIND_TABLES[kind]
        )
        return service.WholeLifePackage(
            tables, tuple(
                {"path": path, "kind": kind, "user_code": user_code}
                for path in paths
            ),
        )
    mock = MagicMock(side_effect=parse)
    monkeypatch.setattr(service, "parse_sources", mock)
    return mock


def test_all_four_sources_merge_in_database_order_with_provenance(parse_kind):
    files = {
        "IAF": ["premium.txt"], "Dividend": ["div1.txt", "div2.txt"],
        "PUI": ["pui.txt"], "CVF": ["cv.txt"], "NSP": [], "Dividend map": [],
    }
    package = service.parse_workup(files, " 06 ")
    expected = {"WL_RATE_CV", "WL_RATE_PREM", "WL_DIV_HEADER", "WL_RATE_DIV", "WL_RATE_PUI"}
    assert list(package.tables) == [name for name in service.TABLES if name in expected]
    assert len(package.sources) == 5
    assert parse_kind.call_count == 4
    assert package.sources[0] == {"path": "premium.txt", "kind": "IAF", "user_code": "06"}
    assert all(s["user_code"] == "" for s in package.sources[1:])
    assert files["NSP"] == []


@pytest.mark.parametrize("kind", list(KIND_TABLES))
def test_partial_workups_preserve_each_existing_import_kind(parse_kind, kind):
    package = service.parse_workup({kind: ["source.txt"]}, "01")
    assert set(package.tables) == set(KIND_TABLES[kind])
    parse_kind.assert_called_once_with(
        kind, ["source.txt"], "01" if kind == "IAF" else "", infer_cvf_negatives=False,
    )


@pytest.mark.parametrize("files", [{}, {"CVF": [], "IAF": [], "Dividend": [], "PUI": []}])
def test_empty_workups_fail_before_parsing(parse_kind, files):
    with pytest.raises(PackageValidationError, match="at least one"):
        service.parse_workup(files)
    parse_kind.assert_not_called()


@pytest.mark.parametrize("code", ["", "6", "ABC", "006"])
def test_iaf_requires_valid_company_before_any_source_is_parsed(parse_kind, code):
    with pytest.raises(PackageValidationError, match="two digits"):
        service.parse_workup({"CVF": ["cv.txt"], "IAF": ["premium.txt"]}, code)
    parse_kind.assert_not_called()


def test_unknown_kind_is_rejected_even_when_empty(parse_kind):
    with pytest.raises(PackageValidationError, match="Unsupported"):
        service.parse_workup({"CVF": ["cv.txt"], "TYPO": []})
    parse_kind.assert_not_called()


def test_failure_in_later_source_does_not_return_a_partial_workup(parse_kind):
    initial = service.WholeLifePackage(OrderedDict())
    parse_kind.side_effect = [initial, PackageValidationError("bad PUI source")]
    with pytest.raises(PackageValidationError, match="bad PUI source"):
        service.parse_workup({"CVF": ["cv.txt"], "PUI": ["bad.txt"]})
    assert parse_kind.call_count == 2


def test_source_kinds_cannot_silently_overwrite_another_tables_data(parse_kind):
    table = TableData(service.TABLES["WL_RATE_CV"].spec, ())
    parse_kind.return_value = service.WholeLifePackage(OrderedDict(WL_RATE_CV=table))
    parse_kind.side_effect = None
    with pytest.raises(PackageValidationError, match="overlapping tables"):
        service.parse_workup({"CVF": ["cv.txt"], "PUI": ["pui.txt"]})


def test_cvf_inference_is_forwarded_only_to_cash_values(parse_kind):
    service.parse_workup(
        {"CVF": ["cv.txt"], "PUI": ["pui.txt"]}, infer_cvf_negatives=True,
    )
    assert parse_kind.call_args_list[0].kwargs == {"infer_cvf_negatives": True}
    assert parse_kind.call_args_list[1].kwargs == {"infer_cvf_negatives": False}


@pytest.mark.parametrize("option", ["false", "true", 1, None])
def test_cvf_inference_option_requires_boolean_before_parsing(parse_kind, option):
    with pytest.raises(PackageValidationError, match="true or false"):
        service.parse_workup({"CVF": ["cv.txt"]}, infer_cvf_negatives=option)
    parse_kind.assert_not_called()


def test_cvf_inference_requires_cash_value_files(parse_kind):
    with pytest.raises(PackageValidationError, match="requires CVF"):
        service.parse_workup({"PUI": ["pui.txt"]}, infer_cvf_negatives=True)
    parse_kind.assert_not_called()


def test_workup_cli_persists_progress_without_polluting_json_report(tmp_path, monkeypatch, capsys):
    from tools.rates import wl_rate_workup

    output = tmp_path / "preview.json"
    source = service.WholeLifePackage(OrderedDict(), ({
        "path": "cash.txt", "cvf_inference": {"adjusted_rows": 4},
    },))
    parse = MagicMock(return_value=source)
    monkeypatch.setattr(wl_rate_workup, "parse_sources", parse)
    monkeypatch.setattr(wl_rate_workup.sys, "argv", ["workup", json.dumps({
        "action": "preview", "kind": "CVF", "paths": ["cash.txt"],
        "infer_cvf_negatives": True, "output": str(output),
    })])
    wl_rate_workup.main()
    captured = capsys.readouterr()
    assert json.loads(captured.out) == json.loads(output.read_text())
    phases = [json.loads(line) for line in captured.err.splitlines()]
    assert [item["phase"] for item in phases] == ["parsing", "parsed", "complete"]
    assert phases[1]["inferred_rows"] == 4
    assert json.loads(output.with_suffix(".progress.json").read_text()) == phases[-1]
    parse.assert_called_once_with("CVF", ["cash.txt"], "", infer_cvf_negatives=True)
