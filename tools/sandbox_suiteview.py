"""Spin up an isolated sandbox copy of ~/.suiteview for testing.

Usage (from repo root, venv active):

    # 1. Make a sandbox copy of your real data
    python tools/sandbox_suiteview.py copy

    # 2. (optional) Simulate an identity migration: re-stamp every query's id
    #    while keeping its name — this is what used to dump groups into Commons.
    python tools/sandbox_suiteview.py churn

    # 3. Launch the audit tool against the sandbox (your real data untouched)
    python tools/sandbox_suiteview.py run

Open the Object Browser after step 3: with the fix, queries you had in groups
stay in their groups even after the churn in step 2.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SANDBOX = Path(tempfile.gettempdir()) / "suiteview_sandbox_home"
REAL = Path.home() / ".suiteview"


def _copy() -> None:
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    (SANDBOX / ".suiteview").parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(REAL, SANDBOX / ".suiteview")
    print(f"Sandbox copy ready: {SANDBOX / '.suiteview'}")


def _churn() -> None:
    objs = SANDBOX / ".suiteview" / "query_objects"
    n = 0
    for path in list(objs.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        old = data.get("id")
        if not old:
            continue
        # forge-owned copies are handled separately by reconcile — skip them
        if isinstance(data.get("config"), dict) and "dataforge" in data["config"]:
            continue
        new_id = os.urandom(16).hex()
        data["id"] = new_id
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        path.rename(objs / f"{path.stem.rsplit('__', 1)[0]}__{new_id[:8]}.json")
        n += 1
    print(f"Re-stamped {n} query ids (names unchanged).")


def _run() -> None:
    env = dict(os.environ)
    env["USERPROFILE"] = str(SANDBOX)
    env["HOME"] = str(SANDBOX)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    subprocess.run([sys.executable, "scripts/run_audit.py"], env=env)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "copy"
    {"copy": _copy, "churn": _churn, "run": _run}[cmd]()
