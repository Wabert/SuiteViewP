#!/usr/bin/env python3
"""Verify SuiteView setup is complete and working"""

import sys
from pathlib import Path

# Add parent directory to path so we can import suiteview
sys.path.insert(0, str(Path(__file__).parent.parent))


def check_file_exists(path: Path, description: str) -> bool:
    """Check if a file exists"""
    if path.exists():
        print(f"✓ {description}: {path}")
        return True
    else:
        print(f"✗ {description}: {path} NOT FOUND")
        return False


def check_directory_exists(path: Path, description: str) -> bool:
    """Check if a directory exists"""
    if path.is_dir():
        print(f"✓ {description}: {path}/")
        return True
    else:
        print(f"✗ {description}: {path}/ NOT FOUND")
        return False


def verify_imports() -> bool:
    """Verify key modules can be imported"""
    print("\n=== Verifying Python Imports ===")
    imports = [
        ("PyQt6", "PyQt6.QtWidgets"),
        ("SQLAlchemy", "sqlalchemy"),
        ("Pandas", "pandas"),
        ("Cryptography", "cryptography"),
        ("Database module", "suiteview.data.database"),
        ("Config module", "suiteview.utils.config"),
        ("Logger module", "suiteview.utils.logger"),
        ("Main window", "suiteview.ui.main_window"),
    ]

    all_ok = True
    for name, module in imports:
        try:
            __import__(module)
            print(f"✓ {name} imports successfully")
        except ImportError as e:
            print(f"✗ {name} import failed: {e}")
            all_ok = False

    return all_ok


def verify_database() -> bool:
    """Verify database is initialized"""
    print("\n=== Verifying Database ===")
    try:
        from suiteview.data.database import get_database
        db = get_database()

        expected_tables = [
            'connections',
            'saved_tables',
            'table_metadata',
            'column_metadata',
            'unique_values_cache',
            'saved_queries',
            'user_preferences'
        ]

        cursor = db.execute('SELECT name FROM sqlite_master WHERE type="table"')
        tables = [row[0] for row in cursor.fetchall()]

        all_ok = True
        for table in expected_tables:
            if table in tables:
                print(f"✓ Table '{table}' exists")
            else:
                print(f"✗ Table '{table}' missing")
                all_ok = False

        print(f"\nDatabase location: {db.db_path}")
        return all_ok
    except Exception as e:
        print(f"✗ Database verification failed: {e}")
        return False


def main():
    """Run all verification checks"""
    print("=" * 60)
    print("SuiteView Data Manager - Setup Verification")
    print("=" * 60)

    # Check project structure
    print("\n=== Verifying Project Structure ===")
    base_path = Path(__file__).parent.parent  # Go up from scripts/ to project root

    checks = []

    # Main files
    checks.append(check_file_exists(base_path / "requirements.txt", "Requirements file"))
    checks.append(check_file_exists(base_path / "setup.py", "Setup file"))
    checks.append(check_file_exists(base_path / "run_windows.bat", "Run script"))
    checks.append(check_file_exists(base_path / "README.md", "README"))

    # Directories
    checks.append(check_directory_exists(base_path / "venv_window", "Virtual environment"))
    checks.append(check_directory_exists(base_path / "suiteview", "Main package"))
    checks.append(check_directory_exists(base_path / "suiteview" / "ui", "UI package"))
    checks.append(check_directory_exists(base_path / "suiteview" / "core", "Core package"))
    checks.append(check_directory_exists(base_path / "suiteview" / "data", "Data package"))
    checks.append(check_directory_exists(base_path / "suiteview" / "utils", "Utils package"))
    checks.append(check_directory_exists(base_path / "scripts", "Scripts directory"))
    checks.append(check_directory_exists(base_path / "tests", "Tests directory"))
    checks.append(check_directory_exists(base_path / "docs", "Docs directory"))

    # Key Python files
    checks.append(check_file_exists(base_path / "suiteview" / "main.py", "Main entry point"))
    checks.append(check_file_exists(base_path / "suiteview" / "ui" / "main_window.py", "Main window"))
    checks.append(check_file_exists(base_path / "suiteview" / "ui" / "styles.qss", "Stylesheet"))
    checks.append(check_file_exists(base_path / "suiteview" / "data" / "database.py", "Database module"))
    checks.append(check_file_exists(base_path / "suiteview" / "utils" / "config.py", "Config module"))
    checks.append(check_file_exists(base_path / "suiteview" / "utils" / "logger.py", "Logger module"))

    # Screen files
    checks.append(check_file_exists(base_path / "suiteview" / "ui" / "connections_screen.py", "Connections screen"))
    checks.append(check_file_exists(base_path / "suiteview" / "ui" / "mydata_screen.py", "My Data screen"))
    checks.append(check_file_exists(base_path / "suiteview" / "ui" / "dbquery_screen.py", "DB Query screen"))
    checks.append(check_file_exists(base_path / "suiteview" / "ui" / "xdbquery_screen.py", "XDB Query screen"))

    # Verify imports
    checks.append(verify_imports())

    # Verify database
    checks.append(verify_database())

    # Summary
    print("\n" + "=" * 60)
    total = len(checks)
    passed = sum(checks)

    if passed == total:
        print(f"✓ ALL CHECKS PASSED ({passed}/{total})")
        print("=" * 60)
        print("\nSetup is complete and ready!")
        print("\nTo run the application:")
        print("  run_windows.bat")
        print("\nOr:")
        print("  .\\venv_window\\Scripts\\Activate.ps1")
        print("  python -m suiteview.main")
        return 0
    else:
        print(f"✗ SOME CHECKS FAILED ({passed}/{total} passed)")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
