"""
SuiteView Distribution Builder
================================
Builds SuiteView into a distributable folder with all required data files.

Steps:
  1. Cleans previous build artifacts
  2. Runs PyInstaller with SuiteView.spec
  3. Creates a ZIP archive for easy distribution

Usage:
  python scripts/build_distribution.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)

# ── Configuration ───────────────────────────────────────────────────────

SPEC_FILE = PROJECT_ROOT / "SuiteView.spec"
DIST_DIR = PROJECT_ROOT / "dist"
DIST_NAME = "SuiteView"

# ── Resolve venv Python ────────────────────────────────────────────────
# PyInstaller MUST run under the venv interpreter so that it discovers
# venv-installed packages (PyQt6, sqlalchemy, etc.).  If the build script
# is accidentally launched with the system Python, sys.executable won't
# have those packages and the resulting EXE will fail at runtime with
# "No module named 'PyQt6'".
#
# Resolution order:
#   1. venv/Scripts/python.exe  (relative to project root)
#   2. sys.executable           (fallback — assumes caller used the venv)

_venv_python = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
if _venv_python.exists():
    PYTHON_EXE = str(_venv_python)
else:
    PYTHON_EXE = sys.executable
    print(f"  ⚠ venv not found at {_venv_python}, falling back to {PYTHON_EXE}")


def step(msg: str):
    """Print a build step."""
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}\n")


def main():
    print(r"""
    ╔═══════════════════════════════════════════╗
    ║      SuiteView Distribution Builder       ║
    ╚═══════════════════════════════════════════╝
    """)

    print(f"  Using Python: {PYTHON_EXE}")
    
    # ── Step 1: Clean previous build ───────────────────────────────
    step("Step 1: Cleaning previous build artifacts")
    
    build_dir = PROJECT_ROOT / "build" / DIST_NAME
    dist_output = DIST_DIR / DIST_NAME
    
    if build_dir.exists():
        print(f"  Removing {build_dir}")
        shutil.rmtree(build_dir, ignore_errors=True)
    
    if dist_output.exists():
        print(f"  Removing {dist_output}")
        shutil.rmtree(dist_output, ignore_errors=True)
    
    print("  ✓ Clean")
    
    # ── Step 2: Run PyInstaller ─────────────────────────────────────
    step("Step 2: Building with PyInstaller")
    
    cmd = [
        PYTHON_EXE, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        str(SPEC_FILE),
    ]
    
    print(f"  Running: {' '.join(cmd)}")
    print()
    
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    
    if result.returncode != 0:
        print("\n  ✗ PyInstaller build FAILED!")
        sys.exit(1)
    
    print("\n  ✓ PyInstaller build succeeded")
    
    # ── Step 3: Create ZIP archive ─────────────────────────────────
    step("Step 3: Creating distribution ZIP")
    
    zip_path = DIST_DIR / f"{DIST_NAME}"
    
    if dist_output.exists():
        print(f"  Creating: {zip_path}.zip")
        shutil.make_archive(str(zip_path), 'zip', str(dist_output))
        
        # Get sizes
        zip_file = Path(f"{zip_path}.zip")
        folder_size = sum(f.stat().st_size for f in dist_output.rglob("*") if f.is_file())
        
        print(f"  ✓ ZIP created: {zip_file}")
        print(f"    Folder size: {folder_size / 1024 / 1024:.1f} MB")
        print(f"    ZIP size:    {zip_file.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        print("  ⚠ Distribution folder not found, skipping ZIP")
    
    # ── Done ───────────────────────────────────────────────────────
    print(f"""
    ╔═══════════════════════════════════════════════════════╗
    ║                  BUILD COMPLETE!                      ║
    ╠═══════════════════════════════════════════════════════╣
    ║                                                       ║
    ║  Distribution folder: dist/{DIST_NAME}/               ║
    ║  ZIP archive:         dist/{DIST_NAME}.zip            ║
    ║                                                       ║
    ║  To distribute:                                       ║
    ║  1. Send the ZIP to coworkers                         ║
    ║  2. They extract it to any folder                     ║
    ║  3. Run SuiteView.exe                                 ║
    ║                                                       ║
    ║  Requirements for coworkers:                          ║
    ║  • Windows 10/11                                      ║
    ║  • DB2 ODBC driver (for PolView)                      ║
    ║  • UL_Rates ODBC DSN (for ABR Quote)                  ║
    ║  • Network access to DB2 mainframe (for PolView)      ║
    ║                                                       ║
    ╚═══════════════════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    main()
