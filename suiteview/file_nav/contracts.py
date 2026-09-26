"""Host contracts for FileNav feature mixins."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class TreeHost(Protocol):
    """Tree mixins require tree models, views, and folder navigation helpers."""

    current_details_folder: str | None

    def populate_tree_model(self) -> None: ...
    def load_folder_contents_in_details(self, dir_path: Path) -> None: ...


class DetailsHost(Protocol):
    """Details mixins require a details model, proxy, view, and footer updater."""

    def update_details_footer(self, timing_ms: int | None = None) -> None: ...


class BookmarkHost(Protocol):
    """Bookmark mixins require a BookmarkDataManager-backed store."""

    def save_quick_links(self) -> None: ...
    def is_path_in_quick_links(self, path: str) -> bool: ...


class SharePointHost(Protocol):
    """SharePoint mixins require virtual-path loaders and library persistence."""

    def save_sharepoint_libraries(self) -> None: ...
    def load_sharepoint_contents_in_details(self, sp_path: str, display_name=None) -> None: ...


class LayoutHost(Protocol):
    """Layout mixins require persisted width dictionaries and splitter state."""

    column_widths: dict
    panel_widths: dict

    def save_column_widths(self) -> None: ...
    def save_panel_widths(self) -> None: ...
