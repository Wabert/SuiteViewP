"""Explicit Query Object Viewer mixin contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class BrowserState(Protocol):
    """State every query-object viewer mixin may read."""

    _current: Any
    _current_forge_name: str
    _current_source_path: str
    _current_source_kind: str
    _current_source_payload: dict
    _current_file_source: Any
    _current_data_source: Any
    _loading_detail: bool
    _loading_tree: bool
    _loading_source_tree: bool
    _restoring_left_width: bool
    _left_panel_width: int
    _audit_parent: Any
    _dataforge_builder_windows: list
    _audit_builder_windows: list
    _file_nav_window: Any
    _file_source_is_new: bool
    _embedded_common_tables: Any
    _embedded_registry: Any


@dataclass(slots=True)
class BrowserServices:
    """Collaborators supplied explicitly for tests and future composition."""

    audit_parent: Any = None
    dataforge_builder_windows: list[Any] = field(default_factory=list)
    audit_builder_windows: list[Any] = field(default_factory=list)


MIXIN_CONTRACTS: dict[str, set[str]] = {
    "QueryObjectViewerLayoutMixin": {
        "_left_panel_width",
        "_loading_tree",
        "_loading_source_tree",
        "_restoring_left_width",
        "_embedded_common_tables",
        "_embedded_registry",
    },
    "QueryObjectViewerNavigationMixin": {
        "_current",
        "_loading_tree",
        "_loading_source_tree",
        "_current_source_payload",
    },
    "QueryObjectViewerOrganizerActionsMixin": {
        "_current",
        "_audit_parent",
    },
    "QueryObjectViewerDetailsMixin": {
        "_current",
        "_loading_detail",
    },
    "QueryObjectViewerSourceActionsMixin": {
        "_current_source_path",
        "_current_source_kind",
        "_current_source_payload",
        "_current_file_source",
        "_current_data_source",
        "_file_source_is_new",
    },
    "QueryObjectViewerObjectActionsMixin": {
        "_current",
        "_audit_parent",
        "_dataforge_builder_windows",
        "_audit_builder_windows",
        "_file_nav_window",
    },
}

