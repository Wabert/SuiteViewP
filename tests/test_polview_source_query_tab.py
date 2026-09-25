from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd

from suiteview.polview.ui.tabs.source_query_tab import SourceQueryTab


class DemoSourceTab(SourceQueryTab):
    dsn = "Demo"
    date_label = "POSTED"
    query_button_text = "Demo"
    no_access_message = "No access"

    def _dsn_available(self) -> bool:
        return True

    def _build_query_request(self, policy, date_from, date_to):
        return "SELECT * FROM Demo WHERE Policy = ?", (policy.policy_number,)

    def _fetch_rows(self, sql: str, params: tuple):
        self.last_request = (sql, params)
        return ["POSTED", "VALUE"], [(date(2026, 9, 25), 10)]


def test_source_query_tab_runs_query_and_round_trips_state(qtbot):
    tab = DemoSourceTab()
    qtbot.addWidget(tab)

    policy = SimpleNamespace(
        exists=True,
        company_code="01",
        policy_number="U1234567",
        valuation_date=date(2026, 9, 25),
    )
    tab.load_policy(policy)
    tab.date_from.setText("09/01/2026")
    tab.date_to.setText("09/30/2026")

    tab._on_query()

    assert tab.last_request == ("SELECT * FROM Demo WHERE Policy = ?", ("U1234567",))
    assert tab._status_label.text() == "1 record(s) found."

    state = tab.export_state()
    assert state["from"] == "09/01/2026"
    assert state["to"] == "09/30/2026"
    assert isinstance(state["df"], pd.DataFrame)

    restored = DemoSourceTab()
    qtbot.addWidget(restored)
    restored.restore_state(policy, state)

    assert restored.date_from.text() == "09/01/2026"
    assert restored.date_to.text() == "09/30/2026"
    assert restored._status_label.text() == "1 record(s) found."
