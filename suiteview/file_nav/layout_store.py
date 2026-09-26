"""Persistence helpers for FileNav widths and panel visibility."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from suiteview.core.json_store import write_json

logger = logging.getLogger(__name__)


class LayoutStore:
    """Load and save FileNav JSON layout dictionaries."""

    def __init__(self, column_widths_file: Path, panel_widths_file: Path) -> None:
        self.column_widths_file = column_widths_file
        self.panel_widths_file = panel_widths_file

    def load_column_widths(self) -> dict:
        return self._load(self.column_widths_file, "column widths")

    def save_column_widths(self, widths: dict) -> None:
        self._save(self.column_widths_file, widths, "column widths")

    def load_panel_widths(self) -> dict:
        return self._load(self.panel_widths_file, "panel widths")

    def save_panel_widths(self, widths: dict) -> None:
        self._save(self.panel_widths_file, widths, "panel widths")

    @staticmethod
    def _load(path: Path, label: str) -> dict:
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as handle:
                    return json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to load FileNav %s: %s", label, exc)
        return {}

    @staticmethod
    def _save(path: Path, data: dict, label: str) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json(path, data, ensure_ascii=True)
        except OSError as exc:
            logger.error("Failed to save FileNav %s: %s", label, exc)
