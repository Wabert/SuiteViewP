"""Segment 68 uses the physical source columns, including termination type 9."""

import re
import sqlite3

import pytest

from suiteview.audit.cyberlife_query import build_cyberlife_sql
from suiteview.audit.tabs.adv_tab import AdvTab
from suiteview.audit.tabs.benefits_tab import BenefitsTab
from suiteview.audit.tabs.coverages_tab import CoveragesTab
from suiteview.audit.tabs.display_tab import DisplayTab
from suiteview.audit.tabs.plancode_tab import PlancodeTab
from suiteview.audit.tabs.policy2_tab import Policy2Tab
from suiteview.audit.tabs.policy_tab import PolicyTab


@pytest.fixture
def tab(qtbot):
    widget = Policy2Tab()
    qtbot.addWidget(widget)
    return widget


def _select(tab, codes):
    tab.chk_change_seq.setChecked(True)
    for i in range(tab.list_change_seq.count()):
        item = tab.list_change_seq.item(i)
        item.setSelected(item.text().split(" - ", 1)[0] in codes)


def _build(tab, schema="DB2TAB", coverage_level=False):
    return build_cyberlife_sql(
        schema, "I", "25", policy_tab=PolicyTab(), display_tab=DisplayTab(),
        policy2_tab=tab, adv_tab=AdvTab(), coverages_tab=CoveragesTab(),
        plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab(),
        coverage_level=coverage_level,
    )


@pytest.mark.parametrize("schema", ["DB2TAB", "UNIT"])
@pytest.mark.parametrize("coverage_level", [False, True])
def test_change_segment_uses_verified_columns_and_complete_policy_key(tab, schema, coverage_level):
    _select(tab, {"4"})
    sql = _build(tab, schema, coverage_level)
    assert f"'9' AS CHG_TYP_CD FROM {schema}.LH_COV_TMN" in sql
    for table in ("LH_NT_COV_CHG", "LH_NT_COV_CHG_SCH", "LH_SPM_BNF_CHG_SCH"):
        assert f"TCH_POL_ID, CHG_TYP_CD FROM {schema}.{table}" in sql
    for key in ("CK_SYS_CD", "CK_CMP_CD", "TCH_POL_ID"):
        assert f"POLICY1.{key} = CHANGE_SEGMENT.{key}" in sql
    assert "CHANGE_SEGMENT.CHG_TYP_CD IN ('4')" in sql


@pytest.mark.parametrize("codes,expected", [
    ({"4"}, [("benefit", "4"), ("change", "4"), ("scheduled", "4")]),
    ({"9"}, [("termination", "9")]),
    ({"4", "9"}, [
        ("benefit", "4"), ("change", "4"), ("scheduled", "4"), ("termination", "9"),
    ]),
])
def test_generated_union_filters_real_codes_without_inventing_termination_column(tab, codes, expected):
    _select(tab, codes)
    sql = _build(tab, "main")
    cte = re.search(r"CHANGE_SEGMENT AS \(\n.*?\)", sql, re.DOTALL).group()
    predicate = re.search(r"CHANGE_SEGMENT.CHG_TYP_CD IN \([^)]+\)", sql).group()
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE LH_COV_TMN (CK_SYS_CD TEXT, CK_CMP_CD TEXT, TCH_POL_ID TEXT)")
        db.execute("INSERT INTO LH_COV_TMN VALUES ('I', '01', 'termination')")
        for table, name in (
            ("LH_NT_COV_CHG", "change"), ("LH_NT_COV_CHG_SCH", "scheduled"),
            ("LH_SPM_BNF_CHG_SCH", "benefit"),
        ):
            db.execute(
                f"CREATE TABLE {table} "
                "(CK_SYS_CD TEXT, CK_CMP_CD TEXT, TCH_POL_ID TEXT, CHG_TYP_CD TEXT)",
            )
            db.executemany(
                f"INSERT INTO {table} VALUES ('I', '01', ?, ?)",
                [(name, "4"), (name, "4"), (name, "3")],
            )
        rows = db.execute(
            f"WITH {cte} SELECT TCH_POL_ID, CHG_TYP_CD FROM CHANGE_SEGMENT "
            f"WHERE {predicate} ORDER BY TCH_POL_ID, CHG_TYP_CD",
        ).fetchall()
    assert rows == expected


def test_change_segment_selection_roundtrip_and_reset(tab, qtbot):
    _select(tab, {"4", "9"})
    restored = Policy2Tab()
    qtbot.addWidget(restored)
    restored.set_state(tab.get_state())
    assert _build(restored) == _build(tab)
    restored.set_state({})
    assert "CHANGE_SEGMENT" not in _build(restored)
    restored.chk_change_seq.setChecked(True)
    assert "CHANGE_SEGMENT" not in _build(restored)
    _select(restored, {"4"})
    restored.chk_change_seq.setChecked(False)
    assert "CHANGE_SEGMENT" not in _build(restored)
