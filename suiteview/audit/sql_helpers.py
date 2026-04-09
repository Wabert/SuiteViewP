"""
Shared SQL helper functions used by both CyberLife and TAI query builders.
"""
from __future__ import annotations

from datetime import date


def fmt_time(secs: float) -> str:
    """Format seconds as HH:MM:SS."""
    m, s = divmod(int(secs), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def today_str() -> str:
    """Return today's date as yyyy-mm-dd for DB2 MONTHS_BETWEEN."""
    return date.today().strftime("%Y-%m-%d")


def esc(val: str) -> str:
    """Escape single quotes for SQL."""
    return val.replace("'", "''")


def selected_codes(listbox) -> list[str]:
    """Extract the code portion from selected listbox items.

    Handles formats like:
      '21-Premium Paying'       → '21'
      '0 - Traditional ...'     → '0'
      'A - New Business ...'    → 'A'
      'AL'                      → 'AL'
    """
    codes = []
    for item in listbox.selectedItems():
        text = item.text()
        if " - " in text:
            codes.append(text.split(" - ", 1)[0].strip())
        elif "-" in text:
            codes.append(text.split("-", 1)[0].strip())
        else:
            codes.append(text.strip())
    return codes


def in_list(codes: list[str]) -> str:
    """Build a SQL IN value list: 'A', 'B', 'C'."""
    return ", ".join(f"'{esc(c)}'" for c in codes)


def add_int_range(wheres: list, column: str, lo_widget, hi_widget):
    """Append integer >= / <= clauses if the range widgets have values."""
    lo = lo_widget.text().strip()
    hi = hi_widget.text().strip()
    if lo and lo.lstrip("-").isdigit():
        wheres.append(f"{column} >= {int(lo)}")
    if hi and hi.lstrip("-").isdigit():
        wheres.append(f"{column} <= {int(hi)}")


def add_date_range(wheres: list, column: str, lo_widget, hi_widget):
    """Append date >= / <= clauses if the range widgets have values."""
    lo = lo_widget.text().strip()
    hi = hi_widget.text().strip()
    if lo:
        wheres.append(f"{column} >= '{esc(lo)}'")
    if hi:
        wheres.append(f"{column} <= '{esc(hi)}'")


def add_decimal_range(wheres: list, column: str, lo_widget, hi_widget):
    """Append numeric >= / <= clauses if the range widgets have values."""
    lo = lo_widget.text().strip()
    hi = hi_widget.text().strip()
    try:
        if lo:
            wheres.append(f"{column} >= {float(lo)}")
    except ValueError:
        pass
    try:
        if hi:
            wheres.append(f"{column} <= {float(hi)}")
    except ValueError:
        pass
