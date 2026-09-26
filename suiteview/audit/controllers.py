"""Focused controllers for the Audit window."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from suiteview.core.db2_constants import DEFAULT_SCHEMA, REGION_SCHEMA_MAP

from .cyberlife_criteria import AuditCriteriaBundle, CriteriaCollector
from .cyberlife_query import build_cyberlife_sql


@dataclass(slots=True)
class AuditModeController:
    """Owns AuditWindow mode switching and mode-specific setup dispatch."""

    window: Any

    def switch_mode(self, mode: str) -> None:
        window = self.window
        if mode == window._current_mode:
            return
        previous = window._current_mode
        window._current_mode = mode
        if mode in window._dynamic_queries:
            window._last_query_mode = mode
        elif mode in window._dataforge_groups:
            window._last_forge_mode = mode
        prev_had_picker = (
            previous in window._dynamic_queries
            or previous in window._dataforge_groups
            or previous == "__forge_blank__"
            or previous == "__query_blank__"
        )
        self._set_mode_visibility(mode, previous)
        self._enter_mode(mode, prev_had_picker)

    def _set_mode_visibility(self, mode: str, previous: str) -> None:
        window = self.window
        window.setUpdatesEnabled(False)
        try:
            is_cyberlife = mode == "cyberlife"
            window.tabs.setVisible(is_cyberlife)
            window.cyberlife_bottom_bar.setVisible(is_cyberlife)
            window._forge_blank.setVisible(mode == "__forge_blank__")
            window._query_blank.setVisible(mode == "__query_blank__")
            window.manual_sql_object_tab.setVisible(mode == "__manual_sql_object__")
            window.csv_excel_object_tab.setVisible(mode == "__csv_excel_object__")
            for name, query in window._dynamic_queries.items():
                if name == mode:
                    query.setVisible(True)
                elif name == previous:
                    query.setVisible(False)
            for name, forge in window._dataforge_groups.items():
                if name == mode:
                    forge.setVisible(True)
                elif name == previous:
                    forge.setVisible(False)
        finally:
            window.setUpdatesEnabled(True)

    def _enter_mode(self, mode: str, prev_had_picker: bool) -> None:
        window = self.window
        if mode in window._dataforge_groups or mode == "__forge_blank__":
            window._enter_forge_mode(mode, prev_had_picker)
        elif mode in window._dynamic_queries or mode == "__query_blank__":
            window._enter_query_mode(mode, prev_had_picker)
        elif mode == "__manual_sql_object__":
            window._enter_manual_sql_object_mode()
        elif mode == "__csv_excel_object__":
            window._enter_csv_excel_object_mode()
        else:
            window._enter_cyberlife_mode()


@dataclass(slots=True)
class CyberlifeRunController:
    """Builds CyberLife SQL from AuditWindow controls."""

    window: Any

    def build_sql(self) -> str:
        window = self.window
        region = window.cmb_region.currentText()
        schema = REGION_SCHEMA_MAP.get(region, DEFAULT_SCHEMA)
        criteria = CriteriaCollector(AuditCriteriaBundle(
            schema=schema,
            sys_code=window.cmb_system.currentText().strip(),
            max_count_text=window.txt_max_count.text().strip(),
            coverage_level=window.chk_coverage_level.isChecked(),
            coverage_scope=window.cmb_coverage_scope.currentText(),
            tabs=self._registered_tabs(),
        )).collect()
        return build_cyberlife_sql(criteria)

    def _registered_tabs(self) -> dict[str, Any]:
        window = self.window
        return {
            "policy": window.policy_tab,
            "display": window.display_tab,
            "custom_display": window.custom_display_tab,
            "policy2": window.policy2_tab,
            "people": window.people_tab,
            "adv": window.adv_tab,
            "coverages": window.coverages_tab,
            "plancode": window.plancode_tab,
            "benefits": window.benefits_tab,
            "transaction": window.transaction_tab,
            "segment52": window.segment52_tab,
            "wl": window.wl_tab,
        }


@dataclass(slots=True)
class QueryObjectPersistenceController:
    """Owns serializing CyberLife builder state for QueryObject persistence."""

    window: Any

    def cyberlife_state(self) -> dict:
        window = self.window
        return {
            "max_count": window.txt_max_count.text().strip(),
            "coverage_level": window.chk_coverage_level.isChecked(),
            "coverage_scope": window.cmb_coverage_scope.currentText(),
            "tabs": {
                key: tab.get_state()
                for key, tab in window._cyberlife_criteria_tabs()
            },
        }


@dataclass(slots=True)
class VisualQueryController:
    """Facade for Visual Query actions that still live on AuditWindow."""

    window: Any

    def open_builder(self) -> None:
        self.window._open_visual_query_builder()


@dataclass(slots=True)
class PickerBindingController:
    """Facade for picker binding refreshes while the split continues."""

    window: Any

    def refresh_query_objects(self) -> None:
        self.window._refresh_picker_query_list()

