@echo off
REM ============================================================
REM  Launch SuiteView Illustration against LIVE production data
REM  (DB2 / UL_Rates). Double-click to run. No local SQLite.
REM ============================================================
setlocal
cd /d "%~dp0"

REM --- Locate the venv Python (worktree first, then main repo) ---
set "PY=%~dp0venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%~dp0..\..\SuiteViewP\venv\Scripts\python.exe"

if not exist "%PY%" (
    echo Could not find the venv Python interpreter.
    echo Looked for:
    echo   %~dp0venv\Scripts\python.exe
    echo   %~dp0..\..\SuiteViewP\venv\Scripts\python.exe
    echo.
    pause
    exit /b 1
)

REM --- Make sure LOCAL mode is OFF so we hit the live database ---
set "SUITEVIEW_LOCAL_DATA="

"%PY%" "%~dp0scripts\run_illustration_live.py" %*

REM --- Keep the window open if the app exited with an error ---
if errorlevel 1 (
    echo.
    echo The Illustration app exited with an error ^(see messages above^).
    pause
)
endlocal
