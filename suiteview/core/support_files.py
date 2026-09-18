"""Canonical support directories and path-scoped authorization for file browsers.

Copying *out* is read access. Moves/renames must check both endpoints; recursive
deletes must check their target, including ancestors of a protected directory.
Personal files and application settings outside these roots are not restricted.
"""

import os
from pathlib import Path

from suiteview.core.access_control import guard_support_files_writable


def onedrive_directory() -> str:
    return str(Path.home() / "OneDrive - American National Insurance Company")


def process_control_directory() -> str:
    return os.path.join(onedrive_directory(), "Life Product - Process_Control")


def policy_support_directory() -> str:
    return os.path.join(process_control_directory(), "Policy Support")


def abr_support_directory() -> str:
    return os.path.join(
        onedrive_directory(),
        "Life Product - Accelerated_Benefits",
        "Accelerated Death Benefit (ABR11 & ABR14)",
    )


def support_file_roots() -> tuple[str, ...]:
    return policy_support_directory(), abr_support_directory()


def _normalize_path(path: str) -> str:
    normalized = os.path.normcase(os.path.normpath(path))
    if normalized.startswith("\\\\?\\unc\\"):
        return "\\\\" + normalized[8:]
    if normalized.startswith(("\\\\?\\", "\\\\.\\")):
        return normalized[4:]
    return normalized


def _normalized_paths(path: str | os.PathLike) -> set[str]:
    absolute = os.path.abspath(os.fspath(path))
    return {
        _normalize_path(absolute),
        _normalize_path(os.path.realpath(absolute)),
    }


def is_support_file_path(path: str | os.PathLike) -> bool:
    """Whether mutating this path affects a support root, child or ancestor.

    Check both lexical and resolved paths so junctions/symlinks cannot redirect
    a generic file-browser mutation around the canonical-directory restriction.
    """
    if not path:
        return False
    candidates = _normalized_paths(path)
    for root in support_file_roots():
        for candidate in candidates:
            for normalized_root in _normalized_paths(root):
                try:
                    shared = os.path.commonpath((candidate, normalized_root))
                except ValueError:
                    continue  # Different drives.
                if shared in (candidate, normalized_root):
                    return True
    return False


def guard_support_file_paths(
    *paths: str | os.PathLike, action: str = "modify policy support files"
) -> None:
    """Reauthorize only mutations that touch canonical policy-support paths."""
    if any(is_support_file_path(path) for path in paths):
        guard_support_files_writable(action)
