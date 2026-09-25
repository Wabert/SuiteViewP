import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from suiteview.polview.config.policy_records import POLICY_RECORD_TABLES
from suiteview.polview.ui.tree_panel import PolicyRecordTreeWidget


_QT_APP = None
_SEGMENT_53_TABLES = [
    "LH_ASSET_RAL_SCH",
    "LH_ATM_TRS_SCH",
    "LH_AWD_PYE_ALC",
    "LH_AWD_SCH",
    "LH_DCA_SCH",
    "LH_MKT_TM_AUT",
    "LH_SWF_SCH",
]


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _record_item(tree, record_name):
    for index in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(index)
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("name") == record_name:
            return item
    return None


def test_segment53_translation_tables_are_registered():
    assert POLICY_RECORD_TABLES["Policy Record 53"] == _SEGMENT_53_TABLES


def test_segment53_tables_show_data_and_access_errors_from_presence_map():
    _app()
    presence = {table: False for table in _SEGMENT_53_TABLES}
    presence["LH_ATM_TRS_SCH"] = True
    presence["LH_SWF_SCH"] = "SQLCODE=-551: user does not have SELECT privilege"
    tree = PolicyRecordTreeWidget()
    tree.build_tables_tree(presence)

    record = _record_item(tree, "Policy Record 53")
    assert record is not None
    children = [
        record.child(index).data(0, Qt.ItemDataRole.UserRole)
        for index in range(record.childCount())
    ]
    assert {
        (child["type"], child["name"])
        for child in children
    } == {
        ("table", "LH_ATM_TRS_SCH"),
        ("table_error", "LH_SWF_SCH"),
    }

    error_item = next(
        record.child(index)
        for index in range(record.childCount())
        if record.child(index).data(
            0, Qt.ItemDataRole.UserRole
        )["type"] == "table_error"
    )
    assert "unavailable" in error_item.text(0)
    assert "SQLCODE=-551" in error_item.toolTip(0)
    assert tree._table_data_cache["LH_SWF_SCH"] is None

    snapshot = tree._save_tree_snapshot()
    tree._restore_tree_snapshot(snapshot)
    restored = _record_item(tree, "Policy Record 53")
    restored_error = next(
        restored.child(index)
        for index in range(restored.childCount())
        if restored.child(index).data(
            0, Qt.ItemDataRole.UserRole
        )["type"] == "table_error"
    )
    assert "SQLCODE=-551" in restored_error.toolTip(0)
