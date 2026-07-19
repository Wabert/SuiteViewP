"""Illustration Compare tab — two or three scenarios side by side.

Each of the three scenario pickers (A, B, C) is a compare-source combo with
exactly three slots: "Current Inputs" (the live Illustration Inputs tab), an
optional saved case, and "(none)" — it NEVER enumerates the case store. To
compare against a saved case, drag its row from the Saved Cases panel and drop
it on a picker (custom ``application/x-suiteview-saved-case`` MIME carrying the
case name); the drop replaces that picker's case slot and selects it. A leads
on Current Inputs; B and C start at "(none)". Any picker at "(none)" is skipped,
so a comparison runs over the two or three active pickers. Run Comparison
executes them through the same pipeline as Run Values on a background thread.
The outcome lands as:

* a KPI delta strip — outcome (lapse vs sustains), MEC status, first
  GP-exception year, total premium outlay, AV/SV/DB at years 5/10/20/end —
  with green/red delta coloring where direction is meaningful for two
  scenarios; with three, each chip shows all three values and both deltas
  against A on a neutral line (deltas live ONLY here — the ledger below
  carries values, not arithmetic);
* the annual ledger as side-by-side scenario blocks in a FilterTableView:
  Year | Age, then each scenario's measures under a grouped header titled
  with its scenario name, a thin solid divider column between blocks; and
* an Excel export mirroring that layout (new unsaved workbook: KPI sheet +
  ledger sheet with a merged scenario-name row over each block).

Scenario labels are visible everywhere — the strip's leading label chips, the
ledger's grouped block headers, and the Excel sheets all carry "Current
Inputs" or the saved-case name. A failed scenario raises a loud per-side
banner (same visual language as the Values tab's guaranteed-failure strip)
and NEVER hides the surviving sides' results. When the loaded policy changes,
``clear_results()`` wipes the strip and ledger so results are never
misattributed to another policy.

All comparison logic lives in ``suiteview.illustration.core.compare_runner``;
this tab is a thin Qt shell that extracts each side's widget state into a
``ScenarioSpec`` on the UI thread.
"""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.core.compare_runner import (
    MIN_SCENARIOS,
    ComparisonResult,
    ScenarioSpec,
    kpi_summary_frame,
    ledger_column_groups,
    ledger_header_labels,
    run_comparison,
    separator_columns,
    side_tags,
)
from suiteview.illustration.models import case_store
from suiteview.illustration.models.case_store import CaseStoreError, SavedCase
from suiteview.ui.widgets.filter_table_view import FilterTableView

from .saved_cases_panel import SAVED_CASE_MIME
from .styles import (
    INPUT_CAPTION_STYLE,
    INPUT_COMBO_STYLE,
    PURPLE_BG,
    PURPLE_DARK,
    VALUE_BUTTON_STYLE,
    WHITE,
)

logger = logging.getLogger(__name__)

CURRENT_INPUTS_LABEL = "Current Inputs"
NO_SCENARIO_LABEL = "(none)"

# Combo userData marker for a picker's "(none)" entry — distinct from None,
# which means "Current Inputs".
_NO_SCENARIO = "__no_scenario__"

# Side letters assigned by position among the ACTIVE (non-"(none)") pickers.
_SIDE_LETTERS = "ABC"

_DEFAULT_STATUS = "Load a policy, pick two scenarios, then Run Comparison."

_SECONDARY_BUTTON_STYLE = (
    "QPushButton { background: #F3ECFC; color: #4B2383; border: 1px solid #7E57C2;"
    " border-radius: 5px; font-size: 10px; font-weight: bold; padding: 3px 12px;"
    " min-height: 22px; }"
    "QPushButton:hover { background: #E6DAF8; }"
    "QPushButton:disabled { color: #9A8FB0; border-color: #C9B8E4; }"
)

_BANNER_STYLE = (
    "background-color: #7A1020; color: #FFD54F; border: 1px solid #D4A017;"
    " border-radius: 4px; font-size: 12px; font-weight: bold; padding: 5px 9px;")

_NOTE_STYLE = (
    "background-color: #F6F1FB; color: #4B2383; border: 1px solid #B79CDE;"
    " border-radius: 4px; font-size: 11px; padding: 4px 8px;")

_LABEL_CHIP_STYLE = (
    "background-color: #2A1458; color: #FFD54F; border: 1px solid #5E35A5;"
    " border-radius: 4px; font-size: 11px; font-weight: bold; padding: 3px 10px;")

_TONE_COLORS = {"good": "#69F0AE", "bad": "#FF8A80", "neutral": "#FFD54F"}
_CHIPS_PER_ROW = 8

# The divider columns between scenario blocks: thin and SOLID-filled top to
# bottom (the model paints every data row of the column) so the blocks read
# clearly divided — a pink vertical rule, not a tint. Pink #A5355E is the
# accent already carried by the Excel export's header/divider fill (0xA5355E);
# reused here so screen and workbook agree. Excel's COM Interior.Color is BGR,
# so the same pink is 0x5E35A5 there.
_SEPARATOR_COLOR = "#A5355E"
_SEPARATOR_COLOR_BGR = 0x5E35A5
_SEPARATOR_WIDTH = 5

# Scenario picker: the shared input-combo look plus a pink drop-highlight
# border while a valid saved-case drag hovers over it.
_SCENARIO_COMBO_STYLE = (
    INPUT_COMBO_STYLE
    + "QComboBox[dropActive=\"true\"] { border: 2px solid #A5355E;"
    " background: #FBEEF3; }"
)


class _ScenarioComboBox(QComboBox):
    """A compare-source picker restricted to three entries: ``Current Inputs``,
    an optional dropped saved case, and ``(none)`` — in that order.

    It NEVER enumerates the case store. The only way to choose a saved case is
    to drag its row from the Saved Cases panel and drop it here; the drop
    replaces the dropped-case slot (showing the case name) and selects it.
    ``(none)`` selects nothing and skips the side. Store access lives in the
    tab: this widget only reads the dropped name off the MIME and emits it."""

    case_drop_requested = pyqtSignal(str)   # dropped row's case name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._dropped_case: Optional[SavedCase] = None
        self.build_entries()

    def build_entries(self):
        """(Re)build the fixed entries, preserving the current selection and
        any dropped case. Order: Current Inputs, [dropped case], (none)."""
        prior = self.currentData()
        self.blockSignals(True)
        self.clear()
        self.addItem(CURRENT_INPUTS_LABEL, None)
        if self._dropped_case is not None:
            self.addItem(self._dropped_case.name, self._dropped_case)
        self.addItem(NO_SCENARIO_LABEL, _NO_SCENARIO)
        self.setCurrentIndex(self._index_for(prior))
        self.blockSignals(False)

    def _index_for(self, data) -> int:
        if isinstance(data, SavedCase) and self._dropped_case is not None:
            return 1
        if data == _NO_SCENARIO:
            return self.count() - 1
        return 0

    def dropped_case(self) -> Optional[SavedCase]:
        return self._dropped_case

    def set_dropped_case(self, case: SavedCase):
        """Replace the dropped-case slot with ``case`` and select it."""
        self._dropped_case = case
        self.build_entries()
        self.setCurrentIndex(1)   # sits between Current Inputs and (none)

    def select_none(self):
        self.setCurrentIndex(self.count() - 1)

    # ── drag & drop ──────────────────────────────────────────────────
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(SAVED_CASE_MIME):
            event.acceptProposedAction()
            self._set_drop_active(True)
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(SAVED_CASE_MIME):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._set_drop_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if self.handle_dropped_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def handle_dropped_mime(self, mime) -> bool:
        """Parse a saved-case drop payload: emit the dropped case name and
        return True when it carries one, else False. Split out from
        ``dropEvent`` so it is testable with a plain ``QMimeData`` (no live
        ``QDropEvent`` needed)."""
        if not mime.hasFormat(SAVED_CASE_MIME):
            return False
        self._set_drop_active(False)
        name = bytes(mime.data(SAVED_CASE_MIME)).decode("utf-8")
        if name:
            self.case_drop_requested.emit(name)
        return True

    def _set_drop_active(self, active: bool):
        self.setProperty("dropActive", "true" if active else "false")
        style = self.style()
        style.unpolish(self)
        style.polish(self)


class _DeltaChip(QWidget):
    """Caption over the per-scenario values and the colored delta — the
    Overview KPI chip, grown a third line for the comparison."""

    def __init__(self, row, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "background-color: #2A1458; border: 1px solid #5E35A5; border-radius: 4px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 4)
        layout.setSpacing(0)
        caption = QLabel(row.caption.upper())
        caption.setStyleSheet(
            "color: #B79CDE; background: transparent; border: none; font-size: 9px;")
        values = QLabel("  →  ".join(row.values))
        values.setStyleSheet(
            "color: #E8DDF8; background: transparent; border: none;"
            " font-size: 10px; font-weight: bold;")
        delta = QLabel(f"Δ {row.delta_text}")
        delta.setStyleSheet(
            f"color: {_TONE_COLORS.get(row.tone, _TONE_COLORS['neutral'])};"
            " background: transparent; border: none;"
            " font-size: 12px; font-weight: bold;")
        layout.addWidget(caption)
        layout.addWidget(values)
        layout.addWidget(delta)


class _CompareWorker(QThread):
    """Runs one comparison off the UI thread through compare_runner."""

    finished_result = pyqtSignal(object)   # ComparisonResult
    failed = pyqtSignal(str)

    def __init__(self, specs: list, runner=run_comparison, parent=None):
        super().__init__(parent)
        self._specs = list(specs)
        self._runner = runner

    def run(self):  # pragma: no cover - thread body exercised synchronously in tests
        try:
            self.finished_result.emit(self._runner(self._specs))
        except Exception as exc:  # defensive — run_comparison isolates per side
            logger.error("Comparison run failed: %s", exc, exc_info=True)
            self.failed.emit(str(exc))


class IllustrationCompareTab(QWidget):
    """Two-scenario comparison: pickers + KPI delta strip + the side-by-side
    scenario-block ledger."""

    def __init__(self, parent=None, *, window=None, runner=run_comparison,
                 case_directory=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        self._window = window
        self._runner = runner
        self._case_directory = case_directory
        self._worker: Optional[_CompareWorker] = None
        self._result: Optional[ComparisonResult] = None
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── controls row: pickers + buttons, packed left with end stretch ──
        controls = QHBoxLayout()
        controls.setSpacing(6)
        self.scenario_combos: list[_ScenarioComboBox] = []
        for caption_text in ("Scenario A", "Scenario B", "Scenario C"):
            caption = QLabel(caption_text)
            caption.setStyleSheet(INPUT_CAPTION_STYLE)
            controls.addWidget(caption)
            combo = _ScenarioComboBox()
            combo.setStyleSheet(_SCENARIO_COMBO_STYLE)
            combo.setMinimumWidth(190)
            combo.setToolTip(
                "Current Inputs, (none), or a saved case dragged here from the "
                "Saved Cases panel.\nDrop a case onto this picker to compare "
                "against it; (none) skips the side.")
            combo.case_drop_requested.connect(
                lambda name, c=combo: self._on_case_dropped(c, name))
            controls.addWidget(combo)
            self.scenario_combos.append(combo)
        (self.scenario_a_combo, self.scenario_b_combo,
         self.scenario_c_combo) = self.scenario_combos
        # A defaults to Current Inputs (the live baseline); B and C start at
        # (none) — a saved case enters a picker only by drag-and-drop.
        self.scenario_b_combo.select_none()
        self.scenario_c_combo.select_none()
        self.run_btn = QPushButton("Run Comparison")
        self.run_btn.setStyleSheet(VALUE_BUTTON_STYLE)
        self.run_btn.setFixedHeight(26)
        self.run_btn.clicked.connect(self._on_run)
        controls.addWidget(self.run_btn)
        self.excel_btn = QPushButton("Excel")
        self.excel_btn.setStyleSheet(_SECONDARY_BUTTON_STYLE)
        self.excel_btn.setFixedHeight(26)
        self.excel_btn.setEnabled(False)
        self.excel_btn.setToolTip(
            "Open the KPI summary + comparison ledger in a new unsaved Excel workbook")
        self.excel_btn.clicked.connect(self._on_export)
        controls.addWidget(self.excel_btn)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.status_label = QLabel(_DEFAULT_STATUS)
        self.status_label.setStyleSheet(
            f"color: {PURPLE_DARK}; background: transparent; font-size: 10px;"
            " font-weight: bold;")
        layout.addWidget(self.status_label)

        # Per-scenario failure banners — loud, never silent (same visual
        # language as the Values tab's guaranteed-failure strip).
        self.banner_a = QLabel("", self)
        self.banner_b = QLabel("", self)
        self.banner_c = QLabel("", self)
        self.banners = (self.banner_a, self.banner_b, self.banner_c)
        for banner in self.banners:
            banner.setWordWrap(True)
            banner.setStyleSheet(_BANNER_STYLE)
            banner.setVisible(False)
            layout.addWidget(banner)
        # Saved-case apply warnings (inputs that did not land) — amber note.
        self.apply_note = QLabel("", self)
        self.apply_note.setWordWrap(True)
        self.apply_note.setStyleSheet(_NOTE_STYLE)
        self.apply_note.setVisible(False)
        layout.addWidget(self.apply_note)

        # ── KPI delta strip: label chips lead, then the KPI chips ──
        self.kpi_container = QWidget(self)
        self.kpi_container.setStyleSheet("background: transparent;")
        self.kpi_grid = QGridLayout(self.kpi_container)
        self.kpi_grid.setContentsMargins(0, 0, 0, 0)
        self.kpi_grid.setHorizontalSpacing(6)
        self.kpi_grid.setVerticalSpacing(6)
        layout.addWidget(self.kpi_container)

        # ── the side-by-side scenario-block annual ledger ──
        self.ledger_view = FilterTableView(self)
        self.ledger_view.setStyleSheet(f"QWidget {{ background-color: {WHITE}; }}")
        self.ledger_view.set_search_visible(False)
        self.ledger_view.apply_ledger_style()
        self.ledger_view.set_sort_enabled(False)
        self.ledger_view.set_filtering_enabled(False)
        self.ledger_view.set_full_row_selection(True)
        layout.addWidget(self.ledger_view, 1)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_scenario_choices()

    # ── scenario pickers ─────────────────────────────────────────────

    def refresh_scenario_choices(self):
        """Refresh the fixed picker entries.

        The pickers NEVER enumerate the case store — a saved case enters a
        picker only via drag-and-drop from the Saved Cases panel — so this
        only re-applies each picker's three slots (Current Inputs, the dropped
        case if any, (none)), preserving its current selection and dropped
        case."""
        for combo in self.scenario_combos:
            combo.build_entries()

    def _on_case_dropped(self, combo: "_ScenarioComboBox", name: str):
        """A saved-case row was dropped on ``combo``: resolve it from the store
        by name and load it into the picker (replacing any prior dropped case)
        as the selected comparison source."""
        try:
            case = case_store.load_case(name, directory=self._case_directory)
        except CaseStoreError as exc:
            self.status_label.setText(
                f"Could not load dropped case '{name}' — {exc}")
            return
        combo.set_dropped_case(case)
        self.status_label.setText(f"Comparing against saved case '{case.name}'.")

    def _selected_case(self, combo: QComboBox) -> Optional[SavedCase]:
        data = combo.currentData()
        return data if isinstance(data, SavedCase) else None

    def _third_scenario_active(self) -> bool:
        return self.scenario_c_combo.currentData() != _NO_SCENARIO

    # ── run ──────────────────────────────────────────────────────────

    def _on_run(self):
        window = self._window
        key = getattr(window, "_current_key", None) if window else None
        if self._worker is not None and self._worker.isRunning():
            return

        active = [combo for combo in self.scenario_combos
                  if combo.currentData() != _NO_SCENARIO]
        if len(active) < MIN_SCENARIOS:
            QMessageBox.information(
                self, "Run Comparison",
                "Pick at least two scenarios to compare. Set two pickers to "
                "Current Inputs or drop a saved case onto them — (none) skips "
                "a side.")
            return
        # Side letters follow position among the ACTIVE pickers, so a skipped
        # middle side never leaves a lettering gap.
        sides = [(_SIDE_LETTERS[i], self._selected_case(combo))
                 for i, combo in enumerate(active)]
        if all(case is None for _side, case in sides):
            QMessageBox.information(
                self, "Run Comparison",
                "Pick a saved case on at least one side — comparing Current "
                "Inputs to itself would show no differences.")
            return
        # A live loaded policy is only required when a side actually runs on
        # it: any active Current Inputs slot. Saved cases carry their own
        # frozen policy snapshot, so a comparison built purely from dropped
        # cases runs with no policy loaded at all.
        if key is None and any(case is None for _side, case in sides):
            QMessageBox.information(
                self, "Run Comparison",
                "Load a policy to compare Current Inputs (or set that "
                "scenario to a saved case).")
            return

        # Status header: the loaded policy, or the dropped cases' policy when
        # nothing is loaded (every side is a saved case then).
        policy_number = key[0] if key else next(
            case.policy_number.strip() for _side, case in sides
            if case is not None)
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            # Each side owns its policy data: a saved case runs against its own
            # frozen snapshot (no live fetch — that data is gone in snapshot
            # view), Current Inputs against the window's loaded policy. Only a
            # legacy snapshot-less case triggers a live fetch, done lazily
            # inside _build_spec, so comparing saved cases never touches DB2.
            specs = [self._build_spec(case, key, side=side)
                     for side, case in sides]
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            logger.error("Comparison setup failed: %s", exc, exc_info=True)
            QMessageBox.critical(
                self, "Run Comparison", f"Could not prepare the comparison:\n{exc}")
            return
        QApplication.restoreOverrideCursor()

        self._show_apply_warnings(specs)
        tags = side_tags(*[spec.label for spec in specs])
        self.status_label.setText(
            f"Running comparison for {policy_number} — {' vs '.join(tags)}...")
        self.run_btn.setEnabled(False)
        self.excel_btn.setEnabled(False)

        self._worker = _CompareWorker(specs, runner=self._runner, parent=self)
        self._worker.finished_result.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _build_spec(self, case: Optional[SavedCase], key: tuple,
                    side: str) -> ScenarioSpec:
        """Build one side's ScenarioSpec.

        A saved case carrying a frozen policy snapshot (schema v2+) is
        materialized against THAT snapshot — the policy exactly as it was when
        the case was saved — so the comparison reproduces the case and never
        depends on live DB2. ``Current Inputs`` runs on the window's currently
        loaded policy data; a legacy v1 case (no snapshot) falls back to a fresh
        live fetch.

        Materializing a saved case against the LIVE policy was the "two
        different cases, identical values" bug: while viewing a saved case the
        window holds no live policy (``window._policy is None``), so the
        throwaway tab loaded from ``None`` and its PolicyContext stayed empty —
        every dated change row (a DBO or face change) then failed to resolve its
        effective date and silently dropped, collapsing two different cases onto
        the same base-policy projection. This mirrors how
        ``main_window._on_run_values`` projects the frozen snapshot in snapshot
        view.
        """
        window = self._window
        if case is None:
            base = (getattr(window, "_illustration_data", None)
                    or self._fetch_live_policy_data(key))
            return self._spec_from_tab(CURRENT_INPUTS_LABEL, window.inputs_tab, base)

        from .inputs_tab import IllustrationInputsTab

        snapshot = case.policy_snapshot
        if snapshot is not None:
            # Deepcopy so neither the tab load nor the engine can mutate the
            # case's stored snapshot across repeated comparisons.
            base_policy = load_policy = deepcopy(snapshot)
            has_shadow = bool(getattr(snapshot, "has_shadow_account", False))
            shadow_ceased = bool(getattr(snapshot, "ccv_ceased", False))
        else:
            base_policy = self._fetch_live_policy_data(key)
            load_policy = window._policy
            illustration_data = getattr(window, "_illustration_data", None)
            has_shadow = bool(getattr(illustration_data, "has_shadow_account", False))
            shadow_ceased = bool(getattr(illustration_data, "ccv_ceased", False))

        tab = IllustrationInputsTab()
        try:
            tab.load_data_from_policy(
                load_policy, has_shadow=has_shadow, shadow_ceased=shadow_ceased)
            warnings = tab.apply_case_inputs(case.inputs)
            spec = self._spec_from_tab(case.name, tab, base_policy)
            spec.apply_warnings = [f"[{side} · {case.name}] {w}" for w in warnings]
            return spec
        finally:
            tab.deleteLater()

    @staticmethod
    def _fetch_live_policy_data(key: tuple):
        """Live illustration data for a policy — only for Current Inputs (when
        the window has none loaded) and legacy snapshot-less cases."""
        from suiteview.illustration.core.illustration_policy_service import (
            build_illustration_data,
        )
        if key is None:
            # Only reachable for a legacy v1 case (no frozen snapshot) with no
            # policy loaded — there is nothing to project it against.
            raise CaseStoreError(
                "This saved case predates policy snapshots — load its policy "
                "before comparing against it.")
        policy_number, region, company_code = key
        return build_illustration_data(
            policy_number, region=region, company_code=company_code)

    @staticmethod
    def _spec_from_tab(label: str, inputs_tab, policy_data) -> ScenarioSpec:
        """The same widget reads Run Values performs, bundled for the worker."""
        from suiteview.illustration.core.scenario_builder import (
            build_illustration_scenario,
        )
        scenario = build_illustration_scenario(
            policy_data,
            inforce_overrides=inputs_tab.export_inforce_overrides(),
            future_inputs=inputs_tab.export_input_set(),
        )
        return ScenarioSpec(
            label=label,
            scenario=scenario,
            months=inputs_tab.projection_months(scenario.projectable_policy),
            options=inputs_tab.export_options(),
            stop_on_lapse=inputs_tab.stop_on_lapse_enabled(),
            lumpsum_to_next=inputs_tab.lumpsum_to_next_enabled(),
            max_level=inputs_tab.max_level_request(),
            min_level=inputs_tab.min_level_request(),
            shadow_level=inputs_tab.shadow_level_request(),
            payoff_requests=inputs_tab.loan_payoff_requests(),
        )

    def _show_apply_warnings(self, specs: list):
        warnings = [w for spec in specs for w in spec.apply_warnings]
        if warnings:
            self.apply_note.setText(
                "Some saved-case inputs did not apply to this policy:\n"
                + "\n".join(f"•  {w}" for w in warnings))
            self.apply_note.setVisible(True)
        else:
            self.apply_note.setVisible(False)

    def _on_finished(self, result: ComparisonResult):
        self._worker = None
        self.populate_comparison(result)

    def _on_failed(self, message: str):
        self._worker = None
        self.run_btn.setEnabled(True)
        self.status_label.setText(f"Comparison failed: {message}")
        QMessageBox.critical(
            self, "Run Comparison", f"Comparison run failed:\n{message}")

    # ── results ──────────────────────────────────────────────────────

    def clear_results(self, message: str = _DEFAULT_STATUS):
        """Wipe every rendered result (chips, KPIs, ledger, banners, status).

        Called by the main window whenever the loaded policy changes so a
        previous policy's comparison can never sit mislabeled under the new
        policy's pickers."""
        import pandas as pd

        self._result = None
        self.excel_btn.setEnabled(False)
        for banner in self.banners:
            banner.setVisible(False)
        self.apply_note.setVisible(False)
        self._clear_kpi_grid()
        self.ledger_view.set_dataframe(pd.DataFrame(), limit_rows=False)
        self.ledger_view.set_column_groups(None)
        self.status_label.setText(message)

    def populate_comparison(self, result: ComparisonResult):
        """Render a finished comparison (also the test seam)."""
        self._result = result
        self.run_btn.setEnabled(True)
        outcomes = result.outcomes
        tags = side_tags(*[o.label for o in outcomes])

        for banner, outcome, tag in zip(self.banners, outcomes, tags):
            if outcome.error:
                banner.setText(
                    f"⚠ Scenario '{tag}' failed — no values for this side: "
                    f"{outcome.error}")
                banner.setVisible(True)
            else:
                banner.setVisible(False)
        for banner in self.banners[len(outcomes):]:
            banner.setVisible(False)

        self._rebuild_kpi_strip(result, tags)

        ledger = result.ledger
        self.ledger_view.set_dataframe(ledger, limit_rows=False)
        self.ledger_view.set_numeric_formatting(
            default_decimals=2, column_decimals={"Year": 0, "Age": 0})
        if not ledger.empty:
            # One block per scenario: plain measure names per column, the
            # scenario names in a grouped header over each block, and a thin
            # SOLID divider column between blocks.
            seps = separator_columns(ledger)
            self.ledger_view.set_header_labels(ledger_header_labels(ledger))
            self.ledger_view.set_column_groups(
                ledger_column_groups(ledger, *[o.label for o in outcomes]))
            self.ledger_view.set_column_backgrounds(
                {sep: QColor(_SEPARATOR_COLOR) for sep in seps})
            self.ledger_view.set_frozen_column_count(2)   # Year | Age stay put
            self.ledger_view.autofit_columns_to_data()
            for sep in seps:
                self.ledger_view.set_column_width(sep, _SEPARATOR_WIDTH)
        else:
            self.ledger_view.set_column_groups(None)
        self.excel_btn.setEnabled(bool(result.kpis) or not result.ledger.empty)

        oks = [o.ok for o in outcomes]
        if all(oks):
            # The chips above already name every side — keep this minimal.
            self.status_label.setText("Comparison ready.")
        elif any(oks):
            survivors = ", ".join(
                f"'{tag}'" for tag, ok in zip(tags, oks) if ok)
            self.status_label.setText(
                f"Comparison partially ready — only {survivors} ran; "
                "see the failure banner above.")
        else:
            self.status_label.setText(
                "Comparison failed on every scenario — see the banners above.")

    def _clear_kpi_grid(self):
        while self.kpi_grid.count():
            item = self.kpi_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_kpi_strip(self, result: ComparisonResult, tags):
        self._clear_kpi_grid()

        # Leading label chips — the scenario names, never anonymous A/B/C.
        legend = QHBoxLayout()
        legend.setSpacing(6)
        for prefix, tag in zip("ABC", tags):
            chip = QLabel(f"{prefix} · {tag}")
            chip.setStyleSheet(_LABEL_CHIP_STYLE)
            legend.addWidget(chip)
        legend.addStretch(1)
        legend_host = QWidget(self.kpi_container)
        legend_host.setStyleSheet("background: transparent;")
        legend_host.setLayout(legend)
        self.kpi_grid.addWidget(legend_host, 0, 0, 1, _CHIPS_PER_ROW)

        for index, row in enumerate(result.kpis):
            grid_row = 1 + index // _CHIPS_PER_ROW
            grid_col = index % _CHIPS_PER_ROW
            self.kpi_grid.addWidget(_DeltaChip(row), grid_row, grid_col)
        # Pad the last row so chips stay packed left.
        self.kpi_grid.setColumnStretch(_CHIPS_PER_ROW, 1)

    # ── Excel export ─────────────────────────────────────────────────

    def _on_export(self):
        result = self._result
        if result is None:
            return
        try:
            from suiteview.core.excel_export import (
                ExcelExportError, dump_to_new_workbook,
            )

            kpi_frame = kpi_summary_frame(result)
            kpi_rows = [tuple("" if v is None else v for v in rec)
                        for rec in kpi_frame.itertuples(index=False, name=None)]
            excel, wb, ws = dump_to_new_workbook(
                list(kpi_frame.columns), kpi_rows,
                sheet_name="Compare KPIs", autofilter=False)
            self._style_header(ws, len(kpi_frame.columns))

            ledger = result.ledger
            if not ledger.empty:
                ws2 = wb.Worksheets.Add(After=wb.Worksheets(wb.Worksheets.Count))
                ws2.Name = "Compare Ledger"[:31]
                self._write_ledger_sheet(excel, ws2, result)
                ws2.Activate()
            ws.Activate()
        except ExcelExportError as e:
            QMessageBox.warning(self, "Excel Error", str(e))
        except Exception as e:  # pragma: no cover - UI guard
            logger.error("Comparison export failed: %s", e, exc_info=True)
            QMessageBox.warning(self, "Export Error", f"Could not export:\n{e}")

    @staticmethod
    def _write_ledger_sheet(excel, ws, result: ComparisonResult):
        """The ledger sheet mirrors the tab: a merged scenario-name row over
        each block, plain measure headers beneath, a narrow separator column
        between the blocks, then the data. Rows 1-2 stay frozen."""
        ledger = result.ledger
        columns = list(ledger.columns)
        labels = ledger_header_labels(ledger)
        groups = ledger_column_groups(
            ledger, *[o.label for o in result.outcomes])
        col_pos = {str(name): i + 1 for i, name in enumerate(columns)}

        group_row = [""] * len(columns)
        for label, names in groups:
            group_row[col_pos[str(names[0])] - 1] = label
        header_row = [labels.get(name, str(name)) for name in columns]
        data_rows = [
            tuple("" if v is None or (isinstance(v, float) and v != v)
                  else v for v in rec)
            for rec in ledger.itertuples(index=False, name=None)]
        all_rows = [tuple(group_row), tuple(header_row)] + data_rows

        rng = ws.Range(ws.Cells(1, 1), ws.Cells(len(all_rows), len(columns)))
        rng.Value = all_rows
        for label, names in groups:
            span = ws.Range(
                ws.Cells(1, col_pos[str(names[0])]),
                ws.Cells(1, col_pos[str(names[-1])]))
            span.Merge()
        IllustrationCompareTab._style_header(ws, len(columns), rows=2)

        ws.Range("A3").Select()
        excel.ActiveWindow.FreezePanes = True
        ws.Columns.AutoFit()
        # Divider columns: narrow and SOLID-filled top to bottom so each block
        # boundary reads as a pink vertical rule (matches the on-screen table;
        # COM Interior.Color is BGR, so this is pink #A5355E).
        for sep in separator_columns(ledger):
            pos = col_pos[str(sep)]
            ws.Columns(pos).ColumnWidth = 0.8
            fill = ws.Range(ws.Cells(1, pos), ws.Cells(len(all_rows), pos))
            fill.Interior.Color = _SEPARATOR_COLOR_BGR

    @staticmethod
    def _style_header(ws, column_count: int, rows: int = 1):
        """White bold on Illustration purple (BGR for #5E35A5), centered."""
        hdr = ws.Range(ws.Cells(1, 1), ws.Cells(rows, column_count))
        hdr.Font.Color = 0xFFFFFF
        hdr.Font.Bold = True
        hdr.Interior.Color = 0xA5355E
        hdr.HorizontalAlignment = -4108  # xlCenter
