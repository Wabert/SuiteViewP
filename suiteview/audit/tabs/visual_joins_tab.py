"""Visual Query joins tab with an Access-style table canvas."""
from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal

from suiteview.audit.dataforge.forge_canvas_view import ForgeJoinCanvas
from suiteview.audit.field_picker_panel import _FieldLoaderThread

logger = logging.getLogger(__name__)

_HOW_TO_SQL = {
    "inner": "INNER JOIN",
    "left": "LEFT OUTER JOIN",
    "right": "RIGHT OUTER JOIN",
    "outer": "FULL OUTER JOIN",
}
_SQL_TO_HOW = {value: key for key, value in _HOW_TO_SQL.items()}


def _join_key(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right)))


class VisualJoinsTab(ForgeJoinCanvas):
    """Canvas-based replacement for the Visual Query join-card tab.

    The SQL builder still consumes the old ``get_join_infos()`` shape, so this
    class adapts canvas relationships into the existing join-info dictionaries.
    """

    state_changed = pyqtSignal()

    def __init__(self, tables: list[str] | None = None,
                 dsn: str = "", parent=None):
        super().__init__(
            parent,
            source_label="Table",
            add_menu_label="Add Table",
        )
        self._tables = list(tables or [])
        self._dsn = dsn
        self._common_table_cols: dict[str, list[tuple[str, str]]] = {}
        self._table_columns: dict[str, list[str]] = {}
        self._column_types: dict[str, dict[str, str]] = {}
        self._loaders: dict[str, _FieldLoaderThread] = {}
        self._join_metadata: dict[tuple[str, str], dict] = {}
        self.update_tables(self._tables)

    def showEvent(self, event):
        super().showEvent(event)
        self._load_visible_table_columns()

    def set_table_columns(self, table: str, columns: list[str],
                          column_types: dict[str, str] | None = None) -> None:
        self._table_columns[table] = list(columns)
        self._column_types[table] = dict(column_types or {})
        self._refresh_canvas_sources()

    def update_tables(self, tables: list[str]):
        common_names = set(self._common_table_cols)
        self._tables = [table for table in tables if table not in common_names]
        self._refresh_canvas_sources()
        if self.isVisible():
            self._load_visible_table_columns()

    def update_common_tables(self, common_cols: dict[str, list[tuple[str, str]]]):
        old_common = set(self._common_table_cols)
        self._tables = [table for table in self._tables if table not in old_common]
        self._common_table_cols = dict(common_cols)
        for table, cols in self._common_table_cols.items():
            self._table_columns[table] = [col for col, _type_name in cols]
            self._column_types[table] = {col: type_name for col, type_name in cols}
        self._refresh_canvas_sources()

    def add_table(self, table: str) -> bool:
        return self.add_query_table(table)

    def _all_tables(self) -> list[str]:
        names: list[str] = []
        for table in [*self._tables, *sorted(self._common_table_cols, key=str.lower)]:
            if table and table not in names:
                names.append(table)
        return names

    def _refresh_canvas_sources(self):
        names = self._all_tables()
        self._available_query_names = list(names)
        self._available_query_columns = {
            name: self._table_columns.get(name, []) for name in names
        }
        self._removed_aliases &= set(names)
        visible = [name for name in names if name not in self._removed_aliases]
        self.model.set_sources(
            visible,
            self._available_query_columns,
            self._column_types,
            add_missing=True,
        )
        self.scene.rebuild()
        self.state_changed.emit()

    def _load_visible_table_columns(self):
        if not self._dsn:
            return
        for table in self._all_tables():
            if table in self._table_columns or table in self._loaders:
                continue
            loader = _FieldLoaderThread(self._dsn, table, self)
            self._loaders[table] = loader
            loader.columns_loaded.connect(self._on_columns_loaded)
            loader.error_occurred.connect(lambda msg, t=table: self._on_columns_error(t, msg))
            loader.finished.connect(lambda t=table: self._loaders.pop(t, None))
            loader.start()

    def _on_columns_loaded(self, table: str, columns: list[tuple]):
        self._table_columns[table] = [str(col[0]) for col in columns if col and col[0]]
        self._column_types[table] = {
            str(col[0]): str(col[1]) for col in columns if len(col) > 1 and col[0]
        }
        self._refresh_canvas_sources()

    def _on_columns_error(self, table: str, msg: str):
        logger.warning("Visual join canvas could not load columns for %s: %s", table, msg)

    def get_join_infos(self) -> list[dict]:
        infos: list[dict] = []
        for join in self.model.joins:
            if not join.enabled:
                continue
            keys = join.complete_keys()
            if not keys:
                continue
            metadata = self._join_metadata.get(
                _join_key(join.left_source, join.right_source), {})
            infos.append({
                "left_table": join.left_source,
                "right_table": join.right_source,
                "join_type": _HOW_TO_SQL.get(join.how, "INNER JOIN"),
                "alias_left": metadata.get("alias_left", ""),
                "alias_right": metadata.get("alias_right", ""),
                "on_pairs": [(key.left_field, key.right_field) for key in keys],
                "extra_conditions": metadata.get("extra_conditions", []),
            })
        return infos

    def get_state(self) -> dict:
        state = super().get_state()
        state["cards"] = self._cards_from_canvas()
        if self._join_metadata:
            state["metadata"] = {
                "|".join(key): value for key, value in self._join_metadata.items()
            }
        return state

    def set_state(self, state: dict):
        self._join_metadata.clear()
        metadata = state.get("metadata", {})
        for raw_key, value in metadata.items():
            parts = raw_key.split("|", 1)
            if len(parts) == 2:
                self._join_metadata[_join_key(parts[0], parts[1])] = dict(value)

        if "sources" in state or "joins" in state:
            super().set_state(state)
            self._refresh_canvas_sources()
            return

        self._set_legacy_cards(state.get("cards", []))

    def _set_legacy_cards(self, cards: list[dict]):
        for card in cards:
            left = card.get("left_table", "")
            right = card.get("right_table", "")
            if not left or not right:
                continue
            for table in (left, right):
                if table not in self._tables and table not in self._common_table_cols:
                    self._tables.append(table)
            key = _join_key(left, right)
            self._join_metadata[key] = {
                "alias_left": card.get("alias_left", ""),
                "alias_right": card.get("alias_right", ""),
                "extra_conditions": [
                    (cond.get("column", ""), cond.get("expr", ""))
                    for cond in card.get("extra_conditions", [])
                    if cond.get("column", "") or cond.get("expr", "")
                ],
            }
            self._seed_columns_from_card(card)
        self._refresh_canvas_sources()
        for card in cards:
            left = card.get("left_table", "")
            right = card.get("right_table", "")
            if not left or not right:
                continue
            join_type = card.get("join_type", "INNER JOIN")
            for cond in card.get("on_conditions", []):
                left_col = cond.get("left", "")
                right_col = cond.get("right", "")
                if left_col and right_col:
                    self.scene.add_link(left, left_col, right, right_col)
            self.model.set_how(left, right, _SQL_TO_HOW.get(join_type, "inner"))
            join = self.model.find_join(left, right)
            if join is not None:
                join.enabled = card.get("enabled", True)
        self.scene.rebuild()
        self.state_changed.emit()

    def _seed_columns_from_card(self, card: dict):
        left = card.get("left_table", "")
        right = card.get("right_table", "")
        for table, side in ((left, "left"), (right, "right")):
            if not table:
                continue
            columns = self._table_columns.setdefault(table, [])
            for cond in card.get("on_conditions", []):
                col = cond.get(side, "")
                if col and col not in columns:
                    columns.append(col)

    def _cards_from_canvas(self) -> list[dict]:
        cards: list[dict] = []
        for index, join in enumerate(self.model.joins, start=1):
            metadata = self._join_metadata.get(
                _join_key(join.left_source, join.right_source), {})
            cards.append({
                "card_id": f"join_{index}",
                "enabled": join.enabled,
                "collapsed": False,
                "left_table": join.left_source,
                "right_table": join.right_source,
                "join_type": _HOW_TO_SQL.get(join.how, "INNER JOIN"),
                "alias_left": metadata.get("alias_left", ""),
                "alias_right": metadata.get("alias_right", ""),
                "on_conditions": [
                    {"left": key.left_field, "right": key.right_field}
                    for key in join.keys
                ],
                "extra_conditions": [
                    {"column": col, "expr": expr}
                    for col, expr in metadata.get("extra_conditions", [])
                ],
            })
        return cards

    def card_count(self) -> int:
        return len(self.model.joins)