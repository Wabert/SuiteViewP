"""Block until a file exists and is non-empty (or a timeout elapses).

Small foreground waiter for orchestrating long background runs (e.g. an Excel
COM comparison writing its JSON result) without shell sleep loops.

Usage:
    venv\\Scripts\\python.exe tools/wait_for_file.py <path> [timeout_seconds]

Exit 0 and print {"ok": true, "size": N} once the file is non-empty; exit 2 on
timeout (default 540 s).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def main() -> int:
    path = Path(sys.argv[1])
    timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 540.0
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if size > 0:
            # Give the writer a moment to finish flushing, then re-stat.
            time.sleep(2.0)
            print(json.dumps({"ok": True, "size": path.stat().st_size}))
            return 0
        time.sleep(5.0)
    print(json.dumps({"ok": False, "error": f"timeout after {timeout}s"}))
    return 2


if __name__ == "__main__":
    sys.exit(main())
