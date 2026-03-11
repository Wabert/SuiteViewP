"""
SuiteView Tests Package

This module sets up the Python path to allow importing from the suiteview package.
"""
import sys
from pathlib import Path

# Add parent directory to path so tests can import suiteview
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
