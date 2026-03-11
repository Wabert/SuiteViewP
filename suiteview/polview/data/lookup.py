"""
Data lookup engine.

Loads JSON reference data files and provides lookup methods for:
- Mortality tables (CKAPTB32)
- Plancodes (OfficialPlancodeTable)
- Benefits
- Policy record to DB2 table mappings
"""

import json
import os
from typing import Any, Dict, List, Optional

_DATA_DIR = os.path.dirname(os.path.abspath(__file__))


class DataLookup:
    """Central lookup for reference data tables extracted from SuiteView workbook."""

    def __init__(self):
        self._mortality: Optional[List[Dict]] = None
        self._mortality_index: Optional[Dict[str, Dict]] = None
        self._plancodes: Optional[List[Dict]] = None
        self._plancode_index: Optional[Dict[str, Dict]] = None
        self._benefits: Optional[List[Dict]] = None
        self._benefit_index_by_code: Optional[Dict[str, Dict]] = None
        self._benefit_index_by_mnemonic: Optional[Dict[str, Dict]] = None
        self._policy_records: Optional[Dict[str, List[str]]] = None
        self._table_to_records: Optional[Dict[str, List[str]]] = None

    # =========================================================================
    # Lazy loaders
    # =========================================================================

    def _load_json(self, filename: str) -> Any:
        path = os.path.join(_DATA_DIR, filename)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _ensure_mortality(self):
        if self._mortality is None:
            self._mortality = self._load_json("ckaptb32_mortality_tables.json")
            self._mortality_index = {}
            for entry in self._mortality:
                code = entry["mortality_code"]
                # First entry wins for duplicates (matches VBA filter behavior)
                if code not in self._mortality_index:
                    self._mortality_index[code] = entry

    def _ensure_plancodes(self):
        if self._plancodes is None:
            self._plancodes = self._load_json("official_plancode_table.json")
            self._plancode_index = {}
            for entry in self._plancodes:
                code = entry["plancode"]
                if code not in self._plancode_index:
                    self._plancode_index[code] = entry

    def _ensure_benefits(self):
        if self._benefits is None:
            self._benefits = self._load_json("benefits.json")
            self._benefit_index_by_code = {}
            self._benefit_index_by_mnemonic = {}
            for entry in self._benefits:
                code = entry["code"]
                mnemonic = entry["mnemonic"]
                if code not in self._benefit_index_by_code:
                    self._benefit_index_by_code[code] = entry
                if mnemonic not in self._benefit_index_by_mnemonic:
                    self._benefit_index_by_mnemonic[mnemonic] = entry

    def _ensure_policy_records(self):
        if self._policy_records is None:
            self._policy_records = self._load_json("policy_record_db2_tables.json")
            # Build reverse index: table name -> list of policy records
            self._table_to_records = {}
            for record, tables in self._policy_records.items():
                for table in tables:
                    if table not in self._table_to_records:
                        self._table_to_records[table] = []
                    self._table_to_records[table].append(record)

    # =========================================================================
    # Mortality table lookups (CKAPTB32)
    # =========================================================================

    def get_mortality_entry(self, code: str) -> Optional[Dict]:
        """Get full mortality table entry by code."""
        self._ensure_mortality()
        return self._mortality_index.get(str(code).strip())

    def get_mortality_description(self, code: str) -> str:
        """Get mortality table description for a code. Returns code if not found."""
        if not code or str(code).strip() == "":
            return ""
        code = str(code).strip()
        entry = self.get_mortality_entry(code)
        return entry["description"] if entry else code

    def get_mortality_mnemonic(self, code: str) -> str:
        """Get mortality table mnemonic for a code."""
        entry = self.get_mortality_entry(str(code).strip())
        return entry["mnemonic"] if entry else ""

    def get_mortality_final_age(self, code: str) -> Optional[int]:
        """Get final mortality table age for a code."""
        entry = self.get_mortality_entry(str(code).strip())
        return entry["final_age"] if entry else None

    def get_mortality_select_period(self, code: str) -> Optional[int]:
        """Get mortality select period for a code."""
        entry = self.get_mortality_entry(str(code).strip())
        return entry["select_period"] if entry else None

    def get_all_mortality_entries(self) -> List[Dict]:
        """Get all mortality table entries."""
        self._ensure_mortality()
        return list(self._mortality)

    # =========================================================================
    # Plancode lookups (OfficialPlancodeTable)
    # =========================================================================

    def get_plancode_entry(self, plancode: str) -> Optional[Dict]:
        """Get full plancode entry."""
        self._ensure_plancodes()
        return self._plancode_index.get(str(plancode).strip())

    def get_plancode_description(self, plancode: str, field: str = "common_name") -> str:
        """
        Get a plancode field value. 
        Fields: product_class, product_type, product_subtype, product_subtype2,
                common_name, group, category, bucket
        Returns 'Not Found' if plancode not in table.
        """
        entry = self.get_plancode_entry(str(plancode).strip())
        if entry is None:
            return "Not Found"
        return entry.get(field, "Not Found")

    def get_plancode_product_class(self, plancode: str) -> str:
        """Get ProductClass for a plancode."""
        return self.get_plancode_description(plancode, "product_class")

    def get_plancode_product_type(self, plancode: str) -> str:
        """Get ProductType for a plancode."""
        return self.get_plancode_description(plancode, "product_type")

    def get_plancode_common_name(self, plancode: str) -> str:
        """Get CommonName for a plancode."""
        return self.get_plancode_description(plancode, "common_name")

    def get_plancode_group(self, plancode: str) -> str:
        """Get Group for a plancode (WL, TERM, UL, etc.)."""
        return self.get_plancode_description(plancode, "group")

    def get_plancode_category(self, plancode: str) -> str:
        """Get Category for a plancode."""
        return self.get_plancode_description(plancode, "category")

    def get_plancode_bucket(self, plancode: str) -> str:
        """Get Bucket for a plancode."""
        return self.get_plancode_description(plancode, "bucket")

    def get_all_plancode_entries(self) -> List[Dict]:
        """Get all plancode entries."""
        self._ensure_plancodes()
        return list(self._plancodes)

    # =========================================================================
    # Benefit lookups
    # =========================================================================

    def get_benefit_by_code(self, code: str) -> Optional[Dict]:
        """Get benefit entry by type+subtype code (e.g., '10', '#6')."""
        self._ensure_benefits()
        return self._benefit_index_by_code.get(str(code).strip())

    def get_benefit_by_mnemonic(self, mnemonic: str) -> Optional[Dict]:
        """Get benefit entry by mnemonic (e.g., 'ADB', 'ABCH')."""
        self._ensure_benefits()
        return self._benefit_index_by_mnemonic.get(str(mnemonic).strip())

    def get_benefit_description(self, code: str) -> str:
        """Get benefit description by code. Returns code if not found."""
        entry = self.get_benefit_by_code(str(code).strip())
        return entry["description"] if entry else str(code)

    def get_benefit_mnemonic_for_code(self, code: str) -> str:
        """Get benefit mnemonic for a type+subtype code."""
        entry = self.get_benefit_by_code(str(code).strip())
        return entry["mnemonic"] if entry else ""

    def get_all_benefit_entries(self) -> List[Dict]:
        """Get all benefit entries."""
        self._ensure_benefits()
        return list(self._benefits)

    # =========================================================================
    # Policy Record DB2 Table lookups
    # =========================================================================

    def get_tables_for_record(self, record: str) -> List[str]:
        """Get DB2 table names for a policy record (e.g., 'Policy Record 01')."""
        self._ensure_policy_records()
        return self._policy_records.get(record, [])

    def get_records_for_table(self, table_name: str) -> List[str]:
        """Get policy record(s) that contain a given DB2 table."""
        self._ensure_policy_records()
        return self._table_to_records.get(table_name, [])

    def get_sorted_policy_records(self) -> List[str]:
        """Return policy records sorted numerically."""
        self._ensure_policy_records()
        def sort_key(record: str) -> int:
            try:
                return int(record.split()[-1])
            except (ValueError, IndexError):
                return 999
        return sorted(self._policy_records.keys(), key=sort_key)
    
    def get_all_policy_record_tables(self) -> Dict[str, List[str]]:
        """Get the full policy record -> tables mapping."""
        self._ensure_policy_records()
        return dict(self._policy_records)

    def get_all_db2_tables(self) -> List[str]:
        """Return all unique DB2 table names sorted."""
        self._ensure_policy_records()
        tables = set()
        for table_list in self._policy_records.values():
            tables.update(table_list)
        return sorted(tables)

    # Table descriptions - kept here since they're reference data
    TABLE_DESCRIPTIONS = {
        "LH_BAS_POL": "Basic Policy Information",
        "LH_FXD_PRM_POL": "Fixed Premium Policy",
        "TH_BAS_POL": "Basic Policy (Tracking History)",
        "LH_COV_PHA": "Coverage Phase",
        "LH_NEW_BUS_COV_PHA": "New Business Coverage Phase",
        "TH_COV_PHA": "Coverage Phase (Tracking History)",
        "LH_SST_XTR_CRG": "Substandard Extra Charge",
        "LH_SPM_BNF": "Supplemental Benefits",
        "LH_AGT_COM_AMT": "Agent Commission Amount",
        "LH_AGT_COM_RLE": "Agent Commission Role",
        "LH_POL_TOTALS": "Policy Totals",
        "LH_POL_YR_TOT": "Policy Year Totals",
        "LH_POL_CAL_YR_TOT": "Policy Calendar Year Totals",
        "LH_POL_FND_VAL_TOT": "Policy Fund Value Totals",
        "LH_FND_ALC": "Fund Allocation",
        "LH_TAMRA_7_PY_YR": "TAMRA 7-Pay Year",
        "LH_TAMRA_MEC_PRM": "TAMRA MEC Premium",
        "LH_COM_TARGET": "Commission Target",
        "LH_COV_TARGET": "Coverage Target",
        "LH_POL_TARGET": "Policy Target",
        "LH_CWA_ACY": "Cash With Application Activity",
        "LH_CSH_VAL_LOAN": "Cash Value Loan",
        "LH_FND_VAL_LOAN": "Fund Value Loan",
        "LH_POL_MVRY_VAL": "Policy Monthly Anniversary Value",
        "LH_CTT_CLIENT": "Contact Client",
        "LH_CTT_NOTE": "Contact Note",
        "LH_BIL_FRM_CTL": "Billing Form Control",
        "LH_DTL_SUS": "Detail Suspense",
        "LH_ISU_MKT_DTA": "Issue Market Data",
        "LH_TRD_POL": "Traditional Policy",
        "LH_NON_TRD_POL": "Non-Traditional Policy",
    }

    def get_table_description(self, table_name: str) -> str:
        """Get human-readable description for a DB2 table name."""
        return self.TABLE_DESCRIPTIONS.get(table_name, table_name)
