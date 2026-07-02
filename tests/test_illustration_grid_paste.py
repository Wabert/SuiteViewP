"""Grid Inputs clipboard paste (headless Qt).

Every Grid Inputs table (ExcelTableWidget) offers a right-click "Paste from
Clipboard" that writes a tab-separated Excel range starting at the clicked
cell. The table grows to fit; the paste is capped at 2,000 rows.
"""
import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.models.input_set import TransactionKind
from suiteview.illustration.ui.inputs_tab import ExcelTableWidget, IllustrationInputsTab

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _tab() -> IllustrationInputsTab:
    _app()
    return IllustrationInputsTab()


def test_paste_starts_at_the_clicked_row():
    tab = _tab()
    table = tab.loan_repayment_table
    table.paste_text("06/09/2026\t100.00\n07/09/2026\t200.00", start_row=5)

    assert table.item(5, 0).text() == "06/09/2026"
    assert table.item(5, 1).text() == "100.00"
    assert table.item(6, 0).text() == "07/09/2026"
    assert table.item(6, 1).text() == "200.00"
    # Rows before the clicked row are untouched.
    assert table.item(4, 0).text() == ""


def test_paste_grows_the_table_and_new_rows_match_the_originals():
    tab = _tab()
    table = tab.unscheduled_premium_table
    assert table.rowCount() == 100

    text = "\n".join(f"06/09/{2026 + i}\t{i}.00" for i in range(150))
    table.paste_text(text, start_row=0)

    assert table.rowCount() == 150
    assert table.item(149, 0).text() == "06/09/2175"
    assert table.item(149, 1).text() == "149.00"
    assert table.rowHeight(149) == 20


def test_paste_caps_at_2000_rows():
    tab = _tab()
    table = tab.specific_loan_table

    text = "\n".join(f"06/09/2026\t{i}" for i in range(2_500))
    table.paste_text(text, start_row=0)

    assert ExcelTableWidget.MAX_PASTE_ROWS == 2_000
    assert table.rowCount() == 2_000
    assert table.item(1_999, 1).text() == "1999"


def test_paste_drops_columns_past_the_table_edge():
    tab = _tab()
    table = tab.loan_repayment_table  # Date | Amount — two columns
    table.paste_text("06/09/2026\t100.00\tEXTRA", start_row=0)

    assert table.item(0, 0).text() == "06/09/2026"
    assert table.item(0, 1).text() == "100.00"


def test_paste_starting_at_a_later_column():
    tab = _tab()
    table = tab.withdrawal_table  # Date | Amount | Type
    table.paste_text("250.00\tGross", start_row=3, start_col=1)

    assert table.item(3, 0).text() == ""
    assert table.item(3, 1).text() == "250.00"
    assert table.item(3, 2).text() == "Gross"


def test_pasted_rows_export_as_transactions():
    tab = _tab()
    tab.loan_repayment_table.paste_text("06/09/2026\t100.00\n07/09/2026\t200.00", start_row=0)

    repayments = [
        t for t in tab.export_input_set().dated_transactions
        if t.kind == TransactionKind.LOAN_REPAYMENT
    ]
    assert [(t.effective_date, t.amount) for t in repayments] == [
        (date(2026, 6, 9), 100.0),
        (date(2026, 7, 9), 200.0),
    ]
