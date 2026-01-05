"""
Mainframe Terminal Screen - TN3270 Terminal Emulator UI
Provides a 3270 terminal interface for TSO/ISPF access
"""

import logging
import time
import json
import socket
import ssl
from typing import List
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
                              QPushButton, QLabel, QLineEdit, QComboBox,
                              QGroupBox, QGridLayout, QMessageBox, QFrame,
                              QSplitter, QStatusBar, QToolBar, QSpinBox, QCheckBox,
                              QApplication, QDialog, QDialogButtonBox, QFormLayout,
                              QTabWidget, QTabBar, QProgressBar, QTableWidget,
                              QTableWidgetItem, QHeaderView, QAbstractItemView, QMenu,
                              QSizePolicy)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QEventLoop, QUrl
from PyQt6.QtGui import QFont, QTextCursor, QColor, QTextCharFormat, QKeyEvent, QKeySequence, QDesktopServices

from suiteview.core.tn3270 import TN3270Client, Screen, AID

logger = logging.getLogger(__name__)


class TerminalReceiveThread(QThread):
    """Background thread for receiving terminal data"""
    screen_updated = pyqtSignal(object)  # Emits Screen object
    connection_lost = pyqtSignal(str)
    
    def __init__(self, client: TN3270Client):
        super().__init__()
        self.client = client
        self.running = True
    
    def run(self):
        """Continuously receive screen updates"""
        while self.running and self.client.connected:
            try:
                if self.client.receive_screen():
                    self.screen_updated.emit(self.client.screen)
            except Exception as e:
                logger.error(f"Receive error: {e}")
                self.connection_lost.emit(str(e))
                break
    
    def stop(self):
        """Stop the receive thread"""
        self.running = False


class TerminalWidget(QTextEdit):
    """Custom text widget that displays 3270 screen and handles keyboard input"""
    
    key_pressed = pyqtSignal(object)  # Emits QKeyEvent
    enter_pressed = pyqtSignal()  # Enter key
    pf_key_pressed = pyqtSignal(int)  # PF key number
    clear_pressed = pyqtSignal()  # Clear key
    
    def __init__(self):
        super().__init__()
        
        # Set monospace font for terminal display
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        
        # Terminal styling
        self.setStyleSheet("""
            QTextEdit {
                background-color: #000000;
                color: #00FF00;
                border: 2px solid #2c5f8d;
                padding: 5px;
            }
            QTextEdit:focus {
                border: 2px solid #27ae60;
            }
        """)
        
        # Allow editing (not read-only)
        self.setReadOnly(False)
        
        # Disable line wrap to maintain 80-column format
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        
        # Screen dimensions
        self.rows = 24
        self.cols = 80
        
        # Current cursor position
        self.cursor_row = 0
        self.cursor_col = 0
        
        # Track the current screen content for detecting changes
        self.screen_content = ""
        self.last_screen = None
        
        # Track all typed characters by buffer address
        self.typed_chars = {}  # {buffer_address: "character"}
        
        # Track overwrite mode (3270 terminals are always overwrite mode)
        self.overwrite_mode = True
        
        # Field tracking for input
        self.input_fields = []  # List of (start_addr, length, content)
        self.current_field_index = -1
        
    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard input"""
        key = event.key()
        modifiers = event.modifiers()
        
        # Ctrl+V - paste from clipboard
        if key == Qt.Key.Key_V and modifiers & Qt.KeyboardModifier.ControlModifier:
            self._paste_from_clipboard()
            return
        
        # Function keys F1-F12
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F12:
            pf_num = key - Qt.Key.Key_F1 + 1
            self.pf_key_pressed.emit(pf_num)
            return
        
        # F13-F24 via Shift+F1-F12
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F12:
                pf_num = key - Qt.Key.Key_F1 + 13
                self.pf_key_pressed.emit(pf_num)
                return
        
        # Enter key
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.enter_pressed.emit()
            return
        
        # Escape = Clear
        if key == Qt.Key.Key_Escape:
            self.clear_pressed.emit()
            return
        
        # Tab - move to next input field
        if key == Qt.Key.Key_Tab:
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                self._tab_to_prev_field()
            else:
                self._tab_to_next_field()
            return
        
        # Backtab (Shift+Tab handled above)
        if key == Qt.Key.Key_Backtab:
            self._tab_to_prev_field()
            return
        
        # Insert key - toggle overwrite mode (but 3270 is typically always overwrite)
        if key == Qt.Key.Key_Insert:
            self.overwrite_mode = not self.overwrite_mode
            logger.info(f"Overwrite mode: {self.overwrite_mode}")
            return
        
        # Delete key - delete character at cursor
        if key == Qt.Key.Key_Delete:
            current_addr = self.get_cursor_address()
            if current_addr in self.typed_chars:
                del self.typed_chars[current_addr]
            # Replace with space in display
            cursor = self.textCursor()
            if not cursor.atEnd():
                cursor.deleteChar()
                cursor.insertText(' ')
                cursor.movePosition(QTextCursor.MoveOperation.Left)
                self.setTextCursor(cursor)
            return
        
        # Backspace - move back and clear character
        if key == Qt.Key.Key_Backspace:
            current_addr = self.get_cursor_address()
            if current_addr > 0:
                prev_addr = current_addr - 1
                # Remove from typed_chars
                if prev_addr in self.typed_chars:
                    del self.typed_chars[prev_addr]
                # Move cursor back and replace with space
                cursor = self.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.Left)
                cursor.deleteChar()
                cursor.insertText(' ')
                cursor.movePosition(QTextCursor.MoveOperation.Left)
                self.setTextCursor(cursor)
            return
        
        # Arrow keys - allow navigation
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down,
                   Qt.Key.Key_Home, Qt.Key.Key_End, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            super().keyPressEvent(event)
            return
        
        # Regular printable characters - always overwrite mode
        text = event.text()
        if text and text.isprintable():
            current_addr = self.get_cursor_address()
            
            # Store the actual character typed
            self.typed_chars[current_addr] = text
            
            # Check if this is a password field - show blank instead
            is_pwd = self._in_password_field()
            if is_pwd:
                display_char = ' '
                logger.info(f"Typing in password field at {current_addr}")
            else:
                display_char = text
                logger.info(f"Typing '{text}' at {current_addr}")
            
            # Always overwrite: delete current char, insert new one
            cursor = self.textCursor()
            
            # Force color to green for typing if not in password field
            if not is_pwd:
                fmt = QTextCharFormat()
                fmt.setForeground(QColor("#00FF00"))
                cursor.setCharFormat(fmt)
            
            if not cursor.atEnd():
                cursor.deleteChar()
            cursor.insertText(display_char)
            self.setTextCursor(cursor)
            return
        
        # Pass other keys to parent
        self.key_pressed.emit(event)
    
    def _tab_to_next_field(self):
        """Move cursor to next input field"""
        if not self.last_screen:
            return
        
        current_addr = self.get_cursor_address()
        next_addr = self.last_screen.get_next_input_field(current_addr)
        
        if next_addr is None:
            # No next field found - try wrapping to first input field
            input_fields = self.last_screen.get_input_fields()
            if input_fields:
                input_fields.sort(key=lambda f: f.address)
                next_addr = input_fields[0].address + 1
            else:
                logger.warning("No input fields on screen")
                return
        
        row = next_addr // 80
        col = next_addr % 80
        # Debug: show buffer content around field
        start = row * 80 + max(0, col - 5)
        end = row * 80 + min(80, col + 10)
        buffer_slice = ''.join(self.last_screen.buffer[start:end])
        logger.info(f"Tab: current={current_addr}, next field addr={next_addr}, row={row}, col={col}")
        logger.info(f"Tab: buffer around field: '{buffer_slice}' (cols {col-5} to {col+10})")
        self._move_cursor_to_address(next_addr)
        new_addr = self.get_cursor_address()
        logger.info(f"Tab: after move, cursor at addr={new_addr}, row={new_addr//80}, col={new_addr%80}")
    
    def _tab_to_prev_field(self):
        """Move cursor to previous input field (backtab)"""
        if not self.last_screen:
            return
        
        current_addr = self.get_cursor_address()
        prev_addr = self.last_screen.get_prev_input_field(current_addr)
        
        if prev_addr is None:
            # No prev field found - wrap to LAST input field on screen
            input_fields = self.last_screen.get_input_fields()
            if input_fields:
                # Sort by address descending to get the last one
                input_fields.sort(key=lambda f: f.address, reverse=True)
                prev_addr = input_fields[0].address + 1
                logger.info(f"Shift+Tab: wrapping to last field at addr={prev_addr}")
            else:
                logger.warning("No input fields on screen")
                return
        
        logger.info(f"Shift+Tab: current={current_addr}, prev field addr={prev_addr}")
        self._move_cursor_to_address(prev_addr)
    
    def _move_cursor_to_address(self, addr: int):
        """Move the text cursor to a specific buffer address"""
        row = addr // self.cols
        col = addr % self.cols
        
        # Get the actual text and count positions
        text = self.toPlainText()
        lines = text.split('\n')
        
        # Calculate position by counting actual characters
        text_pos = 0
        for i in range(row):
            if i < len(lines):
                text_pos += len(lines[i]) + 1  # +1 for newline
        
        # Add column offset within the row
        if row < len(lines):
            text_pos += min(col, len(lines[row]))
        
        cursor = self.textCursor()
        cursor.setPosition(min(text_pos, len(text)))
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        
        logger.info(f"_move_cursor_to_address: addr={addr} -> row={row}, col={col}, text_pos={text_pos}")
    
    def _in_password_field(self) -> bool:
        """Check if cursor is currently in a password (non-display) field"""
        if not self.last_screen:
            return False
        current_addr = self.get_cursor_address()
        return self.last_screen.is_password_field(current_addr)
    
    def _paste_from_clipboard(self):
        """Paste text from clipboard into terminal at current cursor position"""
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        
        if not text:
            return
        
        # Only paste first line (no newlines in 3270 fields)
        text = text.split('\n')[0].split('\r')[0]
        
        is_password = self._in_password_field()
        
        for char in text:
            if char.isprintable():
                current_addr = self.get_cursor_address()
                
                # Store the actual character
                self.typed_chars[current_addr] = char
                
                # Display blank for password fields, actual char otherwise
                cursor = self.textCursor()
                if not cursor.atEnd():
                    cursor.deleteChar()
                cursor.insertText(' ' if is_password else char)
                self.setTextCursor(cursor)
        
        logger.info(f"Pasted {len(text)} characters from clipboard")
    
    def get_all_typed_content(self) -> List[tuple]:
        """Get all typed content as list of (address, content_string) sorted by address"""
        if not self.typed_chars:
            return []
        # Group consecutive characters into fields
        sorted_addrs = sorted(self.typed_chars.keys())
        fields = []
        current_start = sorted_addrs[0]
        current_content = self.typed_chars[current_start]
        prev_addr = current_start
        
        for addr in sorted_addrs[1:]:
            if addr == prev_addr + 1:
                # Consecutive - append to current field
                current_content += self.typed_chars[addr]
            else:
                # Gap - save current field and start new one
                if current_content.strip():
                    fields.append((current_start, current_content))
                current_start = addr
                current_content = self.typed_chars[addr]
            prev_addr = addr
        
        # Don't forget the last field
        if current_content.strip():
            fields.append((current_start, current_content))
        
        logger.debug(f"get_all_typed_content: typed_chars={self.typed_chars}, fields={fields}")
        return fields
    
    def display_screen(self, screen: Screen):
        """Display 3270 screen content with color support based on field attributes"""
        # Save cursor position before update
        old_cursor = self.textCursor().position()
        
        self.clear()
        
        # Clear typed characters buffer on new screen
        self.typed_chars = {}
        
        self.screen_content = screen.get_text()
        self.last_screen = screen
        
        cursor = self.textCursor()
        
        # Color definitions matching typical 3270 terminal colors
        colors = {
            'green': QColor("#00FF00"),      # Normal unprotected
            'yellow': QColor("#FFFF00"),     # Intensified/highlighted  
            'red': QColor("#FF6B6B"),        # Error messages
            'cyan': QColor("#00FFFF"),       # Protected fields (labels)
            'white': QColor("#FFFFFF"),      # High intensity protected
            'blue': QColor("#6699FF"),       # Blue fields
        }
        
        # Build a color map for each position based on fields
        # Sort fields by address to process in order
        sorted_fields = sorted(screen.fields, key=lambda f: f.address)
        
        # Default format (green for input areas)
        default_format = QTextCharFormat()
        default_format.setForeground(colors['green'])
        
        # Process screen character by character with colors
        for row in range(screen.rows):
            for col in range(screen.cols):
                addr = row * screen.cols + col
                char = screen.buffer[addr]
                
                # Determine color based on which field this position belongs to
                char_format = QTextCharFormat()
                char_format.setForeground(colors['green'])  # default
                
                # Find the field this character belongs to
                current_field = None
                for f in sorted_fields:
                    if f.address <= addr:
                        current_field = f
                    else:
                        break
                
                if current_field:
                    if current_field.protected:
                        if current_field.intensified:
                            # Intensified protected = white/yellow (headers, titles)
                            char_format.setForeground(colors['yellow'])
                        else:
                            # Normal protected = cyan (labels)
                            char_format.setForeground(colors['cyan'])
                    else:
                        # Unprotected (input) fields
                        if current_field.intensified:
                            char_format.setForeground(colors['white'])
                        else:
                            char_format.setForeground(colors['green'])
                
                cursor.insertText(char, char_format)
            
            # Add newline between rows (except last)
            if row < screen.rows - 1:
                cursor.insertText('\n', default_format)
        
        # Position cursor at the 3270 cursor position sent by mainframe
        cursor_addr = screen.cursor_address
        
        self.cursor_row = cursor_addr // self.cols
        self.cursor_col = cursor_addr % self.cols
        
        logger.info(f"display_screen: positioning cursor at addr={cursor_addr} (row={self.cursor_row}, col={self.cursor_col})")
        
        # Move text cursor to match 3270 cursor using proper calculation
        self._move_cursor_to_address(cursor_addr)
        
        # Log field info for debugging
        input_fields = screen.get_input_fields()
        if input_fields:
            for f in input_fields[:3]:  # Show first 3 input fields
                field_row = f.address // 80
                field_col = f.address % 80
                data_start = f.address + 1  # Data starts after field attribute
                # Get content at this field
                field_content = ''.join(screen.buffer[data_start:data_start+20])
                logger.info(f"Input field at addr={f.address} (row={field_row}, col={field_col}), data_start={data_start}, content='{field_content}'")
        
        # Give focus to the terminal
        self.setFocus()
    
    def get_modified_text(self) -> str:
        """Get the current text from the terminal (may include user modifications)"""
        return self.toPlainText()
    
    def get_input_at_cursor(self) -> tuple:
        """Get the text the user has typed and the cursor address"""
        current_text = self.toPlainText()
        cursor_pos = self.textCursor().position()
        
        # Convert cursor position to 3270 buffer address (accounting for newlines)
        row = 0
        col = cursor_pos
        for i, char in enumerate(current_text[:cursor_pos]):
            if char == '\n':
                row += 1
                col = cursor_pos - i - 1
        
        buffer_addr = row * self.cols + min(col, self.cols - 1)
        
        # For now, return all modified content on the current line
        lines = current_text.split('\n')
        if row < len(lines):
            line_content = lines[row]
        else:
            line_content = ""
        
        return buffer_addr, line_content
    
    def get_cursor_address(self) -> int:
        """Get current cursor position as 3270 buffer address"""
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()
        
        # Count rows and find column by iterating through text
        row = 0
        col = 0
        for i, char in enumerate(text):
            if i >= pos:
                break
            if char == '\n':
                row += 1
                col = 0
            else:
                col += 1
        
        return row * self.cols + min(col, self.cols - 1)


class TerminalSettingsDialog(QDialog):
    """Settings dialog for terminal connection options"""
    
    def __init__(self, parent=None, host="PRODESA", port=992, ssl=True, term_type="IBM-3278-2-E", userid="", password=""):
        super().__init__(parent)
        self.parent_screen = parent  # Store parent to access connection manager
        self.setWindowTitle("Terminal Settings")
        self.setModal(True)
        self.setMinimumWidth(420)
        
        # Dialog styling
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                color: #333;
                border: 1px solid #ccc;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 8px;
                background-color: white;
            }
            QLabel {
                color: #333;
                font-size: 12px;
            }
            QCheckBox {
                color: #333;
                font-size: 12px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Common input style
        input_style = """
            QLineEdit, QSpinBox, QComboBox {
                padding: 8px;
                border: 1px solid #bbb;
                border-radius: 4px;
                background-color: white;
                color: #333;
                font-size: 12px;
                min-height: 20px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border-color: #2c5f8d;
                border-width: 2px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                width: 12px;
                height: 12px;
            }
        """
        
        # Connection Settings Group
        conn_group = QGroupBox("Connection")
        conn_form = QFormLayout()
        conn_form.setSpacing(12)
        conn_form.setContentsMargins(15, 20, 15, 15)
        
        # Host input
        self.host_input = QLineEdit()
        self.host_input.setText(host)
        self.host_input.setPlaceholderText("mainframe.example.com")
        self.host_input.setStyleSheet(input_style)
        conn_form.addRow("Host:", self.host_input)
        
        # Port input
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(port)
        self.port_input.setStyleSheet(input_style)
        conn_form.addRow("Port:", self.port_input)
        
        # SSL checkbox
        self.ssl_checkbox = QCheckBox("Enable SSL/TLS")
        self.ssl_checkbox.setChecked(ssl)
        self.ssl_checkbox.stateChanged.connect(self.on_ssl_changed)
        conn_form.addRow("Security:", self.ssl_checkbox)
        
        # Terminal type
        self.term_type_combo = QComboBox()
        self.term_type_combo.addItems([
            "IBM-3278-2-E",
            "IBM-3278-2",
            "IBM-3279-2-E",
            "IBM-3279-2",
            "IBM-3278-3-E",
            "IBM-3278-4-E",
            "IBM-3278-5-E",
        ])
        self.term_type_combo.setCurrentText(term_type)
        self.term_type_combo.setStyleSheet(input_style)
        conn_form.addRow("Terminal Type:", self.term_type_combo)
        
        conn_group.setLayout(conn_form)
        layout.addWidget(conn_group)
        
        # Note about credentials
        cred_note = QLabel("💡 Use the 'User' button at the bottom of the window to set your credentials.")
        cred_note.setStyleSheet("""
            QLabel {
                color: #666;
                font-style: italic;
                padding: 10px;
                background-color: #f0f8ff;
                border-radius: 4px;
                border: 1px solid #cce5ff;
            }
        """)
        cred_note.setWordWrap(True)
        layout.addWidget(cred_note)
        
        # Port Scanner Group
        scan_group = QGroupBox("Port Scanner")
        scan_layout = QVBoxLayout()
        scan_layout.setSpacing(8)
        scan_layout.setContentsMargins(15, 20, 15, 15)
        
        # Scan button and progress
        scan_btn_layout = QHBoxLayout()
        self.scan_button = QPushButton("🔍 Scan Ports")
        self.scan_button.setStyleSheet("""
            QPushButton {
                background-color: #3182ce;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #4299e1;
            }
            QPushButton:disabled {
                background-color: #a0aec0;
            }
        """)
        self.scan_button.clicked.connect(self.start_port_scan)
        scan_btn_layout.addWidget(self.scan_button)
        
        self.scan_progress = QProgressBar()
        self.scan_progress.setVisible(False)
        self.scan_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #bbb;
                border-radius: 4px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #3182ce;
            }
        """)
        scan_btn_layout.addWidget(self.scan_progress)
        scan_btn_layout.addStretch()
        scan_layout.addLayout(scan_btn_layout)
        
        # Results table
        self.scan_results = QTableWidget()
        self.scan_results.setColumnCount(4)
        self.scan_results.setHorizontalHeaderLabels(["Port", "Status", "SSL?", "Description"])
        self.scan_results.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.scan_results.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.scan_results.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.scan_results.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.scan_results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.scan_results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.scan_results.setMaximumHeight(150)
        self.scan_results.setStyleSheet("""
            QTableWidget {
                border: 1px solid #bbb;
                border-radius: 4px;
                background-color: white;
                font-size: 11px;
                outline: none;
            }
            QTableWidget::item {
                padding: 0px;
                margin: 0px;
                border: none;
                outline: none;
            }
            QTableWidget::item:selected {
                background-color: #0078d4;
                color: white;
                border: none;
                outline: none;
            }
            QTableWidget::item:focus {
                border: none;
                outline: none;
            }
            QHeaderView::section {
                background-color: #e2e8f0;
                padding: 5px;
                border: none;
                font-weight: bold;
            }
        """)
        self.scan_results.cellDoubleClicked.connect(self.on_port_selected)
        scan_layout.addWidget(self.scan_results)
        
        # Help text
        scan_help = QLabel("Double-click a port to use it. Right-click port 443 to open in browser.")
        scan_help.setStyleSheet("color: #718096; font-size: 10px; font-style: italic;")
        scan_layout.addWidget(scan_help)
        
        # Enable context menu for the results table
        self.scan_results.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.scan_results.customContextMenuRequested.connect(self.on_port_context_menu)
        
        scan_group.setLayout(scan_layout)
        layout.addWidget(scan_group)
        
        # Add some spacing before buttons
        layout.addSpacing(10)
        
        # Custom styled buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                padding: 10px 25px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
                min-width: 80px;
                border: none;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        ok_button = QPushButton("OK")
        ok_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 10px 25px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
                min-width: 80px;
                border: none;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        ok_button.clicked.connect(self.accept)
        ok_button.setDefault(True)
        button_layout.addWidget(ok_button)
        
        layout.addLayout(button_layout)
    
    def on_ssl_changed(self, state):
        """Update port when SSL is toggled"""
        if state == Qt.CheckState.Checked.value:
            if self.port_input.value() == 23:
                self.port_input.setValue(992)
        else:
            if self.port_input.value() == 992:
                self.port_input.setValue(23)
    
    def get_settings(self):
        """Return the current settings"""
        # Get credentials from MAINFRAME_USER connection
        userid = ""
        password = ""
        if self.parent_screen and hasattr(self.parent_screen, 'conn_manager'):
            user_conn = self.parent_screen.conn_manager.get_connection("MAINFRAME_USER")
            if user_conn:
                userid = user_conn.get('username', '')
                if user_conn.get('password'):
                    password = self.parent_screen.cred_manager.decrypt_password(user_conn.get('password', ''))
        
        return {
            'host': self.host_input.text(),
            'port': self.port_input.value(),
            'ssl': self.ssl_checkbox.isChecked(),
            'term_type': self.term_type_combo.currentText(),
            'userid': userid,
            'password': password
        }
    
    def start_port_scan(self):
        """Start scanning common TN3270 ports on the host"""
        host = self.host_input.text().strip()
        if not host:
            QMessageBox.warning(self, "No Host", "Please enter a hostname first.")
            return
        
        # Common TN3270 and related ports to scan
        ports_to_scan = [
            (23, False, "Standard Telnet (no encryption)"),
            (992, True, "TN3270 over TLS/SSL (secure)"),
            (623, False, "Alternative TN3270 port"),
            (1023, False, "Alternative TN3270 port"),
            (2023, False, "Alternative TN3270 port"),
            (3023, False, "Alternative TN3270 port"),
            (10023, False, "High-port TN3270"),
            (10992, True, "High-port TN3270 SSL"),
            (443, True, "HTTPS (sometimes TN3270)"),
            (8023, False, "Custom TN3270 port"),
        ]
        
        self.scan_button.setEnabled(False)
        self.scan_button.setText("Scanning...")
        self.scan_progress.setVisible(True)
        self.scan_progress.setMaximum(len(ports_to_scan))
        self.scan_progress.setValue(0)
        
        self.scan_results.setRowCount(0)
        
        QApplication.processEvents()
        
        open_ports = []
        
        for i, (port, try_ssl, description) in enumerate(ports_to_scan):
            self.scan_progress.setValue(i + 1)
            QApplication.processEvents()
            
            result = self._test_port(host, port, try_ssl)
            
            if result['open']:
                open_ports.append((port, result['ssl_works'], description, result['details']))
        
        # Display results
        self.scan_results.setRowCount(len(open_ports))
        for row, (port, ssl_works, description, details) in enumerate(open_ports):
            self.scan_results.setItem(row, 0, QTableWidgetItem(str(port)))
            
            status_item = QTableWidgetItem("✅ Open")
            status_item.setForeground(QColor("#27ae60"))
            self.scan_results.setItem(row, 1, status_item)
            
            ssl_text = "Yes" if ssl_works else "No"
            ssl_item = QTableWidgetItem(ssl_text)
            if ssl_works:
                ssl_item.setForeground(QColor("#3182ce"))
            self.scan_results.setItem(row, 2, ssl_item)
            
            desc_text = f"{description}"
            if details:
                desc_text += f" - {details}"
            self.scan_results.setItem(row, 3, QTableWidgetItem(desc_text))
        
        if not open_ports:
            self.scan_results.setRowCount(1)
            self.scan_results.setItem(0, 0, QTableWidgetItem("-"))
            no_result = QTableWidgetItem("No open ports found")
            no_result.setForeground(QColor("#e74c3c"))
            self.scan_results.setItem(0, 1, no_result)
            self.scan_results.setItem(0, 2, QTableWidgetItem("-"))
            self.scan_results.setItem(0, 3, QTableWidgetItem("Check hostname or firewall"))
        
        self.scan_button.setEnabled(True)
        self.scan_button.setText("🔍 Scan Ports")
        self.scan_progress.setVisible(False)
    
    def _test_port(self, host: str, port: int, try_ssl: bool) -> dict:
        """Test if a port is open and optionally check SSL.
        
        Returns dict with 'open', 'ssl_works', 'details' keys.
        """
        result = {'open': False, 'ssl_works': False, 'details': ''}
        
        # First try plain connection
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)  # 2 second timeout
            sock.connect((host, port))
            result['open'] = True
            
            # Try to read initial data (TN3270 servers often send negotiation)
            try:
                sock.settimeout(0.5)
                data = sock.recv(100)
                if data:
                    # Check for TN3270 telnet negotiation bytes
                    if b'\xff' in data:  # IAC byte - telnet negotiation
                        result['details'] = "TN3270 negotiation detected"
                    elif b'SSH' in data:
                        result['details'] = "SSH server"
                    elif b'HTTP' in data or b'<' in data:
                        result['details'] = "HTTP/Web server"
            except:
                pass
            
            sock.close()
            
            # If SSL suggested, try SSL connection
            if try_ssl or port in [992, 443, 10992]:
                try:
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    
                    sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock2.settimeout(2.0)
                    ssl_sock = context.wrap_socket(sock2, server_hostname=host)
                    ssl_sock.connect((host, port))
                    result['ssl_works'] = True
                    result['details'] = "SSL/TLS connection OK"
                    ssl_sock.close()
                except ssl.SSLError as e:
                    if result['open']:
                        result['details'] = "Open but SSL failed"
                except:
                    pass
            
        except socket.timeout:
            result['details'] = 'Timeout'
        except ConnectionRefusedError:
            result['details'] = 'Refused'
        except socket.gaierror:
            result['details'] = 'DNS error'
        except Exception as e:
            result['details'] = str(e)[:30]
        
        return result
    
    def on_port_selected(self, row: int, col: int):
        """Handle double-click on a port result to use that port"""
        port_item = self.scan_results.item(row, 0)
        ssl_item = self.scan_results.item(row, 2)
        
        if port_item and port_item.text() != "-":
            try:
                port = int(port_item.text())
                self.port_input.setValue(port)
                
                # Auto-set SSL checkbox based on scan result
                if ssl_item:
                    use_ssl = ssl_item.text() == "Yes"
                    self.ssl_checkbox.setChecked(use_ssl)
                
                self.scan_results.clearSelection()
            except ValueError:
                pass
    
    def on_port_context_menu(self, pos):
        """Show context menu for port results (e.g., open HTTPS in browser)"""
        item = self.scan_results.itemAt(pos)
        if not item:
            return
        
        row = item.row()
        port_item = self.scan_results.item(row, 0)
        ssl_item = self.scan_results.item(row, 2)
        
        if not port_item or port_item.text() == "-":
            return
        
        try:
            port = int(port_item.text())
        except ValueError:
            return
        
        menu = QMenu(self)
        
        # Add "Use this port" action
        use_action = menu.addAction("📡 Use this port for TN3270")
        
        # Add "Open in browser" for HTTPS ports
        is_ssl = ssl_item and ssl_item.text() == "Yes"
        if port in [443, 8443, 9443] or (is_ssl and port not in [992, 10992]):
            menu.addSeparator()
            browser_action = menu.addAction("🌐 Open in Browser (HTTPS)")
            browser_action.setData(("browser", port, True))
        
        # For any open port, offer HTTP option
        menu.addSeparator()
        http_action = menu.addAction("🌐 Open in Browser (HTTP)")
        http_action.setData(("browser", port, False))
        
        # Show the menu and handle selection
        action = menu.exec(self.scan_results.viewport().mapToGlobal(pos))
        
        if action:
            if action.data() and action.data()[0] == "browser":
                _, p, use_https = action.data()
                host = self.host_input.text().strip()
                protocol = "https" if use_https else "http"
                url = f"{protocol}://{host}:{p}/" if p not in [80, 443] else f"{protocol}://{host}/"
                QDesktopServices.openUrl(QUrl(url))
            elif action == use_action:
                self.port_input.setValue(port)
                if ssl_item:
                    self.ssl_checkbox.setChecked(ssl_item.text() == "Yes")


class MainframeTerminalScreen(QWidget):
    """Mainframe Terminal Screen with TN3270 emulation"""
    
    def __init__(self):
        super().__init__()
        
        # Allow this widget to shrink and expand flexibly
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Set a reasonable minimum size that allows window to be made smaller
        self.setMinimumSize(250, 300)
        
        self.client: TN3270Client = None
        self.receive_thread: TerminalReceiveThread = None
        self.input_buffer = ""
        self.current_input_address = 0
        
        # Settings file for persistence
        from pathlib import Path
        self.settings_file = Path.home() / '.suiteview' / 'terminal_settings.json'
        
        # Connection settings (stored for settings dialog)
        self.conn_host = ""
        self.conn_port = 992
        self.conn_ssl = True
        self.conn_term_type = "IBM-3278-2-E"
        self.conn_userid = ""
        self.conn_password = ""
        
        # Flag to auto-fill credentials after connect
        self.pending_autofill = False
        
        # Flag to use OPEN command for secondary sessions (dual terminal support)
        self.use_open_for_new_session = False
        
        # Load saved settings
        self._load_settings()
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Connection bar - simplified
        conn_frame = QFrame()
        conn_frame.setStyleSheet("""
            QFrame {
                background-color: #1a365d;
                border-radius: 5px;
                padding: 5px;
            }
        """)
        conn_layout = QHBoxLayout(conn_frame)
        conn_layout.setContentsMargins(10, 5, 10, 5)
        
        # Connection status label
        self.conn_status_label = QLabel(f"⚫ {self.conn_host}")
        self.conn_status_label.setStyleSheet("color: #888; font-weight: bold; font-size: 12px;")
        conn_layout.addWidget(self.conn_status_label)
        
        conn_layout.addStretch()
        
        # Settings button
        self.settings_button = QPushButton("⚙️ Settings")
        self.settings_button.setStyleSheet("""
            QPushButton {
                background-color: #4a5568;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a6578;
            }
        """)
        self.settings_button.clicked.connect(self.show_settings)
        conn_layout.addWidget(self.settings_button)
        
        # Connect/Disconnect button
        self.connect_button = QPushButton("🔌 Connect")
        self.connect_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        self.connect_button.clicked.connect(self.toggle_connection)
        conn_layout.addWidget(self.connect_button)
        
        layout.addWidget(conn_frame)
        
        # Quick navigation buttons bar
        nav_frame = QFrame()
        nav_frame.setStyleSheet("""
            QFrame {
                background-color: #2d3748;
                border-radius: 5px;
                padding: 0px;
            }
        """)
        nav_layout = QHBoxLayout(nav_frame)
        nav_layout.setContentsMargins(4, 2, 4, 2)
        nav_layout.setSpacing(4)
        
        nav_label = QLabel("Quick Nav:")
        nav_label.setStyleSheet("color: #a0aec0; font-weight: bold; font-size: 11px;")
        nav_layout.addWidget(nav_label)
        
        # Common button style for nav buttons
        nav_btn_style = """
            QPushButton {
                background-color: #805ad5;
                color: white;
                padding: 1px 5px;
                border-radius: 3px;
                font-weight: bold;
                font-size: 11px;
                min-width: 42px;
                min-height: 18px;
            }
            QPushButton:hover {
                background-color: #9f7aea;
            }
            QPushButton:disabled {
                background-color: #4a5568;
                color: #718096;
            }
        """

        # Compact quick-nav buttons grid (4x4, room for more later)
        nav_buttons_widget = QWidget()
        nav_buttons_grid = QGridLayout(nav_buttons_widget)
        nav_buttons_grid.setContentsMargins(0, 0, 0, 0)
        nav_buttons_grid.setHorizontalSpacing(1)
        nav_buttons_grid.setVerticalSpacing(1)

        def _make_nav_btn(text: str, tooltip: str, region_option: str = "") -> QPushButton:
            btn = QPushButton(text)
            btn.setStyleSheet(nav_btn_style)
            btn.setToolTip(tooltip)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda: self.start_cics_sequence(text, region_option))
            return btn

        # Place current regions in a tight 2x2 area within the 4x4 grid
        self.ckas_button = _make_nav_btn("CKAS", "Auto-login to CKAS (CICS Cyberlife Dev)", "1")
        self.ckmo_button = _make_nav_btn("CKMO", "Auto-login to CKMO (CICS Model Office)", "5")
        self.ckpr_button = _make_nav_btn("CKPR", "Auto-login to CKPR (Cyberlife Production)", "7")
        self.cksr_button = _make_nav_btn("CKSR", "Auto-login to CKSR", "")

        nav_buttons_grid.addWidget(self.ckas_button, 0, 0)
        nav_buttons_grid.addWidget(self.ckmo_button, 0, 1)
        nav_buttons_grid.addWidget(self.ckpr_button, 1, 0)
        nav_buttons_grid.addWidget(self.cksr_button, 1, 1)

        nav_layout.addWidget(nav_buttons_widget)

        nav_layout.addSpacing(6)
        
        # Policy lookup section
        policy_label = QLabel("Policy:")
        policy_label.setStyleSheet("color: #a0aec0; font-weight: bold; font-size: 11px;")
        nav_layout.addWidget(policy_label)
        
        # Policy number input (up to 10 digits)
        self.policy_input = QLineEdit()
        self.policy_input.setPlaceholderText("Policy #")
        self.policy_input.setMaxLength(10)
        self.policy_input.setFixedWidth(100)
        self.policy_input.setStyleSheet("""
            QLineEdit {
                background-color: #2d3748;
                color: white;
                border: 1px solid #4a5568;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border-color: #805ad5;
            }
        """)
        nav_layout.addWidget(self.policy_input)
        
        # Company combobox
        co_label = QLabel("Co:")
        co_label.setStyleSheet("color: #a0aec0; font-weight: bold; font-size: 11px;")
        nav_layout.addWidget(co_label)
        
        self.company_combo = QComboBox()
        self.company_combo.addItems(["01", "04", "06", "08", "26"])
        self.company_combo.setCurrentText("01")
        self.company_combo.setFixedWidth(60)
        self.company_combo.setStyleSheet("""
            QComboBox {
                background-color: #2d3748;
                color: white;
                border: 1px solid #4a5568;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QComboBox:focus {
                border-color: #805ad5;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #a0aec0;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: #2d3748;
                color: white;
                selection-background-color: #805ad5;
            }
        """)
        nav_layout.addWidget(self.company_combo)
        
        nav_layout.addStretch()
        
        # Automation status label
        self.automation_status = QLabel("")
        self.automation_status.setStyleSheet("color: #f6e05e; font-size: 11px;")
        nav_layout.addWidget(self.automation_status)
        
        layout.addWidget(nav_frame)
        
        # Main terminal area
        terminal_frame = QFrame()
        terminal_frame.setStyleSheet("""
            QFrame {
                background-color: #000000;
                border: 3px solid #2c5f8d;
                border-radius: 5px;
            }
        """)
        terminal_layout = QVBoxLayout(terminal_frame)
        terminal_layout.setContentsMargins(0, 0, 0, 0)
        
        # Terminal display
        self.terminal = TerminalWidget()
        self.terminal.key_pressed.connect(self.handle_key)
        self.terminal.enter_pressed.connect(self.send_screen_input)
        self.terminal.pf_key_pressed.connect(self.send_pf_key)
        self.terminal.clear_pressed.connect(self.send_clear)
        terminal_layout.addWidget(self.terminal)
        
        layout.addWidget(terminal_frame, 1)
        
        # Input line removed - type directly on screen and press Enter
        # Keep a reference for compatibility but don't show it
        self.input_line = None
        
        # Function key bar
        pf_frame = QFrame()
        pf_frame.setStyleSheet("""
            QFrame {
                background-color: #1e3a5f;
                border-radius: 5px;
                padding: 3px;
            }
        """)
        pf_layout = QHBoxLayout(pf_frame)
        pf_layout.setContentsMargins(5, 3, 5, 3)
        pf_layout.setSpacing(3)
        
        # PF keys row 1 (PF1-PF12)
        pf_style = """
            QPushButton {
                background-color: #2c5f8d;
                color: white;
                padding: 5px 8px;
                border-radius: 3px;
                font-size: 10px;
                min-width: 40px;
            }
            QPushButton:hover {
                background-color: #3d7ab5;
            }
            QPushButton:pressed {
                background-color: #1a4971;
            }
        """
        
        for i in range(1, 13):
            btn = QPushButton(f"PF{i}")
            btn.setStyleSheet(pf_style)
            btn.clicked.connect(lambda checked, n=i: self.send_pf_key(n))
            pf_layout.addWidget(btn)
        
        pf_layout.addSpacing(10)
        
        # Special keys
        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet(pf_style)
        clear_btn.clicked.connect(self.send_clear)
        pf_layout.addWidget(clear_btn)
        
        pa1_btn = QPushButton("PA1")
        pa1_btn.setStyleSheet(pf_style)
        pa1_btn.clicked.connect(lambda: self.send_pa_key(1))
        pf_layout.addWidget(pa1_btn)
        
        pa2_btn = QPushButton("PA2")
        pa2_btn.setStyleSheet(pf_style)
        pa2_btn.clicked.connect(lambda: self.send_pa_key(2))
        pf_layout.addWidget(pa2_btn)
        
        pf_layout.addStretch()
        
        layout.addWidget(pf_frame)
        
        # Status bar
        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("""
            color: #e74c3c;
            font-weight: bold;
            padding: 5px;
            font-size: 11px;
        """)
        layout.addWidget(self.status_label)
    
    def show_settings(self):
        """Show the settings dialog"""
        dialog = TerminalSettingsDialog(
            self,
            host=self.conn_host,
            port=self.conn_port,
            ssl=self.conn_ssl,
            term_type=self.conn_term_type,
            userid=self.conn_userid,
            password=self.conn_password
        )
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            settings = dialog.get_settings()
            self.conn_host = settings['host']
            self.conn_port = settings['port']
            self.conn_ssl = settings['ssl']
            self.conn_term_type = settings['term_type']
            self.conn_userid = settings['userid']
            self.conn_password = settings['password']
            
            # Save settings to disk
            self._save_settings()
            
            # Update status label
            self.update_connection_status()
    
    def _load_settings(self):
        """Load terminal settings from disk"""
        import json
        
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
                
                self.conn_host = settings.get('host', self.conn_host)
                self.conn_port = settings.get('port', self.conn_port)
                self.conn_ssl = settings.get('ssl', self.conn_ssl)
                self.conn_term_type = settings.get('term_type', self.conn_term_type)
                self.conn_userid = settings.get('userid', self.conn_userid)
                self.conn_password = settings.get('password', self.conn_password)
                
                logger.info(f"Loaded terminal settings from {self.settings_file}")
            except Exception as e:
                logger.error(f"Failed to load terminal settings: {e}")
    
    def _save_settings(self):
        """Save terminal settings to disk"""
        import json
        
        try:
            # Ensure directory exists
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            
            settings = {
                'host': self.conn_host,
                'port': self.conn_port,
                'ssl': self.conn_ssl,
                'term_type': self.conn_term_type,
                'userid': self.conn_userid,
                'password': self.conn_password
            }
            
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
            
            logger.info(f"Saved terminal settings to {self.settings_file}")
        except Exception as e:
            logger.error(f"Failed to save terminal settings: {e}")
    
    def update_connection_status(self):
        """Update the connection status label"""
        if self.client and self.client.connected:
            ssl_text = " (SSL)" if self.conn_ssl else ""
            # Include assigned LU name if available
            lu_text = f" [{self.client.assigned_lu_name}]" if self.client.assigned_lu_name else ""
            self.conn_status_label.setText(f"🟢 {self.conn_host}:{self.conn_port}{ssl_text}{lu_text}")
            self.conn_status_label.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 12px;")
        else:
            self.conn_status_label.setText(f"⚫ {self.conn_host}")
            self.conn_status_label.setStyleSheet("color: #888; font-weight: bold; font-size: 12px;")
    
    def toggle_connection(self):
        """Connect or disconnect from mainframe"""
        if self.client and self.client.connected:
            self.disconnect_from_mainframe()
        else:
            self.connect_to_mainframe()
    
    def connect_to_mainframe(self):
        """Establish connection to mainframe"""
        host = self.conn_host
        port = self.conn_port
        terminal_type = self.conn_term_type
        use_ssl = self.conn_ssl
        
        if not host:
            QMessageBox.warning(self, "Error", "Please enter a hostname in Settings")
            return
        
        ssl_text = " (SSL)" if use_ssl else ""
        self.status_label.setText(f"Connecting to {host}:{port}{ssl_text}...")
        self.status_label.setStyleSheet("color: #f39c12; font-weight: bold; padding: 5px; font-size: 11px;")
        
        # Process events to update UI before blocking connection
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        try:
            self.client = TN3270Client(host, port, use_ssl=use_ssl)
            self.client.terminal_type = terminal_type
            
            if self.client.connect():
                # Include LU name in status if assigned
                lu_text = f" [{self.client.assigned_lu_name}]" if self.client.assigned_lu_name else ""
                self.status_label.setText(f"Connected to {host}:{port}{ssl_text}{lu_text}")
                self.status_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 5px; font-size: 11px;")
                
                self.connect_button.setText("🔌 Disconnect")
                self.connect_button.setStyleSheet("""
                    QPushButton {
                        background-color: #e74c3c;
                        color: white;
                        padding: 8px 20px;
                        border-radius: 4px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #c0392b;
                    }
                """)
                
                # Disable settings while connected
                self.settings_button.setEnabled(False)
                
                # Update connection status
                self.update_connection_status()
                
                # Display initial screen if we got one during negotiation
                screen_text = self.client.screen.get_text() if self.client.screen else ""
                if screen_text and screen_text.strip():
                    logger.info(f"Displaying initial screen ({len(screen_text)} chars)")
                    self.terminal.display_screen(self.client.screen)
                    # Set flag to auto-fill credentials on next screen update if we have them
                    # BUT NOT if pending_autofill was explicitly set to False (automation mode)
                    if not hasattr(self, '_skip_autofill') or not self._skip_autofill:
                        if self.conn_userid or self.conn_password:
                            self.pending_autofill = True
                            # Try to auto-fill now if the screen has input fields
                            QTimer.singleShot(500, self._try_autofill_credentials)
                else:
                    logger.warning("No initial screen data received during negotiation")
                    # Show a placeholder message
                    self.terminal.setPlainText("Connected. Waiting for mainframe response...\n\nIf this screen stays blank, try pressing Enter or a PF key.")
                    # Also set autofill flag for when screen arrives (unless automation)
                    if not hasattr(self, '_skip_autofill') or not self._skip_autofill:
                        if self.conn_userid or self.conn_password:
                            self.pending_autofill = True
                
                # Start receive thread
                self.receive_thread = TerminalReceiveThread(self.client)
                self.receive_thread.screen_updated.connect(self.on_screen_update)
                self.receive_thread.connection_lost.connect(self.on_connection_lost)
                self.receive_thread.start()
                
                # Enable input - focus on terminal for direct screen input
                if self.input_line:
                    self.input_line.setEnabled(True)
                    self.input_line.setFocus()
                else:
                    self.terminal.setFocus()
                
                logger.info(f"Connected to mainframe {host}:{port}")
                
            else:
                self.status_label.setText("Connection failed")
                self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 5px; font-size: 11px;")
                ssl_note = "\n• SSL/TLS may be required or misconfigured" if use_ssl else "\n• Try enabling SSL/TLS"
                QMessageBox.critical(self, "Connection Failed", 
                    f"Could not connect to {host}:{port}{ssl_text}\n\nPlease check:\n"
                    "• The hostname is correct\n"
                    f"• The port is correct (you're using {port})\n"
                    "• The mainframe is accessible from your network"
                    f"{ssl_note}")
                
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.status_label.setText(f"Error: {str(e)}")
            self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 5px; font-size: 11px;")
            QMessageBox.critical(self, "Error", f"Connection failed:\n{str(e)}")

    def disconnect_from_mainframe(self):
        """Disconnect from mainframe"""
        if self.receive_thread:
            self.receive_thread.stop()
            self.receive_thread.wait(2000)
            self.receive_thread = None
        
        if self.client:
            self.client.disconnect()
            self.client = None
        
        self.status_label.setText("Disconnected")
        self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 5px; font-size: 11px;")
        
        self.connect_button.setText("🔌 Connect")
        self.connect_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        
        # Enable settings button
        self.settings_button.setEnabled(True)
        
        # Update connection status label
        self.update_connection_status()
        
        # Clear terminal and reset state
        self.terminal.clear()
        self.terminal.typed_chars = {}
        self._screen_update_count = 0
        self.pending_autofill = False
        
        logger.info("Disconnected from mainframe")
    
    def on_screen_update(self, screen: Screen):
        """Handle screen update from receive thread"""
        self.terminal.display_screen(screen)
        
        # Increment screen update counter for _wait_for_screen
        self._screen_update_count = getattr(self, '_screen_update_count', 0) + 1
        
        # Try auto-fill if pending
        if self.pending_autofill:
            QTimer.singleShot(100, self._try_autofill_credentials)
    
    def _try_autofill_credentials(self):
        """Try to auto-fill userid and password into the first two input fields"""
        if not self.pending_autofill:
            return
        
        if not self.terminal.last_screen:
            return
        
        screen = self.terminal.last_screen
        input_fields = screen.get_input_fields()
        
        if not input_fields:
            logger.debug("No input fields found for autofill")
            return
        
        # Sort fields by address
        input_fields.sort(key=lambda f: f.address)
        
        # Fill first field with userid if we have one
        if self.conn_userid and len(input_fields) >= 1:
            field = input_fields[0]
            field_start = field.address + 1  # Data starts after field attribute
            
            # Type userid into this field
            for i, char in enumerate(self.conn_userid):
                self.terminal.typed_chars[field_start + i] = char
            
            logger.info(f"Auto-filled userid into field at {field_start}")
        
        # Fill second field with password if we have one
        if self.conn_password and len(input_fields) >= 2:
            field = input_fields[1]
            field_start = field.address + 1
            
            # Type password into this field
            for i, char in enumerate(self.conn_password):
                self.terminal.typed_chars[field_start + i] = char
            
            logger.info(f"Auto-filled password into field at {field_start}")
        
        # Refresh display to show userid (password will be hidden)
        if self.conn_userid or self.conn_password:
            self._refresh_autofilled_display()
        
        # Only auto-fill once
        self.pending_autofill = False
    
    def _refresh_autofilled_display(self):
        """Refresh the terminal display to show auto-filled content"""
        if not self.terminal.last_screen:
            return
        
        screen = self.terminal.last_screen
        input_fields = screen.get_input_fields()
        input_fields.sort(key=lambda f: f.address)
        
        # Get current cursor position
        cursor = self.terminal.textCursor()
        
        # Update display for first field (userid - visible)
        if self.conn_userid and len(input_fields) >= 1:
            field = input_fields[0]
            field_start = field.address + 1
            
            # Move cursor to field start and type the characters visually
            self.terminal._move_cursor_to_address(field_start)
            cursor = self.terminal.textCursor()
            
            for char in self.conn_userid:
                if not cursor.atEnd():
                    cursor.deleteChar()
                cursor.insertText(char)
            
            self.terminal.setTextCursor(cursor)
        
        # Second field (password) - characters are already in typed_chars but display as blanks
        # because _in_password_field() should detect it
        
        # Move cursor to after userid field or password field
        if len(input_fields) >= 2:
            # Position cursor at password field
            pwd_field_start = input_fields[1].address + 1
            self.terminal._move_cursor_to_address(pwd_field_start)
        elif len(input_fields) >= 1 and self.conn_userid:
            # Position cursor after userid
            uid_field_start = input_fields[0].address + 1
            self.terminal._move_cursor_to_address(uid_field_start + len(self.conn_userid))
    
    def on_connection_lost(self, error: str):
        """Handle lost connection"""
        self.disconnect_from_mainframe()
        QMessageBox.warning(self, "Connection Lost", f"Connection to mainframe lost:\n{error}")
    
    def handle_key(self, event: QKeyEvent):
        """Handle keyboard input from terminal"""
        if not self.client or not self.client.connected:
            return
        
        key = event.key()
        modifiers = event.modifiers()
        
        # Function keys
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F12:
            pf_num = key - Qt.Key.Key_F1 + 1
            self.send_pf_key(pf_num)
        elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            self.send_screen_input()
        elif key == Qt.Key.Key_Escape:
            self.send_clear()
        elif key == Qt.Key.Key_Tab:
            # Tab to next field - handled by 3270
            pass
        else:
            # Regular character - add to input buffer
            text = event.text()
            if text and text.isprintable():
                self.input_buffer += text
                if self.input_line:
                    self.input_line.setText(self.input_buffer)
    
    def send_screen_input(self):
        """Send input typed directly on the screen to mainframe"""
        if not self.client or not self.client.connected:
            logger.warning("Cannot send - not connected")
            return
        
        # Update client cursor position to match UI cursor
        # This ensures the mainframe knows exactly where the user was when they hit Enter
        current_cursor_addr = self.terminal.get_cursor_address()
        if self.client.screen:
            self.client.screen.cursor_address = current_cursor_addr
            logger.debug(f"Updated client cursor address to {current_cursor_addr}")
        
        # Log the raw typed_chars for debugging
        logger.info(f"typed_chars before sending: {self.terminal.typed_chars}")
        
        if not self.terminal.typed_chars or not self.terminal.last_screen:
            # Nothing typed - just send ENTER
            self.client.send_aid(AID.ENTER, None)
            logger.info("Sent ENTER with no modified fields")
            return
        
        # Build complete field contents by merging typed chars with original buffer
        screen = self.terminal.last_screen
        input_fields = screen.get_input_fields()
        modified_fields = []
        
        # For each input field, check if any typed_chars fall within it
        for field in input_fields:
            field_start = field.address + 1  # Data starts after field attribute
            
            # Find the end of this field (next field start or end of screen)
            field_end = screen.rows * screen.cols
            for other in screen.fields:
                if other.address > field.address and other.address < field_end:
                    field_end = other.address
            
            # Check if any typed characters are in this field
            typed_in_field = {addr: char for addr, char in self.terminal.typed_chars.items() 
                            if field_start <= addr < field_end}
            
            # Include field if it was modified by user OR if it was pre-modified by host (MDT set)
            if typed_in_field or field.modified:
                # Build complete field content from buffer + typed chars
                field_content = []
                for addr in range(field_start, field_end):
                    if addr in self.terminal.typed_chars:
                        field_content.append(self.terminal.typed_chars[addr])
                    else:
                        field_content.append(screen.buffer[addr])
                
                # Join content - DO NOT rstrip() indiscriminately as it breaks clearing fields
                # We send the full field content to be safe and robust
                content_str = ''.join(field_content)
                
                # Only skip if truly empty and not modified? 
                # Actually, if modified, we must send it, even if empty (though fields are usually spaces/nulls)
                modified_fields.append((field_start, content_str))
                
                is_password = field.hidden if hasattr(field, 'hidden') else not field.display
                if is_password:
                    logger.info(f"Field at {field_start}: [HIDDEN, len={len(content_str)}, modified={field.modified}]")
                else:
                    logger.info(f"Field at {field_start}: '{content_str}' (modified={field.modified})")
        
        logger.info(f"Modified fields to send: {len(modified_fields)} fields")
        
        # Send ENTER with all modified fields
        self.client.send_aid(AID.ENTER, modified_fields if modified_fields else None)
        
        # Clear typed characters after sending
        self.terminal.typed_chars = {}
        
        logger.info(f"Sent screen input with {len(modified_fields)} modified fields")
    
    def send_pf_key(self, pf_num: int):
        """Send PF key"""
        if not self.client or not self.client.connected:
            return
        
        self.client.send_pf_key(pf_num)
        logger.debug(f"Sent PF{pf_num}")
    
    def send_clear(self):
        """Send CLEAR key"""
        if not self.client or not self.client.connected:
            return
        
        self.client.send_clear()
        logger.debug("Sent CLEAR")
    
    def send_pa_key(self, pa_num: int):
        """Send PA key"""
        if not self.client or not self.client.connected:
            return
        
        self.client.send_pa_key(pa_num)
        logger.debug(f"Sent PA{pa_num}")
    
    def closeEvent(self, event):
        """Handle widget close"""
        self.disconnect_from_mainframe()
        super().closeEvent(event)
    
    # ==================== AUTOMATION METHODS ====================
    
    def _capture_screen_count(self) -> int:
        """Capture current screen update count before sending a command."""
        return getattr(self, '_screen_update_count', 0)
    
    def _wait_for_screen_from(self, initial_count: int, timeout_ms: int = 2000) -> bool:
        """Wait for screen update count to exceed initial_count.
        
        Args:
            initial_count: The count captured BEFORE sending a command
            timeout_ms: Maximum time to wait (default 2000ms)
        
        Returns True if screen was received, False if timeout.
        """
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            self._wait(10)  # Check every 10ms
            if getattr(self, '_screen_update_count', 0) > initial_count:
                return True
        
        logger.warning(f"_wait_for_screen_from: timeout after {timeout_ms}ms")
        return False
    
    def _send_enter_and_wait(self, timeout_ms: int = 2000) -> bool:
        """Send Enter and wait for screen response. Returns True if screen received."""
        count = self._capture_screen_count()
        self._auto_send_enter()
        return self._wait_for_screen_from(count, timeout_ms)
    
    def _send_pf_and_wait(self, pf_num: int, timeout_ms: int = 2000) -> bool:
        """Send PF key and wait for screen response. Returns True if screen received."""
        count = self._capture_screen_count()
        self._auto_send_pf(pf_num)
        return self._wait_for_screen_from(count, timeout_ms)
    
    def _type_and_enter(self, text: str, use_menu_field: bool = False, timeout_ms: int = 2000) -> bool:
        """Type text into first field (or menu field) and send Enter. Returns True if screen received."""
        logger.info(f"_type_and_enter: text='{text}', use_menu_field={use_menu_field}")
        
        # Type the text
        if use_menu_field:
            self._auto_type_at_menu_field(text)
        else:
            self._auto_type_in_first_field(text)
        
        # Capture count AFTER typing, right before sending
        count = self._capture_screen_count()
        logger.info(f"_type_and_enter: captured count={count}, sending Enter...")
        self._wait(15)  # Brief wait for typed_chars to register
        self._auto_send_enter()
        result = self._wait_for_screen_from(count, timeout_ms)
        logger.info(f"_type_and_enter: wait result={result}, new count={self._capture_screen_count()}")
        return result
    
    def _wait(self, ms: int):
        """Wait for ms milliseconds while keeping UI responsive"""
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()
    
    def start_ckpr_sequence(self):
        """Start the CKPR auto-login sequence (legacy, calls new method)."""
        self.start_cics_sequence("CKPR", "7")
    
    def _check_reconnect_screen(self) -> bool:
        """Check if current screen is asking to reconnect (session already active).
        
        Returns True if this is the 'USER ON TERM' reconnect screen.
        """
        if not self.terminal.last_screen:
            return False
        
        screen_text = ''.join(self.terminal.last_screen.buffer).upper()
        # Look for the reconnect message
        return "USER ON TERM" in screen_text or "TO ACQUIRE" in screen_text
    
    def _check_multiple_logon_screen(self) -> bool:
        """Check if current screen is the MULTIPLE LOGON screen.
        
        This screen appears when the userid is already logged in on another terminal.
        User can press PF6 to create a new logon session.
        
        Returns True if this is the 'MULTIPLE LOGON' screen.
        """
        if not self.terminal.last_screen:
            return False
        
        screen_text = ''.join(self.terminal.last_screen.buffer).upper()
        # Look for the multiple logon screen indicators
        is_multiple_logon = "MULTIPLE LOGON" in screen_text or "F6=CREATE NEW LOGON" in screen_text
        if is_multiple_logon:
            logger.info("Detected MULTIPLE LOGON screen")
        return is_multiple_logon
    
    def _handle_multiple_logon_screen(self):
        """Handle the MULTIPLE LOGON screen by pressing PF6 to create a new session.
        
        After PF6, we go directly to the PRIMARY APPLICATION SELECTION MENU - 
        same as a fresh login. No need to re-enter credentials.
        """
        logger.info("Handling MULTIPLE LOGON screen - pressing PF6 to create new logon session")
        self._send_pf_and_wait(6)
        
        # After PF6, we should be at the PRIMARY APPLICATION SELECTION MENU
        self._wait(200)  # Brief wait for screen to stabilize
        
        # Log what screen we're at for debugging
        if self.terminal.last_screen:
            screen_text = ''.join(self.terminal.last_screen.buffer)
            logger.info(f"Screen after PF6 (first 160 chars): {screen_text[:160]}")
        
        # PF6 takes us directly to PRIMARY APP MENU - no need to re-login
        if self._check_primary_app_menu():
            logger.info("At PRIMARY APPLICATION SELECTION MENU after PF6 - ready to navigate")
    
    def _check_login_screen(self) -> bool:
        """Check if current screen is the login screen (has User ID field).
        
        Returns True if this appears to be the initial login screen.
        """
        if not self.terminal.last_screen:
            return False
        
        screen_text = ''.join(self.terminal.last_screen.buffer).upper()
        # Look for login screen indicators
        return "USER ID" in screen_text and "PASSWORD" in screen_text
    
    def _fill_credentials_and_enter(self):
        """Fill userid and password into the login screen fields and send Enter."""
        if not self.terminal.last_screen:
            logger.warning("No screen available for credential entry")
            return
        
        screen = self.terminal.last_screen
        input_fields = screen.get_input_fields()
        
        if not input_fields:
            logger.warning("No input fields found for credentials")
            return
        
        input_fields.sort(key=lambda f: f.address)
        logger.info(f"Found {len(input_fields)} input fields for re-login")
        
        # Clear typed chars
        self.terminal.typed_chars = {}
        
        # Type userid into first field
        if self.conn_userid and len(input_fields) >= 1:
            field_start = input_fields[0].address + 1
            for i, char in enumerate(self.conn_userid):
                self.terminal.typed_chars[field_start + i] = char
            logger.info(f"Filled userid into field at {field_start}")
        
        # Type password into second field
        if self.conn_password and len(input_fields) >= 2:
            field_start = input_fields[1].address + 1
            for i, char in enumerate(self.conn_password):
                self.terminal.typed_chars[field_start + i] = char
            logger.info(f"Filled password into field at {field_start}")
        
        # Send Enter
        self._wait(20)
        self._send_enter_and_wait()
    
    def _handle_reconnect_screen(self):
        """Handle the reconnect screen by typing password and pressing PF1.
        
        After PF1, the mainframe returns to the login screen, so we need to
        re-enter credentials and send Enter.
        """
        logger.info("Detected reconnect screen - typing password and pressing PF1")
        
        # Type password into the first input field (the reconnect prompt field)
        if self.terminal.last_screen:
            input_fields = self.terminal.last_screen.get_input_fields()
            if input_fields:
                input_fields.sort(key=lambda f: f.address)
                field_start = input_fields[0].address + 1
                
                self.terminal.typed_chars = {}
                for i, char in enumerate(self.conn_password):
                    self.terminal.typed_chars[field_start + i] = char
                
                logger.info(f"Typed password for reconnect at field {field_start}")
        
        # Send PF1 to acquire the session
        self._wait(20)
        self._send_pf_and_wait(1)
        
        # After PF1, we're back at the login screen - need to re-enter credentials
        if self._check_login_screen():
            logger.info("Back at login screen after reconnect - re-entering credentials")
            self._fill_credentials_and_enter()
    
    def _check_primary_app_menu(self) -> bool:
        """Check if current screen is the PRIMARY APPLICATION SELECTION MENU.
        
        This screen has F4=CKAS, F5=CKMO, F6=CKPR shortcuts.
        """
        if not self.terminal.last_screen:
            return False
        
        screen_text = ''.join(self.terminal.last_screen.buffer).upper()
        return "PRIMARY APPLICATION SELECTION MENU" in screen_text or "F4=CKAS" in screen_text
    
    def _check_vtam_switch_menu(self) -> bool:
        """Check if current screen is the VTAM/Switch Session Selection menu.
        
        This is the menu with options like:
         1 TSO, 2 JQP, 3 CICS, 4 IMS
        
        It also has the OPEN command for starting new sessions.
        """
        if not self.terminal.last_screen:
            return False
        
        screen_text = ''.join(self.terminal.last_screen.buffer).upper()
        return "VTAM/SWITCH" in screen_text or "SESSION SELECTION" in screen_text
    
    def _send_open_command(self):
        """Send OPEN command to start a new session on VTAM/Switch menu.
        
        This is how you can have multiple concurrent sessions.
        """
        logger.info("Sending OPEN command to start new session")
        # Type OPEN into the command field (===>)
        self._auto_type_in_first_field("OPEN")
        self._wait(20)
        self._send_enter_and_wait()
    
    def _get_cics_applid(self, region_name: str) -> str:
        """Get the VTAM APPLID for a CICS region.
        
        These are the application IDs used with the OPEN command on VTAM/Switch.
        Confirmed working: OPEN CICSCKAS, OPEN CICSCKMO, OPEN CICSCKPR
        """
        applids = {
            "CKAS": "CICSCKAS",  # CICS CYBERLIFE DEV - confirmed
            "CKMO": "CICSCKMO",  # CICS Model Office - confirmed
            "CKPR": "CICSCKPR",  # Cyberlife Production - confirmed
            "CKSR": "CICSCKSR",  # (assumed) add if region exists
        }
        return applids.get(region_name.upper(), "")
    
    def _open_application(self, applid: str):
        """Open a specific application by APPLID using OPEN command.
        
        This creates a new session to the specified application.
        """
        logger.info(f"Opening application: {applid}")
        # Type "OPEN applid" into the command field
        self._auto_type_in_first_field(f"OPEN {applid}")
        self._wait(20)
        self._send_enter_and_wait()
    
    def _get_cics_pf_key(self, region_name: str) -> int:
        """Get the PF key for direct CICS region access from PRIMARY APP MENU.
        
        Returns PF key number (4, 5, or 6) or 0 if not found.
        """
        pf_keys = {
            "CKAS": 4,
            "CKMO": 5, 
            "CKPR": 6
        }
        return pf_keys.get(region_name.upper(), 0)
    
    def _handle_1992_sequence(self, region_name: str):
        """Handle the specific launch sequence for Port 1992.
        
        Sequence:
        1. (Already done) Login / PF6
        2. Blank Screen -> Enter -> Enter
        3. Primary App Menu -> Type ID (120/122/125) -> Enter -> Wait -> Enter
        4. CICS Screen -> "0000" -> Enter -> F2 -> F2 -> F2
        5. Policy Entry
        """
        logger.info(f"Starting Port 1992 sequence for {region_name}")
        self.automation_status.setText(f"🔄 {region_name} (1992 sequence)...")
        
        # Step 2: Blank screen -> Enter twice
        # We are at the blank screen now (after login or PF6)
        logger.info("Sending first Enter for blank screen")
        self._send_enter_and_wait()
        self._wait(500)
        logger.info("Sending second Enter for blank screen")
        self._send_enter_and_wait()
        self._wait(500)
        
        # Step 3: Primary Application Selection Menu
        # CKAS = 120, CKMO = 122, CKPR = 125
        # CKSR: type CICSCKSR at the input (same step, different selector)
        region_selectors = {
            "CKAS": "120",
            "CKMO": "122",
            "CKPR": "125",
            "CKSR": "CICSCKSR",
        }
        selector = region_selectors.get(region_name.upper())

        if not selector:
            logger.error(f"Unknown region for 1992 sequence: {region_name}")
            self.automation_status.setText(f"❌ Unknown region {region_name}")
            return

        logger.info(f"Selecting region {region_name} (selector {selector})")
        self._type_and_enter(selector)
        
        # Wait a bit and send Enter again
        self._wait(1000)
        logger.info("Sending confirmation Enter")
        self._send_enter_and_wait()
        
        # Step 4: CICS/TS Screen (Welcome to ...)
        # Type "0000" at top left (MENU)
        self._wait(500)
        logger.info("At CICS screen - typing 0000")
        
        # "Put the cursor at the top left and type '0000' where you see 'MENU'"
        self._type_and_enter("0000", use_menu_field=True)
        
        # F2 three times
        logger.info("Sending F2, F2, F2")
        self._send_pf_and_wait(2)
        self._send_pf_and_wait(2)
        self._send_pf_and_wait(2)
        
        # Step 5: Policy Entry
        policy_number = self.policy_input.text().strip()
        if policy_number:
            company = self.company_combo.currentText()
            # "62D2,{policy}  ;newco={company};."
            policy_cmd = f"62D2,{policy_number}  ;newco={company};."
            self.automation_status.setText(f"🔄 Looking up {policy_number}...")
            logger.info(f"Entering policy command: {policy_cmd}")
            self._type_and_enter(policy_cmd)
            
        # Done
        elapsed = time.time() - getattr(self, '_sequence_start_time', 0)
        self.automation_status.setText(f"✅ {region_name} (1992) {elapsed:.1f}s")

    def start_cics_sequence(self, region_name: str, region_option: str):
        """Start the CICS auto-login sequence for any region.
        
        Args:
            region_name: Display name (CKAS, CKMO, CKPR)
            region_option: The option number to select on VTAM screen (1, 5, 7) - legacy, not used
        
        Sequence: Connect → Login → (from PRIMARY APP MENU) → type CICSCKAS/CICSCKMO/CICSCKPR → Enter → 0000 → F2 → F2 → F2
        """
        if not self.conn_userid or not self.conn_password:
            QMessageBox.warning(self, "Credentials Required", 
                f"Please set your User ID and Password in Settings before using {region_name} auto-login.")
            return
        
        start_time = time.time()
        self._sequence_start_time = start_time
        self.automation_status.setText(f"🔄 {region_name}...")
        
        # Disconnect if already connected (switching regions)
        if self.client and self.client.connected:
            self.disconnect_from_mainframe()
            self._wait(200)  # Brief pause after disconnect
        
        # Reset state before starting - skip auto-fill since we handle credentials ourselves
        self._screen_update_count = 0
        self.pending_autofill = False
        self._skip_autofill = True  # Tell connect() not to auto-fill
        self.terminal.typed_chars = {}
        
        # Connect and wait for login screen (capture count before connect)
        count = self._capture_screen_count()
        self.connect_to_mainframe()
        self._wait_for_screen_from(count, timeout_ms=3000)
        
        # Clear skip flag for future manual connects
        self._skip_autofill = False
        
        # Manually fill credentials and send Enter (this waits for response)
        self._fill_credentials_and_enter()
        
        # Wait for the response screen after login attempt
        self._wait(300)
        
        # Check if we got the "MULTIPLE LOGON" screen (userid already logged in elsewhere)
        # This is the key screen for dual terminal - press PF6 to create new logon session
        if self._check_multiple_logon_screen():
            self.automation_status.setText(f"🔄 {region_name} (creating new logon)...")
            logger.info("MULTIPLE LOGON screen detected - pressing PF6 for new session")
            self._handle_multiple_logon_screen()
            # Wait for the post-PF6 screen
            self._wait(300)
        
        # Check if we got the "session already active" reconnect screen (USER ON TERM)
        if self._check_reconnect_screen():
            self.automation_status.setText(f"🔄 {region_name} (reconnecting)...")
            self._handle_reconnect_screen()
            self._wait(300)
        
        # Check for Port 1992 sequence (only for configured regions)
        if self.client and self.client.port == 1992:
            if region_name.upper() in {"CKAS", "CKMO", "CKPR", "CKSR"}:
                self._handle_1992_sequence(region_name)
                return

        # Wait a moment for the post-login screen to arrive
        self._wait(200)
        
        # Log what screen we're seeing for debugging - full screen
        if self.terminal.last_screen:
            screen_text = ''.join(self.terminal.last_screen.buffer)
            logger.info(f"=== POST-LOGIN SCREEN (full) ===")
            for row in range(24):
                line = screen_text[row*80:(row+1)*80].rstrip()
                if line.strip():
                    logger.info(f"Row {row:2d}: {line}")
            logger.info(f"=== END POST-LOGIN SCREEN ===")
        
        # Check what screen we're at and navigate accordingly
        if self._check_primary_app_menu():
            # PRIMARY APPLICATION SELECTION MENU - type CICS region name directly
            cics_applid = self._get_cics_applid(region_name)  # e.g., CICSCKAS, CICSCKMO, CICSCKPR
            if cics_applid:
                self.automation_status.setText(f"🔄 {region_name} (typing {cics_applid})...")
                logger.info(f"Typing {cics_applid} to navigate to {region_name}")
                self._type_and_enter(cics_applid)
            else:
                logger.warning(f"No CICS APPLID for {region_name}")
                
        elif self._check_vtam_switch_menu():
            # VTAM/Switch Session Selection menu

            applid = self._get_cics_applid(region_name)
            
            # If this is a secondary session, use OPEN with APPLID to create new session
            if self.use_open_for_new_session:
                if applid:
                    self.automation_status.setText(f"🔄 {region_name} (OPEN {applid})...")
                    logger.info(f"Using OPEN {applid} to start new session for dual terminal")
                    self._open_application(applid)
                    self._wait(500)
                    # After OPEN applid, we should go directly to that CICS region
                    # Skip the normal navigation - go straight to MENU screen
                else:
                    # No APPLID known, try OPEN then navigate
                    self.automation_status.setText(f"🔄 {region_name} (OPEN new session)...")
                    logger.info("Using OPEN command (no APPLID) for dual terminal")
                    self._type_and_enter("OPEN")
                    self._wait(300)
                    # Then navigate normally
                    self._type_and_enter("3")
                    self._wait(200)
                    self._type_and_enter(region_option)
                    self._send_enter_and_wait()
            else:
                # Normal single session
                if applid:
                    # If APPLID is known, OPEN it (no region option needed)
                    self.automation_status.setText(f"🔄 {region_name} (OPEN {applid})...")
                    logger.info(f"Using OPEN {applid} to start session")
                    self._open_application(applid)
                    self._wait(500)
                else:
                    # Navigate: 3 (CICS) → region option
                    if not region_option:
                        logger.error(f"No region option configured for {region_name}")
                        self.automation_status.setText(f"❌ No region option for {region_name}")
                        return

                    self.automation_status.setText(f"🔄 {region_name} (VTAM menu)...")
                    logger.info("At VTAM/Switch menu - selecting CICS (option 3)")
                    self._type_and_enter("3")  # Select CICS
                    
                    # Now we should be at CICS regions menu - select the specific region
                    self._wait(200)
                    logger.info(f"Selecting CICS region option {region_option}")
                    self._type_and_enter(region_option)
                    
                    # Confirm screen - just Enter
                    self._send_enter_and_wait()
        else:
            # Unknown menu - try legacy navigation
            logger.info("Unknown menu - using legacy navigation (3 → 4 → region)")
            self._type_and_enter("3")
            self._type_and_enter("4")
            self._type_and_enter(region_option)
            self._send_enter_and_wait()
        
        # MENU screen - need extra time for this screen to load
        self._wait(100)  # Give screen time to fully arrive
        
        # MENU screen - type 0000
        self._type_and_enter("0000", use_menu_field=True)
        
        # F2 three times
        self._send_pf_and_wait(2)
        self._send_pf_and_wait(2)
        self._send_pf_and_wait(2)
        
        # If policy number is provided, send policy lookup command
        policy_number = self.policy_input.text().strip()
        if policy_number:
            company = self.company_combo.currentText()
            # Build the command: 62D2,AA000604  ;newco=01;.
            policy_cmd = f"62D2,{policy_number}  ;newco={company};."
            self.automation_status.setText(f"🔄 Looking up {policy_number}...")
            self._type_and_enter(policy_cmd)
        
        # Done!
        elapsed = time.time() - start_time
        self.automation_status.setText(f"✅ {region_name} {elapsed:.1f}s")

    def _auto_type_credentials_and_enter(self):
        """Type userid and password into first two fields and send Enter"""
        if not self.terminal.last_screen:
            logger.warning("No screen available for credential entry")
            return
        
        screen = self.terminal.last_screen
        input_fields = screen.get_input_fields()
        
        if not input_fields:
            logger.warning("No input fields found on screen for credentials")
            return
        
        input_fields.sort(key=lambda f: f.address)
        logger.info(f"Found {len(input_fields)} input fields for credentials")
        
        # Clear typed chars first
        self.terminal.typed_chars = {}
        
        # Type userid into first field
        if self.conn_userid and len(input_fields) >= 1:
            field_start = input_fields[0].address + 1
            for i, char in enumerate(self.conn_userid):
                self.terminal.typed_chars[field_start + i] = char
            logger.info(f"Auto-typed userid '{self.conn_userid}' into field at {field_start}")
        
        # Type password into second field
        if self.conn_password and len(input_fields) >= 2:
            field_start = input_fields[1].address + 1
            for i, char in enumerate(self.conn_password):
                self.terminal.typed_chars[field_start + i] = char
            logger.info(f"Auto-typed password (len={len(self.conn_password)}) into field at {field_start}")
        
        logger.info(f"typed_chars before Enter: {len(self.terminal.typed_chars)} chars")
        
        # Send Enter with a small delay to ensure chars are registered
        QTimer.singleShot(100, self._auto_send_enter)
    
    def _auto_type_in_first_field(self, text: str):
        """Type text into the first input field"""
        if not self.terminal.last_screen:
            logger.warning("No screen available for typing")
            return
        
        screen = self.terminal.last_screen
        input_fields = screen.get_input_fields()
        
        if not input_fields:
            logger.warning("No input fields found")
            return
        
        input_fields.sort(key=lambda f: f.address)
        field_start = input_fields[0].address + 1
        
        # Clear any existing typed chars in this area
        self.terminal.typed_chars = {}
        
        for i, char in enumerate(text):
            self.terminal.typed_chars[field_start + i] = char
        
        logger.info(f"Auto-typed '{text}' into field at {field_start}")
    
    def _auto_type_at_menu_field(self, text: str):
        """Find the field near 'Menu' text and type into it, clearing existing content"""
        if not self.terminal.last_screen:
            logger.warning("No screen available")
            return
        
        screen = self.terminal.last_screen
        
        # Search for "MENU" in the screen buffer
        screen_text = ''.join(screen.buffer).upper()
        menu_pos = screen_text.find("MENU")
        
        if menu_pos == -1:
            logger.warning("Could not find 'MENU' on screen, using first input field")
            self._auto_type_in_first_field(text)
            return
        
        logger.info(f"Found 'MENU' at buffer position {menu_pos}")
        
        # Find the input field that starts right after or near MENU
        # MENU is at position X, and we need to find the field where we type
        input_fields = screen.get_input_fields()
        input_fields.sort(key=lambda f: f.address)
        
        # Look for a field on the same row as MENU or nearby
        menu_row = menu_pos // 80
        
        target_field = None
        for field in input_fields:
            field_row = field.address // 80
            # Look for field on same row or within a row
            if abs(field_row - menu_row) <= 1:
                target_field = field
                break
        
        if target_field is None and input_fields:
            # Fallback to first input field
            target_field = input_fields[0]
        
        if target_field:
            field_start = target_field.address + 1
            
            # Find field end to know how much to clear
            field_end = screen.rows * screen.cols
            for other in screen.fields:
                if other.address > target_field.address and other.address < field_end:
                    field_end = other.address
            
            # Clear the entire field first by writing spaces, then write our text
            # This ensures we overwrite any existing content like "MENU"
            self.terminal.typed_chars = {}
            field_length = min(field_end - field_start, 20)  # Clear up to 20 chars
            for i in range(field_length):
                if i < len(text):
                    self.terminal.typed_chars[field_start + i] = text[i]
                else:
                    self.terminal.typed_chars[field_start + i] = ' '
            
            logger.info(f"Auto-typed '{text}' at MENU field (addr {field_start}), cleared {field_length} chars")
        else:
            logger.warning("No input field found near MENU")
    
    def _auto_send_enter(self):
        """Send Enter key for automation"""
        if not self.client or not self.client.connected:
            logger.warning("Cannot send - not connected")
            return
        
        logger.info(f"_auto_send_enter: typed_chars count = {len(self.terminal.typed_chars)}")
        
        # Build modified fields from typed_chars
        if self.terminal.typed_chars and self.terminal.last_screen:
            screen = self.terminal.last_screen
            input_fields = screen.get_input_fields()
            modified_fields = []
            
            logger.info(f"_auto_send_enter: found {len(input_fields)} input fields")
            
            for field in input_fields:
                field_start = field.address + 1
                field_end = screen.rows * screen.cols
                for other in screen.fields:
                    if other.address > field.address and other.address < field_end:
                        field_end = other.address
                
                typed_in_field = {addr: char for addr, char in self.terminal.typed_chars.items() 
                                if field_start <= addr < field_end}
                
                if typed_in_field:
                    field_content = []
                    for addr in range(field_start, field_end):
                        if addr in self.terminal.typed_chars:
                            field_content.append(self.terminal.typed_chars[addr])
                        else:
                            field_content.append(screen.buffer[addr])
                    content_str = ''.join(field_content).rstrip()
                    if content_str:
                        modified_fields.append((field_start, content_str))
                        logger.info(f"_auto_send_enter: field at {field_start} = '{content_str[:20]}...' (len={len(content_str)})")
            
            logger.info(f"_auto_send_enter: sending {len(modified_fields)} modified fields")
            self.client.send_aid(AID.ENTER, modified_fields if modified_fields else None)
        else:
            logger.info("_auto_send_enter: no typed_chars, sending plain ENTER")
            self.client.send_aid(AID.ENTER, None)
        
        self.terminal.typed_chars = {}
        logger.info("Automation: Sent ENTER")
    
    def _auto_send_pf(self, pf_num: int):
        """Send PF key for automation"""
        if not self.client or not self.client.connected:
            return
        
        self.client.send_pf_key(pf_num)
        logger.info(f"Automation: Sent PF{pf_num}")


class DualTerminalScreen(QWidget):
    """Dual terminal screen with two side-by-side MainframeTerminalScreen instances.
    
    Allows running two concurrent mainframe sessions (e.g., CKAS and CKPR).
    """
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """Initialize the dual terminal layout"""
        layout = QHBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Create splitter for resizable panes
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #2c5f8d;
                width: 6px;
            }
            QSplitter::handle:hover {
                background-color: #3d7ab5;
            }
        """)
        
        # Allow smooth, continuous resizing
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setOpaqueResize(True)
        
        # Create two terminal instances
        self.terminal_left = MainframeTerminalScreen()
        self.terminal_right = MainframeTerminalScreen()
        
        # Mark the right terminal to use OPEN command for new sessions
        # This enables dual terminal support via VTAM/Switch OPEN command
        self.terminal_right.use_open_for_new_session = True
        
        # Add to splitter
        self.splitter.addWidget(self.terminal_left)
        self.splitter.addWidget(self.terminal_right)
        
        # Set equal initial sizes with actual pixel values for smooth operation
        # These will be adjusted proportionally when window is resized
        self.splitter.setSizes([400, 400])
        
        layout.addWidget(self.splitter)
    
    def disconnect_all(self):
        """Disconnect both terminals"""
        self.terminal_left.disconnect_from_mainframe()
        self.terminal_right.disconnect_from_mainframe()
    
    def closeEvent(self, event):
        """Handle widget close - disconnect both terminals"""
        self.disconnect_all()
        super().closeEvent(event)
