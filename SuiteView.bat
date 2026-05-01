@echo off
REM SuiteView - Main Application Launcher
REM Double-click this file to start SuiteView
cd /d "%~dp0"
start "" /D "%~dp0" "%~dp0venv\Scripts\pythonw.exe" "%~dp0scripts\run_suiteview.py"

