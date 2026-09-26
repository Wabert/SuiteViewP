"""
QueryObject Viewer Window — unified browser for saved query objects.

Shows visual query designs, QDefinitions, Cyberlife-produced objects, manual SQL,
and ad hoc sources from the QueryObject store in one place.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QWidget

from suiteview.audit.query_object import QueryObject
from suiteview.core.access_control import guard_app_access, requires_app_access
from suiteview.ui.widgets.frameless_window import FramelessWindowBase

from suiteview.audit.query_object_viewer.common import (
    _BORDER_COLOR,
    _HEADER_COLORS,
)
from suiteview.audit.query_object_viewer.details import QueryObjectViewerDetailsMixin
from suiteview.audit.query_object_viewer.layout import QueryObjectViewerLayoutMixin
from suiteview.audit.query_object_viewer.navigation import QueryObjectViewerNavigationMixin
from suiteview.audit.query_object_viewer.context_menus import QueryObjectViewerOrganizerActionsMixin
from suiteview.audit.query_object_viewer.object_actions import QueryObjectViewerObjectActionsMixin
from suiteview.audit.query_object_viewer.source_actions import QueryObjectViewerSourceActionsMixin


class QueryObjectViewerWindow(
    QueryObjectViewerLayoutMixin,
    QueryObjectViewerNavigationMixin,
    QueryObjectViewerOrganizerActionsMixin,
    QueryObjectViewerDetailsMixin,
    QueryObjectViewerSourceActionsMixin,
    QueryObjectViewerObjectActionsMixin,
    FramelessWindowBase,
):
    """Non-blocking QueryObject browser and inspector."""

    _instance = None

    def __init__(self, parent=None):
        guard_app_access("QUERY")
        self._current: QueryObject | None = None
        self._current_forge_name = ""
        self._current_source_path = ""
        self._current_source_kind = ""
        self._current_source_payload: dict = {}
        self._current_file_source = None
        self._current_data_source = None
        self._loading_detail = False
        self._loading_tree = False
        self._loading_source_tree = False
        self._restoring_left_width = False
        self._left_panel_width = self._load_left_panel_width()
        self._audit_parent = parent
        self._dataforge_builder_windows: list[QDialog] = []
        self._audit_builder_windows: list[QWidget] = []
        self._file_nav_window = None
        self._file_source_is_new = False  # editing an unsaved (new) File Source
        self._embedded_common_tables = None
        self._embedded_registry = None
        super().__init__(
            title="Object Browser",
            default_size=(1120, 620),
            min_size=(760, 420),
            parent=None,
            header_colors=_HEADER_COLORS,
            border_color=_BORDER_COLOR,
        )

    @classmethod
    @requires_app_access("QUERY")
    def show_instance(cls, parent=None):
        if cls._instance is None or not cls._instance.isVisible():
            cls._instance = cls(parent)
            cls._instance.show()
        else:
            if parent is not None:
                cls._instance._audit_parent = parent
            cls._instance.refresh()
            cls._instance.raise_()
            cls._instance.activateWindow()
        return cls._instance
