import unittest

from PyQt6.QtWidgets import QApplication

from suiteview.audit.dynamic_query import DB2, SQL_SERVER, build_dynamic_sql, build_join_sql
from suiteview.audit.dynamic_group import DynamicQuery


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


if __name__ == "__main__":
    unittest.main()