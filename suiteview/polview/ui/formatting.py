"""
Shared formatting utilities for the UI layer.

Centralizes _format_currency, _format_date, _format_amount, and _is_numeric
which were previously duplicated across 8+ widget classes in main_window.py.
"""

import platform
from datetime import datetime, date


# Platform-aware US date format (no leading zero on month)
US_DATE_FMT = "%#m/%d/%Y" if platform.system() == "Windows" else "%-m/%d/%Y"


def format_currency(value, prefix: str = "") -> str:
    """Format a numeric value as currency (e.g. '1,234.56' or '$1,234.56').
    
    Args:
        value: Numeric value, string, or None.
        prefix: Optional prefix like '$'. Default is no prefix.
    
    Returns:
        Formatted string, or '' if value is None/empty.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if s in ("", "None", "Null"):
        return ""
    try:
        return f"{prefix}{float(value):,.2f}"
    except (ValueError, TypeError):
        return s


def format_date(value, output_format: str = None) -> str:
    """Format a date value to a consistent string representation.
    
    Handles datetime objects, date objects, ISO date strings (YYYY-MM-DD),
    and timestamp strings. Returns '' for None/empty/null values.
    
    Args:
        value: Date value (datetime, date, string, or None).
        output_format: strftime format string. Default is US_DATE_FMT (m/d/yyyy).
    
    Returns:
        Formatted date string, or '' if value is None/empty.
    """
    if output_format is None:
        output_format = US_DATE_FMT
    if value is None:
        return ""
    
    # Handle date/datetime objects directly
    if isinstance(value, (datetime, date)):
        return value.strftime(output_format)
    
    s = str(value).strip()
    if s in ("", "None", "Null", "0"):
        return ""
    
    try:
        # Try ISO format first (YYYY-MM-DD with possible timestamp)
        if len(s) >= 10 and "-" in s:
            d = datetime.strptime(s[:10], "%Y-%m-%d")
            return d.strftime(output_format)
        return s
    except (ValueError, TypeError):
        return s


def format_amount(value) -> str:
    """Format a numeric amount — integers without decimals, floats with 2 decimals.
    
    Args:
        value: Numeric value or None.
    
    Returns:
        Formatted string (e.g. '110,000' or '1,234.56'), or '' if None/empty.
    """
    if value is None or str(value).strip() in ("", "None"):
        return ""
    try:
        v = float(value)
        if v == int(v):
            return f"{int(v):,}"
        return f"{v:,.2f}"
    except (ValueError, TypeError):
        return str(value)


def format_rate(value, divisor: float = 1.0, decimals: int = 4, suffix: str = "") -> str:
    """Format a rate/percentage value.
    
    Args:
        value: Rate value or None.
        divisor: Divide by this before formatting (e.g. 100 for basis points).
        decimals: Number of decimal places.
        suffix: Suffix to append (e.g. '%').
    
    Returns:
        Formatted string, or '' if None/empty/zero.
    """
    if value is None or str(value).strip() in ("", "None"):
        return ""
    try:
        rate = float(value) / divisor
        if rate == 0:
            return ""
        return f"{rate:.{decimals}f}{suffix}"
    except (ValueError, TypeError):
        return str(value)


def is_numeric(text: str) -> bool:
    """Check if a string looks like a numeric value (for right-alignment).
    
    Strips currency symbols, commas, and percent signs before checking.
    """
    if not text:
        return False
    cleaned = text.replace(',', '').replace('$', '').replace('%', '').strip()
    try:
        float(cleaned)
        return True
    except ValueError:
        return False
