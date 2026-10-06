"""Calculated-value hover tips and the "Copy Tip Contents" right-click action."""

from datetime import date
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication, QMenu, QTableWidgetItem

from suiteview.illustration.core.calc_engine import surrender_charge_units
from suiteview.illustration.core.interim_value import InterimAccountValue, InterimPremium
from suiteview.polview.services.policy_prefetch import SurrenderChargeCoverage, SurrenderValues
from suiteview.polview.services.targets_view_model import _prem_allowed_gpt
from suiteview.polview.ui.tabs import adv_prod_tooltips, targets_tooltips
from suiteview.polview.ui.tabs.targets_tab import AccumulatorsWidget, MinimumPremiumWidget
from suiteview.polview.ui.widgets import (
    ClickableTooltipLabel, CopyableLabel, StyledInfoTableGroup, tooltip_plain_text,
)


def _choose(monkeypatch, text, seen):
    """Make QMenu.exec record the menu's actions and pick the one named ``text``."""
    def exec_(menu, position):
        seen[:] = [action.text() for action in menu.actions() if action.text()]
        return next((a for a in menu.actions() if a.text() == text), None)
    monkeypatch.setattr(QMenu, "exec", exec_)


# ── Copy Tip Contents ────────────────────────────────────────────────────────

def test_value_with_hover_tip_offers_copy_tip_contents(qtbot, monkeypatch):
    label = CopyableLabel("1,815.79")
    qtbot.addWidget(label)
    label.setToolTip("MD = COI + Other + Expenses\n1,168.08 + 0.00 + 647.71 = 1,815.79")
    seen = []
    _choose(monkeypatch, "Copy Tip Contents", seen)
    QApplication.clipboard().setText("before")
    label.customContextMenuRequested.emit(QPoint(1, 1))
    assert seen == ["Copy", "Copy Tip Contents"]
    assert QApplication.clipboard().text() == label.toolTip()

    _choose(monkeypatch, "Copy", seen)
    label.customContextMenuRequested.emit(QPoint(1, 1))
    assert QApplication.clipboard().text() == "1,815.79"


def test_value_without_hover_tip_only_offers_copy(qtbot, monkeypatch):
    label = CopyableLabel("7")
    qtbot.addWidget(label)
    seen = []
    _choose(monkeypatch, "Copy", seen)
    label.customContextMenuRequested.emit(QPoint(1, 1))
    assert seen == ["Copy"]


def test_source_tip_keeps_raw_table_action_and_adds_copy_tip(qtbot, monkeypatch):
    group = StyledInfoTableGroup("Info", show_table=False)
    qtbot.addWidget(group)
    group.add_field("Plan", "plan")
    group.set_field_sources({"plan": "LH_COV_PHA.PLN_DES_SER_CD"})
    group.window().open_source_table = lambda table: None
    seen = []
    _choose(monkeypatch, "Copy Tip Contents", seen)
    group._fields["plan"].customContextMenuRequested.emit(QPoint(1, 1))
    assert seen == ["Copy", "Copy Tip Contents", "Show LH_COV_PHA rows in Raw Table"]
    assert QApplication.clipboard().text() == "Source: LH_COV_PHA.PLN_DES_SER_CD"


def test_field_label_help_offers_copy_tip_contents(qtbot, monkeypatch):
    label = ClickableTooltipLabel("CCV:", "Current Cash Value help")
    qtbot.addWidget(label)
    seen = []
    _choose(monkeypatch, "Copy Tip Contents", seen)
    label.customContextMenuRequested.emit(QPoint(1, 1))
    assert seen == ["Show Info", "Copy Tip Contents", "Copy Label"]
    assert QApplication.clipboard().text() == "Current Cash Value help"


def test_table_cell_with_hover_tip_offers_copy_tip_contents(qtbot, monkeypatch):
    group = StyledInfoTableGroup("Values", show_info=False)
    qtbot.addWidget(group)
    group.setup_table(["M", "MD"])
    group.load_table_data([["7", "1,815.79"]])
    item = group.table.item(0, 1)
    item.setToolTip("MD tip")
    monkeypatch.setattr(group.table._data_table, "itemAt", lambda pos: item)
    seen = []
    _choose(monkeypatch, "Copy Tip Contents", seen)
    group.table._show_context_menu(QPoint(1, 1))
    assert seen[:2] == ["Copy Cell", "Copy Tip Contents"]
    assert QApplication.clipboard().text() == "MD tip"

    plain = group.table.item(0, 0)
    monkeypatch.setattr(group.table._data_table, "itemAt", lambda pos: plain)
    group.table._show_context_menu(QPoint(1, 1))
    assert "Copy Tip Contents" not in seen


def test_rich_text_tips_copy_as_plain_text(qtbot):
    plain = tooltip_plain_text("<b>Value</b><hr><nobr>DB2: X.Y</nobr>")
    assert "Value" in plain and "DB2: X.Y" in plain and "<" not in plain
    assert tooltip_plain_text("a < b\nc") == "a < b\nc"


# ── Account Values tips ─────────────────────────────────────────────────────

def _surrender():
    return SurrenderValues(
        surrender_charge=13774.81, surrender_value=-21515.08, account_value=-7740.27,
        policy_debt=0.0, as_of=date(2026, 9, 7), original_units_basis=False,
        coverages=(SurrenderChargeCoverage(1, 1000.0, 13.77481, 13774.81),),
    )


def test_surrender_tips_show_the_working():
    charge = adv_prod_tooltips.surrender_charge_tip(_surrender())
    assert "Surrender Charge as of 9/07/2026" in charge
    assert "current specified amount / 1,000" in charge
    assert "before that monthliversary is processed" in charge
    assert "Cov 1: 13.77481 x 1,000 units = 13,774.81" in charge
    assert charge.endswith("= 13,774.81")
    value = adv_prod_tooltips.surrender_value_tip(_surrender())
    assert value.splitlines()[1:] == [
        "  Account Value: -7,740.27",
        "- Surrender Charge: 13,774.81",
        "- Policy Debt: 0.00",
        "= -21,515.08",
    ]


def test_rule_5_iswl_surrender_tip_shows_the_percentage_of_account_value():
    surrender = SurrenderValues(
        surrender_charge=600.0, surrender_value=9400.0, account_value=10000.0,
        policy_debt=0.0, as_of=date(2006, 6, 11), original_units_basis=False,
        coverages=(SurrenderChargeCoverage(1, 25.0, 0.06, 600.0, pct_of_account_value=True),),
    )
    charge = adv_prod_tooltips.surrender_charge_tip(surrender)
    assert "rule 5" in charge and "units" not in charge
    assert "Cov 1: 6% x AV 10,000.00 = 600.00" in charge
    assert charge.endswith("= 600.00")


def test_interim_tip_explains_the_roll_forward():
    tip = adv_prod_tooltips.interim_av_tip(InterimAccountValue(
        valuation_date=date(2026, 9, 7), quote_date=date(2026, 9, 29),
        next_monthliversary=date(2026, 10, 7), valuation_account_value=-7740.27,
        premiums=(InterimPremium(date(2026, 9, 20), 100.0, 95.0),),
        interest=0.0, account_value=-7645.27,
    ))
    assert "declared rate over exact days" in tip
    assert "+ Premium 09/20/2026: 95.00 net (100.00 gross)" in tip
    assert "= -7,645.27" in tip
    assert tip.endswith("Valid until the 10/07/2026 monthliversary.")


def test_sum_and_monthly_tips():
    tip = adv_prod_tooltips.sum_tip("T", "S", [("GP", -7740.27), ("U1", 0.0)], -7740.27)
    assert tip.splitlines() == ["T", "S", "GP: -7,740.27", "U1: 0.00", "= -7,740.27"]
    assert "No loans" in adv_prod_tooltips.sum_tip("T", "", [], 0.0, empty="No loans")
    assert adv_prod_tooltips.monthly_deduction_tip(1168.08, None, 647.71, 1815.79).endswith(
        "1,168.08 + 0.00 + 647.71 = 1,815.79")
    assert adv_prod_tooltips.sp_prem_cease_age_tip(10, 45, 55).endswith("10 + 45 = 55")


@pytest.mark.parametrize("sa_basis,expected", [("CurrentSA", 120.0), ("OriginalSA", 250.0)])
def test_surrender_charge_units_follow_sa_basis(sa_basis, expected):
    segment = SimpleNamespace(units=120.0, original_face_amount=250000.0)
    assert surrender_charge_units(segment, SimpleNamespace(sa_basis=sa_basis)) == expected
    assert surrender_charge_units(segment, None) == 120.0


# ── Targets & Accumulators tips ─────────────────────────────────────────────

def _gpt_policy(gpt="GP"):
    return SimpleNamespace(
        product=SimpleNamespace(gpt_cvat=gpt),
        targets=SimpleNamespace(gsp=50000, accumulated_glp_target=30000),
        billing=SimpleNamespace(premium_td=42000),
        values=SimpleNamespace(total_withdrawals=2000),
    )


def test_prem_allowed_gpt_returns_value_and_inputs():
    value, inputs = _prem_allowed_gpt(_gpt_policy(), True)
    assert value == 10000.0
    assert inputs == {"gsp": 50000.0, "accum_glp": 30000.0,
                      "premium_td": 42000.0, "withdrawals": 2000.0}
    assert _prem_allowed_gpt(_gpt_policy("CVAT"), True) == ("N/A", None)
    tip = targets_tooltips.prem_allowed_gpt_tip(inputs, value)
    assert "max(50,000.00, 30,000.00) = 50,000.00" in tip
    assert tip.endswith("50,000.00 - 42,000.00 + 2,000.00 = 10,000.00")


def test_accumulator_calculated_fields_have_tips(qtbot):
    widget = AccumulatorsWidget()
    qtbot.addWidget(widget)
    value, inputs = _prem_allowed_gpt(_gpt_policy(), True)
    widget.load_data({
        "premiums_paid": 1500.0, "reg_prem": 1000.0, "additional_prem": 500.0,
        "prem_allowed_gpt": value, "prem_allowed_gpt_inputs": inputs, "gcv": {},
    })
    assert widget._fields["premiums_paid_label"].toolTip().endswith(
        "1,000.00 + 500.00 = 1,500.00")
    assert widget._fields["prem_allowed_gpt_label"].toolTip().endswith("= 10,000.00")
    widget.load_data({"prem_allowed_gpt": "N/A", "prem_allowed_gpt_inputs": None, "gcv": {}})
    assert widget._fields["prem_allowed_gpt_label"].toolTip().startswith("N/A")


def test_minimum_premium_tips(qtbot):
    widget = MinimumPremiumWidget()
    qtbot.addWidget(widget)
    widget.load_data(
        [{"TAR_TYP_CD": "MT", "TAR_PRM_AMT": 100.0}, {"TAR_TYP_CD": "MT", "TAR_PRM_AMT": 25.0}],
        [{"COV_PHA_NBR": 1, "COV_UNT_QTY": 250, "COV_VPU_AMT": 1000, "PLN_DES_SER_CD": "UL1"}],
        [{"COV_PHA_NBR": 1, "PRM_RT_TYP_CD": "M", "RNL_RT": 4800}],
    )
    assert widget._fields["annual_min_label"].toolTip().endswith("125.00 x 12 = 1,500.00")
    assert widget._fields["monthly_min_label"].toolTip().splitlines()[1:] == [
        "+ 100.00", "+ 25.00", "= 125.00"]
    assert widget.table.item(0, 2).toolTip().endswith("250 x 1,000 = 250,000.00")
    assert widget.table.item(0, 3).toolTip().endswith(
        "250,000.00 / 1,000 x 4.800 = 1,200.00")
