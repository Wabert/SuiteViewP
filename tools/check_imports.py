"""Import the given modules and report success/failure.

Catches import-time errors (bad symbols, missing names, signature typos in class
bodies) without constructing any Qt widgets — defining a QWidget subclass needs
no QApplication, so this runs headless on the minipc.

    venv\\Scripts\\python.exe tools/check_imports.py '["pkg.mod_a", "pkg.mod_b"]'
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    os.environ.setdefault("SUITEVIEW_LOCAL_DATA", "1")
    modules = json.loads(sys.argv[1]) if len(sys.argv) > 1 else []
    failures = 0
    for name in modules:
        try:
            importlib.import_module(name)
            print(f"  ok  {name}")
        except Exception as exc:  # noqa: BLE001 — we want every failure surfaced
            failures += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(modules) - failures}/{len(modules)} imported")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
