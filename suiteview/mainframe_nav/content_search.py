"""Background dataset-content search worker for Mainframe Nav."""

import logging
import re

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class ContentSearchThread(QThread):
    """Search selected mainframe datasets without blocking the UI."""

    progress_update = pyqtSignal(str, int, int)
    search_complete = pyqtSignal(object)

    def __init__(self, ftp_manager, datasets, search_strings, case_sensitive, whole_word, current_dataset):
        super().__init__()
        self.ftp_manager = ftp_manager
        self.datasets = datasets
        self.search_strings = search_strings
        self.case_sensitive = case_sensitive
        self.whole_word = whole_word
        self.current_dataset = current_dataset
        self._is_cancelled = False

    def cancel(self):
        """Cancel the search."""
        self._is_cancelled = True

    def run(self):
        """Search through datasets."""
        results = []
        errors = []
        skipped = []
        total = len(self.datasets)

        for idx, dataset_info in enumerate(self.datasets):
            if self._is_cancelled:
                break

            member_name = dataset_info["name"]
            full_path = dataset_info["full_path"]
            dsorg = dataset_info.get("dsorg", "")

            self.progress_update.emit(f"Searching {member_name}...", idx + 1, total)

            if dsorg == "PO":
                skipped.append(f"{member_name} (PO dataset - cannot read directly)")
                continue

            try:
                content, _total_lines = self.ftp_manager.read_dataset(full_path, max_lines=None)
                if not content:
                    skipped.append(f"{member_name} (empty or no content)")
                    continue

                dataset_matches = self._find_matches(content)
                if dataset_matches:
                    results.append(
                        {
                            "dataset": member_name,
                            "full_path": full_path,
                            "matches": dataset_matches,
                        }
                    )
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error searching {member_name}: {error_msg}")
                errors.append(f"{member_name}: {error_msg}")

        self.search_complete.emit(
            {
                "results": results,
                "errors": errors,
                "skipped": skipped,
            }
        )

    def _find_matches(self, content: str) -> list[dict]:
        dataset_matches = []
        for search_str in self.search_strings:
            pattern = re.escape(search_str).replace(r"\*", ".*").replace(r"\?", ".")
            if self.whole_word:
                pattern = r"\b" + pattern + r"\b"

            flags = 0 if self.case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)
            matches = []
            for line_num, line in enumerate(content.split("\n"), 1):
                if regex.search(line):
                    matches.append(
                        {
                            "line_number": line_num,
                            "line_content": line.strip(),
                        }
                    )

            if matches:
                dataset_matches.append(
                    {
                        "search_string": search_str,
                        "matches": matches[:10],
                    }
                )
        return dataset_matches
