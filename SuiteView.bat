@echo off
cd /d "%~dp0"
.\venv_window\Scripts\python.exe -c "import sys; sys.path.insert(0, '.'); from suiteview.main import main; main()"
