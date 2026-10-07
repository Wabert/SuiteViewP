"""Application version and build identity for support traceability.

``app_build_label()`` is written into support exports so a reported number can
be traced to the exact code that produced it. The git commit comes from a ``BUILD_SHA`` file stamped into the
packaged EXE by ``SuiteView.spec``; source runs ask git directly. Either may be
unavailable, in which case the label carries the version alone — never a
guessed commit.
"""
from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

import suiteview

BUILD_SHA_FILENAME = "BUILD_SHA"
_PACKAGE_DIR = Path(suiteview.__file__).resolve().parent


def app_version() -> str:
    return suiteview.__version__


def _stamped_sha(package_dir: Path) -> str:
    try:
        return (package_dir / BUILD_SHA_FILENAME).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def git_sha(repo_dir: Path) -> str:
    """Short HEAD commit of a source checkout, with ``+dirty`` for tracked edits."""
    if not (repo_dir / ".git").exists():
        return ""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"], cwd=repo_dir,
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo_dir,
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    return f"{sha}+dirty" if sha and dirty else sha


@lru_cache(maxsize=1)
def build_sha() -> str:
    """The commit this build came from, or "" when it cannot be determined."""
    return _stamped_sha(_PACKAGE_DIR) or git_sha(_PACKAGE_DIR.parent)


def app_build_label() -> str:
    """``SUITEVIEW 5.2 BUILD fed416a`` (``SUITEVIEW 5.2`` when the commit is unknown)."""
    sha = build_sha()
    return f"SUITEVIEW {app_version()}" + (f" BUILD {sha}" if sha else "")
