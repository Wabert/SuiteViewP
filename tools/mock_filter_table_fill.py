"""Render FilterTableView with underfilling columns to verify the trailing
strip looks right after removing stretch-last-section.

Renders two variants — stock style and the Illustration ledger style — into
one PNG at ~/.suiteview/mock_filter_table_fill.png for visual inspection.

Usage:
    venv\\Scripts\\python.exe tools/mock_filter_table_fill.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    import pandas as pd
    from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

    app = QApplication.instance() or QApplication(sys.argv)

    from suiteview.ui.widgets.filter_table_view import FilterTableView

    df = pd.DataFrame({
        "Date": [f"2026-{m:02d}-09" for m in range(1, 13)],
        "Year": [7] * 12,
        "Month": list(range(1, 13)),
        "GP Limit Reached": [0.0] * 12,
        "Exc Prem Gross": [0.0] * 12,
        "Exception Prem": [0.0] * 12,
    })

    host = QWidget()
    host.setStyleSheet("background-color: #EDE7F6;")
    layout = QVBoxLayout(host)

    stock = FilterTableView()
    stock.set_dataframe(df)
    layout.addWidget(stock)

    ledger = FilterTableView()
    ledger.apply_ledger_style()
    ledger.set_dataframe(df)
    ledger.autofit_columns_to_data()
    layout.addWidget(ledger)

    host.resize(900, 560)
    host.show()
    app.processEvents()

    out = Path.home() / ".suiteview" / "mock_filter_table_fill.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    host.grab().save(str(out))
    print(f"saved {out}")


if __name__ == "__main__":
    main()
