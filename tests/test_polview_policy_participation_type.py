"""Policy tab: Participation Type Code (base LH_COV_PHA.DIV_PTP_TYP_CD) and untitled columns."""
from types import SimpleNamespace

import pytest

from suiteview.polview.models.cl_polrec.policy_translations import translate_participation_type_code
from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.ui.tabs.policy_tab import PolicyTab


class _FakePolicy:
    def __init__(self, participation):
        self._fields = {"participation_type_code": participation}
        self.values = SimpleNamespace(mec_indicator="0")
        self.dividends = SimpleNamespace(nfo_code="1", nfo_description="APL then ETI")
        self.product = SimpleNamespace(is_advanced_product=False)

    def field_value(self, name):
        return self._fields.get(name)


@pytest.mark.parametrize(
    ("raw", "text"),
    [("A", "A - Participating (dividends)"),
     ("9", "9 - Participating but divs are paid up"),
     ("0", "0 - Nonparticipating"),
     (" ", "(blank) - Nonparticipating"),
     ("Z", "Z - Unknown"),
     (None, "")],
)
def test_policy_tab_shows_participation_type_code(qtbot, raw, text):
    tab = PolicyTab()
    qtbot.addWidget(tab)

    tab._populate_entry_and_status_fields(_FakePolicy(raw), tab.col2)

    assert tab.col2.get_value("ptp_typ_cd") == text


def test_participation_type_sits_directly_above_nonforfeiture_option(qtbot):
    tab = PolicyTab()
    qtbot.addWidget(tab)
    layout = tab.col2._info_layout

    def row(attr):
        return layout.getItemPosition(layout.indexOf(tab.col2._fields[attr]))[0]

    assert row("ptp_typ_cd") == row("mec_status") + 1
    assert row("nfo_opt") == row("ptp_typ_cd") + 1
    assert tab.col2._labels["ptp_typ_cd"].text() == "Participation Type Code:"


def test_policy_tab_columns_have_no_group_titles(qtbot):
    tab = PolicyTab()
    qtbot.addWidget(tab)

    assert [c.title() for c in (tab.col1, tab.col2, tab.col3)] == ["", "", ""]


def test_participation_type_code_reads_base_coverage_phase():
    policy = object.__new__(PolicyInformation)
    calls = []

    def data_item(table, field, *args):
        calls.append((table, field, args))
        return "B"

    policy.data_item = data_item

    assert policy.field_value("participation_type_code") == "B"
    assert calls == [("LH_COV_PHA", "DIV_PTP_TYP_CD", (0,))]
    assert translate_participation_type_code("B ") == "Participating with coupons"
