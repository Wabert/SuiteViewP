"""Shared JSON file persistence.

Many SuiteView modules persist small dicts/lists to disk as JSON (bookmarks,
saved queries, column widths, window/settings state). Historically each site
re-implemented the same load/save logic with inconsistent handling of three
hazards:

* the file not existing yet (first run),
* the file being corrupt (truncated / invalid JSON),
* a crash mid-write leaving a half-written, unreadable file.

This module centralises that. ``read_json`` returns a default instead of
raising on a missing or corrupt file; ``write_json`` writes atomically
(temp file in the same directory, then ``os.replace``) so a crash can never
leave a partially written file in place, and creates parent directories as
needed.

``JsonStore`` is a thin convenience wrapper binding a single path to those
two functions.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, Union

logger = logging.getLogger(__name__)

PathLike = Union[str, os.PathLike]


def ensure_dir(path: PathLike) -> Path:
    """Create ``path`` as a directory and return it as a ``Path``."""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def safe_filename(name: str) -> str:
    """Convert a SuiteView user label to the legacy safe filename form."""
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def read_json(path: PathLike, default: Any = None) -> Any:
    """Load JSON from ``path``.

    Returns ``default`` if the file does not exist or cannot be parsed
    (logging a warning in the corrupt-file case). Never raises for a missing
    or malformed file — callers get the default and carry on.
    """
    p = Path(path)
    if not p.exists():
        return default
    try:
        with p.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read JSON from %s: %s", p, e)
        return default


def write_file_atomic(path: PathLike, write_to_temp: Callable[[Path], None]) -> None:
    """Run ``write_to_temp`` against a same-directory temp file, then replace."""
    p = Path(path)
    ensure_dir(p.parent)

    fd, tmp_name = tempfile.mkstemp(
        dir=str(p.parent), prefix=f".{p.name}.", suffix=".tmp")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        write_to_temp(tmp)
        with tmp.open("r+b") as fh:
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            logger.debug("Could not remove failed atomic-write temp file %s", tmp, exc_info=True)
        raise


def write_text_atomic(
    path: PathLike,
    text: str,
    *,
    encoding: str = "utf-8",
) -> None:
    """Atomically write text to ``path``."""
    write_file_atomic(path, lambda tmp: tmp.write_text(text, encoding=encoding))


def write_json(
    path: PathLike,
    data: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> None:
    """Atomically write ``data`` as JSON to ``path``.

    Creates parent directories if needed. Writes to a temp file in the same
    directory and ``os.replace``s it into place, so a crash mid-write leaves
    the previous file intact rather than a truncated one.
    """
    def write_to_temp(tmp: Path) -> None:
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=indent, ensure_ascii=ensure_ascii)
            fh.flush()
            os.fsync(fh.fileno())

    write_file_atomic(path, write_to_temp)


class JsonStore:
    """A JSON file bound to a path, with safe reads and atomic writes.

    Usage::

        store = JsonStore(path, default={})
        data = store.load()
        data["x"] = 1
        store.save(data)
    """

    def __init__(self, path: PathLike, *, default: Any = None, indent: int = 2):
        self.path = Path(path)
        self._default = default
        self._indent = indent

    def load(self) -> Any:
        """Return the file's contents, or a fresh copy of the default."""
        default = self._default
        if isinstance(default, (dict, list)):
            default = copy.deepcopy(default)  # don't hand out the shared default
        return read_json(self.path, default)

    def save(self, data: Any) -> None:
        write_json(self.path, data, indent=self._indent)

    def exists(self) -> bool:
        return self.path.exists()
