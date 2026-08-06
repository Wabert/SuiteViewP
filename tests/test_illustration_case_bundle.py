"""Readable case bundles (.cases.json) and the imported-case store.

A bundle is the transparent, human-readable export/import format: an envelope
with a ``cases`` array (a single case is just a bundle of one). The imported
store keeps each imported bundle file as its own node, preserving file grouping,
in a collection separate from the saved cases.
"""
import json

import pytest

from suiteview.illustration.models import (
    case_bundle,
    case_store,
    imported_case_store,
)
from suiteview.illustration.models.case_bundle import (
    BUNDLE_SUFFIX,
    CaseBundleError,
)
from suiteview.illustration.models.imported_case_store import (
    ImportedBundleExistsError,
    ImportedCaseError,
)


def _inputs(marker: str = "x") -> dict:
    return {
        "grids": {"unscheduled_premiums": [[0, ["06/15/2027", "1,000"]]]},
        "controls": {"exact_days": True, "duration_years": "20"},
        "dynamic": {"lumpsum": marker, "riders": {}, "sections": {}},
    }


def _saved(name, tmp_path, *, marker="x", policy="UL000001"):
    """Create and return a real SavedCase in a tmp store."""
    store = tmp_path / "saved"
    case_store.save_case(
        name, policy_number=policy, region="CKPR", company_code="01",
        inputs=_inputs(marker), overwrite=True, directory=store)
    return case_store.load_case(name, directory=store)


# ── bundle round-trips ───────────────────────────────────────────────


def test_single_case_bundle_round_trip(tmp_path):
    case = _saved("Case One", tmp_path, marker="one")
    path = case_bundle.write_bundle(tmp_path / "out", [case], name="Case One")
    assert path.name == f"out{BUNDLE_SUFFIX}"

    result = case_bundle.read_bundle(path)
    assert not result.has_errors
    assert len(result.cases) == 1
    loaded = result.cases[0]
    assert loaded.name == "Case One"
    assert loaded.inputs == case.inputs
    assert loaded.policy_number == "UL000001"


def test_multi_case_bundle_uses_same_shape(tmp_path):
    cases = [
        _saved("Alpha", tmp_path, marker="a", policy="UL000001"),
        _saved("Beta", tmp_path, marker="b", policy="UL000002"),
    ]
    path = case_bundle.write_bundle(tmp_path / "batch", cases, name="My Batch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["kind"] == case_bundle.BUNDLE_KIND
    assert isinstance(payload["cases"], list) and len(payload["cases"]) == 2

    result = case_bundle.read_bundle(path)
    assert [c.name for c in result.cases] == ["Alpha", "Beta"]
    assert result.name == "My Batch"


def test_write_bundle_is_pretty_printed(tmp_path):
    case = _saved("Readable", tmp_path)
    path = case_bundle.write_bundle(tmp_path / "r", [case])
    text = path.read_text(encoding="utf-8")
    assert "\n" in text and "  " in text          # indented, not minified


def test_empty_case_list_refused(tmp_path):
    with pytest.raises(CaseBundleError):
        case_bundle.write_bundle(tmp_path / "empty", [])


# ── loud envelope validation ─────────────────────────────────────────


def test_non_json_raises(tmp_path):
    path = tmp_path / "bad.cases.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CaseBundleError):
        case_bundle.read_bundle(path)


def test_wrong_kind_raises(tmp_path):
    path = tmp_path / "wrong.cases.json"
    path.write_text(json.dumps({"kind": "something.else", "cases": []}),
                    encoding="utf-8")
    with pytest.raises(CaseBundleError):
        case_bundle.read_bundle(path)


def test_unknown_version_raises(tmp_path):
    case = _saved("V", tmp_path)
    payload = case_bundle.encode_bundle([case])
    payload["schema_version"] = 999
    path = tmp_path / "v.cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CaseBundleError):
        case_bundle.read_bundle(path)


# ── mixed valid / invalid cases ──────────────────────────────────────


def test_mixed_valid_invalid_collected_not_aborted(tmp_path):
    good = _saved("Good", tmp_path)
    payload = case_bundle.encode_bundle([good])
    # Inject a broken case entry alongside the good one.
    payload["cases"].append({"name": "Broken", "not": "a case"})
    path = tmp_path / "mixed.cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = case_bundle.read_bundle(path)
    assert [c.name for c in result.cases] == ["Good"]
    assert result.has_errors and len(result.errors) == 1
    index, message = result.errors[0]
    assert index == 1
    assert "Broken" in message


# ── imported-case store ──────────────────────────────────────────────


def test_import_single_case_bundle_node_is_case_name(tmp_path):
    store = tmp_path / "imported"
    case = _saved("Solo", tmp_path)
    bundle = imported_case_store.save_imported_bundle(
        "Solo", [case], directory=store)
    assert bundle.is_single
    assert bundle.node_label == "Solo"

    listed = imported_case_store.list_imported_bundles(directory=store)
    assert len(listed) == 1 and listed[0].node_label == "Solo"


def test_import_multi_case_bundle_node_is_display_name(tmp_path):
    store = tmp_path / "imported"
    cases = [_saved("A", tmp_path, policy="UL1"),
             _saved("B", tmp_path, policy="UL2")]
    bundle = imported_case_store.save_imported_bundle(
        "My Batch", cases, directory=store)
    assert not bundle.is_single
    assert bundle.node_label == "My Batch"
    assert [c.name for c in bundle.cases] == ["A", "B"]


def test_import_duplicate_refused_without_overwrite(tmp_path):
    store = tmp_path / "imported"
    case = _saved("Dup", tmp_path)
    imported_case_store.save_imported_bundle("Dup", [case], directory=store)
    assert imported_case_store.bundle_exists("Dup", directory=store)
    with pytest.raises(ImportedBundleExistsError):
        imported_case_store.save_imported_bundle("Dup", [case], directory=store)
    # Overwrite is allowed explicitly.
    imported_case_store.save_imported_bundle(
        "Dup", [case], overwrite=True, directory=store)


def test_unique_display_name_avoids_collision(tmp_path):
    store = tmp_path / "imported"
    case = _saved("N", tmp_path)
    imported_case_store.save_imported_bundle("Batch", [case], directory=store)
    unique = imported_case_store.unique_display_name("Batch", directory=store)
    assert unique == "Batch (2)"


def test_remove_one_case_from_multi_rewrites_bundle(tmp_path):
    store = tmp_path / "imported"
    cases = [_saved("A", tmp_path, policy="UL1"),
             _saved("B", tmp_path, policy="UL2")]
    bundle = imported_case_store.save_imported_bundle(
        "Batch", cases, directory=store)
    remaining = imported_case_store.remove_imported_cases(bundle.path, ["A"])
    assert remaining is not None
    assert [c.name for c in remaining.cases] == ["B"]


def test_remove_last_case_deletes_file(tmp_path):
    store = tmp_path / "imported"
    case = _saved("Solo", tmp_path)
    bundle = imported_case_store.save_imported_bundle(
        "Solo", [case], directory=store)
    result = imported_case_store.remove_imported_cases(bundle.path, ["Solo"])
    assert result is None
    assert not bundle.path.exists()


def test_remove_whole_bundle(tmp_path):
    store = tmp_path / "imported"
    case = _saved("Solo", tmp_path)
    bundle = imported_case_store.save_imported_bundle(
        "Solo", [case], directory=store)
    imported_case_store.remove_imported_bundle(bundle.path)
    assert imported_case_store.list_imported_bundles(directory=store) == []


def test_load_imported_case_by_name(tmp_path):
    store = tmp_path / "imported"
    cases = [_saved("A", tmp_path, marker="aa", policy="UL1"),
             _saved("B", tmp_path, marker="bb", policy="UL2")]
    bundle = imported_case_store.save_imported_bundle(
        "Batch", cases, directory=store)
    loaded = imported_case_store.load_imported_case(bundle.path, "B")
    assert loaded.name == "B"
    assert loaded.inputs["dynamic"]["lumpsum"] == "bb"
    with pytest.raises(ImportedCaseError):
        imported_case_store.load_imported_case(bundle.path, "Missing")
