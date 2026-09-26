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

    @property
    def data_file(self) -> Path:
        return profile_path('scratchpad.txt')

    # -- persistence ----------------------------------------------------------

    def _load(self):
        data_file = self.data_file
        if data_file.exists():
            try:
                self._text = data_file.read_text(encoding="utf-8")
                logger.info("Loaded scratchpad from %s", data_file)
            except Exception as e:
                logger.error("Failed to load scratchpad: %s", e, exc_info=True)

    def save(self, text: str):
        self._text = text
        try:
            data_file = self.data_file
            data_file.parent.mkdir(parents=True, exist_ok=True)
            data_file.write_text(text, encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save scratchpad: %s", e, exc_info=True)

    def get_text(self) -> str:
        return self._text


def get_scratchpad_manager() -> ScratchPadDataManager:
    """Convenience accessor."""
    return ScratchPadDataManager.instance()
