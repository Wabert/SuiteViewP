"""
Shared mechanics for CyberLife "ONLINE TABLES LIST" report files
(CKULTB01, CKULTB04, ...).

These reports are mainframe prints with ASA carriage control in column 1
('1' = new page, '0' = section header), a self-describing argument/function
dictionary at the top, dashed separator rows, and two-physical-line data
records. This module owns the streaming loop with progress reporting; each
table's parser supplies its own skip/record logic.
"""

from __future__ import annotations

import os
import re
from typing import Callable, Iterator, Optional

DASHES_RE = re.compile(r"^[\s\-]+$")
DATE_RE = re.compile(r"\d{2}/\d{2}/\d{4}$")


def iter_report_lines(
    input_path: str,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> Iterator[str]:
    """Stream lines from a report file, reporting 0.0-1.0 progress.

    Reads via ``readline()`` rather than the file iterator protocol — the
    iterator disables ``fh.tell()`` ("telling position disabled by next()
    call"), which is needed for progress on 100 MB+ files.
    """
    size = os.path.getsize(input_path) or 1
    lines_seen = 0
    with open(input_path, "r", encoding="utf-8", errors="replace") as fh:
        while True:
            line = fh.readline()
            if not line:
                break
            lines_seen += 1
            if progress_cb is not None and (lines_seen & 0x3FFF) == 0:
                progress_cb(min(fh.tell() / size, 1.0))
            yield line
    if progress_cb is not None:
        progress_cb(1.0)
