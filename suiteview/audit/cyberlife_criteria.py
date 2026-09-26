"""Widget-free CyberLife audit criteria snapshots."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QListWidget


@dataclass(frozen=True)
class TextCriteria:
    value: str = ""

    def text(self) -> str:
        return self.value


@dataclass(frozen=True)
class CheckCriteria:
    checked: bool = False

    def isChecked(self) -> bool:
        return self.checked


@dataclass(frozen=True)
class ComboCriteria:
    value: str = ""

    def currentText(self) -> str:
        return self.value


@dataclass(frozen=True)
class ListItemCriteria:
    label: str
    user_data: Any = None

    def text(self) -> str:
        return self.label

    def data(self, _role: Any = None) -> Any:
        return self.user_data


@dataclass(frozen=True)
class ListCriteria:
    selected: tuple[ListItemCriteria, ...] = ()

    def selectedItems(self) -> list[ListItemCriteria]:
        return list(self.selected)


@dataclass(frozen=True)
class MultiSelectCriteria:
    value: str = ""
    selected: tuple[str, ...] = ()

    def text(self) -> str:
        return self.value

    def selected_values(self) -> list[str]:
        return list(self.selected)


@dataclass(frozen=True)
class TabCriteria:
    attrs: Mapping[str, Any] = field(default_factory=dict)

    def __getattr__(self, name: str) -> Any:
        try:
            return self.attrs[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


@dataclass(frozen=True)
class PolicyCriteria(TabCriteria):
    pass


@dataclass(frozen=True)
class DisplayCriteria(TabCriteria):
    pass


@dataclass(frozen=True)
class Policy2Criteria(TabCriteria):
    pass


@dataclass(frozen=True)
class AdvCriteria(TabCriteria):
    pass


@dataclass(frozen=True)
class CoveragesCriteria(TabCriteria):
    pass


@dataclass(frozen=True)
class BenefitsCriteria(TabCriteria):
    pass


@dataclass(frozen=True)
class PeopleCriteria(TabCriteria):
    pass


@dataclass(frozen=True)
class Segment52Criteria(TabCriteria):
    state: Mapping[str, Any] = field(default_factory=dict)

    def get_state(self) -> Mapping[str, Any]:
        return self.state


@dataclass(frozen=True)
class PlancodeCriteria(TabCriteria):
    plancodes: tuple[str, ...] = ()
    policies: tuple[str, ...] = ()
    cov1_only: bool = False

    def get_plancodes(self) -> list[str]:
        return list(self.plancodes)

    def get_policies(self) -> list[str]:
        return list(self.policies)

    def cov1_plancode_match_only(self) -> bool:
        return self.cov1_only


@dataclass(frozen=True)
class TransactionTabCriteria:
    first: Any
    second: Any

    def criteria(self) -> tuple[Any, Any]:
        return self.first, self.second


@dataclass(frozen=True)
class CustomDisplayCriteria:
    selected_fields: tuple[tuple[str, str], ...] = ()
    criteria_filters: tuple[tuple[str, tuple[str, ...], str, str], ...] = ()

    def get_selected_fields(self) -> list[tuple[str, str]]:
        return list(self.selected_fields)

    def get_criteria_filters(self) -> list[tuple[str, list[str], str, str]]:
        return [
            (table, list(fields), match_type, value)
            for table, fields, match_type, value in self.criteria_filters
        ]


@dataclass(frozen=True)
class WlCriteria(TabCriteria):
    participation_codes: tuple[str, ...] = ()

    def selected_participation_codes(self) -> list[str]:
        return list(self.participation_codes)


@dataclass(frozen=True)
class AuditCriteria:
    schema: str
    sys_code: str
    max_count_text: str
    policy: PolicyCriteria
    display: DisplayCriteria
    policy2: Policy2Criteria
    adv: AdvCriteria
    coverages: CoveragesCriteria
    plancode: PlancodeCriteria
    benefits: BenefitsCriteria
    transaction: TransactionTabCriteria | None = None
    coverage_level: bool = False
    coverage_scope: str = "All Covs"
    custom_display: CustomDisplayCriteria | None = None
    people: PeopleCriteria | None = None
    segment52: Segment52Criteria | None = None
    wl: WlCriteria | None = None


def _freeze_listbox(widget: QListWidget) -> ListCriteria:
    selected = []
    for item in widget.selectedItems():
        selected.append(ListItemCriteria(
            item.text(),
            item.data(Qt.ItemDataRole.UserRole),
        ))
    return ListCriteria(tuple(selected))


def _freeze_value(value: Any) -> Any:
    if isinstance(value, QLineEdit):
        return TextCriteria(value.text())
    if isinstance(value, QCheckBox):
        return CheckCriteria(value.isChecked())
    if isinstance(value, QComboBox):
        return ComboCriteria(value.currentText())
    if isinstance(value, QListWidget):
        return _freeze_listbox(value)
    if hasattr(value, "selected_values") and hasattr(value, "text"):
        return MultiSelectCriteria(value.text(), tuple(value.selected_values()))
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, list):
        return [_freeze_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _freeze_value(item) for key, item in value.items()}
    return value


def _freeze_tab(tab: Any, cls: type[TabCriteria]) -> TabCriteria:
    if tab is None:
        return cls({})
    attrs = {
        name: _freeze_value(value)
        for name, value in vars(tab).items()
        if not name.startswith("_")
    }
    return cls(attrs)


def _freeze_plancode(tab: Any) -> PlancodeCriteria:
    base = _freeze_tab(tab, PlancodeCriteria)
    return PlancodeCriteria(
        base.attrs,
        tuple(tab.get_plancodes()),
        tuple(tab.get_policies()),
        tab.cov1_plancode_match_only(),
    )


def _freeze_transaction(tab: Any | None) -> TransactionTabCriteria | None:
    if tab is None:
        return None
    first, second = tab.criteria()
    return TransactionTabCriteria(first, second)


def _freeze_custom_display(tab: Any | None) -> CustomDisplayCriteria | None:
    if tab is None:
        return None
    selected = tuple((table, field) for table, field in tab.get_selected_fields())
    filters = tuple(
        (table, tuple(fields), match_type, value)
        for table, fields, match_type, value in tab.get_criteria_filters()
    )
    return CustomDisplayCriteria(selected, filters)


def _freeze_wl(tab: Any | None) -> WlCriteria | None:
    if tab is None:
        return None
    base = _freeze_tab(tab, WlCriteria)
    return WlCriteria(base.attrs, tuple(tab.selected_participation_codes()))


def _freeze_segment52(tab: Any | None) -> Segment52Criteria | None:
    if tab is None:
        return None
    base = _freeze_tab(tab, Segment52Criteria)
    return Segment52Criteria(base.attrs, tab.get_state())


def collect_audit_criteria(
    schema: str,
    sys_code: str,
    max_count_text: str,
    policy_tab: Any,
    display_tab: Any,
    policy2_tab: Any,
    adv_tab: Any,
    coverages_tab: Any,
    plancode_tab: Any,
    benefits_tab: Any,
    transaction_tab: Any | None = None,
    coverage_level: bool = False,
    coverage_scope: str = "All Covs",
    custom_display_tab: Any | None = None,
    people_tab: Any | None = None,
    segment52_tab: Any | None = None,
    wl_tab: Any | None = None,
) -> AuditCriteria:
    """Read Qt widgets once and return immutable SQL-builder criteria."""
    return AuditCriteria(
        schema=schema,
        sys_code=sys_code,
        max_count_text=max_count_text,
        policy=_freeze_tab(policy_tab, PolicyCriteria),
        display=_freeze_tab(display_tab, DisplayCriteria),
        policy2=_freeze_tab(policy2_tab, Policy2Criteria),
        adv=_freeze_tab(adv_tab, AdvCriteria),
        coverages=_freeze_tab(coverages_tab, CoveragesCriteria),
        plancode=_freeze_plancode(plancode_tab),
        benefits=_freeze_tab(benefits_tab, BenefitsCriteria),
        transaction=_freeze_transaction(transaction_tab),
        coverage_level=coverage_level,
        coverage_scope=coverage_scope,
        custom_display=_freeze_custom_display(custom_display_tab),
        people=_freeze_tab(people_tab, PeopleCriteria) if people_tab is not None else None,
        segment52=_freeze_segment52(segment52_tab),
        wl=_freeze_wl(wl_tab),
    )
