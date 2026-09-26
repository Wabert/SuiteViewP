#!/usr/bin/env python3
"""SuiteView packaged entry point."""

from __future__ import annotations

import sys

from suiteview.startup import StartupOptions, run_suiteview


def build_options() -> StartupOptions:
    """Options for the packaged/source module entry point."""

    return StartupOptions(crash_log_name="crash.log")


def main() -> int:
    """Application entry point."""

    return run_suiteview(build_options())


if __name__ == "__main__":
    sys.exit(main())
