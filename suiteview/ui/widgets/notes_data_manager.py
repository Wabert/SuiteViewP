"""
Notes Data Manager

Simple persistence for the Notes Panel.
Stores a single plain-text string in ~/.suiteview/notes.txt.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class NotesDataManager:
    """Singleton that reads/writes a plain text notes file."""

    _instance = None
    _initialized = False

    DATA_FILE = Path.home() / ".suiteview" / "notes.txt"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if NotesDataManager._initialized:
            return
        NotesDataManager._initialized = True
        self._text = ""
        self._load()

    @classmethod
    def instance(cls) -> "NotesDataManager":
        return cls()

    @classmethod
    def reset_instance(cls):
        cls._instance = None
        cls._initialized = False

    # -- persistence ----------------------------------------------------------

    def _load(self):
        if self.DATA_FILE.exists():
            try:
                self._text = self.DATA_FILE.read_text(encoding="utf-8")
            except Exception as e:
                logger.error("Failed to load notes: %s", e, exc_info=True)
                self._text = ""
        else:
            self._text = ""

    def get_text(self) -> str:
        return self._text

    def save(self, text: str):
        self._text = text
        try:
            self.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.DATA_FILE.write_text(text, encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save notes: %s", e, exc_info=True)


def get_notes_manager() -> NotesDataManager:
    """Get the singleton NotesDataManager instance."""
    return NotesDataManager.instance()
