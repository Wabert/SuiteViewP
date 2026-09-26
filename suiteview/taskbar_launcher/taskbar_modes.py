"""SuiteViewTaskbar docking, compact/floating mode, and mouse handlers."""

import ctypes
import logging
import os
import time
import traceback
import webbrowser
from pathlib import Path

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QLineEdit,
    QPushButton,
    QSystemTrayIcon,
)

from suiteview.core.access_control import (
    requires_app_access,
)
from suiteview.taskbar_launcher import appbar
from suiteview.ui.widgets.frame_geometry import (
    resize_edge_at,
    resize_geometry_for_edge,
    update_cursor_for_resize_edge,
)

logger = logging.getLogger(__name__)
from suiteview.taskbar_launcher.bookmark_bars_popup import BookmarkBarsPopup
from suiteview.taskbar_launcher.file_nav_window import FileNavWindow


class TaskbarModesMixin:
    def _toggle_maximize(self):
        """Toggle between maximized and normal window state"""
        if self._is_maximized:
            self.showNormal()
            self._is_maximized = False
            self.maximize_btn.setText("☐")
            self.maximize_btn.setToolTip("Maximize")
        else:
            self.showMaximized()
            self._is_maximized = True
            self.maximize_btn.setText("❐")
            self.maximize_btn.setToolTip("Restore")
    
    def _toggle_compact_mode(self):
        """Toggle between compact mode (mini bar) and normal mode.
        
        Called by double-clicking the SuiteView label.
        Three states:
        - Full window         → collapse to docked compact bar
        - Docked compact bar  → undock to floating mini-bar
        - Floating mini-bar   → re-dock to compact bar
        """
        if getattr(self, '_is_floating_mode', False):
            # Floating → re-dock to compact bar
            self._exit_floating_mode()
            self._enter_compact_mode(initial=False)
        elif self._is_compact_mode:
            # Docked compact → undock to floating mini-bar
            self._enter_floating_mode()
        else:
            # Full window → docked compact
            self._enter_compact_mode(initial=False)

    def _enter_floating_mode(self):
        """Undock the compact bar into a short, draggable floating bar.
        
        Shows only:  SuiteView [ P ] [ F ] [ A ] [ R ] [ Q ] [ Al ] [✕]
        The bar becomes draggable and is not docked to the taskbar.
        """
        # First unregister appbar so the desktop work area is restored
        self._unregister_appbar()

        # Hide everything except the core tool buttons
        if hasattr(self, 'tab_widget'):
            self.tab_widget.hide()
        if hasattr(self, 'footer_bar'):
            self.footer_bar.hide()
        if hasattr(self, 'sidebar_container'):
            self.sidebar_container.hide()
        if hasattr(self, 'minimize_btn'):
            self.minimize_btn.hide()
        if hasattr(self, 'maximize_btn'):
            self.maximize_btn.hide()
        if hasattr(self, 'header_spacer'):
            self.header_spacer.hide()

        # Hide compact-mode policy lookup inputs (not needed in floating)
        if hasattr(self, 'compact_region_combo'):
            self.compact_region_combo.hide()
        if hasattr(self, 'compact_policy_input'):
            self.compact_policy_input.hide()

        # Hide the screenshot button, tools menu, scratchpad, audit icon (floating shows only P/F/A/Q)
        if hasattr(self, 'quick_screenshot_btn'):
            self.quick_screenshot_btn.hide()
        if hasattr(self, 'tools_menu_btn'):
            self.tools_menu_btn.hide()
        if hasattr(self, 'scratchpad_window_btn'):
            self.scratchpad_window_btn.hide()
        if hasattr(self, 'file_history_btn'):
            self.file_history_btn.hide()

        self._is_compact_mode = False
        self._is_floating_mode = True
        self._apply_permissions(self._launcher_access)
        if hasattr(self, 'close_btn'):
            self.close_btn.show()

        # Set height to just the header
        bar_h = 42
        self.setMinimumSize(100, bar_h)
        self.setMaximumHeight(bar_h)

        bar_w = self.layout().sizeHint().width()

        # Position: center of screen, near bottom (above taskbar)
        avail = QApplication.primaryScreen().availableGeometry()
        bar_x = avail.x() + (avail.width() - bar_w) // 2
        bar_y = avail.bottom() - bar_h - 10  # 10px above bottom

        # Keep stay-on-top but as a normal floating window
        was_visible = self.isVisible()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowMinMaxButtonsHint
                            | Qt.WindowType.WindowStaysOnTopHint)
        self.setGeometry(bar_x, bar_y, bar_w, bar_h)
        if was_visible:
            self.show()

        # Restore taskbar icon so user can click on it
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW  = 0x00040000
            user32 = ctypes.windll.user32
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style = (ex_style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
            user32.ShowWindow(hwnd, 0)  # SW_HIDE
            user32.ShowWindow(hwnd, 5)  # SW_SHOW
        except Exception:
            logger.debug("Best-effort taskbar style refresh failed", exc_info=True)

    def _exit_floating_mode(self):
        """Exit floating mini-bar mode (caller will re-dock or restore)."""
        self._is_floating_mode = False

        # Remove height cap
        self.setMaximumHeight(16777215)
        self.setMinimumSize(330, 40)

        # Restore all header widgets to their proper visibility
        # (the caller — _enter_compact_mode or _exit_compact_mode — will
        #  handle showing/hiding the right widgets for the target state)
        self._apply_permissions(self._launcher_access)
        if hasattr(self, 'tools_menu_btn'):
            self.tools_menu_btn.show()
        if hasattr(self, 'header_spacer'):
            self.header_spacer.show()
    
    def _enter_compact_mode(self, initial=False):
        """Collapse to the compact mini-bar docked above the taskbar.

        The bar spans the FULL screen width and sits immediately above the
        Windows taskbar.  The shell AppBar shrinks the desktop work area
        so its bottom edge aligns with the TOP of our bar — exactly like
        docking a new toolbar.  The bar is NOT draggable while docked.

        Args:
            initial: True when called at startup (no stored geometry yet).
        """
        # Store current full-window geometry so we can restore it later
        if not initial:
            self._stored_geometry = self.geometry()

        # --- Hide content widgets ---
        if hasattr(self, 'tab_widget'):
            self.tab_widget.hide()
        if hasattr(self, 'footer_bar'):
            self.footer_bar.hide()
        if hasattr(self, 'sidebar_container'):
            self.sidebar_container.hide()
        # Hide minimize and maximize — not needed in docked bar
        if hasattr(self, 'minimize_btn'):
            self.minimize_btn.hide()
        if hasattr(self, 'maximize_btn'):
            self.maximize_btn.hide()
        # Keep close_btn visible so user can quit to tray
        if hasattr(self, 'close_btn'):
            self.close_btn.show()
        # Keep the stretch spacer — pushes ✕ to the far right across the full width
        if hasattr(self, 'header_spacer'):
            self.header_spacer.show()
        # Show compact-mode policy lookup inputs
        if hasattr(self, 'compact_region_combo'):
            self.compact_region_combo.show()
        if hasattr(self, 'compact_policy_input'):
            self.compact_policy_input.show()
        self._apply_permissions(self._launcher_access)

        # Shrink to just the header bar height
        bar_h = 42  # header height + 2 px border top/bottom
        self.setMinimumSize(100, bar_h)
        self.setMaximumHeight(bar_h)

        # availableGeometry() gives us the screen EXCLUDING the taskbar.
        # We sit immediately above the taskbar: x=0, y = avail.bottom() - bar_h
        # Width = full physical screen width so we span edge-to-edge.
        avail  = QApplication.primaryScreen().availableGeometry()
        full   = QApplication.primaryScreen().geometry()
        bar_w  = full.width()
        bar_x  = full.left()
        bar_y  = avail.bottom() - bar_h        # just above the taskbar

        # Apply always-on-top Qt flag — requires hide/show to take effect
        was_visible = self.isVisible()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowMinMaxButtonsHint
                            | Qt.WindowType.WindowStaysOnTopHint)
        self.setGeometry(bar_x, bar_y, bar_w, bar_h)
        if was_visible:
            self.show()

        # Hide from taskbar using native Windows API (reliable, unlike Qt Tool flag)
        self._apply_toolwindow_style()
        if not self._hidden_to_tray:
            try:
                # Force shell to notice the style change
                hwnd = int(self.winId())
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
                ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
            except Exception:
                logger.debug("Best-effort compact-mode shell refresh failed", exc_info=True)

        self._is_compact_mode = True

        # Register as a Windows AppBar so the shell reserves screen space.
        # This must happen AFTER the window is shown (so winId() is valid).
        # While we're minimised to the tray there is no bar on screen, so the
        # desktop keeps its full work area until _show_from_tray re-docks us.
        if not self._hidden_to_tray:
            self._register_appbar(bar_h)

    # ------------------------------------------------------------------
    #  Windows AppBar API – proper desktop space reservation
    # ------------------------------------------------------------------
    #  Instead of the fragile SPI_SETWORKAREA (which can be overridden by
    #  Explorer at any time), we register our window as an "AppBar" using
    #  SHAppBarMessage.  This is the same mechanism the Windows taskbar
    #  uses and is the officially supported way to dock a toolbar and
    #  have other windows respect the reserved space.
    #
    #  Flow:  ABM_NEW  →  ABM_QUERYPOS  →  ABM_SETPOS  →  SetWindowPos
    #  Tear-down:  ABM_REMOVE
    # ------------------------------------------------------------------

    def _register_appbar(self, bar_h: int, _retry: bool = True):
        """Register this window as a Windows AppBar docked to the bottom edge.

        The shell shrinks the desktop work area by *bar_h* pixels at the bottom
        so maximised / snapped windows never overlap our bar.

        Registration is verified by reading the monitor work area back: the
        shell can report success and still leave the work area untouched (for
        example when it is holding a stale registration for our HWND), so a
        single clean retry is attempted before giving up.
        """
        self._ignore_screen_events_until = time.monotonic() + 1.5

        hwnd = int(self.winId())
        # Convert bar_h from Qt logical pixels → physical pixels
        dpr = self.devicePixelRatioF()
        bar_h_phys = round(bar_h * dpr)

        rect = appbar.register_bottom(hwnd, bar_h_phys)
        if rect is None:
            self._appbar_registered = False
            if _retry:
                appbar.unregister(hwnd)
                self._register_appbar(bar_h, _retry=False)
            else:
                self._notify_docking_failure()
            return

        self._appbar_registered = True

        if not appbar.space_reserved(hwnd, rect[1]):
            if _retry:
                logger.warning("AppBar reserved no space — retrying registration")
                appbar.unregister(hwnd)
                self._appbar_registered = False
                self._register_appbar(bar_h, _retry=False)
                return
            appbar.unregister(hwnd)
            self._appbar_registered = False
            self._notify_docking_failure()
            return

        logger.info(f"AppBar registered: rect={rect}")

    def _notify_docking_failure(self):
        logger.error("SuiteView could not reserve desktop space for the mini-bar")
        self.tray_icon.showMessage(
            "SuiteView docking failed",
            "Windows did not reserve desktop space. Click the SuiteView tray "
            "icon to retry docking.",
            QSystemTrayIcon.MessageIcon.Warning,
            5000,
        )

    def _unregister_appbar(self, force: bool = False):
        """Unregister the AppBar so the shell restores the full work area.

        Pass ``force=True`` to issue ABM_REMOVE even when we don't believe we
        are registered — that clears any registration the shell still holds for
        our HWND, which would otherwise make the next ABM_NEW fail.
        """
        if not force and not self._appbar_registered:
            return
        self._ignore_screen_events_until = time.monotonic() + 1.5
        appbar.unregister(int(self.winId()))
        self._appbar_registered = False
        logger.info("AppBar unregistered — work area restored")

    @requires_app_access("FILENAV")
    def _exit_compact_mode(self):
        """Expand from compact mini-bar back to the full window."""
        # Unregister the AppBar FIRST, before repositioning our window
        self._unregister_appbar(force=True)

        # Remember where the bar was so we can return to it later
        self._compact_bar_pos = self.geometry().topLeft()

        # Remove the height cap
        self.setMaximumHeight(16777215)  # Qt's QWIDGETSIZE_MAX
        self.setMinimumSize(330, 40)

        # Restore content widgets
        if hasattr(self, 'tab_widget'):
            self.tab_widget.show()
        if hasattr(self, 'footer_bar'):
            self.footer_bar.show()
        if hasattr(self, 'sidebar_container'):
            self.sidebar_container.show()
        if hasattr(self, 'minimize_btn'):
            self.minimize_btn.show()
        if hasattr(self, 'maximize_btn'):
            self.maximize_btn.show()
        if hasattr(self, 'close_btn'):
            self.close_btn.show()
        if hasattr(self, 'header_spacer'):
            self.header_spacer.show()
        # Hide compact-mode policy lookup inputs
        if hasattr(self, 'compact_region_combo'):
            self.compact_region_combo.hide()
        if hasattr(self, 'compact_policy_input'):
            self.compact_policy_input.hide()

        # Determine target geometry before touching flags
        if self._stored_geometry:
            target_geo = self._stored_geometry
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            w, h = 1400, 800
            x = screen.x() + (screen.width() - w) // 2
            y = screen.y() + (screen.height() - h) // 2
            target_geo = QRect(x, y, w, h)

        # Remove always-on-top flag — requires hide/show on Windows to take effect
        was_visible = self.isVisible()

        # Restore taskbar icon: remove WS_EX_TOOLWINDOW before changing Qt flags
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW  = 0x00040000
            user32 = ctypes.windll.user32
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style = (ex_style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
        except Exception:
            logger.debug("Best-effort AppWindow style restore failed", exc_info=True)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setGeometry(target_geo)
        if was_visible:
            self.show()
            self.activateWindow()
            self.raise_()

        self._is_compact_mode = False

    def mousePressEvent(self, event):
        """Handle mouse press for dragging and resizing"""
        # Right-click anywhere on the bar → show bookmark bars popup
        if event.button() == Qt.MouseButton.RightButton:
            # Don't show popup if clicking on a button
            widget_at = self.childAt(event.pos())
            if not isinstance(widget_at, (QPushButton, QComboBox, QLineEdit, QAbstractButton)):
                self._show_bookmark_bars_popup(event.globalPosition().toPoint())
                event.accept()
                return

        # Docked compact bar is not movable or resizable
        if self._is_compact_mode:
            super().mousePressEvent(event)
            return
        
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            
            # Check if we're on a resize edge (not in floating mode)
            if not getattr(self, '_is_floating_mode', False):
                edge = resize_edge_at(pos, self.rect(), self._resize_margin)
                if edge and not self._is_maximized:
                    self._resizing = True
                    self._resize_edge = edge
                    self._resize_start_pos = event.globalPosition().toPoint()
                    self._start_geometry = self.geometry()
                    event.accept()
                    return
            
            # Check if we're in the header bar (for dragging)
            header_rect = self.header_bar.geometry()
            if header_rect.contains(pos):
                # Don't drag if clicking on buttons
                widget_at = self.childAt(pos)
                if isinstance(widget_at, QPushButton):
                    super().mousePressEvent(event)
                    return
                
                self._drag_pos = event.globalPosition().toPoint()
                event.accept()
                return
        
        super().mousePressEvent(event)

    def _show_bookmark_bars_popup(self, global_pos):
        """Show a floating popup with all bookmark bars as vertical panels."""
        # Close any existing popup before opening a new one.
        # (No timestamp guard — a right-click elsewhere on the bar should
        # close the old popup AND immediately reopen at the new position.)
        if hasattr(self, '_bookmark_popup') and self._bookmark_popup is not None:
            try:
                self._bookmark_popup.close()
            except RuntimeError:
                logger.debug("Bookmark popup was already deleted before reopening", exc_info=True)
            self._bookmark_popup = None

        screen_obj = QApplication.screenAt(global_pos) or QApplication.primaryScreen()
        screen = screen_obj.availableGeometry()
        popup = BookmarkBarsPopup(
            parent_bar=self,
            maximum_height=max(120, screen.height() - 8),
        )
        popup.bookmark_activated.connect(self._on_popup_bookmark_activated)
        self._bookmark_popup = popup

        # Size the popup first so we know its dimensions
        popup.adjustSize()
        popup_height = popup.sizeHint().height()
        popup_width  = popup.sizeHint().width()

        # Prefer to show above the bar; otherwise use the largest visible
        # position on the current monitor.
        bar_geo = self.geometry()
        y = bar_geo.top() - popup_height - 4
        if y < screen.top():
            y = bar_geo.bottom() + 4
        y = max(screen.top(), min(y, screen.bottom() - popup_height + 1))

        # Horizontally: centre the popup on the right-click X position,
        # clamped so it stays fully on screen.
        x = global_pos.x() - popup_width // 2
        x = max(screen.left(), min(x, screen.right() - popup_width + 1))

        popup.move(x, y)
        popup.show()
        popup.raise_()
        popup.activateWindow()

    def _on_popup_bookmark_activated(self, path):
        """Handle a bookmark activation from the popup.

        Folder bookmarks open in the FileNav window so the SuiteView compact
        bar stays right where it is.
        Files are opened with the default application.
        URLs are opened in the browser.
        """
        # Close the popup first
        if hasattr(self, '_bookmark_popup') and self._bookmark_popup is not None:
            try:
                self._bookmark_popup.close()
            except RuntimeError:
                logger.debug("Bookmark popup was already deleted before activation", exc_info=True)
            self._bookmark_popup = None

        if not path:
            return

        if path.startswith('http://') or path.startswith('https://'):
            webbrowser.open(path)
        elif Path(path).is_dir():
            # Open the folder in the FileNav window — SuiteView bar stays put
            self._open_file_nav_at(path)
        else:
            try:
                os.startfile(path)
            except Exception as e:
                logger.error(f"Failed to open bookmark path: {e}")

    @requires_app_access("FILENAV")
    def _open_file_nav_at(self, path):
        """Open (or reuse) the FileNav window and navigate it to *path*."""
        # Guard against stale C++ wrapped object
        if self.file_nav_window is not None:
            try:
                _ = self.file_nav_window.isVisible()
            except RuntimeError:
                self.file_nav_window = None

        if self.file_nav_window is None:
            try:
                self.file_nav_window = FileNavWindow(parent_bar=self)
                self._setup_child_window(self.file_nav_window, "FileNav")
            except Exception as e:
                logger.error(f"Failed to open File Navigator: {e}\n{traceback.format_exc()}")
                return

        # Show / raise the window
        self._bring_to_front(self.file_nav_window)

        # Navigate the current (or a new) tab to the requested folder
        try:
            current_tab = self.file_nav_window.tab_widget.currentWidget()
            if current_tab and hasattr(current_tab, 'navigate_to_bookmark_folder'):
                current_tab.navigate_to_bookmark_folder(path)
            elif current_tab and hasattr(current_tab, 'navigate_to_path'):
                current_tab.navigate_to_path(path)
        except Exception as e:
            logger.error(f"FileNav navigation failed: {e}")
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging and resizing"""
        # Docked compact bar is not movable or resizable — just pass through
        if self._is_compact_mode:
            super().mouseMoveEvent(event)
            return
        
        pos = event.pos()
        
        # Update cursor when not pressing
        if not event.buttons():
            edge = resize_edge_at(pos, self.rect(), self._resize_margin)
            update_cursor_for_resize_edge(self, edge)
            super().mouseMoveEvent(event)
            return
        
        if event.buttons() == Qt.MouseButton.LeftButton:
            # Handle resizing (takes priority - check first)
            if self._resizing and self._resize_edge and self._resize_start_pos is not None:
                delta = event.globalPosition().toPoint() - self._resize_start_pos
                self.setGeometry(resize_geometry_for_edge(
                    self._start_geometry,
                    delta,
                    self._resize_edge,
                    QSize(330, 46),
                ))
                event.accept()
                return
            
            # Handle dragging (only if not resizing)
            if self._drag_pos is not None and not self._resizing:
                # If maximized, restore and center on cursor
                if self._is_maximized:
                    self._is_maximized = False
                    self.showNormal()
                    self.maximize_btn.setText("☐")
                    # Reposition so cursor is centered on title bar
                    new_geo = self.geometry()
                    self._drag_pos = event.globalPosition().toPoint()
                    self.move(
                        self._drag_pos.x() - new_geo.width() // 2,
                        self._drag_pos.y() - 20
                    )
                else:
                    delta = event.globalPosition().toPoint() - self._drag_pos
                    self.move(self.pos() + delta)
                    self._drag_pos = event.globalPosition().toPoint()
                event.accept()
                return
        
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release"""
        self._drag_pos = None
        self._resizing = False
        self._resize_edge = None
        self._resize_start_pos = None
        super().mouseReleaseEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """Handle double-click on title bar.
        
        - Double-click on the SuiteView label → toggle compact/full mode
          (handled by the label's own mouseDoubleClickEvent override)
        - Double-click elsewhere on header (not a button) → maximize/restore (full mode only)
        """
        if event.button() == Qt.MouseButton.LeftButton:
            header_rect = self.header_bar.geometry()
            if header_rect.contains(event.pos()):
                widget_at = self.childAt(event.pos())
                # Maximize/restore when double-clicking empty header space (full mode only)
                if not isinstance(widget_at, QPushButton) and not self._is_compact_mode:
                    self._toggle_maximize()
                    event.accept()
                    return
        super().mouseDoubleClickEvent(event)
    
    def paintEvent(self, event):
        """Paint a gold border around the frameless window.
        
        In compact mode the bottom border is the most visible element —
        draw it slightly thicker for emphasis.
        """
        super().paintEvent(event)
        painter = QPainter(self)
        r = self.rect().adjusted(1, 1, -1, -1)
        # Draw the full gold border (all four sides)
        painter.setPen(QPen(QColor("#D4A017"), 2))
        painter.drawRect(r)
        # Extra-thick bottom gold accent (signature mini-bar look)
        painter.setPen(QPen(QColor("#D4A017"), 3))
        painter.drawLine(r.bottomLeft(), r.bottomRight())
        painter.end()
