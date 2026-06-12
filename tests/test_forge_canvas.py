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
    m.get_source("pol").width = 260.0
    m.get_source("re").collapsed = True
    m.add_link("pol", "company_code", "re", "company_code")
    m.add_link("pol", "policy_number", "re", "policy_number")
    m.set_how("pol", "re", "outer")

    state = m.to_state()
    m2 = JoinCanvasModel()
    m2.from_state(state)
    assert [s.alias for s in m2.sources] == ["pol", "re"]
    assert m2.get_source("pol").x == 120.0
    assert m2.get_source("pol").width == 260.0
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
            "pol": ["company_code", "policy_number", "face_amount"] + [f"extra_{i}" for i in range(20)],
            "re": ["company_code", "policy_number", "reinsurer"],
        },
    )
    # Available Sources stay out of the join canvas until explicitly added.
    boxes = [it for it in canvas.scene.items() if isinstance(it, SourceBoxItem)]
    assert len(boxes) == 0
    assert canvas.add_query_table("pol")
    assert canvas.add_query_table("re")
    assert not canvas.add_query_table("pol")
    boxes = [it for it in canvas.scene.items() if isinstance(it, SourceBoxItem)]
    assert len(boxes) == 2
    pol_box = next(box for box in boxes if box.alias == "pol")
    assert pol_box._body_rows() == pol_box.visible_rows
    pol_box.width = 260.0
    pol_box.resize_rows(5)
    assert pol_box.visible_rows == 17

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
    assert next(s for s in state["sources"] if s["alias"] == "pol")["width"] == 260.0
    canvas2 = ForgeJoinCanvas()
    canvas2.set_state(state)
    pol_box2 = next(it for it in canvas2.scene.items()
                    if isinstance(it, SourceBoxItem) and it.alias == "pol")
    assert pol_box2.width == 260.0
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

    canvas.scene.remove_source("re")
    assert canvas.model.get_source("re") is None
    assert not canvas.model.joins
    print("  view smoke (boxes/lines/specs/state/remove)  OK")


def test_view_explicit_add_and_removed_persist():
    """Regression: queries require explicit join-canvas add; removals persist."""
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover
        print(f"  autoadd/removed SKIPPED (no PyQt6: {exc})")
        return
    from suiteview.audit.dataforge.forge_canvas_view import (
        ForgeJoinCanvas, SourceBoxItem,
    )
    app = QApplication.instance() or QApplication([])
    assert app is not None

    canvas = ForgeJoinCanvas()
    canvas.update_queries(["a", "b"], {"a": ["x"], "b": ["y"]})
    assert canvas.model.sources == []
    assert canvas.add_query_table("a")
    assert canvas.add_query_table("b")
    assert {s.alias for s in canvas.model.sources} == {"a", "b"}

    # Explicitly remove one; it must stay gone across a later source sync.
    canvas._remove_query_table("b")
    assert {s.alias for s in canvas.model.sources} == {"a"}
    canvas.update_queries(["a", "b", "c"], {"a": ["x"], "b": ["y"], "c": ["z"]})
    assert {s.alias for s in canvas.model.sources} == {"a"}

    # Removal persists through a save/restore round-trip.
    state = canvas.get_state()
    assert state.get("removed") == ["b"]
    canvas2 = ForgeJoinCanvas()
    canvas2.set_state(state)
    canvas2.update_queries(["a", "b", "c"], {"a": ["x"], "b": ["y"], "c": ["z"]})
    assert {s.alias for s in canvas2.model.sources} == {"a"}

    # Re-adding via the context-menu path clears the removal flag.
    assert canvas2.add_query_table("b")
    assert canvas2.add_query_table("c")
    assert {s.alias for s in canvas2.model.sources} == {"a", "b", "c"}
    boxes = [it for it in canvas2.scene.items() if isinstance(it, SourceBoxItem)]
    assert len(boxes) == 3
    print("  explicit add + removed-table persistence  OK")


def test_view_append_table_workflow():
    try:
        from PyQt6.QtCore import QPointF
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover
        print(f"  append view SKIPPED (no PyQt6: {exc})")
        return
    from suiteview.audit.dataforge.forge_canvas_view import (
        AppendBoxItem, ForgeJoinCanvas, JoinLineItem, SourceBoxItem,
    )
    app = QApplication.instance() or QApplication([])
    assert app is not None

    canvas = ForgeJoinCanvas()
    canvas.update_queries(
        ["ca", "cb", "pol"],
        {
            "ca": ["company_code", "policy_number", "claim_amount", "office"],
            "cb": ["COMPANY_CODE", "POLICY_NUMBER", "claim_amount", "examiner"],
            "pol": ["company_code", "policy_number", "face_amount"],
        },
        {
            "ca": {"claim_amount": "INTEGER"},
            "cb": {"claim_amount": "DECIMAL"},
            "pol": {},
        },
    )
    assert canvas._add_append_table(QPointF(120, 80))
    assert canvas.model.appends[0].name == "AppendTable"
    assert canvas._add_query_to_append("AppendTable", "ca")
    assert canvas._add_query_to_append("AppendTable", "cb")

    append_box = next(it for it in canvas.scene.items()
                      if isinstance(it, AppendBoxItem))
    assert append_box.members == ["ca", "cb"]
    assert append_box.fields == ["company_code", "policy_number", "claim_amount"]
    assert "claim_amount" in append_box.type_conflicts
    assert not [it for it in canvas.scene.items()
                if isinstance(it, SourceBoxItem) and it.alias in {"ca", "cb"}]

    assert canvas.add_query_table("pol")
    assert canvas.scene.add_link("AppendTable", "policy_number", "pol", "policy_number")
    lines = [it for it in canvas.scene.items() if isinstance(it, JoinLineItem)]
    assert len(lines) == 1
    assert canvas.to_config_appends() == [
        {"alias": "AppendTable", "members": ["ca", "cb"]}]

    canvas._remove_append_member("AppendTable", "cb")
    assert canvas.model.get_source("cb") is None
    assert canvas.model.get_append("AppendTable").members == ["ca"]
    print("  append view workflow  OK")


# ── Append Tables (design §9) ─────────────────────────────────────────────

def _append_model() -> JoinCanvasModel:
    m = JoinCanvasModel()
    m.set_sources(
        ["ca", "cb", "pol"],
        columns={
            "ca": ["company_code", "policy_number", "claim_amount", "office"],
            "cb": ["company_code", "policy_number", "claim_amount", "examiner"],
            "pol": ["company_code", "policy_number", "face_amount"],
        },
    )
    return m


def test_append_membership_and_shared_fields():
    m = _append_model()
    ap = m.add_append("All Claims")
    m.add_member("All Claims", "ca")
    m.add_member("All Claims", "cb")
    assert ap.members == ["ca", "cb"]
    assert m.member_of("ca") == "All Claims"
    # Shared fields: ordered intersection, first member's order.
    assert m.shared_fields("All Claims") == [
        "company_code", "policy_number", "claim_amount"]
    assert m.fields_of("All Claims") == m.shared_fields("All Claims")

    # A member can't be in two appends; Append Table names can match Source
    # names but must stay unique against other Append Tables.
    m.add_append("Other")
    try:
        m.add_member("Other", "ca")
        raise AssertionError("expected double-membership rejection")
    except ValueError:
        pass
    m.add_append("pol")
    try:
        m.add_append("pol")
        raise AssertionError("expected append-name collision rejection")
    except ValueError:
        pass

    # Removing a member deletes its canvas source state instead of restoring a
    # full Source box.
    m.remove_member("All Claims", "cb")
    assert m.member_of("cb") is None
    assert m.get_source("cb") is None
    m.remove_append("All Claims")
    assert m.member_of("ca") is None
    print("  append membership + shared fields  OK")


def test_append_rejects_joined_sources_and_links_via_append():
    m = _append_model()
    # A Source with existing joins cannot be added to an Append Table.
    m.add_link("ca", "company_code", "pol", "company_code")
    m.add_append("All Claims")
    try:
        m.add_member("All Claims", "ca")
        raise AssertionError("expected joined-source rejection")
    except ValueError as e:
        assert "already has joins" in str(e)
    m.remove_join("ca", "pol")
    # Members can't be join endpoints anymore...
    m.add_member("All Claims", "ca")
    try:
        m.add_link("ca", "company_code", "pol", "company_code")
        raise AssertionError("expected member-endpoint rejection")
    except ValueError as e:
        assert "Append Table" in str(e)
    # ...but the Append Table itself can.
    m.add_member("All Claims", "cb")
    j = m.add_link("All Claims", "policy_number", "pol", "policy_number")
    assert {j.left_source, j.right_source} == {"All Claims", "pol"}
    specs = m.to_join_specs()
    assert specs[0].left_source in ("All Claims", "pol")
    print("  append rejects joined sources; append is joinable  OK")


def test_append_prunes_joins_when_shared_fields_change():
    m = JoinCanvasModel()
    m.set_sources(
        ["ca", "cb", "cc", "pol"],
        columns={
            "ca": ["company_code", "policy_number", "claim_amount"],
            "cb": ["company_code", "policy_number", "claim_amount"],
            "cc": ["company_code", "policy_number"],
            "pol": ["company_code", "claim_amount"],
        },
    )
    m.add_append("All Claims")
    m.add_member("All Claims", "ca")
    m.add_member("All Claims", "cb")
    m.add_link("All Claims", "claim_amount", "pol", "claim_amount")
    assert len(m.joins) == 1
    m.add_member("All Claims", "cc")
    assert m.shared_fields("All Claims") == ["company_code", "policy_number"]
    assert m.joins == []

    m = JoinCanvasModel()
    m.set_sources(
        ["a", "b", "c", "pol"],
        columns={
            "a": ["PolicyNumber", "claim_amount"],
            "b": ["policynumber", "claim_amount"],
            "c": ["POLICYNUMBER", "claim_amount"],
            "pol": ["POLICYNUMBER"],
        },
    )
    m.add_append("All Policies")
    m.add_member("All Policies", "a")
    m.add_member("All Policies", "b")
    m.add_link("All Policies", "PolicyNumber", "pol", "POLICYNUMBER")
    m.remove_member("All Policies", "a")
    assert m.shared_fields("All Policies") == ["policynumber", "claim_amount"]
    assert m.joins[0].keys[0].left_field == "policynumber"
    print("  append prunes joins when shared fields change  OK")


def test_append_specs_config_and_state_round_trip():
    m = _append_model()
    m.add_append("All Claims", x=120, y=80)
    m.add_member("All Claims", "ca")
    m.add_member("All Claims", "cb")
    m.add_link("All Claims", "company_code", "pol", "company_code")

    specs = m.to_append_specs()
    assert len(specs) == 1
    assert specs[0].alias == "All Claims" and specs[0].members == ("ca", "cb")
    assert m.to_config_appends() == [
        {"alias": "All Claims", "members": ["ca", "cb"]}]
    ops = m.get_append_ops()
    assert ops[0]["columns"] == ["company_code", "policy_number", "claim_amount"]

    # State round-trip preserves the append (position included).
    m2 = JoinCanvasModel()
    m2.from_state(m.to_state())
    ap = m2.get_append("All Claims")
    assert ap is not None and ap.members == ["ca", "cb"]
    assert ap.x == 120 and ap.y == 80
    assert m2.member_of("ca") == "All Claims"
    assert len(m2.joins) == 1

    # Reconcile: a member whose query disappears is pruned from the append.
    m2.set_sources(["ca", "pol"],
                   columns={"ca": ["company_code"], "pol": ["company_code"]})
    assert m2.get_append("All Claims").members == ["ca"]
    print("  append specs/config/state round-trip + reconcile  OK")


def test_append_validate_warnings():
    m = _append_model()
    m.add_append("Lonely")
    m.add_member("Lonely", "ca")
    warnings = m.validate()
    assert any("only one member" in w for w in warnings), warnings
    print("  append validate warnings  OK")


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
        test_append_membership_and_shared_fields,
        test_append_rejects_joined_sources_and_links_via_append,
        test_append_prunes_joins_when_shared_fields_change,
        test_append_specs_config_and_state_round_trip,
        test_append_validate_warnings,
        test_view_smoke,
        test_view_explicit_add_and_removed_persist,
        test_view_append_table_workflow,
    ]
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("=" * 60)
    print(f"All {len(tests)} tests passed.")


if __name__ == "__main__":
    main()
