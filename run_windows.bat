@echo off
REM SuiteView Data Manager - Windows Launcher
REM Double-click this file to run the application

echo ============================================================
echo SuiteView Data Manager - Starting...
echo ============================================================
echo.

REM Check if virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo Virtual environment not found. Creating...
    python -m venv venv
    echo.
    echo Installing dependencies...
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
    echo.
    echo Setup complete!
    echo.
) else (
    call venv\Scripts\activate.bat
)

REM Run the application
echo Starting SuiteView Data Manager...
echo.
python -m suiteview.main

REM If the script exits with an error, pause to show the error message
if errorlevel 1 (
    echo.
    echo ============================================================
    echo ERROR: Application failed to start
    echo ============================================================
    echo.
    echo Please check:
    echo  - Python is installed (python --version)
    echo  - All dependencies are installed (pip install -r requirements.txt)
    echo.
    pause
)
