"""File Explorer Layout."""
from __future__ import annotations

import logging

from PyQt6.QtCore import (
    QTimer,
)

logger = logging.getLogger(__name__)


class FileExplorerLayoutMixin:
    """Requires: layout_store, column_widths, panel_widths, main_splitter.
    Provides: persisted column widths, panel widths, and details footer text.
    """

    def load_column_widths(self):
        """Load column widths from JSON file"""
        return self.layout_store.load_column_widths()

    def save_column_widths(self):
        """Save column widths to JSON file"""
        self.layout_store.save_column_widths(self.column_widths)

    def on_column_resized(self, logical_index, old_size, new_size):
        """Handle column resize event - debounced save (avoids disk write on every pixel)"""
        self.column_widths[f'col_{logical_index}'] = new_size
        
        # Debounce: cancel any pending save and schedule new one
        if self._column_resize_timer is not None:
            self._column_resize_timer.stop()
        
        self._column_resize_timer = QTimer()
        self._column_resize_timer.setSingleShot(True)
        self._column_resize_timer.timeout.connect(self.save_column_widths)
        self._column_resize_timer.start(500)  # Save after 500ms of no resize activity

    def load_panel_widths(self):
        """Load panel widths from JSON file"""
        return self.layout_store.load_panel_widths()

    def save_panel_widths(self):
        """Save panel widths to JSON file"""
        self.layout_store.save_panel_widths(self.panel_widths)

    def on_splitter_moved(self, pos, index):
        """Handle splitter moved event - debounced save (avoids disk write on every pixel)"""
        if hasattr(self, 'main_splitter'):
            sizes = self.main_splitter.sizes()
            if len(sizes) >= 2:
                self.panel_widths['left_panel'] = sizes[0]
                self.panel_widths['middle_panel'] = sizes[1]
                if len(sizes) >= 3:
                    self.panel_widths['right_panel'] = sizes[2]
                if len(sizes) >= 4 and sizes[3] > 0:
                    self.panel_widths['scratchpad_panel'] = sizes[3]
                
                # Debounce: cancel any pending save and schedule new one
                if self._splitter_move_timer is not None:
                    self._splitter_move_timer.stop()
                
                self._splitter_move_timer = QTimer()
                self._splitter_move_timer.setSingleShot(True)
                self._splitter_move_timer.timeout.connect(self.save_panel_widths)
                self._splitter_move_timer.start(500)  # Save after 500ms of no movement

    def update_details_footer(self, timing_ms=None):
        """Update the details footer with item count and optional timing"""
        if hasattr(self, 'details_footer') and hasattr(self, 'details_sort_proxy'):
            count = self.details_sort_proxy.rowCount()
            
            # Left side: item count
            if count == 0:
                left_text = ""
            elif count == 1:
                left_text = "1 item"
            else:
                left_text = f"{count} items"
            
            # Right side: timing info
            if timing_ms is not None:
                right_text = f"Loaded in {timing_ms}ms"
            else:
                right_text = ""
            
            # Combine with spacing
            if left_text and right_text:
                full_text = f"{left_text}" + " " * 20 + right_text
            else:
                full_text = left_text + right_text
            
            self.details_footer.setText(full_text)
