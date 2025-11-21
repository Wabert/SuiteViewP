# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for SuiteView Data Manager
Creates a standalone Windows executable
"""

block_cipher = None

a = Analysis(
    ['suiteview/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('suiteview/ui/styles.qss', 'suiteview/ui'),
    ],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'sqlalchemy',
        'sqlalchemy.dialects.mssql',
        'sqlalchemy.dialects.oracle',
        'sqlalchemy.dialects.postgresql',
        'sqlalchemy.dialects.sqlite',
        'pandas',
        'openpyxl',
        'cryptography',
        'cryptography.fernet',
        'pyodbc',
        'ibm_db',
        'ibm_db_dbi',
        'win32com.client',
        'win32com.client.dynamic',
        'pythoncom',
        'pywintypes',
        'win32api',
        'win32con',
        'duckdb',
        'xlsxwriter',
        'paramiko',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'IPython',
        'jupyter',
        'notebook',
        'PIL',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SuiteView Data Manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you have one
)
