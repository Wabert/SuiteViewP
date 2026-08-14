# -*- mode: python ; coding: utf-8 -*-
"""
SuiteViewLight Distribution Build Spec
========================================
Builds SuiteViewLight as a one-folder distribution — a trimmed, READ-ONLY
edition for the business area.

Included tools:
  - PolView, FileNav, ABR Quote
  - Audit / Query Tool (READ-ONLY: no Find & Register Unique Values, no registry
    or rate-table writes)
  - View Screenshots, App Data Location (Tools menu)

Read-only behaviour is enforced at runtime by suiteview/core/build_env.py
(is_light_build / is_data_read_only), which keys off the SuiteViewLight EXE name.

Excludes: LLM Agent (copilot, markdown), Rate Manager, Mainframe Navigator,
          ScratchPad, Email Attachments, RERUN illustration.

Usage:
  python -m PyInstaller SuiteViewLight.spec
"""

import os
import sys
from pathlib import Path

# Bundle every captured policy-record screen definition so the Policy Record
# viewer has its static schema at runtime (otherwise it reports "live data
# unavailable" even when DB2 data is present).
_POLICY_RECORD_SCREEN_DATAS = [
    (str(p), 'suiteview/polview/data/policy_record_screens')
    for p in Path('suiteview/polview/data/policy_record_screens').glob('*.json')
]


a = Analysis(
    ['suiteview\\main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # UI stylesheet
        ('suiteview/ui/styles.qss', 'suiteview/ui'),
        # PolView reference data (JSON lookup files)
        ('suiteview/polview/data/benefits.json', 'suiteview/polview/data'),
        ('suiteview/polview/data/ckaptb32_mortality_tables.json', 'suiteview/polview/data'),
        ('suiteview/polview/data/official_plancode_table.json', 'suiteview/polview/data'),
        ('suiteview/polview/data/policy_record_db2_tables.json', 'suiteview/polview/data'),
        # PolView config
        ('suiteview/polview/config/field_tooltips.json', 'suiteview/polview/config'),
        # Audit Tool assets (checkmark glyph used by styled checkboxes)
        ('suiteview/audit/tabs/_checkmark.png', 'suiteview/audit/tabs'),
        # Illustration / GLP Exception plancode and rate data
        ('suiteview/illustration/plancodes/plancode_table.json', 'suiteview/illustration/plancodes'),
        ('suiteview/illustration/plancodes/tRates_CORR.json', 'suiteview/illustration/plancodes'),
        ('suiteview/illustration/plancodes/tRates_IntBonus.json', 'suiteview/illustration/plancodes'),
        ('suiteview/illustration/plancodes/tRates_MDBR.json', 'suiteview/illustration/plancodes'),
        # Policy Record viewer captured screen definitions (seg_<n>.json)
        *_POLICY_RECORD_SCREEN_DATAS,
    ],
    hiddenimports=[
        'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
        'sqlalchemy.dialects.mssql',
        'sqlalchemy.dialects.oracle',
        'sqlalchemy.dialects.postgresql',
        'pyodbc',
        'duckdb',
        'openpyxl',
        'win32com',
        'win32com.client',
        'win32com.client.dynamic',
        'win32api',
        'win32gui',
        'win32con',
        # Audit / Query Tool (read-only) — imported lazily via
        # `from suiteview.audit import launch_audit`, so PyInstaller needs these
        # spelled out or the tool is missing from the Light build.
        'suiteview.audit',
        'suiteview.audit.audit_window',
        'suiteview.audit.main',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt5', 'PySide6', 'PySide2',
        # Exclude dev-only modules from the distribution
        'pytest', 'black', 'flake8',
        # Exclude the LLM Agent stack (not in Light)
        'copilot', 'markdown',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # One-folder mode (fast startup)
    name='SuiteViewLight',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,            # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,                # TODO: Add SuiteView icon (.ico file) here
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SuiteViewLight',
)
