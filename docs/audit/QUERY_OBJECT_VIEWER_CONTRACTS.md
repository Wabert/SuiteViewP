# Query Object Viewer mixin contracts

The Query Object Viewer still uses mixins, but their shared `self.*` contract is
now explicit in `suiteview.audit.query_object_viewer.contracts`.

- `BrowserState` documents the state attributes read by mixins.
- `BrowserServices` groups collaborators that will move to composition over
  time.
- `MIXIN_CONTRACTS` lists required attributes per mixin; the regression test
  asserts `QueryObjectViewerWindow.__init__` initializes each one.

When a mixin starts reading a new attribute, add it to `MIXIN_CONTRACTS` and
initialize it in the window constructor in the same change. Prefer passing a
service/controller instead of adding another implicit attribute.

