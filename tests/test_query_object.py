import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

import pandas as pd
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QListWidgetItem, QMessageBox, QPushButton, QWidget

from suiteview.audit.qdefinition import QDefinition
from suiteview.audit.adhoc_source_intake import (
    dataframe_from_adhoc_metadata,
    delimited_text_spec,
    fixed_width_spec,
    promote_adhoc_source,
    promotion_metadata,
    query_adhoc_object,
    query_object_from_file,
    replace_adhoc_source_path,
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
    fields_from_columns,
    manual_sql_query_object,
    object_from_qdefinition,
    object_from_saved_query,
    qdefinition_from_query_object,
)
from suiteview.audit.query_object_store import (
    copy_object,
    delete_object,
    is_forge_owned,
    list_objects,
    load_object,
    load_object_by_id,
    object_exists,
    rename_object,
    restore_saved_visual_design,
    save_object,
)
from suiteview.audit.query_object_viewer_window import _display_dsn_for_definition, _display_dsn_for_object, _limited_preview_sql, _preview_dialect_for_object
from suiteview.audit.query_object_viewer_window import QueryObjectViewerWindow
from suiteview.audit.saved_query import SavedQuery
from suiteview.audit.tabs.results_tab import ResultsTab
from suiteview.audit import qdef_store, saved_query_store
from suiteview.audit.dataforge.query_field_picker import QueryFieldPicker, _group_query_objects_for_selector, _load_query_source
from suiteview.audit.dataforge import dataforge_store
from suiteview.audit.dataforge.dataforge_model import DataForge, DataForgeSource


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

    def test_visual_query_field_can_be_output_and_input(self):
        saved = SavedQuery(
            name="Visual Input Output Query",
            source_group="QDesigner Test",
            dsn="CKPR_DSN",
            tables=["DB2TAB.LH_BAS_POL"],
            sql="SELECT TCH_POL_ID FROM DB2TAB.LH_BAS_POL",
            result_columns=["TCH_POL_ID"],
            config={
                "tabs": [
                    {
                        "grid": {
                            "fields": {
                                "DB2TAB.LH_BAS_POL.TCH_POL_ID": {
                                    "label_text": "Policy Number",
                                    "mode": 0,
                                }
                            }
                        }
                    }
                ],
            },
        )

        obj = object_from_saved_query(saved)
        roles = [field.role for field in obj.fields if field.name == "TCH_POL_ID"]

        self.assertIn("output", roles)
        self.assertIn("input", roles)

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

    def test_preview_sql_uses_db2_limit_syntax(self):
        preview_sql = _limited_preview_sql(
            "SELECT TCH_POL_ID FROM DB2TAB.LH_BAS_POL",
            25,
            "DB2",
        )

        self.assertEqual(
            preview_sql,
            "SELECT TCH_POL_ID FROM DB2TAB.LH_BAS_POL FETCH FIRST 25 ROWS ONLY",
        )

    def test_preview_sql_keeps_db2_cte_at_top_level(self):
        preview_sql = _limited_preview_sql(
            "WITH COVERAGE1 AS (SELECT * FROM DB2TAB.LH_COV_PHA)\n"
            "SELECT * FROM COVERAGE1",
            25,
            "DB2",
        )

        self.assertTrue(preview_sql.startswith("WITH COVERAGE1 AS"))
        self.assertNotIn("SELECT * FROM (", preview_sql)
        self.assertTrue(preview_sql.endswith("FETCH FIRST 25 ROWS ONLY"))

    def test_preview_sql_inserts_db2_limit_before_isolation_clause(self):
        preview_sql = _limited_preview_sql(
            "SELECT TCH_POL_ID FROM DB2TAB.LH_BAS_POL WITH UR",
            25,
            "DB2",
        )

        self.assertEqual(
            preview_sql,
            "SELECT TCH_POL_ID FROM DB2TAB.LH_BAS_POL FETCH FIRST 25 ROWS ONLY WITH UR",
        )

    def test_preview_sql_uses_sql_server_limit_syntax(self):
        preview_sql = _limited_preview_sql(
            "SELECT Pol, Co FROM TAICession",
            25,
            "SQL_SERVER",
        )

        self.assertTrue(preview_sql.startswith("SELECT TOP 25 * FROM ("))
        self.assertNotIn("FETCH FIRST", preview_sql)

    def test_preview_dialect_prefers_detected_dsn_dialect(self):
        obj = manual_sql_query_object(
            "Manual SQL Server Object",
            sql="SELECT Pol FROM TAICession",
            dsn="UL_Rates",
            result_columns=["Pol"],
        )
        obj.dialect = "DB2"

        with patch("suiteview.audit.query_object_viewer_window.detect_dialect", return_value="SQL_SERVER"):
            self.assertEqual(_preview_dialect_for_object(obj), "SQL_SERVER")

    def test_preview_dialect_falls_back_to_saved_dialect(self):
        obj = manual_sql_query_object(
            "Manual DB2 Object",
            sql="SELECT TCH_POL_ID FROM DB2TAB.LH_BAS_POL",
            dsn="CKPR_DSN",
            result_columns=["TCH_POL_ID"],
        )
        obj.dialect = "DB2"

        with patch("suiteview.audit.query_object_viewer_window.detect_dialect", return_value="UNKNOWN"):
            self.assertEqual(_preview_dialect_for_object(obj), "DB2")

    def test_query_object_viewer_builds_data_source_index(self):
        sql_obj = manual_sql_query_object(
            "Rates SQL",
            sql="SELECT Plan FROM Rates",
            dsn="UL_Rates",
            result_columns=["Plan"],
        )
        file_obj = adhoc_source_object(
            "Claims Source",
            source_type="csv",
            metadata={"path": r"C:\temp\claims.csv"},
            columns=["claim_id"],
        )
        browser = QueryObjectViewerWindow.__new__(QueryObjectViewerWindow)

        index = browser._build_data_source_index([sql_obj, file_obj])

        self.assertIn("ul_rates", index["odbc"])
        self.assertEqual(index["odbc"]["ul_rates"]["label"], "UL_Rates")
        self.assertEqual([obj.name for obj in index["odbc"]["ul_rates"]["objects"]], ["Rates SQL"])
        file_entry = next(iter(index["files"].values()))
        self.assertEqual(file_entry["label"], "claims.csv")
        self.assertEqual(file_entry["path"], r"C:\temp\claims.csv")
        self.assertEqual([obj.name for obj in file_entry["objects"]], ["Claims Source"])

    def test_odbc_detail_rows_mask_sensitive_setup_values(self):
        with patch(
            "suiteview.audit.query_object_viewer_window.get_dsn_details",
            return_value={
                "DSN": "UL_Rates",
                "Driver": "ODBC Driver 17 for SQL Server",
                "Server": "RatesServer",
                "Password": "secret",
            },
        ), patch("suiteview.audit.query_object_viewer_window.detect_dialect", return_value="SQL_SERVER"):
            rows = QueryObjectViewerWindow._odbc_detail_rows("UL_Rates")

        values = {key: value for key, value in rows}
        self.assertEqual(values["Server"], "RatesServer")
        self.assertEqual(values["Password"], "(hidden)")
        self.assertEqual(values["Dialect"], "SQL_SERVER")

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
        self.assertTrue(QueryObjectViewerWindow._can_open_in_builder(obj))
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

    def test_adhoc_sources_seed_into_file_sources_group(self):
        # Kind-based browser grouping was replaced by user-defined Query
        # Groups (DATAFORGE_DESIGN §8); the equivalent guarantee is the
        # organizer's first-run seed, which files adhoc sources under a
        # "File Sources" group.
        from suiteview.audit.query_organizer import _SEED_GROUPS

        seed_map = dict(_SEED_GROUPS)
        self.assertEqual(seed_map.get("adhoc_source"), "File Sources")

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

    def test_adhoc_qdefinition_round_trip_preserves_file_source_kind(self):
        obj = adhoc_source_object(
            "Loose Premiums [Forge]",
            source_type="csv",
            metadata={"path": "C:/temp/loose_premiums.csv"},
            columns=["Policy", "Amount"],
            column_types={"Policy": "TEXT", "Amount": "DECIMAL"},
        )
        obj.config["dataforge"] = {
            "forge_name": "Forge",
            "source_name": "Loose Premiums",
        }

        qdef = QDefinition.from_dict(qdefinition_from_query_object(obj).to_dict())
        restored = object_from_qdefinition(qdef)

        self.assertEqual(restored.kind, OBJECT_KIND_ADHOC_SOURCE)
        self.assertEqual(restored.sources[0].source_type, "csv")
        self.assertEqual(restored.sources[0].metadata["path"], "C:/temp/loose_premiums.csv")
        self.assertEqual(restored.config["dataforge"]["source_name"], "Loose Premiums")

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

    def test_delimited_text_file_becomes_adhoc_query_object(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
            handle.write("Policy|Amount|RunDate\n")
            handle.write("P1|123.45|2026-05-21\n")
            handle.write("P2|67.89|2026-05-22\n")
            text_path = handle.name

        try:
            obj = query_object_from_file(
                text_path,
                name="Delimited Claims",
                format_spec=delimited_text_spec(delimiter="|"),
            )
            df = dataframe_from_adhoc_metadata(
                obj.sources[0].source_type,
                obj.sources[0].metadata,
                columns=["Policy", "Amount"],
            )
        finally:
            os.unlink(text_path)

        self.assertEqual(obj.sources[0].source_type, "csv")
        self.assertEqual(obj.sources[0].metadata["format"], "delimited")
        self.assertEqual(obj.sources[0].metadata["delimiter"], "|")
        self.assertEqual(obj.result_columns, ["Policy", "Amount", "RunDate"])
        self.assertEqual(list(df.columns), ["Policy", "Amount"])
        self.assertEqual(len(df), 2)

    def test_no_header_delimited_text_uses_assigned_column_names(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
            handle.write("P1,123.45,East\n")
            handle.write("P2,67.89,West\n")
            text_path = handle.name

        try:
            obj = query_object_from_file(
                text_path,
                name="No Header Claims",
                format_spec=delimited_text_spec(
                    delimiter=",",
                    has_header=False,
                    column_names=["Policy", "Amount", "Region"],
                ),
            )
            df = query_adhoc_object(
                obj,
                columns=["Policy", "Region"],
                filter_expr="Amount > 100",
                limit=10,
            )
        finally:
            os.unlink(text_path)

        self.assertEqual(obj.result_columns, ["Policy", "Amount", "Region"])
        self.assertEqual(obj.sources[0].metadata["column_names"], ["Policy", "Amount", "Region"])
        self.assertEqual(list(df.columns), ["Policy", "Region"])
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["Policy"], "P1")

    def test_file_source_path_can_change_without_changing_columns(self):
        first_path = ""
        second_path = ""
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as first:
            first.write("P1,123.45,East\n")
            first_path = first.name
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as second:
            second.write("P9,999.00,West\n")
            second_path = second.name

        try:
            obj = query_object_from_file(
                first_path,
                name="Replaceable Claims",
                format_spec=delimited_text_spec(
                    delimiter=",",
                    has_header=False,
                    column_names=["Policy", "Amount", "Region"],
                ),
            )
            original_columns = obj.result_columns[:]
            replace_adhoc_source_path(obj, second_path)
            df = query_adhoc_object(obj, columns=["Policy", "Amount"], limit=10)
        finally:
            if first_path:
                os.unlink(first_path)
            if second_path:
                os.unlink(second_path)

        self.assertEqual(obj.result_columns, original_columns)
        self.assertEqual(obj.sources[0].metadata["path"], second_path)
        self.assertEqual(obj.sources[0].metadata["column_names"], ["Policy", "Amount", "Region"])
        self.assertEqual(df.iloc[0]["Policy"], "P9")
        self.assertEqual(float(df.iloc[0]["Amount"]), 999.0)

    def test_fixed_width_text_file_becomes_adhoc_query_object(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
            handle.write("P00011234520260521\n")
            handle.write("P00020006720260522\n")
            text_path = handle.name

        spec = fixed_width_spec([
            {"name": "Policy", "start": 1, "width": 5},
            {"name": "Amount", "start": 6, "width": 5},
            {"name": "RunDate", "start": 11, "width": 8},
        ])
        try:
            obj = query_object_from_file(text_path, name="Fixed Claims", format_spec=spec)
            df = query_adhoc_object(obj, columns=["Policy", "Amount"], limit=10)
        finally:
            os.unlink(text_path)

        self.assertEqual(obj.sources[0].source_type, "fixed_width")
        self.assertEqual(obj.sources[0].metadata["format"], "fixed_width")
        self.assertEqual(obj.result_columns, ["Policy", "Amount", "RunDate"])
        self.assertEqual(list(df.columns), ["Policy", "Amount"])
        self.assertEqual(df.iloc[0]["Policy"], "P0001")
        self.assertEqual(int(df.iloc[1]["Amount"]), 67)

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

    def test_query_object_store_copies_object_with_new_name(self):
        old_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_dir
            original = adhoc_source_object(
                "Claims Source",
                source_type="csv",
                metadata={"path": "claims.txt", "column_names": ["Policy", "Claim"]},
                columns=["Policy", "Claim"],
            )
            original.description = "Original file source"

            save_object(original)
            copied = copy_object("Claims Source", "Claims Source Copy")
            loaded_original = load_object("Claims Source")
            loaded_copy = load_object("Claims Source Copy")

            self.assertIsNotNone(loaded_original)
            self.assertIsNotNone(loaded_copy)
            self.assertEqual(copied.name, "Claims Source Copy")
            self.assertEqual(loaded_copy.description, "Original file source")
            self.assertEqual(loaded_copy.sources[0].metadata["column_names"], ["Policy", "Claim"])
            self.assertEqual(loaded_copy.result_columns, ["Policy", "Claim"])
            self.assertNotEqual(loaded_original.created_at, loaded_copy.created_at)

        if old_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_dir

    def test_visual_query_object_copy_copies_saved_design(self):
        old_obj_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        old_queries_dir = saved_query_store._QUERIES_DIR
        with tempfile.TemporaryDirectory() as tmp_objects, tempfile.TemporaryDirectory() as tmp_queries:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_objects
            saved_query_store._QUERIES_DIR = saved_query_store.Path(tmp_queries)
            saved = SavedQuery(
                name="Visual Premium Query",
                source_group="Premium Group",
                dsn="CKPR_DSN",
                tables=["DB2TAB.LH_BAS_POL"],
                sql="SELECT TCH_POL_ID FROM DB2TAB.LH_BAS_POL",
                result_columns=["TCH_POL_ID"],
            )
            saved_query_store.save_query(saved)

            copied = copy_object("Visual Premium Query", "Visual Premium Query Copy")
            copied_design = saved_query_store.load_query("Visual Premium Query Copy")

            self.assertEqual(copied.name, "Visual Premium Query Copy")
            self.assertIsNotNone(copied_design)
            self.assertEqual(copied_design.name, "Visual Premium Query Copy")
            self.assertEqual(copied_design.sql, saved.sql)
            self.assertEqual(copied_design.config, saved.config)

        saved_query_store._QUERIES_DIR = old_queries_dir
        if old_obj_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_obj_dir

    def test_visual_query_object_restores_missing_saved_design(self):
        old_obj_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        old_queries_dir = saved_query_store._QUERIES_DIR
        with tempfile.TemporaryDirectory() as tmp_objects, tempfile.TemporaryDirectory() as tmp_queries:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_objects
            saved_query_store._QUERIES_DIR = saved_query_store.Path(tmp_queries)
            obj = object_from_saved_query(SavedQuery(
                name="Copied Before Fix",
                source_group="Premium Group",
                dsn="CKPR_DSN",
                tables=["DB2TAB.LH_BAS_POL"],
                sql="SELECT TCH_POL_ID FROM DB2TAB.LH_BAS_POL",
                result_columns=["TCH_POL_ID"],
                config={"select_tab": {"display_all": False}},
            ))
            obj.description = "Keep object metadata"
            save_object(obj)

            restored = restore_saved_visual_design(obj)
            loaded_object = load_object("Copied Before Fix")

            self.assertIsNotNone(restored)
            self.assertEqual(restored.name, "Copied Before Fix")
            self.assertEqual(restored.config, obj.config)
            self.assertEqual(restored.sql, obj.sql)
            self.assertEqual(loaded_object.description, "Keep object metadata")

        saved_query_store._QUERIES_DIR = old_queries_dir
        if old_obj_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_obj_dir

    def test_is_forge_owned_predicate(self):
        normal = manual_sql_query_object(
            "Claims", sql="SELECT 1", dsn="D", result_columns=["a"])
        forge_copy = manual_sql_query_object(
            "Claims [F]", sql="SELECT 1", dsn="D", result_columns=["a"])
        forge_copy.config["dataforge"] = {"forge_name": "F", "source_name": "Claims"}
        self.assertFalse(is_forge_owned(normal))
        self.assertTrue(is_forge_owned(forge_copy))
        # An empty/blank forge_name is not ownership.
        forge_copy.config["dataforge"] = {"forge_name": "", "source_name": "Claims"}
        self.assertFalse(is_forge_owned(forge_copy))

    def test_rename_object_manual_sql_sticks(self):
        old_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_dir
            obj = manual_sql_query_object(
                "Old Manual", sql="SELECT 1", dsn="D", result_columns=["a"])
            save_object(obj)
            original_id = obj.id

            rename_object(obj, "New Manual")

            self.assertEqual(obj.id, original_id)  # id preserved, no fork
            self.assertIsNone(load_object("Old Manual"))
            renamed = load_object("New Manual")
            self.assertIsNotNone(renamed)
            self.assertEqual(renamed.id, original_id)
            self.assertEqual(len(list_objects()), 1)
        if old_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_dir

    def test_rename_object_visual_sticks_after_design_resave(self):
        old_obj_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        old_queries_dir = saved_query_store._QUERIES_DIR
        with tempfile.TemporaryDirectory() as tmp_objects, tempfile.TemporaryDirectory() as tmp_queries:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_objects
            saved_query_store._QUERIES_DIR = saved_query_store.Path(tmp_queries)
            saved_query_store.save_query(SavedQuery(
                name="Old Visual",
                source_group="G",
                dsn="CKPR_DSN",
                tables=["DB2TAB.LH_BAS_POL"],
                sql="SELECT TCH_POL_ID FROM DB2TAB.LH_BAS_POL",
                result_columns=["TCH_POL_ID"],
            ))
            obj = load_object("Old Visual")
            original_id = obj.id

            rename_object(obj, "New Visual")

            # Object moved, id stable, old name gone.
            self.assertEqual(obj.id, original_id)
            self.assertIsNone(load_object("Old Visual"))
            self.assertEqual(load_object("New Visual").id, original_id)
            # Design snapshot moved; old-name design file is gone.
            self.assertFalse(saved_query_store.query_exists("Old Visual"))
            self.assertTrue(saved_query_store.query_exists("New Visual"))

            # The bug: re-saving the (now new-name) design must NOT resurrect the
            # old name. Saving the design republishes a QueryObject — it should
            # collapse into the one renamed object, not fork a stale "Old Visual".
            saved_query_store.save_query(saved_query_store.load_query("New Visual"))
            self.assertIsNone(load_object("Old Visual"))
            names = sorted(o.name for o in list_objects())
            self.assertEqual(names, ["New Visual"])

        saved_query_store._QUERIES_DIR = old_queries_dir
        if old_obj_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_obj_dir

    def test_queries_dialog_excludes_forge_owned_copies(self):
        from suiteview.audit.dataforge.queries_dialog import _list_query_sources

        old_obj_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        old_qdefs_dir = qdef_store._QDEFS_DIR
        old_queries_dir = saved_query_store._QUERIES_DIR
        with tempfile.TemporaryDirectory() as tmp_objects, tempfile.TemporaryDirectory() as tmp_qdefs, tempfile.TemporaryDirectory() as tmp_queries:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_objects
            qdef_store._QDEFS_DIR = qdef_store.Path(tmp_qdefs)
            saved_query_store._QUERIES_DIR = saved_query_store.Path(tmp_queries)

            standalone = manual_sql_query_object(
                "Claims", sql="SELECT 1", dsn="D", result_columns=["a"])
            forge_copy = manual_sql_query_object(
                "Claims [F]", sql="SELECT 1", dsn="D", result_columns=["a"])
            forge_copy.config["dataforge"] = {"forge_name": "F", "source_name": "Claims"}
            save_object(standalone)
            save_object(forge_copy)

            names = {qd.name for qd in _list_query_sources(forge_name="F")}
            self.assertIn("Claims", names)
            self.assertNotIn("Claims [F]", names)

        qdef_store._QDEFS_DIR = old_qdefs_dir
        saved_query_store._QUERIES_DIR = old_queries_dir
        if old_obj_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_obj_dir

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

    def test_query_object_viewer_initial_selection_populates_detail(self):
        old_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        old_data_sources_dir = os.environ.get("SUITEVIEW_DATA_SOURCES_DIR")
        old_forges_dir = dataforge_store._FORGES_DIR
        with tempfile.TemporaryDirectory() as tmp_dir, \
                tempfile.TemporaryDirectory() as tmp_forges, \
                tempfile.TemporaryDirectory() as tmp_data_sources:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_dir
            # Isolate registered data sources so the ODBC count is deterministic
            # regardless of what's registered on the machine running the test.
            os.environ["SUITEVIEW_DATA_SOURCES_DIR"] = tmp_data_sources
            dataforge_store._FORGES_DIR = dataforge_store.Path(tmp_forges)
            save_object(manual_sql_query_object(
                "Initial Viewer Object",
                sql="SELECT POLICY FROM WORK",
                dsn="WORK_DSN",
                result_columns=["POLICY"],
            ))

            app = QApplication.instance()
            if app is None:
                app = QApplication([])

            window = QueryObjectViewerWindow()
            try:
                app.processEvents()

                # Browser items show the datasource tag (design §8).
                self.assertEqual(
                    [window.left_tabs.tabText(index) for index in range(window.left_tabs.count())],
                    ["Queries", "Data Sources", "Tables", "Registry"],
                )
                self.assertTrue(hasattr(window, "edit_search"))
                self.assertTrue(hasattr(window, "edit_source_search"))
                self.assertFalse(hasattr(window, "btn_expand_all"))
                self.assertFalse(hasattr(window, "btn_collapse_all"))
                self.assertFalse(hasattr(window, "btn_group_new"))
                self.assertFalse(hasattr(window, "btn_group_rename"))
                self.assertFalse(hasattr(window, "btn_group_color"))
                self.assertFalse(hasattr(window, "btn_group_delete"))
                self.assertEqual(window.tree.currentItem().text(0),
                                 "Initial Viewer Object  [WORK_DSN]")
                self.assertEqual(window.lbl_canvas_title.text(),
                                 "Manual SQL Objects: Initial Viewer Object")
                self.assertEqual(window.lbl_name.text(), "Initial Viewer Object")
                self.assertEqual(window.source_tree.topLevelItem(0).text(0), "ODBC (1)")
                odbc_item = window.source_tree.topLevelItem(0).child(0)
                self.assertEqual(odbc_item.text(0), "WORK_DSN")
                self.assertEqual(odbc_item.childCount(), 0)

                window.left_tabs.setCurrentIndex(1)
                app.processEvents()
                odbc_item = window.source_tree.topLevelItem(0).child(0)
                window.source_tree.setCurrentItem(odbc_item)
                app.processEvents()
                self.assertEqual(window.lbl_canvas_title.text(), "Data Sources: WORK_DSN")
            finally:
                window.close()

        dataforge_store._FORGES_DIR = old_forges_dir
        if old_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_dir
        if old_data_sources_dir is None:
            os.environ.pop("SUITEVIEW_DATA_SOURCES_DIR", None)
        else:
            os.environ["SUITEVIEW_DATA_SOURCES_DIR"] = old_data_sources_dir

    def test_query_object_viewer_file_source_keeps_left_width_and_dark_badge(self):
        old_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        old_forges_dir = dataforge_store._FORGES_DIR
        with tempfile.TemporaryDirectory() as tmp_dir, tempfile.TemporaryDirectory() as tmp_forges:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_dir
            dataforge_store._FORGES_DIR = dataforge_store.Path(tmp_forges)
            save_object(adhoc_source_object(
                "Claims File Source",
                source_type="csv",
                metadata={"path": "claims.csv"},
                columns=["claim_id", "amount"],
            ))

            app = QApplication.instance()
            if app is None:
                app = QApplication([])

            window = QueryObjectViewerWindow()
            try:
                app.processEvents()
                window._left_panel_width = 333
                window._apply_left_panel_width()
                app.processEvents()
                self.assertEqual(window._promote_slot.minimumWidth(), 112)
                self.assertEqual(window._promote_slot.maximumWidth(), 112)
                self.assertEqual(window.lbl_canvas_title.text(),
                                 "File Sources: Claims File Source")

                window._browser_splitter.setSizes([250, 870])
                window._on_browser_splitter_moved(250, 1)
                app.processEvents()
                self.assertEqual(window._left_panel_width, 333)

                window.resize(760, 620)
                window._left_panel_width = 520
                window._apply_left_panel_width()
                app.processEvents()
                self.assertLessEqual(window._browser_splitter.sizes()[1], 260)

                def find_query_item(item):
                    payload = item.data(0, Qt.ItemDataRole.UserRole) or {}
                    if payload.get("type") == "query" and payload.get("name") == "Claims File Source":
                        return item
                    for child_index in range(item.childCount()):
                        found = find_query_item(item.child(child_index))
                        if found is not None:
                            return found
                    return None

                file_item = None
                for row in range(window.tree.topLevelItemCount()):
                    file_item = find_query_item(window.tree.topLevelItem(row))
                    if file_item is not None:
                        break

                self.assertIsNotNone(file_item)
                payload = file_item.data(0, Qt.ItemDataRole.UserRole)
                self.assertEqual(payload["badge_fill"], "#B58900")
                self.assertEqual(payload["badge_text_color"], "#FFFFFF")
                # The legacy "Files" group was removed; the only registered
                # source registry is "File Sources". This un-migrated adhoc
                # source therefore lives in the Queries tree, not the source
                # tree, so there is no source-tree node to assert here.

                window.tree.setCurrentItem(file_item)
                app.processEvents()

                self.assertEqual(window._left_panel_width, 520)
            finally:
                window.close()

        dataforge_store._FORGES_DIR = old_forges_dir
        if old_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_dir

    def test_results_tab_clear_results_resets_table_context_and_export(self):
        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        tab = ResultsTab()
        try:
            tab.set_results(pd.DataFrame({"PolicyNumber": ["123"], "CompanyCode": ["01"]}))
            tab.set_query_context(sql="SELECT 1", dsn="CKPR", result_columns=["PolicyNumber"])

            tab.clear_results()

            self.assertIsNone(tab._df)
            self.assertIsNone(tab._query_context)
            self.assertFalse(tab.btn_export.isEnabled())
            self.assertEqual(tab.table.model.rowCount(), 0)
        finally:
            tab.close()

    def test_build_badges_use_cyberlife_and_dark_manual_sql_labels(self):
        from suiteview.audit.build_mode_styles import mode_style
        from suiteview.audit.query_object_viewer_window import _QUERY_BADGES

        self.assertEqual(_QUERY_BADGES[OBJECT_KIND_CYBERLIFE], "CL")
        self.assertEqual(_QUERY_BADGES[OBJECT_KIND_MANUAL_SQL], "SQL")
        self.assertEqual(mode_style(OBJECT_KIND_MANUAL_SQL).color, "#5A3218")

    def test_new_visual_query_confirmation_clears_results_and_sql_tabs(self):
        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        from suiteview.audit.dynamic_group import DynamicQuery

        group = DynamicQuery("Visual Query", "WORK_DSN", [])
        emitted = []
        group.new_query_requested.connect(lambda: emitted.append(True))
        try:
            group.results_tab.set_results(pd.DataFrame({"PolicyNumber": ["123"]}))
            group.sql_tab.set_sql("SELECT * FROM POLICY")
            group.build_sql_tab.set_sql("SELECT * FROM BUILD")
            group.build_sql_results_tab.set_results(
                pd.DataFrame({"PolicyNumber": ["123"]}), sql="SELECT 1", dsn="WORK_DSN")
            group.lbl_result_count.setText("Result count:   1")

            with patch(
                "suiteview.audit.dynamic_group.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ):
                group._confirm_new_query()

            self.assertEqual(emitted, [True])
            self.assertIsNone(group.results_tab._df)
            self.assertEqual(group.sql_tab.txt_sql.toPlainText(), "")
            self.assertEqual(group.build_sql_tab.txt_sql.toPlainText(), "")
            self.assertIsNone(group.build_sql_results_tab._df)
            self.assertEqual(group.lbl_result_count.text(), "Result count:")
        finally:
            group.close()

    def test_cyberlife_clear_selects_policy_tab_and_clears_sql_tabs(self):
        from suiteview.audit.audit_window import AuditWindow

        calls = []

        class FakeCriteriaTab:
            def set_state(self, state):
                calls.append(("criteria", state))

        class FakeText:
            def __init__(self):
                self.value = ""

            def setText(self, value):
                self.value = value

        class FakeCheck:
            def __init__(self):
                self.checked = True

            def setChecked(self, checked):
                self.checked = checked

        class FakeClear:
            def __init__(self, name):
                self.name = name
                self.cleared = False

            def clear_results(self):
                self.cleared = True
                calls.append(self.name)

            def clear_sql(self):
                self.cleared = True
                calls.append(self.name)

        class FakeTabs:
            def __init__(self):
                self.current = None

            def setCurrentWidget(self, widget):
                self.current = widget

        fake = type("FakeAudit", (), {})()
        fake.policy_tab = object()
        fake.tabs = FakeTabs()
        fake.txt_max_count = FakeText()
        fake.chk_coverage_level = FakeCheck()
        fake.results_tab = FakeClear("results")
        fake.sql_tab = FakeClear("sql")
        fake.build_sql_tab = FakeClear("build_sql")
        fake.build_sql_results_tab = FakeClear("build_sql_results")
        fake.lbl_result_count = FakeText()
        fake._cyberlife_criteria_tabs = lambda: [("policy", FakeCriteriaTab())]

        AuditWindow._on_clear_cyberlife(fake)

        self.assertEqual(fake.txt_max_count.value, "25")
        self.assertFalse(fake.chk_coverage_level.checked)
        self.assertEqual(fake.lbl_result_count.value, "Result count:")
        self.assertIs(fake.tabs.current, fake.policy_tab)
        self.assertIn("sql", calls)
        self.assertIn("build_sql", calls)
        self.assertIn("build_sql_results", calls)

    def test_new_forge_confirmation_clears_results_sql_and_code_tabs(self):
        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        from suiteview.audit.dataforge.dataforge_group import DataForgeGroup

        group = DataForgeGroup("⚙ Forge")
        emitted = []
        group.new_forge_requested.connect(lambda: emitted.append(True))
        try:
            group.results_tab.set_results(pd.DataFrame({"PolicyNumber": ["123"]}))
            group.sql_tab.set_forge_sql("SELECT * FROM FORGE")
            group.sql_tab.set_datasets({"Source Query": "SELECT * FROM SOURCE"})
            group.sql_tab.set_manual_state(True, "SELECT * FROM MANUAL")
            group.code_tab.set_code("print('stale')")
            group.lbl_result_count.setText("Result count:   1")

            with patch(
                "suiteview.audit.dataforge.dataforge_group.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ):
                group._confirm_new_forge()

            self.assertEqual(emitted, [True])
            self.assertIsNone(group.results_tab._df)
            self.assertEqual(group.sql_tab.txt_sql.toPlainText(), "")
            self.assertEqual(group.sql_tab.manual_sql, "")
            self.assertFalse(group.sql_tab.manual_mode)
            self.assertEqual(group.code_tab.txt_code.toPlainText(), "")
            self.assertEqual(group.lbl_result_count.text(), "Result count:")
        finally:
            group.close()

    def test_query_object_viewer_shows_hidden_audit_parent_for_builder(self):
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)

        browser = QueryObjectViewerWindow()
        audit_window = QWidget()
        audit_window.open_dataforge_in_builder = lambda forge_name: None
        browser._audit_parent = audit_window

        try:
            self.assertFalse(audit_window.isVisible())
            selected = browser._audit_window_for_builder()

            self.assertIs(selected, audit_window)
            self.assertTrue(audit_window.isVisible())
        finally:
            browser.close()
            audit_window.close()

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

    def test_audit_builder_opens_editable_dataforge_copy_not_original_design(self):
        from suiteview.audit.audit_window import AuditWindow

        obj = manual_sql_query_object(
            "Claims [Forge]",
            sql="SELECT * FROM CLAIMS",
            dsn="FAKE_DSN",
            result_columns=["claim_id"],
        )
        obj.config["dataforge"] = {"forge_name": "Forge", "source_name": "Claims"}
        calls = []
        manual_calls = []

        class DummyAudit:
            def _open_dataforge_source_design(self, opened_obj):
                calls.append(opened_obj.name)
                return True

            def open_manual_sql_object(self, opened_obj):
                manual_calls.append(opened_obj.name)

        with patch("suiteview.audit.query_object_store.load_object", return_value=obj):
            AuditWindow.open_query_object_in_builder(DummyAudit(), obj.name)

        self.assertEqual(calls, [])
        self.assertEqual(manual_calls, ["Claims [Forge]"])

    def test_audit_build_mode_button_width_stays_static(self):
        from suiteview.audit.audit_window import AuditWindow, _BUILD_MODE_BUTTON_WIDTH

        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)

        class DummyAudit:
            pass

        dummy = DummyAudit()
        dummy.btn_build_mode = QPushButton("Cyberlife")
        dummy.btn_build_mode.setFixedSize(_BUILD_MODE_BUTTON_WIDTH, 24)

        for mode in ("cyberlife", "visual", "manual_sql", "file"):
            AuditWindow._style_build_mode_button(dummy, mode)
            self.assertEqual(dummy.btn_build_mode.minimumWidth(), _BUILD_MODE_BUTTON_WIDTH)
            self.assertEqual(dummy.btn_build_mode.maximumWidth(), _BUILD_MODE_BUTTON_WIDTH)
            self.assertEqual(dummy.btn_build_mode.width(), _BUILD_MODE_BUTTON_WIDTH)

    def test_audit_builder_opens_cyberlife_dataforge_copy_itself(self):
        from suiteview.audit.audit_window import AuditWindow

        obj = cyberlife_query_object(
            "Cyberlife Trad CV [Forge]",
            sql="SELECT * FROM DB2TAB.LH_BAS_POL",
            dsn="CKPR_DSN",
            region="CKPR",
            system_code="I",
            criteria={},
            result_columns=["TCH_POL_ID"],
        )
        obj.config["dataforge"] = {
            "forge_name": "Forge",
            "source_name": "Cyberlife Trad CV",
        }
        design_calls = []
        cyberlife_calls = []

        class DummyAudit:
            def _open_dataforge_source_design(self, opened_obj):
                design_calls.append(opened_obj.name)
                return True

            def open_cyberlife_query_object(self, opened_obj):
                cyberlife_calls.append(opened_obj.name)

        with patch("suiteview.audit.query_object_store.load_object", return_value=obj):
            AuditWindow.open_query_object_in_builder(DummyAudit(), obj.name)

        self.assertEqual(design_calls, [])
        self.assertEqual(cyberlife_calls, ["Cyberlife Trad CV [Forge]"])

    def test_cyberlife_dataforge_copy_save_preserves_dataforge_metadata(self):
        from suiteview.audit.audit_window import AuditWindow

        old_obj_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        with tempfile.TemporaryDirectory() as tmp_objects:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_objects
            existing = cyberlife_query_object(
                "Cyberlife Trad CV [Forge]",
                sql="SELECT OLD_COL FROM DB2TAB.LH_BAS_POL",
                dsn="CKPR_DSN",
                region="CKPR",
                system_code="I",
                criteria={"old": True},
                result_columns=["OLD_COL"],
            )
            existing.config["dataforge"] = {
                "forge_name": "Forge",
                "source_name": "Cyberlife Trad CV",
            }
            save_object(existing)

            class Combo:
                def __init__(self, value):
                    self.value = value

                def currentText(self):
                    return self.value

            class Button:
                def setVisible(self, visible):
                    return None

            class SqlTab:
                def set_sql(self, sql):
                    self.sql = sql

            class Signal:
                def emit(self, name):
                    self.name = name

            class DummyAudit:
                _current_mode = "cyberlife"
                _cyberlife_saved_object_name = "Cyberlife Trad CV [Forge]"
                cmb_region = Combo("CKPR")
                cmb_system = Combo("I")
                results_tab = object()
                btn_save_cyberlife = Button()
                sql_tab = SqlTab()
                query_object_saved = Signal()

                def _build_sql(self):
                    return "SELECT NEW_COL FROM DB2TAB.LH_BAS_POL"

                def _cyberlife_query_object_state(self):
                    return {"new": True}

            with patch("suiteview.audit.audit_window.QMessageBox.information"):
                AuditWindow._save_cyberlife_query_object(
                    DummyAudit(), "Cyberlife Trad CV [Forge]")

            saved = load_object("Cyberlife Trad CV [Forge]")
            self.assertIsNotNone(saved)
            self.assertEqual(saved.sql, "SELECT NEW_COL FROM DB2TAB.LH_BAS_POL")
            self.assertEqual(saved.config["criteria"], {"new": True})
            self.assertEqual(saved.config["dataforge"]["forge_name"], "Forge")
            self.assertEqual(saved.config["dataforge"]["source_name"], "Cyberlife Trad CV")
            self.assertEqual(saved.config["dataforge"]["query_object_id"], saved.id)

        if old_obj_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_obj_dir

    def test_forge_assist_open_builder_uses_audit_window_not_popup_editor(self):
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        picker = QueryFieldPicker()
        calls = []

        class FakeAudit:
            def open_query_object_in_builder(self, object_name):
                calls.append(object_name)

            def raise_(self):
                return None

            def activateWindow(self):
                return None

        picker._new_audit_window_for_builder = lambda query_name: FakeAudit()
        picker._open_manual_sql_builder = lambda *args, **kwargs: self.fail("used popup manual SQL builder")
        picker._open_file_source_builder = lambda *args, **kwargs: self.fail("used popup file source builder")

        picker._open_query_builder("Claims [Forge]")

        self.assertEqual(calls, ["Claims [Forge]"])

    def test_forge_assist_builder_save_signal_refreshes_private_source_sql(self):
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        old_obj_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        old_qdefs_dir = qdef_store._QDEFS_DIR
        with tempfile.TemporaryDirectory() as tmp_objects, tempfile.TemporaryDirectory() as tmp_qdefs:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_objects
            qdef_store._QDEFS_DIR = qdef_store.Path(tmp_qdefs)

            obj = cyberlife_query_object(
                "Cyberlife Trad CV [Forge]",
                sql="SELECT TCH_POL_ID FROM DB2TAB.LH_BAS_POL FETCH FIRST 25 ROWS ONLY",
                dsn="CKPR_DSN",
                region="CKPR",
                system_code="I",
                criteria={"max_count": "25"},
                result_columns=["TCH_POL_ID"],
            )
            obj.config["dataforge"] = {
                "forge_name": "Forge",
                "source_name": "Cyberlife Trad CV",
            }
            save_object(obj)

            picker = QueryFieldPicker()
            picker.set_sources([obj.name], forge_name="Forge")
            refreshed = []
            picker.source_refreshed.connect(lambda old, qd: refreshed.append((old, qd)))

            class FakeAuditWindow(QObject):
                query_object_saved = pyqtSignal(str)

            window = FakeAuditWindow()
            with patch("suiteview.audit.main.create_audit_window", return_value=window):
                self.assertIs(picker._new_audit_window_for_builder(obj.name), window)

            obj.sql = "SELECT TCH_POL_ID FROM DB2TAB.LH_BAS_POL"
            obj.config["criteria"] = {"max_count": ""}
            save_object(obj)

            window.query_object_saved.emit(obj.name)

            self.assertEqual(len(refreshed), 1)
            self.assertNotIn("FETCH FIRST 25 ROWS ONLY", picker._sources[obj.name].sql)
            self.assertEqual(
                picker._sources[obj.name].query_object_config["criteria"],
                {"max_count": ""},
            )

        qdef_store._QDEFS_DIR = old_qdefs_dir
        if old_obj_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_obj_dir

    def test_forge_assist_query_double_click_requests_join_table(self):
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        picker = QueryFieldPicker()
        emitted = []
        picker.query_table_requested.connect(emitted.append)

        item = QListWidgetItem("Claims [Forge]")
        item.setData(Qt.ItemDataRole.UserRole, "Claims [Forge]")
        picker._on_query_double_clicked(item)

        self.assertEqual(emitted, ["Claims [Forge]"])

    def test_audit_forge_query_double_click_copies_then_adds_join_table(self):
        from suiteview.audit.audit_window import AuditWindow

        calls = []

        class FakeJoins:
            def add_query_table(self, name):
                calls.append(name)
                return True

        class FakeTabs:
            def setCurrentWidget(self, widget):
                calls.append("tab")

        class FakeGroup:
            def __init__(self):
                self._sources = {}
                self._saved_forge_name = "Forge"
                self.joins_tab = FakeJoins()
                self.tab_widget = FakeTabs()

            def add_source_copy(self, name):
                qd = QDefinition(name=f"{name} [Forge]", result_columns=["claim_id"])
                self._sources[qd.name] = qd
                return qd

            def _schedule_save(self):
                calls.append("save")

        class FakePicker:
            def set_sources(self, names, forge_name="", source_definitions=None):
                calls.append(tuple(names))

        class FakeAudit:
            def _set_forge_picker_sources(self, group):
                self._forge_field_picker.set_sources(
                    list(group._sources.keys()),
                    forge_name=group._saved_forge_name,
                    source_definitions=group._sources,
                )

        fake = FakeAudit()
        fake._current_mode = "forge"
        fake._dataforge_groups = {"forge": FakeGroup()}
        fake._forge_field_picker = FakePicker()

        AuditWindow._on_forge_picker_query_table_requested(fake, "Claims")

        self.assertIn(("Claims [Forge]",), calls)
        self.assertIn("Claims [Forge]", calls)
        self.assertIn("tab", calls)
        self.assertIn("save", calls)

    def test_forge_assist_republishes_stale_copy_before_opening_builder(self):
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        old_obj_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        with tempfile.TemporaryDirectory() as tmp_objects:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_objects
            stale = manual_sql_query_object(
                "Claims [Forge]",
                sql="SELECT * FROM CLAIMS",
                dsn="FAKE_DSN",
                result_columns=["claim_id"],
            )
            save_object(stale)

            qd = QDefinition(
                name="Claims [Forge]",
                forge_name="Forge",
                sql="SELECT * FROM CLAIMS",
                dsn="FAKE_DSN",
                source_design="Claims",
                result_columns=["claim_id"],
            )
            picker = QueryFieldPicker()
            picker._sources[qd.name] = qd

            class FakeSignal:
                def connect(self, callback):
                    return None

            class FakeAudit:
                destroyed = FakeSignal()

                def open_query_object_in_builder(self, object_name):
                    return None

                def raise_(self):
                    return None

                def activateWindow(self):
                    return None

            with patch("suiteview.audit.main.create_audit_window", return_value=FakeAudit()):
                picker._new_audit_window_for_builder(qd.name)
            republished = load_object(qd.name)

            self.assertIsNotNone(republished)
            self.assertEqual(republished.config["dataforge"]["forge_name"], "Forge")

        if old_obj_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_obj_dir

    def test_forge_assist_rename_updates_display_label_and_private_copy(self):
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        old_obj_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        old_qdefs_dir = qdef_store._QDEFS_DIR
        picker = None
        try:
            with tempfile.TemporaryDirectory() as tmp_objects, tempfile.TemporaryDirectory() as tmp_qdefs:
                os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_objects
                qdef_store._QDEFS_DIR = qdef_store.Path(tmp_qdefs)

                forge_name = "Forge"
                old_name = "Claims [Forge]"
                new_name = "Claims Latest [Forge]"
                forge_copy = manual_sql_query_object(
                    old_name,
                    sql="SELECT claim_id, amount FROM CLAIMS",
                    dsn="FAKE_DSN",
                    result_columns=["claim_id", "amount"],
                )
                forge_copy.config["dataforge"] = {
                    "forge_name": forge_name,
                    "source_name": "Claims",
                }
                save_object(forge_copy)
                qd = qdefinition_from_query_object(forge_copy)
                qd.forge_name = forge_name
                qdef_store.save_qdef(qd)

                picker = QueryFieldPicker()
                picker.set_sources(
                    [old_name],
                    forge_name=forge_name,
                    source_definitions={old_name: qd},
                )
                emitted = []
                picker.source_refreshed.connect(
                    lambda old, refreshed: emitted.append((old, refreshed.name)))

                with patch(
                    "PyQt6.QtWidgets.QInputDialog.getText",
                    return_value=("Claims Latest", True),
                ):
                    picker._rename_qdef(old_name)

                self.assertNotIn(old_name, picker._sources)
                self.assertIn(new_name, picker._sources)
                self.assertEqual(
                    QueryFieldPicker._source_display_name(picker._sources[new_name]),
                    "Claims Latest",
                )
                renamed = load_object_by_id(forge_copy.id)
                self.assertIsNotNone(renamed)
                self.assertEqual(renamed.name, new_name)
                self.assertEqual(
                    renamed.config["dataforge"],
                    {
                        "forge_name": forge_name,
                        "source_name": "Claims Latest",
                        "query_object_id": forge_copy.id,
                    },
                )
                self.assertIsNone(qdef_store.load_qdef(old_name, forge_name=forge_name))
                self.assertIsNotNone(qdef_store.load_qdef(new_name, forge_name=forge_name))
                self.assertEqual(emitted, [(old_name, new_name)])
        finally:
            if picker is not None:
                picker.close()
            qdef_store._QDEFS_DIR = old_qdefs_dir
            if old_obj_dir is None:
                os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
            else:
                os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_obj_dir

    def test_forge_assist_rename_allows_stale_target_for_same_source_id(self):
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        old_obj_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        old_qdefs_dir = qdef_store._QDEFS_DIR
        picker = None
        try:
            with tempfile.TemporaryDirectory() as tmp_objects, tempfile.TemporaryDirectory() as tmp_qdefs:
                os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_objects
                qdef_store._QDEFS_DIR = qdef_store.Path(tmp_qdefs)

                forge_name = "Forge"
                old_name = "Claims [Forge]"
                new_name = "CL LTGUL [Forge]"
                forge_copy = manual_sql_query_object(
                    old_name,
                    sql="SELECT claim_id, amount FROM CLAIMS",
                    dsn="FAKE_DSN",
                    result_columns=["claim_id", "amount"],
                )
                forge_copy.config["dataforge"] = {
                    "forge_name": forge_name,
                    "source_name": "Claims",
                }
                save_object(forge_copy)
                old_qd = qdefinition_from_query_object(forge_copy)
                old_qd.forge_name = forge_name
                qdef_store.save_qdef(old_qd)

                stale_target = qdefinition_from_query_object(forge_copy)
                stale_target.name = new_name
                stale_target.forge_name = forge_name
                stale_config = dict(stale_target.query_object_config or {})
                stale_dataforge = dict(stale_config.get("dataforge", {}) or {})
                stale_dataforge["source_name"] = "CL LTGUL"
                stale_config["dataforge"] = stale_dataforge
                stale_target.query_object_config = stale_config
                qdef_store.save_qdef(stale_target)

                picker = QueryFieldPicker()
                picker.set_sources(
                    [old_name],
                    forge_name=forge_name,
                    source_definitions={old_name: old_qd},
                )

                with patch(
                    "PyQt6.QtWidgets.QInputDialog.getText",
                    return_value=("CL LTGUL", True),
                ), patch("PyQt6.QtWidgets.QMessageBox.warning") as warning:
                    picker._rename_qdef(old_name)

                warning.assert_not_called()
                self.assertNotIn(old_name, picker._sources)
                self.assertIn(new_name, picker._sources)
                self.assertEqual(
                    QueryFieldPicker._source_display_name(picker._sources[new_name]),
                    "CL LTGUL",
                )
                self.assertIsNone(qdef_store.load_qdef(old_name, forge_name=forge_name))
                self.assertIsNotNone(qdef_store.load_qdef(new_name, forge_name=forge_name))
                self.assertEqual(load_object_by_id(forge_copy.id).name, new_name)
        finally:
            if picker is not None:
                picker.close()
            qdef_store._QDEFS_DIR = old_qdefs_dir
            if old_obj_dir is None:
                os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
            else:
                os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_obj_dir

    def test_forge_assist_selector_excludes_forge_owned_copies(self):
        # The "add a query" selector must show only standalone queries — a
        # Forge's own Source copy showing up here was the phantom duplicate.
        normal = manual_sql_query_object(
            "Claims", sql="SELECT * FROM CLAIMS", dsn="FAKE_DSN",
            result_columns=["claim_id"])
        forge_copy = manual_sql_query_object(
            "Claims [RGA - EXECUL and Claims]",
            sql="SELECT * FROM CLAIMS", dsn="FAKE_DSN",
            result_columns=["claim_id"])
        forge_copy.config["dataforge"] = {
            "forge_name": "RGA - EXECUL and Claims",
            "source_name": "Claims",
        }

        groups = _group_query_objects_for_selector([normal, forge_copy])

        self.assertIn("Manual SQL Objects", groups)
        names = {obj.name for members in groups.values() for obj in members}
        self.assertEqual(names, {"Claims"})  # forge copy excluded

    def test_query_object_browser_delete_dataforge_records_keeps_original(self):
        old_obj_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        old_qdefs_dir = qdef_store._QDEFS_DIR
        old_forges_dir = dataforge_store._FORGES_DIR
        with tempfile.TemporaryDirectory() as tmp_objects, tempfile.TemporaryDirectory() as tmp_qdefs, tempfile.TemporaryDirectory() as tmp_forges:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_objects
            qdef_store._QDEFS_DIR = qdef_store.Path(tmp_qdefs)
            dataforge_store._FORGES_DIR = dataforge_store.Path(tmp_forges)

            original = manual_sql_query_object(
                "Claims", sql="SELECT * FROM CLAIMS", dsn="FAKE_DSN",
                result_columns=["claim_id"])
            forge_copy = manual_sql_query_object(
                "Claims [RGA - EXECUL and Claims]",
                sql="SELECT * FROM CLAIMS", dsn="FAKE_DSN",
                result_columns=["claim_id"])
            forge_copy.config["dataforge"] = {
                "forge_name": "RGA - EXECUL and Claims",
                "source_name": "Claims",
            }
            save_object(original)
            save_object(forge_copy)
            qdef_store.save_qdef(QDefinition(
                name=forge_copy.name,
                forge_name="RGA - EXECUL and Claims",
                sql=forge_copy.sql,
                dsn=forge_copy.dsn,
                result_columns=forge_copy.result_columns,
            ))
            dataforge_store.save_forge(DataForge(
                name="RGA - EXECUL and Claims",
                sources=[DataForgeSource(
                    query_name=forge_copy.name,
                    definition=forge_copy.to_dict(),
                )],
            ))

            QueryObjectViewerWindow._delete_dataforge_records(
                "RGA - EXECUL and Claims", [forge_copy])

            self.assertIsNone(dataforge_store.load_forge("RGA - EXECUL and Claims"))
            self.assertFalse(object_exists("Claims [RGA - EXECUL and Claims]"))
            self.assertTrue(object_exists("Claims"))

        qdef_store._QDEFS_DIR = old_qdefs_dir
        dataforge_store._FORGES_DIR = old_forges_dir
        if old_obj_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_obj_dir

    def test_query_object_browser_renames_dataforge_source_records(self):
        old_obj_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        old_qdefs_dir = qdef_store._QDEFS_DIR
        old_forges_dir = dataforge_store._FORGES_DIR
        with tempfile.TemporaryDirectory() as tmp_objects, tempfile.TemporaryDirectory() as tmp_qdefs, tempfile.TemporaryDirectory() as tmp_forges:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_objects
            qdef_store._QDEFS_DIR = qdef_store.Path(tmp_qdefs)
            dataforge_store._FORGES_DIR = dataforge_store.Path(tmp_forges)

            forge_name = "Forge"
            old_name = "Claims [Forge]"
            new_name = "Claims Latest [Forge]"
            forge_copy = manual_sql_query_object(
                old_name,
                sql="SELECT claim_id, amount FROM CLAIMS",
                dsn="FAKE_DSN",
                result_columns=["claim_id", "amount"],
            )
            forge_copy.config["dataforge"] = {
                "forge_name": forge_name,
                "source_name": "Claims",
            }
            save_object(forge_copy)
            qdef_store.save_qdef(QDefinition(
                name=old_name,
                forge_name=forge_name,
                sql=forge_copy.sql,
                dsn=forge_copy.dsn,
                result_columns=forge_copy.result_columns,
            ))
            dataforge_store.save_source_snapshot(
                forge_name,
                old_name,
                pd.DataFrame([["C1", 100]], columns=["claim_id", "amount"]),
            )
            dataforge_store.save_forge(DataForge(
                name=forge_name,
                sources=[DataForgeSource(
                    query_name=old_name,
                    definition=forge_copy.to_dict(),
                )],
                config={
                    "sources": [old_name],
                    "filter_tabs": [{
                        "grid": {
                            "fields": {f"{old_name}.claim_id": {}},
                            "positions": {f"{old_name}.claim_id": [0, 0]},
                        }
                    }],
                    "display_tab": {
                        "rows": [{"field_key": f"{old_name}.amount"}],
                    },
                    "joins": [{"left_source": old_name, "right_source": "Other"}],
                },
            ))

            QueryObjectViewerWindow._rename_forge_source_records(
                forge_name,
                forge_copy,
                new_name,
            )

            renamed = load_object_by_id(forge_copy.id)
            self.assertIsNotNone(renamed)
            self.assertEqual(renamed.name, new_name)
            self.assertFalse(object_exists(old_name))
            self.assertTrue(object_exists(new_name))
            self.assertIsNone(qdef_store.load_qdef(old_name, forge_name=forge_name))
            self.assertIsNotNone(qdef_store.load_qdef(new_name, forge_name=forge_name))
            self.assertFalse(dataforge_store.has_source_snapshot(forge_name, old_name))
            self.assertTrue(dataforge_store.has_source_snapshot(forge_name, new_name))
            forge = dataforge_store.load_forge(forge_name)
            self.assertIsNotNone(forge)
            self.assertEqual(forge.sources[0].query_name, new_name)
            self.assertEqual(forge.sources[0].definition["name"], new_name)
            self.assertEqual(forge.config["sources"], [new_name])
            self.assertIn(f"{new_name}.claim_id", forge.config["filter_tabs"][0]["grid"]["fields"])
            self.assertEqual(forge.config["display_tab"]["rows"][0]["field_key"], f"{new_name}.amount")
            self.assertEqual(forge.config["joins"][0]["left_source"], new_name)

        qdef_store._QDEFS_DIR = old_qdefs_dir
        dataforge_store._FORGES_DIR = old_forges_dir
        if old_obj_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_obj_dir

    def test_forge_assist_previews_flat_file_source_without_dsn(self):
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "claims.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("claim_id,amount\nC1,100\nC2,250\n")
            qd = QDefinition(
                name="CLAIMDATA [Forge]",
                source_design="csv",
                result_columns=["claim_id", "amount"],
            )
            qd.query_object_kind = OBJECT_KIND_ADHOC_SOURCE
            qd.query_object_source_metadata = {
                "path": path,
                "delimiter": ",",
                "encoding": "utf-8",
                "header": True,
            }

            picker = QueryFieldPicker()
            df = picker._load_preview_dataframe(qd)

            self.assertEqual(list(df.columns), ["claim_id", "amount"])
            self.assertEqual(len(df), 2)
            self.assertEqual(df.iloc[0]["claim_id"], "C1")

    def test_forge_assist_repairs_stale_flat_file_qdef_for_preview(self):
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        old_obj_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        old_qdefs_dir = qdef_store._QDEFS_DIR
        with tempfile.TemporaryDirectory() as tmp_objects, tempfile.TemporaryDirectory() as tmp_qdefs, tempfile.TemporaryDirectory() as tmp_data:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_objects
            qdef_store._QDEFS_DIR = qdef_store.Path(tmp_qdefs)
            path = os.path.join(tmp_data, "claims.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("claim_id,amount\nC1,100\nC2,250\n")
            original = adhoc_source_object(
                "CLAIMDATA",
                source_type="csv",
                metadata={"path": path},
                columns=["claim_id", "amount"],
            )
            save_object(original)
            qdef_store.save_qdef(QDefinition(
                name="CLAIMDATA [Forge]",
                forge_name="Forge",
                source_design="csv",
                result_columns=["claim_id", "amount"],
            ))

            loaded = _load_query_source("CLAIMDATA [Forge]", forge_name="Forge")
            df = QueryFieldPicker()._load_preview_dataframe(loaded)

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.name, "CLAIMDATA [Forge]")
            self.assertEqual(loaded.query_object_kind, OBJECT_KIND_ADHOC_SOURCE)
            self.assertEqual(loaded.query_object_source_metadata["path"], path)
            self.assertEqual(list(df.columns), ["claim_id", "amount"])
            self.assertEqual(len(df), 2)

        qdef_store._QDEFS_DIR = old_qdefs_dir
        if old_obj_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_obj_dir

    def test_forge_assist_uses_active_flat_file_definition_for_preview(self):
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "claims.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("claim_id,amount\nC1,100\nC2,250\n")
            qd = QDefinition(
                name="CLAIMDATA [Forge]",
                forge_name="Forge",
                source_design="csv",
                result_columns=["claim_id", "amount"],
            )
            qd.query_object_kind = OBJECT_KIND_ADHOC_SOURCE
            qd.query_object_source_metadata = {"path": path}

            picker = QueryFieldPicker()
            picker.set_sources([qd.name], forge_name="Forge", source_definitions={qd.name: qd})
            df = picker._load_preview_dataframe(picker._sources[qd.name])

            self.assertEqual(list(df.columns), ["claim_id", "amount"])
            self.assertEqual(len(df), 2)

    def test_forge_assist_refresh_updates_flat_file_fields_without_changing_kind(self):
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        old_obj_dir = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        old_qdefs_dir = qdef_store._QDEFS_DIR
        with tempfile.TemporaryDirectory() as tmp_objects, tempfile.TemporaryDirectory() as tmp_qdefs:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = tmp_objects
            qdef_store._QDEFS_DIR = qdef_store.Path(tmp_qdefs)
            obj = adhoc_source_object(
                "CLAIMDATA [Forge]",
                source_type="csv",
                metadata={"path": "claims.csv"},
                columns=["claim_id"],
            )
            obj.config["dataforge"] = {"forge_name": "Forge", "source_name": "CLAIMDATA"}
            save_object(obj)

            picker = QueryFieldPicker()
            picker.set_sources([obj.name], forge_name="Forge")
            obj.fields = fields_from_columns(["claim_id", "amount"], source=obj.name)
            save_object(obj)

            picker._refresh_query_source(obj.name)
            refreshed = load_object(obj.name)

            self.assertEqual(picker._sources[obj.name].result_columns, ["claim_id", "amount"])
            self.assertIsNotNone(refreshed)
            self.assertEqual(refreshed.kind, OBJECT_KIND_ADHOC_SOURCE)
            self.assertEqual(refreshed.result_columns, ["claim_id", "amount"])

        qdef_store._QDEFS_DIR = old_qdefs_dir
        if old_obj_dir is None:
            os.environ.pop("SUITEVIEW_QUERY_OBJECTS_DIR", None)
        else:
            os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = old_obj_dir

    def test_flat_file_query_object_displays_file_extension_in_dsn_column(self):
        obj = adhoc_source_object(
            "CLAIMDATA",
            source_type="csv",
            metadata={"path": "C:/temp/claims.csv"},
            columns=["claim_id"],
        )

        self.assertEqual(_display_dsn_for_object(obj), ".csv")

    def test_flat_file_definition_displays_file_extension_in_dsn_column(self):
        definition = {
            "name": "Claims [Forge]",
            "query_object_kind": OBJECT_KIND_ADHOC_SOURCE,
            "source_design": "csv",
            "query_object_source_metadata": {"path": r"C:\temp\claims.txt"},
        }

        self.assertEqual(_display_dsn_for_definition(definition), ".txt")

    def test_database_definition_still_displays_dsn(self):
        definition = {
            "name": "Rates",
            "kind": OBJECT_KIND_EXECUTABLE,
            "dsn": "UL_Rates",
        }

        self.assertEqual(_display_dsn_for_definition(definition), "UL_Rates")

    def test_dataforge_sources_tab_uses_file_extension_from_query_object(self):
        forge_copy = adhoc_source_object(
            "Claims [Forge]",
            source_type="csv",
            metadata={"path": "C:/temp/claims.csv"},
            columns=["claim_id"],
        )
        forge_copy.config["dataforge"] = {
            "forge_name": "Forge",
            "source_name": "Claims",
        }
        forge = DataForge(
            name="Forge",
            sources=[DataForgeSource(
                query_name=forge_copy.name,
                definition={
                    "name": forge_copy.name,
                    "kind": OBJECT_KIND_EXECUTABLE,
                    "source_design": "csv",
                    "result_columns": ["claim_id"],
                },
            )],
        )
        browser = QueryObjectViewerWindow.__new__(QueryObjectViewerWindow)

        rows = browser._forge_source_rows(forge, [forge_copy])

        self.assertEqual(rows[0][3], ".csv")

    def test_dataforge_source_definition_loads_in_audit_builder(self):
        obj = adhoc_source_object(
            "CLAIMDATA [Forge]",
            source_type="csv",
            metadata={"path": "claims.csv"},
            columns=["claim_id", "amount"],
        )
        source = DataForgeSource(
            query_name=obj.name,
            definition=obj.to_dict(),
        )

        from suiteview.audit.audit_window import AuditWindow

        qd = AuditWindow._qdefinition_from_dataforge_source(source, "Forge")

        self.assertIsNotNone(qd)
        self.assertEqual(qd.name, obj.name)
        self.assertEqual(qd.forge_name, "Forge")
        self.assertEqual(qd.query_object_kind, OBJECT_KIND_ADHOC_SOURCE)
        self.assertEqual(qd.result_columns, ["claim_id", "amount"])


if __name__ == "__main__":
    unittest.main()