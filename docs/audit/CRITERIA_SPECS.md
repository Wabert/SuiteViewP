# Audit criteria specs

`suiteview.audit.criteria_specs` describes criteria fields as data:

- `FieldSpec`: widget attribute, user label, widget kind, criteria/state key,
  and layout hints.
- `TabSpec`: named collection of field specs for one tab.
- State helpers read and apply saved state using the existing key names.

`DisplayTab` is generated from `DISPLAY_TAB_SPEC`. `PolicyTab` and
`Policy2Tab` keep their hand-tuned layouts but use specs for save/load state.
This keeps old saved query files compatible while reducing drift between UI,
saved state, and criteria collection.

When adding a criterion:

1. Add the widget to the tab (or add a display `FieldSpec`).
2. Add the matching `FieldSpec` with the existing saved-state key.
3. Add/update a saved-state compatibility test.
4. If it affects SQL, add or extend a CyberLife golden case.

