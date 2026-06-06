"""Tests for the DataForge join-canvas (Phase 2).

Two layers:
  * Pure-model unit tests (no Qt): reconcile, linking, multi-key, orientation,
    rejection rules, conversions to engine specs / legacy merge ops, state
    round-trip, and the two legacy importers.
  * An offscreen-Qt smoke test of the view: build the canvas, push queries,
    add a link programmatically, and confirm specs + state round-trip + the
    rendered line-item count stay consistent with the model.

The Qt smoke test forces ``QT_QPA_PLATFORM=offscreen`` so it runs headless on
the minipc; if PyQt6 is unavailable it is skipped, not failed.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from suiteview.audit.dataforge.forge_canvas_model import (  # noqa: E402
    JoinCanvasModel, JoinKey,
)


# ── Pure-model tests ───────────────────────────────────────────────────────

def _two_source_model() -> JoinCanvasModel:
    m = JoinCanvasModel()
    m.set_sources(
        ["pol", "re"],
        columns={
            "pol": ["company_code", "policy_number", "face_amount"],
            "re": ["company_code", "policy_number", "reinsurer"],
        },
    )
    return m


def test_set_sources_reconcile():
    m = _two_source_model()
    assert [s.alias for s in m.sources] == ["pol", "re"]
    assert m.get_source("pol").field_names() == [
        "company_code", "policy_number", "face_amount"]

    # Move a box, then reconcile: surviving box keeps position, gone box drops.
    m.get_source("pol").x = 999.0
    m.add_link("pol", "company_code", "re", "company_code")
    m.set_sources(["pol", "claims"],
                  columns={"pol": ["company_code"], "claims": ["id"]})
    assert [s.alias for s in m.sources] == ["pol", "claims"]
    assert m.get_source("pol").x == 999.0           # position preserved
    assert m.get_source("pol").field_names() == ["company_code"]  # refreshed
    assert m.joins == []                            # join to dropped 're' gone
    print("  set_sources reconcile (preserve/refresh/drop)  OK")


def test_add_link_multikey_and_orientation():
    m = _two_source_model()
    j1 = m.add_link("pol", "company_code", "re", "company_code")
    j2 = m.add_link("pol", "policy_number", "re", "policy_number")
    assert j1 is j2                                  # same relationship reused
    assert len(j1.keys) == 2
    assert j1.left_source == "pol" and j1.right_source == "re"

    # Adding a key in the reverse direction orients to the stored left/right.
    j3 = m.add_link("re", "reinsurer", "pol", "face_amount")
    assert j3 is j1
    last = j1.keys[-1]
    assert last.left_field == "face_amount" and last.right_field == "reinsurer"
    print("  add_link multi-key + orientation  OK")


def test_add_link_rejections():
    m = _two_source_model()
    try:
        m.add_link("pol", "company_code", "pol", "policy_number")
        assert False, "expected self-join rejection"
    except ValueError:
        pass
    try:
        m.add_link("pol", "company_code", "ghost", "x")
        assert False, "expected missing-source rejection"
    except ValueError:
        pass
    # Duplicate key is a no-op (not an error).
    m.add_link("pol", "company_code", "re", "company_code")
    m.add_link("pol", "company_code", "re", "company_code")
    assert len(m.find_join("pol", "re").keys) == 1
    print("  add_link rejections (self/missing/duplicate)  OK")


def test_remove_key_and_join():
    m = _two_source_model()
    m.add_link("pol", "company_code", "re", "company_code")
    m.add_link("pol", "policy_number", "re", "policy_number")
    m.remove_key("pol", "re", JoinKey("company_code", "company_code"))
    assert len(m.find_join("pol", "re").keys) == 1
    # Removing the last key drops the relationship.
    m.remove_key("pol", "re", JoinKey("policy_number", "policy_number"))
    assert m.find_join("pol", "re") is None
    # remove_join nukes an entire relationship.
    m.add_link("pol", "company_code", "re", "company_code")
    m.remove_join("re", "pol")                       # unordered
    assert m.joins == []
    print("  remove_key + remove_join  OK")


def test_set_how_and_enabled():
    m = _two_source_model()
    m.add_link("pol", "company_code", "re", "company_code")
    m.set_how("pol", "re", "left")
    assert m.find_join("pol", "re").how == "left"
    try:
        m.set_how("pol", "re", "banana")
        assert False, "expected bad join-type rejection"
    except ValueError:
        pass
    m.set_enabled("pol", "re", False)
    assert m.find_join("pol", "re").enabled is False
    assert m.to_join_specs() == []                   # disabled excluded
    print("  set_how + set_enabled  OK")


def test_conversions():
    m = _two_source_model()
    m.add_link("pol", "company_code", "re", "company_code")
    m.add_link("pol", "policy_number", "re", "policy_number")
    m.set_how("pol", "re", "left")

    specs = m.to_join_specs()
    assert len(specs) == 1
    spec = specs[0]
    assert spec.left_source == "pol" and spec.right_source == "re"
    assert spec.left_keys == ("company_code", "policy_number")
    assert spec.right_keys == ("company_code", "policy_number")
    assert spec.how == "left"

    cfg = m.to_config_joins()[0]
    assert cfg["left_keys"] == ["company_code", "policy_number"]
    assert cfg["how"] == "left"

    # Multi-key merge op keeps lists.
    op = m.get_merge_ops()[0]
    assert op["left_on"] == ["company_code", "policy_number"]
    assert op["how"] == "left"

    # Single-key merge op collapses to scalars (legacy compatibility).
    m2 = _two_source_model()
    m2.add_link("pol", "company_code", "re", "company_code")
    op2 = m2.get_merge_ops()[0]
    assert op2["left_on"] == "company_code"
    assert op2["right_on"] == "company_code"
    print("  conversions: specs / config / merge ops  OK")


def test_incomplete_key_excluded():
    m = _two_source_model()
    j = m.add_link("pol", "company_code", "re", "company_code")
    j.keys.append(JoinKey("", "reinsurer"))          # half-drawn key
    assert len(j.complete_keys()) == 1
    assert m.to_join_specs()[0].left_keys == ("company_code",)
    print("  incomplete key excluded from specs  OK")


def test_state_round_trip():
    m = _two_source_model()
    m.get_source("pol").x = 120.0
    m.get_source("pol").y = 80.0
    m.get_source("re").collapsed = True
    m.add_link("pol", "company_code", "re", "company_code")
    m.add_link("pol", "policy_number", "re", "policy_number")
    m.set_how("pol", "re", "outer")

    state = m.to_state()
    m2 = JoinCanvasModel()
    m2.from_state(state)
    assert [s.alias for s in m2.sources] == ["pol", "re"]
    assert m2.get_source("pol").x == 120.0
    assert m2.get_source("re").collapsed is True
    j = m2.find_join("pol", "re")
    assert j.how == "outer" and len(j.keys) == 2
    assert m2.to_join_specs()[0].left_keys == ("company_code", "policy_number")
    print("  state round-trip  OK")


def test_legacy_merges_import():
    merges = [
        {"left": "pol", "right": "re", "left_on": "company_code",
         "right_on": "company_code", "how": "left"},
        {"left": "pol", "right": "claims",
         "left_on": ["company_code", "policy_number"],
         "right_on": ["co", "pol_no"], "how": "inner"},
    ]
    m = JoinCanvasModel.from_legacy_merges(merges)
    assert {s.alias for s in m.sources} == {"pol", "re", "claims"}
    jr = m.find_join("pol", "re")
    assert len(jr.keys) == 1 and jr.how == "left"
    jc = m.find_join("pol", "claims")
    assert len(jc.keys) == 2
    assert jc.keys[1].left_field == "policy_number"
    assert jc.keys[1].right_field == "pol_no"
    print("  legacy merges import  OK")


def test_legacy_cards_import():
    cards = [
        {"left": "pol", "right": "re", "how": "left", "enabled": False,
         "on_pairs": [["company_code", "company_code"],
                      ["policy_number", "policy_number"]]},
        {"left": "pol", "right": "claims", "how": "inner",
         "on_pairs": [["company_code", "co"]]},
        {"left": "x", "right": "y", "how": "inner", "on_pairs": []},  # skipped
    ]
    m = JoinCanvasModel.from_legacy_cards(cards)
    assert {s.alias for s in m.sources} == {"pol", "re", "claims"}
    jr = m.find_join("pol", "re")
    assert len(jr.keys) == 2 and jr.enabled is False     # flag carried over
    jc = m.find_join("pol", "claims")
    assert jc.enabled is True
    print("  legacy cards import (enabled flag carried)  OK")


def test_validate():
    m = _two_source_model()
    j = m.add_link("pol", "company_code", "re", "company_code")
    j.keys.append(JoinKey("not_a_field", "reinsurer"))
    warnings = m.validate()
    assert any("not_a_field" in w for w in warnings)
    print("  validate flags unknown fields  OK")


# ── Offscreen Qt view smoke test ─────────────────────────────────────────────

def test_view_smoke():
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover
        print(f"  view smoke SKIPPED (no PyQt6: {exc})")
        return

    from suiteview.audit.dataforge.forge_canvas_view import (
        ForgeJoinCanvas, JoinLineItem, SourceBoxItem,
    )

    app = QApplication.instance() or QApplication([])
    assert app is not None          # keep a reference alive for the test

    canvas = ForgeJoinCanvas()
    canvas.update_queries(
        ["pol", "re"],
        {
            "pol": ["company_code", "policy_number", "face_amount"],
            "re": ["company_code", "policy_number", "reinsurer"],
        },
    )
    # Two boxes were added to the scene.
    boxes = [it for it in canvas.scene.items() if isinstance(it, SourceBoxItem)]
    assert len(boxes) == 2

    # Programmatic link (same path the drag gesture uses) -> model + a line item.
    assert canvas.scene.add_link("pol", "company_code", "re", "company_code")
    assert canvas.scene.add_link("pol", "policy_number", "re", "policy_number")
    lines = [it for it in canvas.scene.items()
             if isinstance(it, JoinLineItem)]
    assert len(lines) == 2                            # one per key
    specs = canvas.to_join_specs()
    assert len(specs) == 1 and len(specs[0].left_keys) == 2

    # Join-type change propagates to every line of the relationship.
    canvas.scene.set_line_how(lines[0], "left")
    assert all(ln.how == "left" for ln in lines)
    assert canvas.to_join_specs()[0].how == "left"

    # State round-trips through a fresh canvas and rebuilds the same lines.
    state = canvas.get_state()
    canvas2 = ForgeJoinCanvas()
    canvas2.set_state(state)
    lines2 = [it for it in canvas2.scene.items()
              if isinstance(it, JoinLineItem)]
    assert len(lines2) == 2
    assert canvas2.to_join_specs()[0].how == "left"

    # Removing a line drops the key from the model.
    canvas.scene.remove_line(lines[0])
    remaining = [it for it in canvas.scene.items()
                 if isinstance(it, JoinLineItem)]
    assert len(remaining) == 1
    assert len(canvas.to_join_specs()[0].left_keys) == 1
    print("  view smoke (boxes/lines/specs/state/remove)  OK")


def main():
    print("=" * 60)
    print("DataForge join-canvas tests")
    print("=" * 60)
    tests = [
        test_set_sources_reconcile,
        test_add_link_multikey_and_orientation,
        test_add_link_rejections,
        test_remove_key_and_join,
        test_set_how_and_enabled,
        test_conversions,
        test_incomplete_key_excluded,
        test_state_round_trip,
        test_legacy_merges_import,
        test_legacy_cards_import,
        test_validate,
        test_view_smoke,
    ]
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("=" * 60)
    print(f"All {len(tests)} tests passed.")


if __name__ == "__main__":
    main()
