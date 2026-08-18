"""
ABR Quote — Resources dialog.

Two-panel layout: left navigation list, right detail/text panel.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QTextEdit,
    QLabel, QSplitter, QWidget, QPushButton, QMessageBox,
)

from ..models.abr_data import ABRPolicyData, ABRQuoteResult, MedicalAssessment
from .abr_styles import (
    CRIMSON_DARK, CRIMSON_PRIMARY, CRIMSON_BG,
    SLATE_PRIMARY, SLATE_LIGHT, WHITE, GRAY_DARK,
    BUTTON_PRIMARY_STYLE,
)

logger = logging.getLogger(__name__)

# The "Explanation of Benefit" topic is generated dynamically from the current
# quote (see suiteview/abrquote/core/abr_explanation.py). The remaining topics
# are static reference text.
_EXPLANATION_OF_BENEFIT = "Explanation of Benefit"

_STATIC_RESOURCES: dict[str, str] = {
    "Explanation of Interest Rate": (
        "The present-value discount uses the Accelerated Benefit Interest Rate. "
        "As defined in the accelerated-benefit rider, this is a rate the Company "
        "declares that will not exceed the greater of (1) the yield on 90-day "
        "Treasury Bills on the Election Date, or (2) the current maximum "
        "adjustable policy loan interest rate allowed by law. A lower rate "
        "produces a higher Accelerated Benefit Payment; a higher rate produces a "
        "lower payment."
    ),
}

_NAV_ITEMS = [_EXPLANATION_OF_BENEFIT] + list(_STATIC_RESOURCES.keys())


class ResourcesDialog(QDialog):
    """Two-panel resources reference dialog for ABR Quote."""

    def __init__(
        self,
        parent=None,
        policy: Optional[ABRPolicyData] = None,
        result: Optional[ABRQuoteResult] = None,
        assessment: Optional[MedicalAssessment] = None,
        level_annual_premium: Optional[float] = None,
        eligible_db_override: Optional[float] = None,
    ):
        super().__init__(parent)
        self._policy = policy
        self._result = result
        self._assessment = assessment
        self._level_annual_premium = level_annual_premium
        self._eligible_db_override = eligible_db_override
        self._explanation_doc = None  # cached ExplanationDoc for the current topic
        self.setWindowTitle("ABR Quote — Resources")
        self.setMinimumSize(720, 460)
        self.resize(860, 620)
        self._build_ui()
        # Select first item by default
        self._nav_list.setCurrentRow(0)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # ── Left navigation panel ───────────────────────────────────
        nav_widget = QWidget()
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(8, 8, 4, 8)
        nav_layout.setSpacing(4)

        nav_header = QLabel("Topics")
        nav_header.setStyleSheet(f"""
            font-size: 13px;
            font-weight: bold;
            color: {WHITE};
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {CRIMSON_DARK}, stop:1 {CRIMSON_PRIMARY});
            border-radius: 4px;
            padding: 6px 10px;
        """)
        nav_layout.addWidget(nav_header)

        self._nav_list = QListWidget()
        self._nav_list.addItems(_NAV_ITEMS)
        self._nav_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {WHITE};
                border: 1px solid {SLATE_PRIMARY};
                border-radius: 4px;
                font-size: 12px;
                color: {GRAY_DARK};
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px 10px;
            }}
            QListWidget::item:selected {{
                background-color: {CRIMSON_PRIMARY};
                color: {WHITE};
                border-radius: 3px;
            }}
            QListWidget::item:hover:!selected {{
                background-color: {SLATE_LIGHT};
            }}
        """)
        self._nav_list.currentRowChanged.connect(self._on_topic_changed)
        nav_layout.addWidget(self._nav_list)

        nav_widget.setStyleSheet(f"background-color: {CRIMSON_BG};")

        # ── Right detail panel ──────────────────────────────────────
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(4, 8, 8, 8)
        detail_layout.setSpacing(4)

        self._detail_header = QLabel()
        self._detail_header.setStyleSheet(f"""
            font-size: 13px;
            font-weight: bold;
            color: {CRIMSON_DARK};
            padding: 6px 10px;
        """)

        # Export-to-Word button, right-aligned in the header row.
        self._export_btn = QPushButton("Export to Word")
        self._export_btn.setStyleSheet(BUTTON_PRIMARY_STYLE)
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.setFixedHeight(28)
        self._export_btn.clicked.connect(self._on_export_word)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.addWidget(self._detail_header)
        header_row.addStretch(1)
        header_row.addWidget(self._export_btn)
        detail_layout.addLayout(header_row)

        self._detail_text = QTextEdit()
        self._detail_text.setReadOnly(True)
        self._detail_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {WHITE};
                border: 1px solid {SLATE_PRIMARY};
                border-radius: 4px;
                font-size: 12px;
                color: {GRAY_DARK};
                padding: 10px;
            }}
        """)
        detail_layout.addWidget(self._detail_text)

        detail_widget.setStyleSheet(f"background-color: {CRIMSON_BG};")

        # ── Assemble splitter ───────────────────────────────────────
        splitter.addWidget(nav_widget)
        splitter.addWidget(detail_widget)
        splitter.setStretchFactor(0, 1)   # nav: 1 part
        splitter.setStretchFactor(1, 2)   # detail: 2 parts
        splitter.setSizes([220, 460])

        layout.addWidget(splitter)

    def _on_topic_changed(self, row: int):
        if row < 0:
            return
        title = _NAV_ITEMS[row]
        self._detail_header.setText(title)
        if title == _EXPLANATION_OF_BENEFIT:
            from ..core.abr_explanation import (
                build_explanation, explanation_to_html,
            )
            self._explanation_doc = build_explanation(
                self._policy, self._result, self._assessment,
                level_annual_premium=self._level_annual_premium,
                eligible_db_override=self._eligible_db_override,
            )
            self._detail_text.setHtml(explanation_to_html(self._explanation_doc))
            self._export_btn.setVisible(True)
        else:
            self._explanation_doc = None
            self._detail_text.setPlainText(_STATIC_RESOURCES[title])
            self._export_btn.setVisible(False)

    def _on_export_word(self):
        """Export the current Explanation of Benefit to a Word document."""
        if self._explanation_doc is None:
            return
        try:
            from ..core.abr_explanation import explanation_to_docx
            from suiteview.core.word_export import open_in_word, WordExportError
        except ImportError as e:
            QMessageBox.warning(
                self, "Export Error",
                f"Required components are not available:\n{e}",
            )
            return

        # Build a safe, descriptive filename in the temp directory.
        policy_num = (self._policy.policy_number if self._policy else "") or "ABR"
        safe_policy = re.sub(r"[^A-Za-z0-9_-]+", "", policy_num) or "ABR"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(
            tempfile.gettempdir(),
            f"ABR_Benefit_Explanation_{safe_policy}_{stamp}.docx",
        )

        try:
            explanation_to_docx(self._explanation_doc, out_path)
        except ImportError:
            QMessageBox.warning(
                self, "Export Error",
                "python-docx is not available. Cannot export to Word.",
            )
            return
        except Exception as e:
            logger.error("Failed to build Word document: %s", e, exc_info=True)
            QMessageBox.warning(
                self, "Export Error",
                f"Could not build the Word document:\n{e}",
            )
            return

        try:
            open_in_word(out_path)
        except WordExportError as e:
            # The .docx was written successfully; only the pop-up failed.
            QMessageBox.information(
                self, "Document Saved",
                f"The explanation was saved to:\n{out_path}\n\n"
                f"(It could not be opened automatically: {e})",
            )
        except Exception as e:
            logger.error("Failed to open Word: %s", e, exc_info=True)
            QMessageBox.information(
                self, "Document Saved",
                f"The explanation was saved to:\n{out_path}\n\n"
                f"(It could not be opened automatically: {e})",
            )
