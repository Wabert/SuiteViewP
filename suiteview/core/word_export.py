"""Shared "open in Word" helper.

SuiteView's convention (see Agent.md, the "Dump to Excel" section) is that an
"Export" button produces a document and opens it in a visible Office instance
for the user to work with — it does not silently save a final file to a chosen
path. For Word we build the ``.docx`` with ``python-docx`` (rich, reliable
formatting) into a temporary file, then hand that file to a visible Word
instance via COM so the user can review, tweak, and Save-As if they wish.

This module owns the fragile COM lifecycle in one place. Callers build their own
document (with ``python-docx``) and delegate the "make it pop up in Word" step
here.

Typical use::

    from suiteview.core.word_export import open_in_word, WordExportError

    doc.save(tmp_path)              # python-docx Document
    try:
        open_in_word(tmp_path)
    except WordExportError as e:
        QMessageBox.warning(self, "Word Error", str(e))

Dynamic dispatch is used deliberately: it bypasses the ``win32com`` ``gen_py``
static cache, a frequent source of COM corruption errors.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class WordExportError(Exception):
    """Raised when a Word COM export cannot be completed."""


def open_in_word(path: str, visible: bool = True):
    """Open an existing ``.docx`` file in a visible Word instance via COM.

    Args:
        path: Absolute path to the ``.docx`` file to open.
        visible: Whether the Word window should be shown (default True).

    Returns:
        The Word ``Document`` COM object (kept alive by Word itself).

    Raises:
        WordExportError: If ``win32com`` is unavailable or Word cannot open
            the file.
    """
    if not os.path.isfile(path):
        raise WordExportError(f"Document not found: {path}")

    try:
        from win32com.client import dynamic
    except ImportError as e:
        raise WordExportError(
            "win32com is not available. Cannot open the document in Word."
        ) from e

    try:
        word = dynamic.Dispatch("Word.Application")
        word.Visible = visible
        document = word.Documents.Open(
            path,
            ConfirmConversions=False,
            ReadOnly=False,
            AddToRecentFiles=False,
        )
        try:
            word.Activate()
        except Exception:
            logger.debug("Could not activate Word window after opening document", exc_info=True)
        return document
    except Exception as e:  # COM / Word launch failure
        raise WordExportError(f"Could not open the document in Word: {e}") from e
