"""
Rate Manager — IAF Rate File Converter & Reformatter

Converts Cyberlife mainframe IAF (Issue Age Factor) fixed-width text files
into structured Excel spreadsheets and UL_Rates database CSV files.
"""

from suiteview.ratemanager.parser import IAFParser, ParseResult
from suiteview.ratemanager.exporter import IAFExporter
from suiteview.ratemanager.rate_reformatter import RateReformatter, ReformatResult
from suiteview.ratemanager.ckultb04_exporter import export_raw, export_table
from suiteview.ratemanager.benefit_exporter import (
    list_benefit_codes, benefit_summary, export_benefit_table,
)
from suiteview.ratemanager.benefit_db import (
    BenefitDBSpec, build_benefit_db, export_benefit_db,
)
from suiteview.ratemanager.ckultb04_db import CKULTB04DBSpec, build_ckultb04_db
from suiteview.ratemanager import mpf_exporter
from suiteview.ratemanager.ratemanager_window import RateManagerWindow

__all__ = [
    'IAFParser', 'ParseResult', 'IAFExporter',
    'RateReformatter', 'ReformatResult', 'RateManagerWindow',
    'export_raw', 'export_table',
    'list_benefit_codes', 'benefit_summary', 'export_benefit_table',
    'BenefitDBSpec', 'build_benefit_db', 'export_benefit_db',
    'CKULTB04DBSpec', 'build_ckultb04_db',
    'mpf_exporter',
]
