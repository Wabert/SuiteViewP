"""SuiteView script launcher for live and LOCAL DATA modes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.startup import StartupOptions, run_suiteview  # noqa: E402


def build_options(local_data: bool = False) -> StartupOptions:
    """Build startup options for this script entry point."""

    return StartupOptions(local_data=local_data)


def main(local_data: bool = False) -> int:
    """Launch SuiteView through the canonical startup path."""

    return run_suiteview(build_options(local_data=local_data))


if __name__ == "__main__":
    sys.exit(main())
