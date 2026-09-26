# Bookmarks

`BookmarkDataManager` is the only bookmark data source. Bookmark widgets may
cache icons or track popups, but they must not persist bookmark data directly.

## Data

Bookmarks are stored in the unified `bars` format under the SuiteView profile:

- bar `0`: horizontal top bar
- bar `1`: vertical FileNav quick-links sidebar
- categories are items with nested `items`
- every bookmark/category has a manager-issued integer `id`

Use the manager for adds, removes, category lookup, ID generation and saving.

## UI state

`BookmarkUiState` owns transient UI-only state:

- icon provider and icon/path caches
- footer status callback
- open popup registry and global close timer
- drag-in-progress flag
- registered `BookmarkContainer` instances

`BookmarkContainer` accepts an optional `ui_state`; callers normally share the
default state. Tests or isolated widgets can inject a fresh state without
touching bookmark data.

## Rules

- Save through `BookmarkDataManager.save()`.
- Refresh affected containers after data changes.
- Do not resurrect the deprecated top-level `categories` dict.
- Do not introduce another global registry or data cache.
