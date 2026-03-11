"""
Persons tab – transposed person/client information table.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout

from suiteview.core.db2_connection import DB2Connection
from ..formatting import format_date
from ..widgets import StyledInfoTableGroup

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation


class PersonsTab(QWidget):
    """Tab for Persons/Clients view - matches VBA SuiteView layout."""

    # Person-level codes (PRS_CD on the persons table).
    # Different mapping from policy_constants.PERSON_CODES (coverage-level).
    PERSON_CODES = {
        "00": "Primary Insured",
        "01": "Joint insured",
        "10": "Owner",
        "20": "Payor",
        "30": "Beneficiary",
        "40": "Spouse",
        "50": "Dependent",
        "60": "Other",
        "70": "Assignee",
        "A0": "Power of attorney",
        "A1": "Financial advisor",
        "A2": "Third party administrator (TPA)",
        "A3": "Certified public accountant (CPA)",
        "A4": "Plan sponsor",
        "A5": "Conservator",
        "A6": "Domestic partner",
        "A7": "Legal guardian",
        "A8": "Trustee",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.persons_group = StyledInfoTableGroup("Persons", show_info=False)
        self.persons_group.setup_table(["Data Type"])
        layout.addWidget(self.persons_group)

    # ── helpers ──────────────────────────────────────────────────────────

    def _get_person_value(self, row_label: str, person: dict, names: dict) -> str:
        if row_label == "Effective Date":
            return format_date(person.get("EFF_DT"))
        elif row_label == "Person Code":
            return str(person.get("PRS_CD", ""))
        elif row_label == "Description":
            code = str(person.get("PRS_CD", ""))
            return self.PERSON_CODES.get(code, code)
        elif row_label == "Sequence":
            return str(person.get("PRS_SEQ_NBR", ""))
        elif row_label == "Gender":
            return str(person.get("GENDER_CD", ""))
        elif row_label == "Class":
            return str(person.get("OCP_CLS_CD", ""))
        elif row_label == "BirthDay":
            return format_date(person.get("BIR_DT"))
        elif row_label == "First Name":
            first = names.get("CK_FST_NM", "")
            if not first:
                first = person.get("FST_NM", person.get("CK_FST_NM", ""))
            return str(first).strip() if first else ""
        elif row_label == "Last Name":
            last = names.get("CK_LST_NM", "")
            if not last:
                last = person.get("LST_NM", person.get("CK_LST_NM", ""))
            return str(last).strip() if last else ""
        elif row_label == "Suffix":
            suffix = names.get("CK_NM_SFX", "")
            if not suffix:
                suffix = person.get("NM_SFX", person.get("CK_NM_SFX", ""))
            return str(suffix).strip() if suffix else ""
        elif row_label == "OwnerCode":
            own_cd = str(person.get("OWN_CD", "")).strip()
            return "Owner" if own_cd == "A" else ""
        return ""

    _ROW_LABELS = [
        "Effective Date", "Person Code", "Description", "Sequence",
        "Gender", "Class", "BirthDay", "First Name", "Last Name",
        "Suffix", "OwnerCode",
    ]

    def _build_table(self, persons: list, names_data: dict):
        headers = ["Data Type"] + [f"Person {i+1}" for i in range(len(persons))]
        self.persons_group.setup_table(headers)
        table_data = []
        for row_label in self._ROW_LABELS:
            row_data = [row_label]
            for idx, person in enumerate(persons):
                row_data.append(self._get_person_value(row_label, person, names_data.get(idx, {})))
            table_data.append(row_data)
        self.persons_group.load_table_data(table_data)

    # ── data loading ─────────────────────────────────────────────────────

    # TODO: Dead code – never called; main_window uses load_data_from_policy() exclusively.
    def load_data(self, db: DB2Connection, where_clause: str):
        try:
            cols, rows = db.execute_query_with_headers(
                f"SELECT * FROM DB2TAB.LH_CTT_CLIENT WHERE {where_clause} ORDER BY PRS_CD, PRS_SEQ_NBR"
            )
            if not rows:
                self.persons_group.load_table_data([["No person data found"]])
                return

            persons = [dict(zip(cols, row)) for row in rows]

            names_data = {}
            try:
                name_cols, name_rows = db.execute_query_with_headers(
                    f"SELECT * FROM DB2TAB.VH_POL_HAS_LOC_CLT WHERE {where_clause}"
                )
                for idx, row in enumerate(name_rows):
                    names_data[idx] = dict(zip(name_cols, row))
            except Exception:
                pass

            self._build_table(persons, names_data)
        except Exception as e:
            self.persons_group.load_table_data([["Error loading data", str(e)]])

    def load_data_from_policy(self, policy: 'PolicyInformation'):
        try:
            persons = policy.fetch_table("LH_CTT_CLIENT")
            if not persons:
                self.persons_group.load_table_data([["No person data found"]])
                return
            names_list = policy.fetch_table("VH_POL_HAS_LOC_CLT")
            names_data = {i: nd for i, nd in enumerate(names_list)}
            self._build_table(persons, names_data)
        except Exception as e:
            self.persons_group.load_table_data([["Error loading data", str(e)]])
