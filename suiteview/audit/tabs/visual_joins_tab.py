"""Visual Query joins tab with an Access-style table canvas.

The canvas shows the tables the user put on it — by dragging tables (or fields)
from SQL Assist, from the right-click **Add Table** menu, or automatically when a
field from a table is placed on Filter/Display. Tables can be ODBC tables or File
Source datasets; file tables carry a format badge (CSV, EXCEL, ...). Drag a field
onto a field in another table to join them, then click the line to choose the
join type.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QPointF, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from suiteview.audit.dataforge.join_canvas_view import (
    BLUE_JOIN_CANVAS_THEME,
    JoinCanvasView,
)
from suiteview.audit.dynamic_query import null_supplied_tables
from suiteview.audit.field_picker_panel import FIELD_DRAG_MIME, _FieldLoaderThread
from suiteview.audit.join_suggestions import (
    KIND_DATABASE,
    KIND_FILE,
    KIND_LIST,
    suggest_canvas_joins,
)
from suiteview.audit.query_sources import (
    TABLE_DRAG_MIME,
    file_source_badge,
    file_source_table_fields,
    is_file_token,
    is_list_token,
    is_local_token,
    resolve_file_token,
)

logger = logging.getLogger(__name__)

_TOOL_BTN_STYLE = (
    "QPushButton { background-color: #E8F0FB; color: #0A2A5C;"
    " border: 1px solid #1E5BA8; border-radius: 3px; padding: 0px 8px; font-size: 8pt; }"
    "QPushButton:hover { background-color: #D9E8F7; }"
)

_HOW_TO_SQL = {
    "inner": "INNER JOIN",
    "left": "LEFT OUTER JOIN",
    "right": "RIGHT OUTER JOIN",
    "outer": "FULL OUTER JOIN",
}
_SQL_TO_HOW = {value: key for key, value in _HOW_TO_SQL.items()}
_SQL_TO_HOW.update({"LEFT JOIN": "left", "RIGHT JOIN": "right", "FULL JOIN": "outer"})

_EMPTY_TEXT = (
    "Drag tables or file datasets here from SQL Assist\n"
    "(or right-click  \u203a  Add Table)\n\n"
    "Have data in Excel? Copy it and press Ctrl+V here.\n\n"
    "Then drag a field onto a field in another table to join them."
)

ADD_KIND_ODBC = "odbc"
ADD_KIND_FILES = "files"

# Column loaders outlive the tab that started them (see _load_visible_table_columns).
_ACTIVE_COLUMN_LOADERS: set = set()


def _release_loader(loader) -> None:
    loader.wait()
    _ACTIVE_COLUMN_LOADERS.discard(loader)


def _join_key(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right)))


class VisualJoinsTab(JoinCanvasView):
    """Canvas-based replacement for the Visual Query join-card tab.

    The SQL builder still consumes the old ``get_join_infos()`` shape, so this
    class adapts canvas relationships into the existing join-info dictionaries.
    """

    state_changed = pyqtSignal()
    add_tables_requested = pyqtSignal(str)  # ADD_KIND_ODBC / ADD_KIND_FILES
    paste_policy_list_requested = pyqtSignal()
    list_edit_requested = pyqtSignal(str)    # pasted list box double-clicked
    list_remove_requested = pyqtSignal(str)  # pasted list box deleted
    table_view_requested = pyqtSignal(str)   # "Open Table View" on a box

    def __init__(self, tables: list[str] | None = None,
                 dsn: str = "", parent=None):
        super().__init__(
            parent,
            source_label="table",
            add_menu_label="Add Table",
            theme=BLUE_JOIN_CANVAS_THEME,
            allow_appends=False,
            empty_text=_EMPTY_TEXT,
        )
        self._tables: list[str] = []
        self._dsn = dsn
        self._common_table_cols: dict[str, list[tuple[str, str]]] = {}
        self._local_tables: dict[str, str] = {}
        self._list_rows: dict[str, int] = {}
        self._table_columns: dict[str, list[str]] = {}
        self._column_types: dict[str, dict[str, str]] = {}
        self._loaders: dict[str, _FieldLoaderThread] = {}
        self._join_metadata: dict[tuple[str, str], dict] = {}
        self._dismissed_pairs: set[frozenset[str]] = set()
        self._pending_suggestions: list[tuple[str, str, list[tuple[str, str]]]] = []
        self._build_toolbar()
        self.scene.suggestion_accepted.connect(self._accept_suggestion)
        self.scene.changed_model.connect(self._update_suggestions)
        self.update_tables(list(tables or []))

    def _build_toolbar(self):
        """Paste Policy List / Suggest Joins, plus the suggested-join banner."""
        bar = QWidget(self)
        row = QHBoxLayout(bar)
        row.setContentsMargins(4, 3, 4, 1)
        row.setSpacing(4)
        self.btn_paste_list = QPushButton("\U0001F4CB Paste List")
        self.btn_paste_list.setToolTip(
            "Paste rows copied from Excel as a list table. (Ctrl+V)\n"
            "Double-click its box later to review the rows or rename columns.")
        self.btn_paste_list.clicked.connect(self.paste_policy_list_requested)
        self.btn_suggest = QPushButton("\u2728 Suggest Joins")
        self.btn_suggest.setToolTip(
            "Look for matching key fields between tables that aren't joined yet\n"
            "(shown as dashed gold lines — click one to accept it).")
        self.btn_suggest.clicked.connect(self.suggest_joins)
        for btn in (self.btn_paste_list, self.btn_suggest):
            btn.setFixedHeight(22)
            btn.setStyleSheet(_TOOL_BTN_STYLE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(btn)
        row.addStretch(1)

        self.suggestion_banner = QFrame(self)
        self.suggestion_banner.setStyleSheet(
            "QFrame { background: #FFF8DC; border: 1px solid #D4A017; border-radius: 3px; }"
            "QLabel { border: none; color: #5B4300; font-size: 8pt; }")
        banner = QHBoxLayout(self.suggestion_banner)
        banner.setContentsMargins(6, 2, 4, 2)
        banner.setSpacing(4)
        self.lbl_suggestion = QLabel("")
        self.lbl_suggestion.setWordWrap(True)
        banner.addWidget(self.lbl_suggestion, 1)
        self.btn_accept_suggestions = QPushButton("Accept")
        self.btn_accept_suggestions.clicked.connect(self.accept_all_suggestions)
        self.btn_dismiss_suggestions = QPushButton("Dismiss")
        self.btn_dismiss_suggestions.clicked.connect(self.dismiss_suggestions)
        for btn in (self.btn_accept_suggestions, self.btn_dismiss_suggestions):
            btn.setFixedHeight(20)
            btn.setStyleSheet(_TOOL_BTN_STYLE)
            banner.addWidget(btn)
        self.suggestion_banner.setVisible(False)

        layout = self.layout()
        layout.insertWidget(0, bar)
        layout.insertWidget(2, self.suggestion_banner)

    def showEvent(self, event):
        super().showEvent(event)
        self._load_visible_table_columns()

    # ── Table availability ───────────────────────────────────────────────

    def set_dsn(self, dsn: str) -> None:
        """The ODBC DSN whose table columns the canvas loads."""
        if dsn == self._dsn:
            return
        self._dsn = dsn
        for table in [t for t in self._table_columns
                      if t not in self._local_tables and t not in self._common_table_cols]:
            self._table_columns.pop(table, None)
            self._column_types.pop(table, None)
        self._refresh_canvas_sources()
        if self.isVisible():
            self._load_visible_table_columns()

    def set_table_columns(self, table: str, columns: list[str],
                          column_types: dict[str, str] | None = None) -> None:
        self._table_columns[table] = list(columns)
        self._column_types[table] = dict(column_types or {})
        self._refresh_canvas_sources()

    def update_tables(self, tables: list[str]):
        """Set the query's tables (the SQL Assist list) that may go on the canvas."""
        common_names = set(self._common_table_cols)
        self._tables = []
        for table in tables:
            if table and table not in common_names and table not in self._tables:
                self._tables.append(table)
        self._refresh_canvas_sources(drop_unavailable=True)
        if self.isVisible():
            self._load_visible_table_columns()

    def set_local_tables(self, table_sources: dict[str, str],
                         inline_tables: dict[str, dict] | None = None):
        """Record the file datasets and pasted lists (table → ``file:``/``list:``).

        ``inline_tables`` holds pasted lists' ``{"columns": [...], "rows": [...]}``.
        """
        inline_tables = inline_tables or {}
        self._local_tables = {
            t: tok for t, tok in table_sources.items() if is_local_token(tok)}
        tags: dict[str, str] = {}
        for table, token in self._local_tables.items():
            if is_list_token(token):
                data = inline_tables.get(table, {})
                self._list_rows[table] = len(data.get("rows", []))
                tags[table] = "LIST" if data else "MISSING"
                self._table_columns[table] = list(data.get("columns", []))
                self._column_types[table] = {c: "TEXT" for c in data.get("columns", [])}
        for token in {tok for tok in self._local_tables.values() if is_file_token(tok)}:
            members = [t for t, tok in self._local_tables.items() if tok == token]
            fds = resolve_file_token(token)
            if fds is None:
                tags.update({table: "MISSING" for table in members})
                continue
            fields = file_source_table_fields(fds)
            badge = file_source_badge(fds)
            for table in members:
                tags[table] = badge
                cols = fields.get(table, [])
                self._table_columns[table] = [c for c, _t in cols]
                self._column_types[table] = {c: t for c, t in cols}
        self.scene.box_tags = tags
        self._refresh_canvas_sources()

    def update_common_tables(self, common_cols: dict[str, list[tuple[str, str]]]):
        old_common = set(self._common_table_cols)
        self._tables = [table for table in self._tables if table not in old_common]
        self._common_table_cols = dict(common_cols)
        for table, cols in self._common_table_cols.items():
            self._table_columns[table] = [col for col, _type_name in cols]
            self._column_types[table] = {col: type_name for col, type_name in cols}
        self._refresh_canvas_sources(drop_unavailable=True)

    def add_table(self, table: str) -> bool:
        return self.add_query_table(table)

    def ensure_on_canvas(self, table: str) -> bool:
        """Put a table that the query uses on the canvas (no-op if present)."""
        if not table or self.model.get_source(table) is not None:
            return False
        if table not in self._all_tables():
            self._tables.append(table)
            self._refresh_canvas_sources()
        return self.add_query_table(table)

    def canvas_tables(self) -> list[str]:
        return [src.alias for src in self.model.sources]

    def _all_tables(self) -> list[str]:
        names: list[str] = []
        for table in [*self._tables, *sorted(self._common_table_cols, key=str.lower)]:
            if table and table not in names:
                names.append(table)
        return names

    def _refresh_canvas_sources(self, drop_unavailable: bool = False):
        names = self._all_tables()
        if not drop_unavailable:
            # Boxes restored from saved state stay until the table list drops them.
            for src in self.model.sources:
                if src.alias not in names:
                    names.append(src.alias)
        self._available_query_names = list(names)
        self._available_query_columns = {
            name: self._table_columns.get(name, []) for name in names
        }
        self._available_query_types = {
            name: self._column_types.get(name, {}) for name in names
        }
        self._removed_aliases &= set(names)
        visible = [src.alias for src in self.model.sources if src.alias in names]
        self.model.set_sources(
            visible,
            self._available_query_columns,
            self._available_query_types,
            add_missing=False,
        )
        self.scene.rebuild()
        self._update_suggestions()
        self.state_changed.emit()

    def add_query_table(self, name: str, scene_pos: QPointF | None = None) -> bool:
        added = super().add_query_table(name, scene_pos)
        if added:
            self._update_suggestions()
            if self.isVisible():
                self._load_visible_table_columns()
        return added

    # ── Join suggestions ─────────────────────────────────────────────────

    def _table_kind(self, table: str) -> str:
        token = self._local_tables.get(table, "")
        if is_list_token(token):
            return KIND_LIST
        if is_file_token(token) or table in self._common_table_cols:
            return KIND_FILE
        return KIND_DATABASE

    def compute_suggestions(self) -> list[tuple[str, str, list[tuple[str, str]]]]:
        tables = self.canvas_tables()
        return suggest_canvas_joins(
            tables,
            {t: self._table_columns.get(t, []) for t in tables},
            {t: self._table_kind(t) for t in tables},
            {frozenset((j.left_source, j.right_source)) for j in self.model.joins},
            self._dismissed_pairs,
        )

    def _update_suggestions(self):
        suggestions = self.compute_suggestions()
        self._pending_suggestions = suggestions
        self.scene.set_suggestions([
            (left, lcol, right, rcol)
            for left, right, keys in suggestions for lcol, rcol in keys
        ])
        if not suggestions:
            self.suggestion_banner.setVisible(False)
            return
        if len(suggestions) == 1:
            left, right, keys = suggestions[0]
            text = "Suggested join: " + ",  ".join(
                f"{left}.{lcol} = {right}.{rcol}" for lcol, rcol in keys)
        else:
            text = (f"{len(suggestions)} suggested joins are drawn as dashed gold lines "
                    "— click one to accept it, or accept them all.")
        self.lbl_suggestion.setText(text)
        self.btn_accept_suggestions.setVisible(True)
        self.btn_accept_suggestions.setText("Accept" if len(suggestions) == 1 else "Accept all")
        self.suggestion_banner.setVisible(True)

    def suggest_joins(self):
        """Toolbar: forget dismissals and look again; say so when nothing fits."""
        self._dismissed_pairs.clear()
        self._update_suggestions()
        if not self._pending_suggestions:
            unjoined = [t for t in self.canvas_tables()
                        if not any(t in (j.left_source, j.right_source)
                                   for j in self.model.joins)]
            if len(self.canvas_tables()) < 2 or not unjoined:
                message = "Every table on the canvas is already joined." \
                    if len(self.canvas_tables()) >= 2 else \
                    "Put at least two tables on the canvas first."
            else:
                message = ("No matching key fields found for: " + ", ".join(unjoined)
                           + ". Drag a field onto a field in another table to join them.")
            self.lbl_suggestion.setText(message)
            self.btn_accept_suggestions.setVisible(False)
            self.suggestion_banner.setVisible(True)

    def _link_suggestion(self, left: str, right: str, keys: list[tuple[str, str]]):
        """Add a suggested join; extend an outer-join chain rather than break it.

        If one table is already on the optional side of an outer join, an Inner
        join to it would make the design ambiguous (see
        ``dynamic_query.find_outer_join_ambiguity``), so the new join keeps all of
        that table's rows instead.
        """
        optional = null_supplied_tables(self.get_join_infos())
        for lcol, rcol in keys:
            self.scene.add_link(left, lcol, right, rcol)
        keep = left if left in optional else right if right in optional else ""
        join = self.model.find_join(left, right)
        if keep and join is not None:
            self.scene.set_line_how(
                next(ln for ln in self.scene.line_items
                     if {ln.left_box.alias, ln.right_box.alias} == {left, right}),
                "left" if join.left_source == keep else "right")

    def _accept_suggestion(self, left: str, right: str):
        pair = {left, right}
        for s_left, s_right, keys in list(self._pending_suggestions):
            if {s_left, s_right} == pair:
                self._link_suggestion(s_left, s_right, keys)
        self._update_suggestions()

    def accept_all_suggestions(self):
        for left, right, keys in list(self._pending_suggestions):
            self._link_suggestion(left, right, keys)
        self._update_suggestions()

    def dismiss_suggestions(self):
        for left, right, _keys in self._pending_suggestions:
            self._dismissed_pairs.add(frozenset((left, right)))
        self.suggestion_banner.setVisible(False)
        self._update_suggestions()
        self.state_changed.emit()

    # ── Box status (how each table will be fetched) ──────────────────────

    def set_box_status(self, status: dict[str, tuple[str, str]]):
        """Status strips under boxes: table → (ok/warn/info/muted, text)."""
        self.scene.set_box_status(status)

    def box_status(self) -> dict[str, tuple[str, str]]:
        return dict(self.scene.box_status)

    def list_row_count(self, table: str) -> int:
        return self._list_rows.get(table, 0)

    def _view_key_press(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_policy_list_requested.emit()
            return
        super()._view_key_press(event)

    def _load_visible_table_columns(self):
        if not self._dsn or is_local_token(self._dsn):
            return
        for table in self.canvas_tables():
            if (table in self._table_columns or table in self._loaders
                    or table in self._local_tables or table in self._common_table_cols):
                continue
            # Unparented and kept alive by the module registry: closing the query
            # must never destroy a thread that is still waiting on ODBC.
            loader = _FieldLoaderThread(self._dsn, table)
            _ACTIVE_COLUMN_LOADERS.add(loader)
            loader.finished.connect(lambda l=loader: _release_loader(l))
            self._loaders[table] = loader
            loader.columns_loaded.connect(self._on_columns_loaded)
            loader.error_occurred.connect(self._on_columns_error)
            loader.finished.connect(self._on_loader_finished)
            loader.start()

    @pyqtSlot(str, list)
    def _on_columns_loaded(self, table: str, columns: list):
        self._table_columns[table] = [str(col[0]) for col in columns if col and col[0]]
        self._column_types[table] = {
            str(col[0]): str(col[1]) for col in columns if len(col) > 1 and col[0]
        }
        self._refresh_canvas_sources()

    @pyqtSlot(str)
    def _on_columns_error(self, msg: str):
        table = getattr(self.sender(), "table_name", "?")
        logger.warning("Visual join canvas could not load columns for %s: %s", table, msg)

    @pyqtSlot()
    def _on_loader_finished(self):
        self._loaders.pop(getattr(self.sender(), "table_name", ""), None)

    # ── Drag & drop / Add Table menu ─────────────────────────────────────

    def _accepts_external_drop(self, mime) -> bool:
        return mime.hasFormat(TABLE_DRAG_MIME) or mime.hasFormat(FIELD_DRAG_MIME)

    @staticmethod
    def _dropped_tables(mime) -> list[str]:
        tables: list[str] = []
        if mime.hasFormat(TABLE_DRAG_MIME):
            raw = bytes(mime.data(TABLE_DRAG_MIME)).decode("utf-8")
            tables.extend(line.strip() for line in raw.split("\n"))
        if mime.hasFormat(FIELD_DRAG_MIME):
            raw = bytes(mime.data(FIELD_DRAG_MIME)).decode("utf-8")
            tables.extend(line.split("|", 1)[0].strip() for line in raw.split("\n"))
        unique: list[str] = []
        for table in tables:
            if table and table not in unique:
                unique.append(table)
        return unique

    def _handle_external_drop(self, mime, scene_pos: QPointF) -> None:
        for offset, table in enumerate(self._dropped_tables(mime)):
            if table not in self._all_tables():
                self._tables.append(table)
                self._refresh_canvas_sources()
            pos = QPointF(scene_pos.x() + 24 * offset, scene_pos.y() + 24 * offset)
            self.add_query_table(table, pos)

    def _populate_add_menu(self, add_menu, scene_pos: QPointF) -> None:
        names = self._available_to_add()
        if names:
            for name in names:
                label = name
                if is_list_token(self._local_tables.get(name, "")):
                    label = f"{name}   (pasted list)"
                elif name in self._local_tables:
                    label = f"{name}   ({self.scene.box_tags.get(name, 'FILE')} file)"
                elif name in self._common_table_cols:
                    label = f"{name}   (Common Table)"
                act = add_menu.addAction(label)
                act.triggered.connect(
                    lambda _=False, n=name, p=scene_pos: self.add_query_table(n, p))
        else:
            act = add_menu.addAction("All SQL Assist tables are on the canvas")
            act.setEnabled(False)
        add_menu.addSeparator()
        act_db = add_menu.addAction("Browse database tables\u2026")
        act_db.setEnabled(bool(self._dsn) and not is_file_token(self._dsn))
        act_db.triggered.connect(lambda: self.add_tables_requested.emit(ADD_KIND_ODBC))
        act_files = add_menu.addAction("Browse file datasets\u2026")
        act_files.triggered.connect(lambda: self.add_tables_requested.emit(ADD_KIND_FILES))
        act_paste = add_menu.addAction("Paste list from clipboard\u2026")
        act_paste.triggered.connect(self.paste_policy_list_requested)

    # ── Box actions (Table View, pasted-list edit/remove) ────────────────

    def is_list_table(self, table: str) -> bool:
        return is_list_token(self._local_tables.get(table, ""))

    def _extend_source_menu(self, menu, alias: str) -> None:
        menu.addSeparator()
        act_view = menu.addAction("Open Table View\u2026")
        act_view.triggered.connect(lambda _=False, a=alias: self.table_view_requested.emit(a))
        if self.is_list_table(alias):
            act_edit = menu.addAction("Edit Pasted List\u2026")
            act_edit.triggered.connect(lambda _=False, a=alias: self.list_edit_requested.emit(a))

    def _on_box_double_clicked(self, alias: str) -> None:
        if self.is_list_table(alias):
            self.list_edit_requested.emit(alias)

    def _remove_query_table(self, alias: str):
        # A pasted list lives only in this query: deleting its box removes the list.
        if self.is_list_table(alias):
            self.list_remove_requested.emit(alias)
            return
        super()._remove_query_table(alias)

    def rename_table_columns(self, table: str, renames: dict[str, str]) -> None:
        """Follow renamed columns of ``table`` in its joins and on its box."""
        if not renames:
            return
        for join in self.model.joins:
            for key in join.keys:
                if join.left_source == table and key.left_field in renames:
                    key.left_field = renames[key.left_field]
                if join.right_source == table and key.right_field in renames:
                    key.right_field = renames[key.right_field]
        self.scene.rebuild()
        self._update_suggestions()
        self.state_changed.emit()

    # ── SQL adapter ──────────────────────────────────────────────────────

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
        if self._dismissed_pairs:
            state["dismissed_suggestions"] = sorted(
                sorted(pair) for pair in self._dismissed_pairs)
        return state

    def set_state(self, state: dict):
        self._join_metadata.clear()
        self._dismissed_pairs = {
            frozenset(pair) for pair in state.get("dismissed_suggestions", [])
            if len(pair) == 2
        }
        metadata = state.get("metadata", {})
        for raw_key, value in metadata.items():
            parts = raw_key.split("|", 1)
            if len(parts) == 2:
                self._join_metadata[_join_key(parts[0], parts[1])] = dict(value)

        if "sources" in state or "joins" in state:
            super().set_state(state)
            # Keep saved field lists until live column metadata arrives.
            for src in self.model.sources:
                if src.alias not in self._table_columns and src.fields:
                    self._table_columns[src.alias] = src.field_names()
                    self._column_types[src.alias] = {
                        f.name: f.data_type for f in src.fields}
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
            for table in (card.get("left_table", ""), card.get("right_table", "")):
                if table:
                    self.add_query_table(table)
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
