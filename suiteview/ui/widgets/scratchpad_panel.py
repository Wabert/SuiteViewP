"""
ScratchPad Panel

A simple free-form scratchpad that slides out from the right side.
Just a header + a plain QPlainTextEdit that auto-saves on every change.
Enter = newline (normal text editing). No word-wrap — horizontal scroll instead.

Persists to ~/.suiteview/scratchpad.txt via ScratchPadDataManager.
"""

import logging
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPlainTextEdit, QPushButton, QDialog,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QTextOption

from suiteview.ui.widgets.scratchpad_data_manager import get_scratchpad_manager

logger = logging.getLogger(__name__)

# ── Header button style (shared) ───────────────────────────────────────────
_HDR_BTN = """
    QPushButton {
        background: transparent;
        color: #D4A017;
        border: none;
        font-size: %SIZE%;
        padding: 0px 2px;
    }
    QPushButton:hover { color: #FFD700; }
"""

def _hdr_btn(text, tooltip, size="11pt", width=22):
    btn = QPushButton(text)
    btn.setToolTip(tooltip)
    btn.setFixedSize(width, 22)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(_HDR_BTN.replace("%SIZE%", size))
    return btn


# ── Symbol grid characters ─────────────────────────────────────────────────
# 8 columns × 5 rows = 40 characters
GRID_CHARS = [
    # Row 1 — bullets / list markers
    "\u2022", "\u25E6", "\u25AA", "\u25CB", "\u2023", "\u2713", "\u2717", "\u2610",
    # Row 2 — checkboxes, arrows
    "\u2611", "\u2192", "\u2190", "\u2191", "\u2193", "\u21D2", "\u21E8", "\u2605",
    # Row 3 — math / logic
    "\u00B1", "\u00D7", "\u00F7", "\u2260", "\u2264", "\u2265", "\u221E", "\u0394",
    # Row 4 — more math, common
    "\u03A3", "\u00A9", "\u00AE", "\u2122", "\u00B0", "\u2026", "\u00A7", "\u00B6",
    # Row 5 — misc
    "\u2020", "\u2660", "\u2663", "\u2665", "\u2666", "\u266A", "\u00AB", "\u00BB",
]

# Separator strings (inserted as full lines)
SEPARATORS = [
    ("\u2500" * 30, "thin"),
    ("\u2550" * 30, "double"),
    ("\u2014" * 30, "em-dash"),
    ("\u00B7 " * 15, "dots"),
]


# ═══════════════════════════════════════════════════════════════════════════
# SymbolPickerDialog — 8 × 5 grid + separator row
# ═══════════════════════════════════════════════════════════════════════════

class SymbolPickerDialog(QDialog):
    """Non-modal popup with an 8×5 grid of special characters."""

    char_picked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setStyleSheet("""
            QDialog {
                background: #1A3A6A;
                border: 1px solid #D4A017;
            }
        """)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── Character grid ──────────────────────────────────────────────
        grid = QGridLayout()
        grid.setSpacing(2)
        cols = 8
        for i, ch in enumerate(GRID_CHARS):
            btn = QPushButton(ch)
            btn.setFixedSize(28, 26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: #0D3A7A;
                    color: #E0E8FF;
                    border: 1px solid #2563EB;
                    border-radius: 3px;
                    font-family: Consolas, 'Courier New', monospace;
                    font-size: 11pt;
                }
                QPushButton:hover {
                    background: #2563EB;
                    border-color: #FFD700;
                }
            """)
            btn.clicked.connect(lambda checked, c=ch: self._pick(c))
            grid.addWidget(btn, i // cols, i % cols)
        root.addLayout(grid)

        # ── Separator buttons ───────────────────────────────────────────
        sep_lay = QHBoxLayout()
        sep_lay.setSpacing(3)
        for sep_str, label in SEPARATORS:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(22)
            btn.setStyleSheet("""
                QPushButton {
                    background: #0D3A7A;
                    color: #D4A017;
                    border: 1px solid #2563EB;
                    border-radius: 3px;
                    font-size: 8pt;
                    padding: 0px 6px;
                }
                QPushButton:hover {
                    background: #2563EB;
                    border-color: #FFD700;
                }
            """)
            btn.clicked.connect(lambda checked, s=sep_str: self._pick(s))
            sep_lay.addWidget(btn)
        root.addLayout(sep_lay)

    def _pick(self, char):
        self.char_picked.emit(char)
        self.close()


# ═══════════════════════════════════════════════════════════════════════════
# IndentingPlainTextEdit — Custom editor with auto-indentation logic
# ═══════════════════════════════════════════════════════════════════════════

class IndentingPlainTextEdit(QPlainTextEdit):
    """QPlainTextEdit that auto-indents new lines to 4 spaces."""

    def keyPressEvent(self, event):
        # Handle Enter key for auto-indentation
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # User requirement: "basically any time i hit return i want a 3 space indent to be added"
            self.insertPlainText("\n   ")
            self.ensureCursorVisible()
            return
        super().keyPressEvent(event)

# ═══════════════════════════════════════════════════════════════════════════
# ScratchPadPanel
# ═══════════════════════════════════════════════════════════════════════════

class ScratchPadPanel(QWidget):
    """
    Compact scratchpad panel — header + full-height text editor.
    Auto-saves after a short debounce so typing is never interrupted.
    """

    # Emitted when fullscreen toggle is clicked; the parent (file_explorer)
    # listens for this signal to adjust splitter sizes.
    fullscreen_toggled = pyqtSignal(bool)  # True = go fullscreen

    DEFAULT_FONT_SIZE = 9      # pt
    MIN_FONT_SIZE = 7
    MAX_FONT_SIZE = 20

    def __init__(self, parent=None, show_header=True):
        super().__init__(parent)
        self.setMinimumWidth(50)
        self.setStyleSheet("background: #CCE5F8;")
        self._font_size = self.DEFAULT_FONT_SIZE
        self._is_fullscreen = False
        self._show_header = show_header
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._do_save)
        self._build_ui()
        self._load()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──────────────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:0.5 #0D3A7A, stop:1 #082B5C);
                border: none;
            }
        """)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(12, 6, 4, 6)
        h_lay.setSpacing(3)

        title = QLabel("SCRATCHPAD")
        title.setStyleSheet("""
            QLabel {
                background: transparent;
                font-weight: 700;
                font-size: 10pt;
                color: #D4A017;
                letter-spacing: 1px;
            }
        """)
        h_lay.addWidget(title)
        h_lay.addStretch()

        # Timestamp button
        self.stamp_btn = _hdr_btn("\U0001F550", "Insert date/time stamp")
        self.stamp_btn.clicked.connect(self._insert_timestamp)
        h_lay.addWidget(self.stamp_btn)

        # Font decrease
        self.font_down_btn = _hdr_btn("\u2212", "Decrease font size", size="12pt", width=20)
        self.font_down_btn.clicked.connect(self._font_decrease)
        h_lay.addWidget(self.font_down_btn)

        # Font increase
        self.font_up_btn = _hdr_btn("+", "Increase font size", size="12pt", width=20)
        self.font_up_btn.clicked.connect(self._font_increase)
        h_lay.addWidget(self.font_up_btn)

        # Fullscreen toggle
        self.fs_btn = _hdr_btn("\u2922", "Toggle fullscreen", size="13pt", width=22)
        self.fs_btn.clicked.connect(self._toggle_fullscreen)
        h_lay.addWidget(self.fs_btn)

        if self._show_header:
            root.addWidget(header)

        # ── Text editor ─────────────────────────────────────────────────
        self.editor = IndentingPlainTextEdit()
        self.editor.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self._apply_editor_style()
        self.editor.setPlaceholderText("Type anything here\u2026")
        self.editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.editor.customContextMenuRequested.connect(self._show_symbols_popup)
        self.editor.textChanged.connect(self._on_text_changed)
        root.addWidget(self.editor, 1)

    def _apply_editor_style(self):
        self.editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background: #FFFFFF;
                border: none;
                padding: 6px;
                font-family: Consolas, 'Courier New', monospace;
                font-size: {self._font_size}pt;
                color: #0A1E5E;
            }}
            QScrollBar:vertical {{
                background: #E8F0FF;
                width: 8px;
            }}
            QScrollBar::handle:vertical {{
                background: #1E5BA8;
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{
                background: #E8F0FF;
                height: 8px;
            }}
            QScrollBar::handle:horizontal {{
                background: #1E5BA8;
                border-radius: 4px;
                min-width: 20px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
        """)

    # -- persistence ---------------------------------------------------------

    def _load(self):
        mgr = get_scratchpad_manager()
        self.editor.setPlainText(mgr.get_text())

    def _on_text_changed(self):
        self._save_timer.start()

    def _do_save(self):
        mgr = get_scratchpad_manager()
        mgr.save(self.editor.toPlainText())

    # -- header actions ------------------------------------------------------

    def insert_timestamp(self):
        """Insert timestamp with newline and indentation."""
        cursor = self.editor.textCursor()
        
        # Ensure we start on a clean line for the timestamp
        # Check current line content
        cursor.movePosition(cursor.MoveOperation.StartOfBlock, cursor.MoveMode.KeepAnchor)
        text_before = cursor.selectedText()
        if text_before.strip(): 
            # Line has text, move to end and new line
            cursor.clearSelection() 
            cursor.movePosition(cursor.MoveOperation.EndOfBlock) 
            cursor.insertText("\n") 
        else:
            # Line is empty/whitespace, clear it so timestamp is at column 0
            cursor.removeSelectedText()
            
        now = datetime.now()
        hour = now.hour % 12 or 12
        ampm = "am" if now.hour < 12 else "pm"
        stamp = f"{now.month}/{now.day}/{now.year}  {hour}:{now.minute:02d}{ampm}"
        
        cursor.insertText(stamp)
        cursor.insertText("\n   ") # Newline + 3 spaces
        
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def _insert_timestamp(self):
        # Legacy/internal call
        self.insert_timestamp()

    def _font_increase(self):
        if self._font_size < self.MAX_FONT_SIZE:
            self._font_size += 1
            self._apply_editor_style()

    def _font_decrease(self):
        if self._font_size > self.MIN_FONT_SIZE:
            self._font_size -= 1
            self._apply_editor_style()

    def _toggle_fullscreen(self):
        self._is_fullscreen = not self._is_fullscreen
        self.fs_btn.setText("\u2923" if self._is_fullscreen else "\u2922")
        self.fs_btn.setToolTip("Exit fullscreen" if self._is_fullscreen else "Toggle fullscreen")
        self.fullscreen_toggled.emit(self._is_fullscreen)

    # -- symbol picker -------------------------------------------------------

    def _show_symbols_popup(self, pos):
        dlg = SymbolPickerDialog(self.editor)
        dlg.char_picked.connect(self._insert_char)
        dlg.move(self.editor.mapToGlobal(pos))
        dlg.show()

    def _insert_char(self, char):
        self.editor.insertPlainText(char)
        self.editor.setFocus()

    # -- public --------------------------------------------------------------

    def refresh(self):
        self._load()


# ═══════════════════════════════════════════════════════════════════════════
# ScratchPadWindow — standalone frameless window wrapping ScratchPadPanel
# ═══════════════════════════════════════════════════════════════════════════

class ScratchPadWindow:
    """Factory / handle for the ScratchPad floating window.

    Opens a FramelessWindowBase-derived window that embeds the ScratchPadPanel.
    Theme: Forest Green & Parchment — warm sage headers, cream body —
    evokes a physical notepad / notebook feel.

    Usage (from FileExplorerMultiTab):
        win = ScratchPadWindow.open(parent_bar=self)
        win.show(); win.activateWindow(); win.raise_()
    """

    @staticmethod
    def open(parent_bar=None) -> "QWidget":
        """Create and return the ScratchPad window widget."""
        from suiteview.ui.widgets.frameless_window import FramelessWindowBase

        class _ScratchPadWindow(FramelessWindowBase):
            # Forest Green & Parchment palette
            _GREEN_START  = "#2D6A3F"   # Deep forest green
            _GREEN_MID    = "#1F4D2E"   # Dark forest green
            _GREEN_END    = "#163820"   # Darkest forest
            _PARCHMENT    = "#F5EFD8"   # Warm cream / parchment
            _GOLD_ACCENT  = "#C8A84B"   # Warm gold accent
            _PANEL_BG     = "#EDE8D5"   # Parchment panel bg

            def __init__(self):
                # Create timestamp button for header
                from PyQt6.QtWidgets import QPushButton
                btn = QPushButton("\U0001F550") # 🕐 Clock icon
                btn.setToolTip("Insert Timestamp")
                # Style matches FramelessWindowBase header buttons
                btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        border: none;
                        font-size: 16px; 
                        color: #C8A84B;
                        min-width: 30px;
                    }
                    QPushButton:hover {
                        color: #FFD700;
                        background-color: rgba(255, 255, 255, 0.15);
                    }
                """)
                # We can't connect cleanly to panel yet as it's not created.
                # Connect to a lambda that delegates to self.panel if it exists.
                # We'll assign self.panel in build_content.
                btn.clicked.connect(lambda: self.panel.insert_timestamp() if hasattr(self, 'panel') else None)
                
                super().__init__(
                    title="SuiteView: ScratchPad",
                    default_size=(800, 600),
                    min_size=(320, 300),
                    parent=None,
                    header_colors=(
                        _ScratchPadWindow._GREEN_START,
                        _ScratchPadWindow._GREEN_MID,
                        _ScratchPadWindow._GREEN_END,
                    ),
                    border_color=_ScratchPadWindow._GOLD_ACCENT,
                    header_widgets=[btn],
                )
                self.timestamp_btn = btn
                self._parent_bar = parent_bar

                # Centre on screen
                from PyQt6.QtWidgets import QApplication as _QApp
                screen = _QApp.primaryScreen().availableGeometry()
                w, h = 800, 600
                self.setGeometry(
                    screen.x() + (screen.width() - w) // 2,
                    screen.y() + (screen.height() - h) // 2,
                    w, h,
                )

            def build_content(self):
                """Embed the ScratchPadPanel without its inner header (window has its own)."""
                self.panel = ScratchPadPanel(parent=self, show_header=False)
                # Override the panel's light-blue tint with the parchment colour
                self.panel.setStyleSheet(
                    f"background: {_ScratchPadWindow._PANEL_BG}; "
                    f"border: none;"
                )
                # Also restyle the text editor to parchment
                if hasattr(self.panel, 'editor'):
                    self.panel.editor.setStyleSheet(
                        f"QPlainTextEdit {{"
                        f"    background: {_ScratchPadWindow._PARCHMENT};"
                        f"    color: #2B2200;"
                        f"    border: none;"
                        f"    padding: 4px;"
                        f"    font-family: 'Consolas', 'Courier New', monospace;"
                        f"}}"
                    )
                return self.panel

        win = _ScratchPadWindow()
        return win
