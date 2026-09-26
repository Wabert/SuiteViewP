"""
Persons tab – transposed person/client information table.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout

from ...services.persons_grid import PERSON_CODES as PERSON_CODE_LABELS, ROW_LABELS, build_persons_grid
from ..widgets import StyledInfoTableGroup

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation


class PersonsTab(QWidget):
    """Tab for Persons/Clients view - matches VBA SuiteView layout."""

    PERSON_CODES = PERSON_CODE_LABELS

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

    _ROW_LABELS = list(ROW_LABELS)

    def _build_table(self, persons: list, names_data: dict):
        grid = build_persons_grid(persons, [names_data.get(i, {}) for i in range(len(persons))])
        self.persons_group.setup_table(grid.headers)
        self.persons_group.load_table_data(grid.rows)

    # ── data loading ─────────────────────────────────────────────────────

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
            raise
