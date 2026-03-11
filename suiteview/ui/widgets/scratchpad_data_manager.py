"""
ScratchPad Data Manager

Simple persistence for the ScratchPad.
Stores a single plain-text string in ~/.suiteview/scratchpad.txt.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ScratchPadDataManager:
    """Singleton that reads/writes a plain text scratchpad file."""

    _instance = None
    _initialized = False

    DATA_FILE = Path.home() / ".suiteview" / "scratchpad.txt"
    OLD_DATA_FILE = Path.home() / ".suiteview" / "quick_notes.txt"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if ScratchPadDataManager._initialized:
            return
        ScratchPadDataManager._initialized = True
        self._text = ""
        self._migrate_old_file()
        self._load()

    @classmethod
    def instance(cls) -> "ScratchPadDataManager":
        return cls()

    @classmethod
    def reset_instance(cls):
        cls._instance = None
        cls._initialized = False

    # -- migration ------------------------------------------------------------

    def _migrate_old_file(self):
        """Rename quick_notes.txt -> scratchpad.txt if the old file exists."""
        if self.OLD_DATA_FILE.exists() and not self.DATA_FILE.exists():
            try:
                self.OLD_DATA_FILE.rename(self.DATA_FILE)
                logger.info("Migrated %s -> %s", self.OLD_DATA_FILE, self.DATA_FILE)
            except Exception as e:
                logger.error("Failed to migrate old notes file: %s", e, exc_info=True)

    # -- persistence ----------------------------------------------------------

    def _load(self):
        if self.DATA_FILE.exists():
            try:
                self._text = self.DATA_FILE.read_text(encoding="utf-8")
                logger.info("Loaded scratchpad from %s", self.DATA_FILE)
            except Exception as e:
                logger.error("Failed to load scratchpad: %s", e, exc_info=True)

    def save(self, text: str):
        self._text = text
        try:
            self.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.DATA_FILE.write_text(text, encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save scratchpad: %s", e, exc_info=True)

    def get_text(self) -> str:
        return self._text


def get_scratchpad_manager() -> ScratchPadDataManager:
    """Convenience accessor."""
    return ScratchPadDataManager.instance()
