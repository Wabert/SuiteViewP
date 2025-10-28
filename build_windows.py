"""
Build script for creating Windows executable using PyInstaller
Run this on Windows after installing dependencies
"""

import os
import sys
import subprocess

def build_windows_exe():
    """Build Windows executable using PyInstaller"""

    print("=" * 60)
    print("SuiteView Data Manager - Windows Build Script")
    print("=" * 60)

    # Check if PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("\nPyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Build command
    build_cmd = [
        "pyinstaller",
        "--name=SuiteView Data Manager",
        "--windowed",  # No console window
        "--onefile",  # Single executable
        "--icon=resources/icons/app.ico" if os.path.exists("resources/icons/app.ico") else "",
        # Add data files
        "--add-data=suiteview/ui/styles.qss;suiteview/ui",
        # Hidden imports
        "--hidden-import=PyQt6",
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtGui",
        "--hidden-import=PyQt6.QtWidgets",
        "--hidden-import=sqlalchemy.dialects.mssql",
        "--hidden-import=sqlalchemy.dialects.oracle",
        "--hidden-import=sqlalchemy.dialects.postgresql",
        # Entry point
        "suiteview/main.py"
    ]

    # Remove empty icon parameter if no icon exists
    build_cmd = [arg for arg in build_cmd if arg]

    print("\nBuilding executable...")
    print(f"Command: {' '.join(build_cmd)}\n")

    try:
        subprocess.check_call(build_cmd)
        print("\n" + "=" * 60)
        print("Build completed successfully!")
        print("=" * 60)
        print("\nExecutable location: dist/SuiteView Data Manager.exe")
        print("\nYou can now distribute this .exe file to users.")
        print("The .exe is self-contained and doesn't require Python installation.")

    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build_windows_exe()
