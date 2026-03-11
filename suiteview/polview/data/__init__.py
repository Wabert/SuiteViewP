"""
PolView - Data lookup package.
JSON-backed reference data for mortality tables, plancodes, benefits, etc.
"""

from .lookup import DataLookup

# Singleton instance - loaded once, used everywhere
lookup = DataLookup()
