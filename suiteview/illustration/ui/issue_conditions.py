"""Editable issue assumptions, separate from the loaded inforce snapshot."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QHeaderView, QLabel, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.illustration.core.lapse import issue_no_lapse_years, validate_no_lapse_years
from suiteview.illustration.models.input_set import IssueOverrideSet
from suiteview.illustration.models.plancode_config import load_plancode
from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.polview.ui.formatting import format_date
from suiteview.polview.ui.widgets import StyledInfoTableGroup

from .styles import (
    ISSUE_GROUP_STYLE, ISSUE_BLUE_BG, ISSUE_BLUE_DARK, apply_input_checkbox_style,
)


class IssueConditionsPanel(QWidget):
    changed = pyqtSignal()

    ASSUMPTIONS = (
        "This is a hypothetical issue illustration, not a reconstruction of history. "
        "The original issue-date base coverage is used; later increases/COLA and "
        "later riders are excluded. Review the face, option and riders below. "
        "DB option and underwriting default to the loaded values, not verified "
        "original values. Billing and allocation defaults come from the loaded policy; "
        "set premiums and allocations on Input. No historical transactions are replayed.")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy: IllustrationPolicyData | None = None
        self._loading = False
        self._rider_checks: dict[int, QCheckBox] = {}
        self._benefit_checks: dict[tuple[int, str, str], QCheckBox] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.notice = QLabel(
            "Not applicable in Inforce mode. Select New Business - From Issue "
            "to edit the modeled issue conditions.")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.assumptions = QLabel(self.ASSUMPTIONS)
        self.assumptions.setWordWrap(True)
        layout.addWidget(self.assumptions)

        self.identity = StyledInfoTableGroup(
            "Original Issue Basis", columns=3, show_table=False)
        self.identity.setStyleSheet(ISSUE_GROUP_STYLE)
        for caption, key in (
            ("Issue Date", "issue_date"), ("Issue Age", "issue_age"),
            ("Plancode", "plancode"), ("Class", "rate_class"),
            ("Sex", "rate_sex"), ("Rate Basis", "rate_date"),
        ):
            self.identity.add_field(caption, key, 65, 85)
        layout.addWidget(self.identity)

        self.conditions = StyledInfoTableGroup("At-Issue Conditions", show_info=False)
        self.conditions.setStyleSheet(ISSUE_GROUP_STYLE)
        self.conditions.setup_table(["Condition", "Modeled at Issue"])
        table = self.conditions.table._data_table
        table.setRowCount(3)
        for row, caption in enumerate((
            "Base Face Amount", "Death Benefit Option", "No Lapse Period",
        )):
            item = QTableWidgetItem(caption)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 0, item)
        self.face_edit = QDoubleSpinBox()
        self.face_edit.setRange(0.01, 999_999_999_999.99)
        self.face_edit.setDecimals(2)
        self.face_edit.setGroupSeparatorShown(True)
        self.face_edit.setPrefix("$ ")
        self.face_edit.setToolTip("The modeled base face amount must be greater than zero.")
        self.face_edit.setKeyboardTracking(False)
        self.face_edit.valueChanged.connect(self._on_changed)
        self.dbo_combo = QComboBox()
        for code, label in (("A", "A - Level"), ("B", "B - Increasing"), ("C", "C - Return of Premium")):
            self.dbo_combo.addItem(label, code)
        self.dbo_combo.currentIndexChanged.connect(self._on_changed)
        self.no_lapse_years_edit = QDoubleSpinBox()
        self.no_lapse_years_edit.setRange(0, 1_000_000_000)
        self.no_lapse_years_edit.setDecimals(2)
        self.no_lapse_years_edit.setSuffix(" years")
        self.no_lapse_years_edit.setKeyboardTracking(False)
        self.no_lapse_years_edit.setToolTip(
            "During this period from issue, test account value less loans instead "
            "of surrender value. Other existing protections remain available. "
            "Normal lapse rules resume afterward. Defaults to the plan safety-net "
            "(minimum premium) period. Zero disables this convenience override; "
            "fractional years round to the nearest month. This is not a guarantee.")
        self.no_lapse_years_edit.valueChanged.connect(self._on_changed)
        table.setCellWidget(0, 1, self.face_edit)
        table.setCellWidget(1, 1, self.dbo_combo)
        table.setCellWidget(2, 1, self.no_lapse_years_edit)
        table.setRowHeight(0, 26)
        table.setRowHeight(1, 26)
        table.setRowHeight(2, 26)
        table.setColumnWidth(0, 160)
        table.setColumnWidth(1, 245)
        self.conditions.setFixedHeight(151)
        layout.addWidget(self.conditions)

        self.riders = StyledInfoTableGroup("Existing Riders and Benefits", show_info=False)
        self.riders.setStyleSheet(ISSUE_GROUP_STYLE)
        self.riders.setup_table(["Include", "Phase", "Rider / Benefit", "Issue Date", "Amount", "Issue Eligibility"])
        self.riders.table._data_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.riders, 1)
        self.set_issue_mode(False)

    def set_issue_mode(self, enabled: bool):
        self.setStyleSheet(
            f"background-color: {ISSUE_BLUE_BG if enabled else '#ECECEC'};")
        for widget in (self.identity, self.conditions, self.riders):
            widget.setEnabled(enabled and self._policy is not None)
        self.notice.setText(
            "NEW BUSINESS - FROM ISSUE | Current side: scale 1 | "
            "Zero opening balances | Guaranteed basis unchanged"
            if enabled else
            "Not applicable in Inforce mode. Select New Business - From Issue "
            "to edit the modeled issue conditions.")
        self.notice.setStyleSheet(
            f"color: {ISSUE_BLUE_DARK if enabled else '#666666'};"
            f" font-style: {'normal' if enabled else 'italic'}; font-weight: bold;")

    def has_policy(self) -> bool:
        return self._policy is not None

    def load_policy(self, policy):
        self._policy = policy if isinstance(policy, IllustrationPolicyData) else None
        self.assumptions.setText(self.ASSUMPTIONS)
        self._loading = True
        self._rider_checks.clear()
        self._benefit_checks.clear()
        self.riders.table.setRowCount(0)
        try:
            if self._policy is None:
                self.assumptions.setText(
                    "Issue conditions require a complete illustration policy snapshot. "
                    "Reload the policy after resolving any policy-load errors.")
                return
            candidate = build_illustration_scenario(
                policy, run_from_issue=True).projectable_policy
            self.face_edit.setValue(candidate.face_amount)
            self.dbo_combo.setCurrentIndex(self.dbo_combo.findData(candidate.db_option))
            config = load_plancode(policy.plancode) if policy.plancode else None
            self.no_lapse_years_edit.setValue(issue_no_lapse_years(candidate, config))
            for key in ("issue_date", "issue_age", "plancode", "rate_class", "rate_sex"):
                value = getattr(candidate, key)
                self.identity.set_value(
                    key, format_date(value) if key == "issue_date" else str(value))
            self.identity.set_value("rate_date", format_date(candidate.illustration_date))
            eligible_riders = {r.coverage_phase for r in candidate.riders}
            eligible_benefits = {self.benefit_key(b) for b in candidate.benefits}
            for rider in policy.riders:
                key = rider.coverage_phase
                self._rider_checks[key] = self._add_rider(
                    key, rider.description or rider.plancode, rider.issue_date,
                    rider.face_amount, key in eligible_riders)
            for benefit in policy.benefits:
                key = self.benefit_key(benefit)
                self._benefit_checks[key] = self._add_rider(
                    benefit.coverage_phase,
                    benefit.form_number or f"{benefit.benefit_type}{benefit.benefit_subtype}",
                    benefit.issue_date, benefit.benefit_amount, key in eligible_benefits)
            self.riders.table.autoFitAllColumns()
        finally:
            self._loading = False

    @staticmethod
    def benefit_key(benefit):
        return (benefit.coverage_phase, benefit.benefit_type, benefit.benefit_subtype)

    def _add_rider(self, phase, name, issue_date, amount, eligible):
        table = self.riders.table._data_table
        row = table.rowCount()
        table.insertRow(row)
        check = QCheckBox()
        apply_input_checkbox_style(check)
        check.setChecked(eligible)
        check.setEnabled(eligible)
        check.setProperty("issueEligible", eligible)
        check.toggled.connect(self._on_changed)
        table.setCellWidget(row, 0, check)
        for col, value in enumerate((
            phase, name, format_date(issue_date), f"{amount:,.2f}",
            "Available at issue" if eligible else "Excluded - not original issue coverage",
        ), start=1):
            item = QTableWidgetItem(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, col, item)
        return check

    def _on_changed(self, *_args):
        if not self._loading:
            self.changed.emit()

    def export_overrides(self) -> IssueOverrideSet:
        if self._policy is None:
            raise ValueError("Reload a complete policy snapshot before running from issue.")
        if self.face_edit.value() <= 0:
            raise ValueError("At-Issue Conditions: Base Face Amount must be greater than zero.")
        if self.dbo_combo.currentData() is None:
            raise ValueError("At-Issue Conditions: select a Death Benefit Option.")
        return IssueOverrideSet(
            face_amount=self.face_edit.value(),
            db_option=self.dbo_combo.currentData(),
            no_lapse_years=self.no_lapse_years_edit.value(),
            excluded_rider_phases=[
                key for key, check in self._rider_checks.items()
                if check.property("issueEligible") and not check.isChecked()],
            excluded_benefit_keys=[
                key for key, check in self._benefit_checks.items()
                if check.property("issueEligible") and not check.isChecked()],
        )

    def capture_state(self) -> dict:
        return {
            "face_amount": self.face_edit.value(),
            "db_option": self.dbo_combo.currentData(),
            "no_lapse_years": self.no_lapse_years_edit.value(),
            "excluded_rider_phases": [
                key for key, check in self._rider_checks.items()
                if check.property("issueEligible") and not check.isChecked()],
            "excluded_benefit_keys": [
                list(key) for key, check in self._benefit_checks.items()
                if check.property("issueEligible") and not check.isChecked()],
        }

    def apply_state(self, state: dict | None) -> list[str]:
        if not state:
            return []
        warnings = []
        self._loading = True
        try:
            if "no_lapse_years" in state:
                years = validate_no_lapse_years(state["no_lapse_years"])
                if years > self.no_lapse_years_edit.maximum():
                    raise ValueError("Saved No Lapse Period is outside the editor limits.")
                self.no_lapse_years_edit.setValue(years)
            if "face_amount" in state:
                face = state["face_amount"]
                if (not isinstance(face, (int, float))
                        or not self.face_edit.minimum() <= face <= self.face_edit.maximum()):
                    raise ValueError("Saved at-issue face amount is outside the editor limits.")
                self.face_edit.setValue(face)
            if "db_option" in state:
                index = self.dbo_combo.findData(state["db_option"])
                if index < 0:
                    raise ValueError("Saved at-issue death benefit option must be A, B or C.")
                self.dbo_combo.setCurrentIndex(index)
            for checks, excluded in (
                (self._rider_checks, state.get("excluded_rider_phases", [])),
                (self._benefit_checks, [tuple(key) for key in state.get("excluded_benefit_keys", [])]),
            ):
                for key, check in checks.items():
                    check.setChecked(bool(check.property("issueEligible")) and key not in excluded)
                for key in excluded:
                    if key not in checks or not checks[key].property("issueEligible"):
                        warnings.append(f"At-issue rider/benefit {key} is not available on this policy.")
        finally:
            self._loading = False
        return warnings
