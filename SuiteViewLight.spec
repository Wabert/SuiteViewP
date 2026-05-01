# -*- mode: python ; coding: utf-8 -*-
"""
SuiteViewLight Distribution Build Spec
========================================
Builds SuiteViewLight as a one-folder distribution with only core tools:
  - PolView, FileNav, ABR Quote
  - View Screenshots, App Data Location (Tools menu)

Excludes: Audit Tool, ScratchPad, Mainframe Navigator, Email Attachments,
          Task Tracker, Rate File Converter, messaging, duckdb, markdown

Usage:
  python -m PyInstaller SuiteViewLight.spec
"""

import os
import sys


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
    ],
    hiddenimports=[
        'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
        'sqlalchemy.dialects.mssql',
        'sqlalchemy.dialects.oracle',
        'sqlalchemy.dialects.postgresql',
        'pyodbc',
        'openpyxl',
        'win32com',
        'win32com.client',
        'win32com.client.dynamic',
        'win32api',
        'win32gui',
        'win32con',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt5', 'PySide6', 'PySide2',
        # Exclude dev-only modules from the distribution
        'pytest', 'black', 'flake8',
        # Exclude modules not needed in Light build
        'duckdb', 'markdown',
        'suiteview.messaging',
        'suiteview.messaging.message_service',
        'suiteview.messaging.inbox_widget',
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
