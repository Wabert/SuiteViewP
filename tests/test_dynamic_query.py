import unittest

from PyQt6.QtWidgets import QApplication

from suiteview.audit.dynamic_query import DB2, SQL_SERVER, build_dynamic_sql, build_join_sql
from suiteview.audit.dynamic_group import DynamicQuery
from suiteview.audit.field_picker_panel import FieldPickerPanel
from suiteview.audit.tabs.manual_sql_object_editor import ManualSqlObjectEditor


class DynamicQuerySqlTests(unittest.TestCase):
    def test_sql_server_distinct_comes_before_top(self):
        sql = build_dynamic_sql(
            "dbo.orion_pcr3_r",
            "25",
            [],
            select_columns=[{"column": "Co", "field_key": "dbo.orion_pcr3_r.Co", "aggregate": "display"}],
            distinct=True,
            dialect=SQL_SERVER,
        )

        self.assertTrue(sql.startswith("SELECT DISTINCT TOP 25 [Co]"))
        self.assertNotIn("TOP 25 DISTINCT", sql)

    def test_sql_server_join_distinct_comes_before_top(self):
        sql = build_join_sql(
            "dbo.orion_pcr3_r",
            "25",
            [],
            join_infos=[{
                "left_table": "dbo.orion_pcr3_r",
                "right_table": "dbo.other_table",
                "join_type": "INNER JOIN",
                "alias_left": "r",
                "alias_right": "o",
                "on_pairs": [("Pol", "Pol")],
                "extra_conditions": [],
            }],
            select_columns=[{"column": "Co", "field_key": "dbo.orion_pcr3_r.Co", "aggregate": "display"}],
            distinct=True,
            dialect=SQL_SERVER,
        )

        self.assertTrue(sql.startswith("SELECT DISTINCT TOP 25 r.[Co]"))
        self.assertNotIn("TOP 25 DISTINCT", sql)

    def test_db2_distinct_stays_after_select(self):
        sql = build_dynamic_sql(
            "DB2TAB.LH_BAS_POL",
            "25",
            [],
            select_columns=[{"column": "TCH_POL_ID", "field_key": "DB2TAB.LH_BAS_POL.TCH_POL_ID", "aggregate": "display"}],
            distinct=True,
            dialect=DB2,
        )

        self.assertTrue(sql.startswith('SELECT DISTINCT "TCH_POL_ID"'))
        self.assertTrue(sql.endswith("FETCH FIRST 25 ROWS ONLY"))


class DynamicQueryUiTests(unittest.TestCase):
    def test_sql_assist_shows_only_explicit_selected_tables(self):
        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        picker = FieldPickerPanel()
        try:
            picker._load_fields = lambda table: None
            picker.set_connection_options([("Work", "WORK_DSN")], "WORK_DSN")
            picker.set_group(
                "WORK_DSN",
                ["dbo.policy"],
                {},
                pinned_tables=["dbo.coverage"],
            )

            visible_tables = [
                picker.list_tables.item(row).data(0) or picker.list_tables.item(row).text()
                for row in range(picker.list_tables.count())
            ]

            self.assertEqual(visible_tables, ["dbo.policy", "dbo.coverage"])
        finally:
            picker.close()

    def test_manual_sql_save_persists_explicit_assist_tables(self):
        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        editor = ManualSqlObjectEditor()
        emitted = []
        editor.save_requested.connect(emitted.append)
        try:
            editor.set_connection_options([("Work", "WORK_DSN")], "WORK_DSN")
            editor.txt_name.setText("Claims Manual")
            editor.txt_sql.setPlainText("SELECT claim_id FROM dbo.claims")
            editor._result_columns = ["claim_id"]
            editor._column_types = {"claim_id": "INTEGER"}
            editor._on_assist_tables_changed(["dbo.claims", "dbo.policy"])

            editor._emit_save_request(save_as=False)

            self.assertEqual(emitted[0]["sql_assist"]["tables"], ["dbo.claims", "dbo.policy"])
            self.assertEqual(emitted[0]["sql_assist"]["pinned_tables"], ["dbo.claims", "dbo.policy"])
        finally:
            editor.close()

    def test_focus_initial_builder_state_uses_first_populated_tab(self):
        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        group = DynamicQuery(
            "▸ Visual Query",
            "CKPR_DSN",
            ["DB2TAB.LH_BAS_POL", "DB2TAB.LH_COV_PHA"],
        )
        try:
            second_tab = group._add_criteria_tab("Coverage")
            second_tab.add_field_auto(
                "DB2TAB.LH_COV_PHA",
                "POL_ID",
                "VARCHAR(20)",
                "Policy Id",
            )

            group.focus_initial_builder_state()

            self.assertIs(group.tab_widget.currentWidget(), second_tab)
            self.assertEqual(group.preferred_picker_table(), "DB2TAB.LH_COV_PHA")
        finally:
            group.close()

    def test_visual_join_canvas_feeds_existing_join_sql_shape(self):
        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        group = DynamicQuery(
            "▸ Visual Query",
            "CKPR_DSN",
            ["dbo.policy", "dbo.coverage"],
        )
        try:
            group.joins_tab.set_table_columns("dbo.policy", ["pol_id", "co"])
            group.joins_tab.set_table_columns("dbo.coverage", ["pol_id", "cov_no"])

            self.assertTrue(
                group.joins_tab.scene.add_link(
                    "dbo.policy", "pol_id", "dbo.coverage", "pol_id"))

            infos = group.joins_tab.get_join_infos()
            self.assertEqual(infos, [{
                "left_table": "dbo.policy",
                "right_table": "dbo.coverage",
                "join_type": "INNER JOIN",
                "alias_left": "",
                "alias_right": "",
                "on_pairs": [("pol_id", "pol_id")],
                "extra_conditions": [],
            }])

            sql = build_join_sql(
                "dbo.policy",
                "25",
                [],
                join_infos=infos,
                dialect=SQL_SERVER,
            )
            self.assertIn("INNER JOIN dbo.coverage", sql)
            self.assertIn("dbo.policy.[pol_id] = dbo.coverage.[pol_id]", sql)
        finally:
            group.close()


if __name__ == "__main__":
    unittest.main()