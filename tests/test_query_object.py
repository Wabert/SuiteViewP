import os
import tempfile
import unittest
from datetime import datetime

from suiteview.audit.qdefinition import QDefinition
from suiteview.audit.adhoc_source_intake import (
    dataframe_from_adhoc_metadata,
    promote_adhoc_source,
    promotion_metadata,
    query_adhoc_object,
    query_object_from_file,
)
from suiteview.audit.query_object import (
    OBJECT_KIND_ADHOC_SOURCE,
    OBJECT_KIND_CYBERLIFE,
    OBJECT_KIND_EXECUTABLE,
    OBJECT_KIND_MANUAL_SQL,
    OBJECT_KIND_VISUAL,
    SOURCE_STATUS_ADHOC,
    SOURCE_STATUS_REGISTERED,
    adhoc_source_object,
    cyberlife_query_object,
    manual_sql_query_object,
    object_from_qdefinition,
    object_from_saved_query,
    qdefinition_from_query_object,
)
from suiteview.audit.query_object_store import (
    delete_object,
    list_objects,
    load_object,
    object_exists,
    save_object,
)
from suiteview.audit.saved_query import SavedQuery
from suiteview.audit import qdef_store, saved_query_store


class QueryObjectTests(unittest.TestCase):
    def test_saved_query_converts_to_query_object(self):
        saved = SavedQuery(
            name="Premium Query",
            source_group="Premium Group",
            dsn="CKPR_DSN",
            tables=["DB2TAB.LH_BAS_POL", "DB2TAB.LH_COV_PHA"],
            sql="SELECT PolicyNumber FROM DB2TAB.LH_BAS_POL",
            result_columns=["PolicyNumber", "CompanyCode"],
            column_types={"PolicyNumber": "VARCHAR(20)"},
            created_at=datetime(2026, 5, 21, 9, 30),
        )

        obj = object_from_saved_query(saved)

        self.assertEqual(obj.name, "Premium Query")
        self.assertEqual(obj.kind, OBJECT_KIND_VISUAL)
        self.assertEqual(obj.source_design, "Premium Group")
        self.assertEqual(
            [s.name for s in obj.sources],
            ["DB2TAB.LH_BAS_POL", "DB2TAB.LH_COV_PHA"])
        self.assertEqual(obj.result_columns, ["PolicyNumber", "CompanyCode"])
        self.assertEqual(obj.fields[0].data_type, "VARCHAR(20)")

    def test_saved_query_config_populates_object_field_roles(self):
        saved = SavedQuery(
            name="Visual Designer Query",
            source_group="QDesigner Test",
            dsn="CKPR_DSN",
            tables=["DB2TAB.LH_BAS_POL", "DB2TAB.LH_COV_PHA"],
            sql="SELECT TCH_POL_ID FROM DB2TAB.LH_BAS_POL",
            result_columns=[],
            config={
                "select_tab": {
                    "display_all": False,
                    "fields": [
                        {
                            "field_key": "DB2TAB.LH_BAS_POL.TCH_POL_ID",
                            "display_name": "Policy Number",
                        }
                    ],
                },
                "tabs": [
                    {
                        "grid": {
                            "fields": {
                                "DB2TAB.LH_BAS_POL.CK_CMP_CD": {
                                    "label_text": "Company",
                                    "mode": 0,
                                }
                            }
                        }
                    }
                ],
                "joins_tab": {
                    "cards": [
                        {
                            "card_id": "join-1",
                            "left_table": "DB2TAB.LH_BAS_POL",
                            "right_table": "DB2TAB.LH_COV_PHA",
                            "on_conditions": [
                                {"left": "TCH_POL_ID", "right": "POL_ID"}
                            ],
                        }
                    ]
                },
            },
        )

        obj = object_from_saved_query(saved)
        roles = {field.name: field.role for field in obj.fields}

        self.assertEqual(roles["TCH_POL_ID"], "output")
        self.assertEqual(roles["CK_CMP_CD"], "input")
        self.assertEqual(roles["POL_ID"], "join_key")
        self.assertEqual(obj.result_columns, ["TCH_POL_ID", "POL_ID"])

    def test_qdefinition_converts_to_executable_query_object(self):
        qdef = QDefinition(
            name="TAI Snapshot",
            forge_name="Audit Forge",
            sql="SELECT Pol, Co FROM TAICession",
            dsn="UL_Rates",
            source_design="TAI Design",
            result_columns=["Pol", "Co"],
            column_types={"Pol": "VARCHAR(12)", "Co": "VARCHAR(2)"},
            tables=["TAICession"],
        )

        obj = object_from_qdefinition(qdef)

        self.assertEqual(obj.kind, OBJECT_KIND_EXECUTABLE)
        self.assertEqual(obj.dsn, "UL_Rates")
        self.assertEqual(obj.sources[0].name, "TAICession")
        self.assertEqual(obj.result_columns, ["Pol", "Co"])

    def test_query_object_adapts_to_qdefinition_shape(self):
        obj = cyberlife_query_object(
            "Cyberlife For Forge",
            sql="SELECT TCH_POL_ID FROM DB2TAB.LH_BAS_POL",
            dsn="CKPR_DSN",
            region="CKPR",
            system_code="I",
            criteria={},
            result_columns=["TCH_POL_ID"],
            column_types={"TCH_POL_ID": "VARCHAR(20)"},
        )

        qdef = qdefinition_from_query_object(obj)

        self.assertEqual(qdef.name, "Cyberlife For Forge")
        self.assertEqual(qdef.sql, "SELECT TCH_POL_ID FROM DB2TAB.LH_BAS_POL")
        self.assertEqual(qdef.dsn, "CKPR_DSN")
        self.assertEqual(qdef.result_columns, ["TCH_POL_ID"])
        self.assertEqual(qdef.column_types["TCH_POL_ID"], "VARCHAR(20)")

    def test_manual_sql_query_object_captures_output_schema(self):
        obj = manual_sql_query_object(
            "Manual Claims SQL",
            sql="SELECT CLAIM_ID, AMOUNT FROM CLAIMS",
            dsn="CLAIMS_DSN",
            result_columns=["CLAIM_ID", "AMOUNT"],
            column_types={"CLAIM_ID": "TEXT", "AMOUNT": "DECIMAL"},
        )

        self.assertEqual(obj.kind, OBJECT_KIND_MANUAL_SQL)
        self.assertEqual(obj.sql, "SELECT CLAIM_ID, AMOUNT FROM CLAIMS")
        self.assertEqual(obj.dsn, "CLAIMS_DSN")
        self.assertEqual(obj.result_columns, ["CLAIM_ID", "AMOUNT"])
        self.assertEqual(obj.fields[1].data_type, "DECIMAL")

    def test_cyberlife_query_object_marks_common_join_keys(self):
        obj = cyberlife_query_object(
            "Cyberlife Base Extract",
            sql="SELECT * FROM policy",
            dsn="CKPR_DSN",
            region="CKPR",
            system_code="I",
            criteria={"max_count": "25"},
            result_columns=["TCH_POL_ID", "CK_CMP_CD", "CurrentDuration"],
            column_types={"CurrentDuration": "INTEGER"},
        )

        roles = {field.name: field.role for field in obj.fields}
        self.assertEqual(obj.kind, OBJECT_KIND_CYBERLIFE)
        self.assertEqual(obj.dialect, "DB2")
        self.assertEqual(obj.sources[0].source_type, "specialized_builder")
        self.assertEqual(roles["TCH_POL_ID"], "join_key")
        self.assertEqual(roles["CK_CMP_CD"], "join_key")
        self.assertEqual(roles["CurrentDuration"], "output")

    def test_adhoc_source_object_can_remain_temporary(self):
        obj = adhoc_source_object(
            "producer_map_may.csv",
            source_type="csv",
            metadata={"path": "C:/temp/producer_map_may.csv"},
            columns=["producer_id", "territory"],
            column_types={"producer_id": "TEXT"},
        )

        self.assertEqual(obj.kind, OBJECT_KIND_ADHOC_SOURCE)
        self.assertEqual(obj.metadata_status, SOURCE_STATUS_ADHOC)
        self.assertEqual(obj.sources[0].status, SOURCE_STATUS_ADHOC)
        self.assertEqual(obj.result_columns, ["producer_id", "territory"])

    def test_csv_file_becomes_adhoc_query_object(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
            handle.write("Policy,Amount,RunDate\n")
            handle.write("P1,123.45,2026-05-21\n")
            handle.write("P2,67.89,2026-05-22\n")
            csv_path = handle.name

        try:
            obj = query_object_from_file(csv_path, name="Loose Premiums")
        finally:
            os.unlink(csv_path)

        self.assertEqual(obj.name, "Loose Premiums")
        self.assertEqual(obj.kind, OBJECT_KIND_ADHOC_SOURCE)
        self.assertEqual(obj.sources[0].source_type, "csv")
        self.assertEqual(obj.result_columns, ["Policy", "Amount", "RunDate"])
        types = {field.name: field.data_type for field in obj.fields}
        self.assertEqual(types["Policy"], "TEXT")
        self.assertEqual(types["Amount"], "DECIMAL")
        self.assertEqual(types["RunDate"], "DATE")

    def test_adhoc_query_object_adapter_carries_file_metadata(self):
        obj = adhoc_source_object(
            "Loose Premiums",
            source_type="csv",
            metadata={"path": "C:/temp/loose_premiums.csv"},
            columns=["Policy", "Amount"],
            column_types={"Policy": "TEXT", "Amount": "DECIMAL"},
        )

        qdef = qdefinition_from_query_object(obj)

        self.assertEqual(qdef.query_object_kind, OBJECT_KIND_ADHOC_SOURCE)
        self.assertEqual(qdef.query_object_source_metadata["path"], "C:/temp/loose_premiums.csv")
        self.assertEqual(qdef.source_design, "csv")

    def test_adhoc_csv_metadata_loads_dataframe(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
            handle.write("Policy,Amount,Ignored\n")
            handle.write("P1,123.45,x\n")
            csv_path = handle.name

        try:
            df = dataframe_from_adhoc_metadata(
                "csv",
                {"path": csv_path},
                columns=["Policy", "Amount"],
            )
        finally:
            os.unlink(csv_path)

        self.assertEqual(list(df.columns), ["Policy", "Amount"])
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["Policy"], "P1")

    def test_query_adhoc_object_filters_file_rows(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
            handle.write("Policy,Amount,Region\n")
            handle.write("P1,123.45,East\n")
            handle.write("P2,67.89,West\n")
            csv_path = handle.name

        try:
            obj = query_object_from_file(csv_path, name="Loose Premiums")
            df = query_adhoc_object(
                obj,
                columns=["Policy", "Amount"],
                filter_expr="Amount > 100",
                limit=10,
            )
        finally:
            os.unlink(csv_path)

        self.assertEqual(list(df.columns), ["Policy", "Amount"])
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["Policy"], "P1")

    def test_adhoc_promotion_metadata_captures_schema(self):
        obj = adhoc_source_object(
            "Manual Extract",
            source_type="csv",
            metadata={"path": "manual.csv"},
            columns=["Policy", "Amount"],
            column_types={"Policy": "TEXT", "Amount": "DECIMAL"},
        )

        metadata = promotion_metadata(obj)

        self.assertEqual(metadata["name"], "Manual Extract")
        self.assertEqual(metadata["source_type"], "csv")
        self.assertEqual(metadata["source_metadata"]["path"], "manual.csv")
        self.assertEqual(metadata["columns"][1]["data_type"], "DECIMAL")

    def test_promote_adhoc_source_marks_object_registered(self):
        obj = adhoc_source_object(
            "Manual Extract",
            source_type="csv",
            metadata={"path": "manual.csv", "promoted": False},
            columns=["Policy", "Amount"],
            column_types={"Policy": "TEXT", "Amount": "DECIMAL"},
        )

        promoted = promote_adhoc_source(obj)

        self.assertEqual(promoted.metadata_status, SOURCE_STATUS_REGISTERED)
        self.assertEqual(promoted.sources[0].status, SOURCE_STATUS_REGISTERED)
        self.assertTrue(promoted.sources[0].metadata["promoted"])
        self.assertEqual(promoted.config["promotion"]["columns"][0]["name"], "Policy")

    def test_query_object_store_round_trip(self):
        old_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_dir
            obj = adhoc_source_object(
                "monthly_mapping.csv",
                source_type="csv",
                metadata={"path_pattern": "monthly_mapping_*.csv"},
                columns=["code", "description"],
            )

            save_object(obj)

            self.assertTrue(object_exists("monthly_mapping.csv"))
            loaded = load_object("monthly_mapping.csv")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.name, "monthly_mapping.csv")
            self.assertEqual(
                loaded.sources[0].metadata["path_pattern"],
                "monthly_mapping_*.csv")
            self.assertEqual([o.name for o in list_objects()], ["monthly_mapping.csv"])

            delete_object("monthly_mapping.csv")
            self.assertFalse(object_exists("monthly_mapping.csv"))

        if old_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_dir

    def test_query_object_editable_metadata_round_trip(self):
        old_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_dir
            obj = manual_sql_query_object(
                "Editable Manual Object",
                sql="SELECT POLICY, COMPANY FROM WORK",
                dsn="WORK_DSN",
                result_columns=["POLICY", "COMPANY"],
                column_types={"POLICY": "TEXT", "COMPANY": "CHAR(2)"},
            )
            obj.description = "Monthly workbench extract"
            obj.tags = ["monthly", "workbench"]
            obj.fields[0].role = "join_key"
            obj.fields[0].display_name = "Policy Number"

            save_object(obj)

            loaded = load_object("Editable Manual Object")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.description, "Monthly workbench extract")
            self.assertEqual(loaded.tags, ["monthly", "workbench"])
            self.assertEqual(loaded.fields[0].role, "join_key")
            self.assertEqual(loaded.fields[0].display_name, "Policy Number")

        if old_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_dir

    def test_saved_query_store_publishes_query_object(self):
        old_obj_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        old_queries_dir = saved_query_store._QUERIES_DIR
        with tempfile.TemporaryDirectory() as tmp_objects, tempfile.TemporaryDirectory() as tmp_queries:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_objects
            saved_query_store._QUERIES_DIR = saved_query_store.Path(tmp_queries)
            saved = SavedQuery(
                name="Published Query",
                dsn="CKPR_DSN",
                tables=["DB2TAB.LH_BAS_POL"],
                result_columns=["PolicyNumber"],
            )

            saved_query_store.save_query(saved)

            published = load_object("Published Query")
            self.assertIsNotNone(published)
            self.assertEqual(published.name, "Published Query")
            self.assertEqual(published.result_columns, ["PolicyNumber"])

            saved_query_store.delete_query("Published Query")
            self.assertFalse(object_exists("Published Query"))

        saved_query_store._QUERIES_DIR = old_queries_dir
        if old_obj_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_obj_dir

    def test_qdef_store_publishes_query_object(self):
        old_obj_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        old_qdefs_dir = qdef_store._QDEFS_DIR
        with tempfile.TemporaryDirectory() as tmp_objects, tempfile.TemporaryDirectory() as tmp_qdefs:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_objects
            qdef_store._QDEFS_DIR = qdef_store.Path(tmp_qdefs)
            qdef = QDefinition(
                name="Published QDef",
                forge_name="Forge A",
                sql="SELECT Pol FROM TAICession",
                dsn="UL_Rates",
                result_columns=["Pol"],
                tables=["TAICession"],
            )

            qdef_store.save_qdef(qdef)

            published = load_object("Published QDef")
            self.assertIsNotNone(published)
            self.assertEqual(published.kind, OBJECT_KIND_EXECUTABLE)
            self.assertEqual(published.result_columns, ["Pol"])

            qdef_store.delete_qdef("Published QDef", forge_name="Forge A")
            self.assertFalse(object_exists("Published QDef"))

        qdef_store._QDEFS_DIR = old_qdefs_dir
        if old_obj_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_obj_dir


if __name__ == "__main__":
    unittest.main()