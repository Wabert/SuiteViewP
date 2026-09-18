"""
ScratchPad Data Manager

Simple persistence for the ScratchPad.
Stores a single plain-text string in ~/.suiteview/data/notes/scratchpad.txt.
"""

from suiteview.core.profile_paths import profile_path

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ScratchPadDataManager:
    """Singleton that reads/writes a plain text scratchpad file."""

    _instance = None
    _initialized = False

    DATA_FILE = profile_path('scratchpad.txt')

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if ScratchPadDataManager._initialized:
            return
        ScratchPadDataManager._initialized = True
        self._text = ""
        self._load()

    @classmethod
    def instance(cls) -> "ScratchPadDataManager":
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
