# FileNav architecture

FileNav is split into a stable core plus explicit tab collaborators.

## `FileExplorerCore`

`FileExplorerCore` still composes the established feature mixins for tree,
details, search, IO, context menus, file operations, bookmarks, SharePoint,
layout and export. Each mixin carries a `Requires`/`Provides` docstring and the
static test in `tests/test_mixin_contracts.py` checks that `self.*` reads are
provided by the composed host.

Host contracts live in `suiteview/file_nav/contracts.py`:

- `TreeHost`
- `DetailsHost`
- `BookmarkHost`
- `SharePointHost`
- `LayoutHost`

`LayoutStore` owns JSON persistence for column widths and panel widths.

## `FileExplorerTab`

Taskbar tabs are no longer mixin subclasses. A tab extends `FileExplorerCore`
and owns:

- `NavigationController` for breadcrumb/history/back-forward behavior.
- `QuickLinksController` for the sidebar bookmarks and ScratchPad panel.

The tab keeps public navigation method names through the collaborators so
existing callers can still use `navigate_to_path`, `toggle_dual_pane` and the
folder-history helpers. The controllers use explicit tab dependencies and named
delegates; they do not rely on `__getattr__` forwarding.

## Worker ownership

Local depth scans and SharePoint Graph calls run through
`suiteview.ui.workers.WorkerController`; cancellation is asynchronous and does
not block the UI thread.
