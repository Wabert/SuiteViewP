@echo off
REM ============================================================
REM  Launch standalone PolView from THIS folder's code (live DB2).
REM  Used by the "PolView (UX preview)" desktop shortcut to try a
REM  branch checked out in a worktree. Optional: policy number.
REM ============================================================
setlocal
cd /d "%~dp0"

REM --- Locate the venv Python (worktree first, then main repo) ---
set "PY=%~dp0venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%~dp0..\SuiteViewP\venv\Scripts\python.exe"

if not exist "%PY%" (
    echo Could not find the venv Python interpreter.
    echo Looked for:
    echo   %~dp0venv\Scripts\python.exe
    echo   %~dp0..\SuiteViewP\venv\Scripts\python.exe
    echo.
    pause
    exit /b 1
)

REM --- Live data only ---
set "SUITEVIEW_LOCAL_DATA="

for /f "delims=" %%B in ('git -C "%~dp0." branch --show-current 2^>nul') do set "BRANCH=%%B"
echo PolView from %~dp0  (branch: %BRANCH%)
echo This window shows log messages; closing it closes PolView.

"%PY%" "%~dp0scripts\run_polview.py" %*

if errorlevel 1 (
    echo.
    echo PolView exited with an error ^(see messages above^).
    pause
)
endlocal
