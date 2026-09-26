"""System tray, app launching, capture, permission, and resize helpers."""

import ctypes
import logging
import sys
import time
import traceback
from ctypes import wintypes
from datetime import datetime

from PyQt6 import sip
from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCursor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QMenu,
    QMessageBox,
    QSizeGrip,
    QSystemTrayIcon,
    QWidget,
)

from suiteview.core.access_control import (
    AccessDeniedError,
    AccessUnavailableError,
    get_access,
)
from suiteview.core.profile_paths import profile_path, profile_root
from suiteview.ui.access_control import requires_app_access
from suiteview.ui.widgets.file_open_history import FileOpenHistoryPanel
from suiteview.ui.widgets.frame_geometry import (
    ALL_RESIZE_EDGES,
    cursor_for_resize_edge,
    resize_geometry_for_edge,
)
from suiteview.taskbar_launcher.collaborators import TaskbarCollaborator

logger = logging.getLogger(__name__)
from suiteview.taskbar_launcher.file_nav_window import FileNavWindow


def _host_widget(controller_or_widget):
    return getattr(controller_or_widget, "window", controller_or_widget)


class SystemTray(TaskbarCollaborator):
    """Owns tray integration, permissions, app launchers, and child windows."""

    def _apply_permissions(self, access):
        self.state.launcher_access = access
        floating_only_hidden = {
            "scratchpad_window_btn", "file_history_btn", "quick_screenshot_btn",
        }
        controls = (
            ("POLVIEW", "polview_btn"), ("FILENAV", "filenav_btn"),
            ("ABR", "abrquote_btn"), ("RERUN", "illustration_btn"),
            ("QUERY", "audit_btn"), ("ALBERT", "albert_btn"),
            ("SCRATCHPAD", "scratchpad_window_btn"), ("HISTORY", "file_history_btn"),
            ("SCREENSHOT", "quick_screenshot_btn"),
            ("ADMINISTRATOR", "administrator_action"),
        )
        for code, name in controls:
            control = getattr(self.chrome, name, None)
            if control is not None:
                allowed = access is not None and access.allows_app(code)
                control.setEnabled(allowed)
                control.setVisible(allowed and not (
                    self.state.is_floating_mode and name in floating_only_hidden
                ))
        for code, action in self.chrome._permission_actions:
            allowed = access is not None and access.allows_app(code)
            action.setEnabled(allowed)
            action.setVisible(allowed)
        file_access = access is not None and access.allows_app("FILENAV")
        for name in ("tab_widget", "sidebar_container"):
            control = getattr(self.chrome, name, None)
            if control is not None:
                control.setEnabled(file_access)
        if self.state.is_floating_mode:
            self.window.layout().activate()
            self.window.resize(self.window.layout().sizeHint().width(), self.window.height())

    def _refresh_permissions(self):
        try:
            access = get_access(refresh=True)
        except (AccessDeniedError, AccessUnavailableError) as error:
            logger.warning("Cannot refresh SuiteView permissions: %s", error)
            self._apply_permissions(None)
            QMessageBox.warning(_host_widget(self), "SuiteView Access", str(error))
            return
        self._apply_permissions(access)
    
    def _build_suiteview_icon(self, size=64):
        """Build the SuiteView icon - blue square with gold trim and golden S
        
        For Windows taskbar compatibility, this creates an icon with multiple sizes.
        """
        icon = QIcon()
        
        # Add multiple sizes for Windows taskbar compatibility
        # Windows uses different sizes: 16 (small), 32 (medium), 48, 64, 128, 256 (large)
        sizes = [16, 24, 32, 48, 64, 128, 256] if size >= 64 else [size]
        
        for sz in sizes:
            pixmap = self._create_icon_pixmap(sz)
            icon.addPixmap(pixmap)
        
        return icon
    
    def _create_icon_pixmap(self, size):
        """Create a single pixmap for the SuiteView icon at specified size"""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        margin = max(1, size // 32)
        rect_size = size - margin * 2
        
        # Draw blue background with gradient
        gradient = QLinearGradient(0, 0, 0, size)
        gradient.setColorAt(0, QColor("#1E5BA8"))
        gradient.setColorAt(0.5, QColor("#0D3A7A"))
        gradient.setColorAt(1, QColor("#082B5C"))
        
        border_width = max(1, size // 20)
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor("#D4A017"), border_width))  # Gold border
        corner_radius = max(2, size // 8)
        painter.drawRoundedRect(margin, margin, rect_size, rect_size, corner_radius, corner_radius)
        
        # Draw golden "S" in the center
        painter.setPen(QColor("#D4A017"))
        font_size = max(8, int(size * 0.55))
        font = QFont("Georgia", font_size, QFont.Weight.Bold)
        font.setItalic(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "S")
        
        painter.end()
        return pixmap
    
    def _setup_system_tray(self):
        """Setup system tray icon and menu"""
        self.state.tray_icon = QSystemTrayIcon(self)
        self.state.tray_icon.setIcon(self._build_suiteview_icon(64))
        self.state.tray_icon.setToolTip("SuiteView - Click to show")
        
        # Create tray menu
        tray_menu = QMenu()
        tray_menu.setStyleSheet("""
            QMenu {
                background-color: #0D3A7A;
                border: 1px solid #D4A017;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                background-color: transparent;
                color: white;
                padding: 8px 20px;
                font-size: 11px;
            }
            QMenu::item:selected {
                background-color: #3A7DC8;
            }
        """)
        
        # Store as instance variable to prevent garbage collection
        self._quit_action = QAction("Quit SuiteView", self)
        self._quit_action.triggered.connect(self.callbacks._quit_application)
        tray_menu.addAction(self._quit_action)
        
        # Store tray menu as instance variable too
        self._tray_menu = tray_menu
        self.state.tray_icon.setContextMenu(self._tray_menu)
        self.state.tray_icon.activated.connect(self._on_tray_activated)
        self.state.tray_icon.show()
        
        # Also set the window icon
        self.window.setWindowIcon(self._build_suiteview_icon(64))

    def _connect_screen_change_handlers(self):
        """Refresh the compact AppBar when Windows monitor geometry changes."""
        app = QApplication.instance()
        if app is None:
            return

        app.screenAdded.connect(self._on_screen_added)
        app.screenRemoved.connect(self._schedule_bar_refresh)
        app.primaryScreenChanged.connect(self._schedule_bar_refresh)

        for screen in app.screens():
            self._connect_screen_signals(screen)

    def _connect_screen_signals(self, screen):
        if screen is None or screen in self.state.screen_signal_refs:
            return
        screen.geometryChanged.connect(self._schedule_bar_refresh)
        screen.availableGeometryChanged.connect(self._schedule_bar_refresh)
        self.state.screen_signal_refs.append(screen)

    def _on_screen_added(self, screen):
        self._connect_screen_signals(screen)
        self._schedule_bar_refresh()

    def _schedule_bar_refresh(self, *_args):
        if time.monotonic() < self.state.ignore_screen_events_until:
            return
        if self.state.bar_refresh_pending:
            return
        self.state.bar_refresh_pending = True
        QTimer.singleShot(750, self._run_scheduled_bar_refresh)

    def _run_scheduled_bar_refresh(self):
        self.state.bar_refresh_pending = False
        if self.state.is_compact_mode or self.state.is_floating_mode:
            self._refresh_bar_position()

    def _refresh_bar_position(self):
        """Recompute the mini-bar geometry against the current primary screen."""
        if self.state.is_floating_mode:
            self._move_floating_bar_to_current_screen()
            return

        if not self.state.is_compact_mode:
            return

        self.callbacks._unregister_appbar(force=True)
        self.callbacks._enter_compact_mode(initial=True)

    def _move_floating_bar_to_current_screen(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        bar_h = self.window.height() or 42
        bar_w = min(max(self.window.width() or 320, 320), avail.width())
        bar_x = avail.x() + (avail.width() - bar_w) // 2
        bar_y = avail.bottom() - bar_h - 10
        self.window.setGeometry(bar_x, bar_y, bar_w, bar_h)
    
    def _on_tray_activated(self, reason):
        """Handle tray icon clicks"""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.callbacks._show_from_tray()
    
    def _show_from_tray(self):
        """Show and activate the main window.

        Restoring the docked mini-bar must also re-claim the desktop space we
        gave back in :meth:`_hide_to_tray` — otherwise the bar reappears
        floating on top of maximised windows instead of docked beside them.
        """
        self.state.hidden_to_tray = False
        self.restore_window()

        if self.state.is_compact_mode:
            # Re-apply WS_EX_TOOLWINDOW so the bar stays out of the taskbar
            self._apply_toolwindow_style()
            # Re-dock once Qt has finished mapping the window, so the AppBar
            # rectangle is negotiated against a window that really is on screen.
            QTimer.singleShot(0, self._redock_appbar)
        elif self.state.is_floating_mode:
            self._apply_toolwindow_style()

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32":

            msg = wintypes.MSG.from_address(int(message))
            if msg.message == self.state.restore_message:
                self.window._restore_requested.emit()
                return True, 0
            # Windows can also show/restore us without changing Qt's hidden
            # flag. Reconcile on the UI thread, not inside a Win32 callback.
            if self.state.hidden_to_tray:
                if ((msg.message == 0x0018 and msg.wParam)  # WM_SHOWWINDOW
                        or (msg.message == 0x0112
                            and msg.wParam & 0xFFF0 == 0xF120)):  # SC_RESTORE
                    self.window._restore_requested.emit()
        return False, 0

    def _redock_appbar(self):
        """Re-establish the AppBar reservation for the compact mini-bar."""
        if not self.state.is_compact_mode or self.state.hidden_to_tray or not self.window.isVisible():
            return
        self.callbacks._register_appbar(self.window.height() or 42)

    def _apply_toolwindow_style(self):
        """Keep the mini-bar out of the Windows taskbar (WS_EX_TOOLWINDOW)."""
        try:
            hwnd = int(self.window.winId())
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW  = 0x00040000
            user32 = ctypes.windll.user32
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style = (ex_style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
        except Exception:
            logger.debug("Best-effort taskbar style update failed", exc_info=True)

    def _hide_to_tray(self):
        """Hide to system tray"""
        self.state.hidden_to_tray = True
        # Give the desktop its full work area back while we're invisible
        self.callbacks._unregister_appbar(force=True)
        self.window.hide()
        self.state.tray_icon.showMessage(
            "SuiteView",
            "SuiteView is still running. Click the tray icon to restore.",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )
    
    def _quit_application(self):
        """Quit the entire application"""
        logger = logging.getLogger(__name__)
        logger.info("Quit requested from system tray")

        # Preserve Administrator's unsaved-change cancellation before exiting.
        if self.state.administrator_window is not None and not self.state.administrator_window.close():
            return

        # Ask every other window to close BEFORE touching the tray or launcher.
        # A window that stays visible cancels the quit; SuiteView must then
        # remain reachable instead of running on with no window or tray icon.
        blocker = self._close_windows_for_quit()
        if blocker is not None:
            logger.info("Quit cancelled: %s is still open", blocker.windowTitle())
            self.callbacks._bring_to_front(blocker)
            return

        try:
            self.callbacks._unregister_appbar(force=True)
        except Exception as e:
            logger.error(f"Error releasing the AppBar during quit: {e}")
        try:
            self.state.tray_icon.hide()
        except Exception:
            logger.debug("Could not hide tray icon during quit", exc_info=True)
        self.window.close()

        # QApplication.quit() re-asks every window to close and Qt cancels it
        # if any refuses, which left an invisible process holding the
        # single-instance lock. The windows were already asked above.
        QApplication.exit(0)

    def _close_windows_for_quit(self):
        """Close other visible top-level windows; return one that stays open."""

        for window in list(QApplication.topLevelWidgets()):
            try:
                if window is self.window or sip.isdeleted(window) or not window.isVisible():
                    continue
                window.close()
                if not sip.isdeleted(window) and window.isVisible():
                    return window
            except RuntimeError:
                continue
        return None

    @requires_app_access("SCREENSHOT")
    def _take_quick_screenshot(self):
        """Take a screenshot of the primary screen INCLUDING SuiteView windows"""
        try:
            
            # Small delay to ensure screen is fully rendered
            QApplication.processEvents()
            time.sleep(0.05)
            
            # Get screenshots folder
            screenshots_dir = profile_path('screenshots')
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"screenshot_{timestamp}.png"
            filepath = screenshots_dir / filename
            
            # Take screenshot of primary screen (including SuiteView windows)
            screen = QApplication.primaryScreen()
            if screen:
                pixmap = screen.grabWindow(0)
                pixmap.save(str(filepath), 'PNG')
                
                # Notify Screenshot Manager if it's open
                if self.state.screenshot_window is not None and self.state.screenshot_window.isVisible():
                    try:
                        self.state.screenshot_window.add_screenshot_from_file(filepath)
                    except Exception as e:
                        logger.warning(f"Failed to notify Screenshot Manager: {e}")
                
                # Show notification
                self.state.tray_icon.showMessage(
                    "Screenshot Saved",
                    f"Saved to: {filename}",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
                
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
            self.state.tray_icon.showMessage(
                "Screenshot Failed",
                str(e),
                QSystemTrayIcon.MessageIcon.Warning,
                2000
            )
    
    @requires_app_access("SCREENSHOT")
    def _capture_active_window(self):
        """Capture full screen EXCLUDING SuiteView and Screenshot Manager windows"""
        try:
            
            # Track which windows we need to restore
            windows_to_restore = []
            
            # Hide SuiteView main window
            if self.window.isVisible():
                self.window.hide()
                windows_to_restore.append(self.window)
            
            # Hide Screenshot Manager if open
            if self.state.screenshot_window is not None and self.state.screenshot_window.isVisible():
                self.state.screenshot_window.hide()
                windows_to_restore.append(self.state.screenshot_window)
            
            # Process events and wait for windows to hide
            QApplication.processEvents()
            time.sleep(0.15)  # Brief delay for windows to hide
            
            # Now capture the screen
            self._do_capture_excluding_suiteview(windows_to_restore)
                
        except Exception as e:
            logger.error(f"Failed to capture screen: {e}")
            self.state.tray_icon.showMessage(
                "Capture Failed",
                str(e),
                QSystemTrayIcon.MessageIcon.Warning,
                2000
            )
    
    def _do_capture_excluding_suiteview(self, windows_to_restore):
        """Perform the actual capture after hiding SuiteView windows"""
        try:
            
            # Get screenshots folder
            screenshots_dir = profile_path('screenshots')
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"screen_{timestamp}.png"
            filepath = screenshots_dir / filename
            
            # Take screenshot of primary screen
            screen = QApplication.primaryScreen()
            if screen:
                pixmap = screen.grabWindow(0)
                pixmap.save(str(filepath), 'PNG')
                
                # Show notification
                self.state.tray_icon.showMessage(
                    "Screen Captured",
                    f"Saved to: {filename}",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
            
            # Restore all hidden windows
            for window in windows_to_restore:
                window.show()
                window.activateWindow()
                window.raise_()
            
            # Notify Screenshot Manager to reload if it was restored
            if self.state.screenshot_window is not None and self.state.screenshot_window in windows_to_restore:
                try:
                    self.state.screenshot_window._load_existing_screenshots()
                except Exception as e:
                    logger.warning(f"Failed to notify Screenshot Manager: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to capture screen: {e}")
            # Still restore windows on error
            for window in windows_to_restore:
                window.show()
    
    @requires_app_access("ALBERT")
    def _open_agent_chat(self):
        """Open or reuse the folder-scoped Copilot Agent window."""
        if self.state.agent_chat_window is not None:
            try:
                _ = self.state.agent_chat_window.isVisible()
            except RuntimeError:
                self.state.agent_chat_window = None

        if self.state.agent_chat_window is None:
            try:
                from suiteview.agent_chat import AgentChatWindow
                self.state.agent_chat_window = AgentChatWindow()
                self.callbacks._setup_child_window(self.state.agent_chat_window, "LLM Agent")
            except Exception as exc:
                logger.error("Failed to open LLM Agent: %s", exc, exc_info=True)
                QMessageBox.critical(
                    self.window,
                    "LLM Agent Error",
                    f"Failed to open the LLM Agent:\n\n{exc}",
                )
                self.state.agent_chat_window = None
                return
        self.callbacks._bring_to_front(self.state.agent_chat_window)

    @requires_app_access("MAINFRAMENAV")
    def _open_mainframe(self):
        """Open the Mainframe Navigator window"""
        if self.state.mainframe_window is None:
            try:
                from suiteview.mainframe_nav.mainframe_window import MainframeWindow
                self.state.mainframe_window = MainframeWindow()
                self.callbacks._setup_child_window(self.state.mainframe_window, "Mainframe Navigator")
            except Exception as e:
                logger.error(f"Failed to open Mainframe Navigator: {e}")
                QMessageBox.warning(_host_widget(self), "Mainframe Navigator", str(e))
                return
        self.callbacks._bring_to_front(self.state.mainframe_window)
    
    @requires_app_access("SCREENSHOT")
    def _open_screenshot(self):
        """Open the Screenshot Manager window"""
        if self.state.screenshot_window is None:
            try:
                from suiteview.screenshot_manager.screenshot_manager_window import (
                    ScreenShotManagerWindow,
                )
                self.state.screenshot_window = ScreenShotManagerWindow()
                self.callbacks._setup_child_window(self.state.screenshot_window, "Screenshot Manager")
            except Exception as e:
                logger.error(f"Failed to open Screenshot Manager: {e}")
                QMessageBox.warning(_host_widget(self), "Screenshot Manager", str(e))
                return
        else:
            # Reload screenshots to show any new ones taken while window was hidden
            self.state.screenshot_window._load_existing_screenshots()
        self.callbacks._bring_to_front(self.state.screenshot_window)
    
    @requires_app_access("EMAILATTACHMENTS")
    def _open_email_attachments(self):
        """Open the Email Attachments window"""
        if self.state.email_attachments_window is None:
            try:
                from suiteview.ui.email_attachments_window import EmailAttachmentsWindow
                self.state.email_attachments_window = EmailAttachmentsWindow()
                self.state.email_attachments_window.setWindowIcon(self._build_suiteview_icon(32))
            except Exception as e:
                logger.error(f"Failed to open Email Attachments: {e}")
                QMessageBox.warning(_host_widget(self), "Email Attachments", str(e))
                return
        self.callbacks._bring_to_front(self.state.email_attachments_window)
    
    @requires_app_access("POLVIEW")
    def _open_polview(self):
        """Open the PolView - Policy Viewer window"""
        if self.state.polview_window is None:
            try:
                from suiteview.polview.ui.main_window import GetPolicyWindow
                self.state.polview_window = GetPolicyWindow()
                self.callbacks._setup_child_window(self.state.polview_window, "PolView")
                self._wire_polview_illustrator(self.state.polview_window)
            except Exception as e:
                logger.error(f"Failed to open PolView: {e}")
                QMessageBox.warning(_host_widget(self), "PolView", str(e))
                return
        self.callbacks._bring_to_front(self.state.polview_window)

    def _wire_polview_illustrator(self, window):
        """Route PolView's RERUN button through the shared RERUN window."""
        if window is not None and hasattr(window, 'set_illustration_launcher'):
            window.set_illustration_launcher(self._launch_illustration_with_policy)

    def _wire_illustration_polview(self, window):
        """Route RERUN's PolView button through the shared PolView window."""
        if window is not None and hasattr(window, 'set_polview_launcher'):
            window.set_polview_launcher(self._launch_polview_with_policy)

    @requires_app_access("POLVIEW")
    def _get_polview_window(self):
        """Get the shared PolView window (used as provider callback for child tools).

        Creates the window lazily if requested before the taskbar opened it,
        but does NOT show it — the caller decides when to show.
        """
        if self.state.polview_window is None:
            try:
                from suiteview.polview.ui.main_window import GetPolicyWindow
                self.state.polview_window = GetPolicyWindow()
                self.callbacks._setup_child_window(self.state.polview_window, "PolView")
                self._wire_polview_illustrator(self.state.polview_window)
            except ImportError:
                logger.info("PolView package not available")
            except Exception as e:
                logger.error(f"Failed to create PolView: {e}")
                QMessageBox.warning(_host_widget(self), "PolView", str(e))
        return self.state.polview_window

    def _polview_btn_clicked(self):
        """Handle [P] button click — open with policy if input has text, else just open."""
        if (self.state.is_compact_mode
                and hasattr(self.chrome, 'compact_policy_input')
                and self.chrome.compact_policy_input.text().strip()):
            self._open_polview_with_policy()
        else:
            self._open_polview()

    def _compact_policy(self):
        """Return the policy number typed in the compact bar, or '' if none."""
        if (self.state.is_compact_mode
                and hasattr(self.chrome, 'compact_policy_input')):
            return self.chrome.compact_policy_input.text().strip().upper()
        return ""

    def _compact_region(self):
        """Return the region chosen in the compact bar (default CKPR)."""
        if hasattr(self.chrome, 'compact_region_combo'):
            return self.chrome.compact_region_combo.currentText() or "CKPR"
        return "CKPR"

    def _clear_compact_policy(self):
        """Clear the compact-bar policy input after it has been handed off.

        Once a policy has been auto-populated into PolView/RERUN we don't want
        it lingering in the taskbar input, or it would keep re-pulling that same
        policy every time the app is reopened.
        """
        if hasattr(self.chrome, 'compact_policy_input'):
            self.chrome.compact_policy_input.clear()

    def _open_polview_with_policy(self):
        """Open PolView and load the policy specified in the compact bar inputs."""
        policy = self._compact_policy()
        if not policy:
            return

        # Build the complete frame first. load_policy now only queues the
        # background request, so showing it does not wait for a DB connection.
        window = self._get_polview_window()
        if not window or not hasattr(window, 'load_policy'):
            return

        # Only load the typed policy when it's new (not already pulled up).
        # If it's already in PolView's list, leave it on whatever policy was
        # last shown. Company left empty so PolView auto-detects it.
        try:
            already_loaded = (hasattr(window, 'has_policy_loaded')
                              and window.has_policy_loaded(policy))
            if not already_loaded:
                window.load_policy(policy, region=self._compact_region(), company_code="")
            self.callbacks._bring_to_front(window)
        finally:
            # Always clear the handed-off policy so reopening PolView later
            # doesn't keep re-pulling it — even if the load raised.
            self._clear_compact_policy()

    def _abrquote_btn_clicked(self):
        """Open ABR Quote without passing through the compact-bar policy."""
        self._open_abrquote()

    def _illustration_btn_clicked(self):
        """Open Illustration, loading the compact-bar policy when one is typed."""
        policy = self._compact_policy()
        if not policy:
            self._open_illustration()
            return
        try:
            self._launch_illustration_with_policy(
                policy, region=self._compact_region(), company_code="")
        finally:
            # Always clear the handed-off policy so reopening RERUN later
            # doesn't keep re-pulling it — even if the load raised.
            self._clear_compact_policy()

    @requires_app_access("RERUN")
    def _launch_illustration_with_policy(self, policy_number, region="CKPR",
                                         company_code=""):
        """Open (or reuse) RERUN and load *policy_number*.

        Shared by the taskbar RERUN button and PolView's RERUN header button.
        """
        self._open_illustration()
        win = self.state.illustration_window
        if win is not None and hasattr(win, 'load_policy'):
            win.load_policy(policy_number, region=region, company_code=company_code)
        self.callbacks._bring_to_front(win)

    @requires_app_access("POLVIEW")
    def _launch_polview_with_policy(self, policy_number, region="CKPR",
                                    company_code=""):
        """Open (or reuse) PolView and load *policy_number*."""
        self._open_polview()
        win = self.state.polview_window
        if win is not None and hasattr(win, 'load_policy'):
            win.load_policy(policy_number, region=region, company_code=company_code)
        self.callbacks._bring_to_front(win)

    @requires_app_access("QUERY")
    def _open_audit(self):
        """Open the Audit Tool window"""
        if self.state.audit_window is None:
            try:
                from suiteview.audit import launch_audit
                self.state.audit_window = launch_audit()
                self.callbacks._setup_child_window(self.state.audit_window, "Audit Tool")
            except Exception as e:
                logger.error(f"Failed to open Audit Tool: {e}\n{traceback.format_exc()}")
                QMessageBox.warning(_host_widget(self), "Audit Tool Error",
                                    f"Failed to open Audit Tool:\n\n{e}")
                return
        # Share PolView so policies opened from Audit use the same window
        if hasattr(self.state.audit_window, 'set_polview_provider'):
            self.state.audit_window.set_polview_provider(self._get_polview_window)
        # Share RERUN so "Open in Rerun" from Audit reuses the same window
        if hasattr(self.state.audit_window, 'set_illustration_launcher'):
            self.state.audit_window.set_illustration_launcher(
                self._launch_illustration_with_policy)
        self.callbacks._bring_to_front(self.state.audit_window)

    @requires_app_access("ABR")
    def _open_abrquote(self):
        """Open the ABR Quote Tool window"""
        # Guard: if the stored window was destroyed (e.g. C++ object deleted),
        # reset so we recreate it cleanly.
        if self.state.abrquote_window is not None:
            try:
                # Accessing any Qt property on a deleted C++ object raises RuntimeError
                _ = self.state.abrquote_window.isVisible()
            except RuntimeError:
                self.state.abrquote_window = None

        if self.state.abrquote_window is None:
            try:
                from suiteview.abrquote import launch_abrquote
                self.state.abrquote_window = launch_abrquote()
                self.callbacks._setup_child_window(self.state.abrquote_window, "ABR Quote")
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"Failed to open ABR Quote: {e}\n{tb}")
                QMessageBox.critical(_host_widget(self), "ABR Quote Error",
                                     f"Failed to open ABR Quote:\n\n{e}\n\n{tb}")
                self.state.abrquote_window = None  # reset so retry works
                return
        self.callbacks._bring_to_front(self.state.abrquote_window)

    @requires_app_access("RERUN")
    def _open_illustration(self):
        """Open the RERUN app window."""
        if self.state.illustration_window is not None:
            try:
                _ = self.state.illustration_window.isVisible()
            except RuntimeError:
                self.state.illustration_window = None

        if self.state.illustration_window is None:
            try:
                from suiteview.illustration import launch_illustration
                self.state.illustration_window = launch_illustration()
                self.callbacks._setup_child_window(self.state.illustration_window, "RERUN")
                self._wire_illustration_polview(self.state.illustration_window)
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"Failed to open RERUN: {e}\n{tb}")
                QMessageBox.critical(_host_widget(self), "RERUN Error",
                                     f"Failed to open RERUN:\n\n{e}\n\n{tb}")
                self.state.illustration_window = None
                return
        self.callbacks._bring_to_front(self.state.illustration_window)


    @requires_app_access("RATEMANAGER")
    def _open_rate_manager(self):
        """Open the Rate Manager window."""
        if self.state.ratemanager_window is None:
            try:
                from suiteview.ratemanager.ratemanager_window import RateManagerWindow
                self.state.ratemanager_window = RateManagerWindow()
                self.callbacks._setup_child_window(self.state.ratemanager_window, "Rate Manager")
            except Exception as e:
                logger.error(f"Failed to open Rate Manager: {e}")
                QMessageBox.warning(_host_widget(self), "Rate Manager", str(e))
                return
        self.callbacks._bring_to_front(self.state.ratemanager_window)

    def _open_administrator(self):
        """Recheck ADMIN membership even when reopening an existing window."""
        from suiteview.administrator.service import AccessRepository

        try:
            repository = AccessRepository()
            repository.load()
            if self.state.administrator_window is None:
                from suiteview.administrator.window import AdministratorWindow
                self.state.administrator_window = AdministratorWindow(repository=repository)
                self.state.administrator_window.setWindowIcon(self._build_suiteview_icon(32))
                self.state.administrator_window.permissions_changed.connect(
                    self.chrome._administrator_menu_access.refresh)
                self.state.administrator_window.permissions_changed.connect(self.callbacks._refresh_permissions)
            self.callbacks._bring_to_front(self.state.administrator_window)
        except Exception as exc:
            logger.exception("Failed to open Administrator")
            if self.state.administrator_window is not None:
                self.state.administrator_window.hide()
            QMessageBox.warning(_host_widget(self), "Administrator", f"Cannot open Administrator:\n\n{exc}")

    @requires_app_access("ADMINISTRATOR")
    def _open_db2_table_check(self):
        """Open the CKPR DB2 Table Check window."""
        if self.state.db2_check_window is None:
            try:
                from suiteview.ui.db2_table_check_window import DB2TableCheckWindow
                self.state.db2_check_window = DB2TableCheckWindow(region="CKPR")
                self.callbacks._setup_child_window(
                    self.state.db2_check_window, "DB2 Table Check")
            except Exception as e:
                logger.error(
                    "Failed to open DB2 Table Check: %s", e, exc_info=True)
                QMessageBox.warning(
                    self.window,
                    "DB2 Table Check Error",
                    f"Failed to open DB2 Table Check:\n\n{e}",
                )
                self.state.db2_check_window = None
                return
        self.callbacks._bring_to_front(self.state.db2_check_window)

    @requires_app_access("FILENAV")
    def _open_file_nav(self):
        """Open the File Navigator as a separate window."""
        # Guard: if the stored window was destroyed, reset it
        if self.state.file_nav_window is not None:
            try:
                _ = self.state.file_nav_window.isVisible()
            except RuntimeError:
                self.state.file_nav_window = None

        if self.state.file_nav_window is None:
            try:
                self.state.file_nav_window = FileNavWindow(parent_bar=self.window)
                self.callbacks._setup_child_window(self.state.file_nav_window, "FileNav")
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"Failed to open File Navigator: {e}\n{tb}")
                self.state.file_nav_window = None
                return
        self.callbacks._bring_to_front(self.state.file_nav_window)

    @requires_app_access("FILENAV")
    def _open_app_data_location(self):
        """Navigate to the app data folder (~/.suiteview) in the details view"""
        app_data_dir = profile_root()
        # Create the directory if it doesn't exist
        app_data_dir.mkdir(parents=True, exist_ok=True)
        # Navigate to it in the current tab's details pane
        current_tab = self.get_current_tab()
        if current_tab and hasattr(current_tab, 'navigate_to_path'):
            current_tab.navigate_to_path(str(app_data_dir))

    @requires_app_access("SCRATCHPAD")
    def _toggle_scratchpad_window(self):
        """Toggle the ScratchPad window visibility."""
        # Guard: if the stored window was destroyed, reset it
        if self.state.scratchpad_window is not None:
            try:
                _ = self.state.scratchpad_window.isVisible()
            except RuntimeError:
                self.state.scratchpad_window = None

        if self.state.scratchpad_window is None:
            try:
                from suiteview.scratchpad.scratchpad_panel import ScratchPadWindow
                self.state.scratchpad_window = ScratchPadWindow.open(parent_bar=self)
                self.callbacks._setup_child_window(self.state.scratchpad_window, "ScratchPad")
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"Failed to open ScratchPad window: {e}\n{tb}")
                QMessageBox.warning(_host_widget(self), "ScratchPad", str(e))
                self.state.scratchpad_window = None
                return

        if self.state.scratchpad_window.isVisible():
            self.state.scratchpad_window.hide()
        else:
            self.callbacks._bring_to_front(self.state.scratchpad_window)

    @requires_app_access("HISTORY")
    def _toggle_file_open_history(self):
        """Toggle the File Open History popup panel."""
        if not self.state.file_open_history_panel is not None or self.state.file_open_history_panel is None:
            self.state.file_open_history_panel = FileOpenHistoryPanel(self.window)

        panel = self.state.file_open_history_panel
        if panel.isVisible():
            panel.hide()
        elif panel.was_recently_hidden():
            # Popup auto-closed because user clicked the H button — treat as "close" toggle
            pass
        else:
            panel.show_under(self.chrome.file_history_btn)

    
    def _bring_to_front(self, window):
        """Show a child window and reliably bring it to the foreground."""
        restore = getattr(window, "restore_window", None)
        if callable(restore):
            # FramelessWindowBase restores to the pre-minimize state (keeping a
            # maximized window maximized) and keeps its own flags in sync.
            restore()
        else:
            if window.windowState() & Qt.WindowState.WindowMinimized:
                window.setWindowState((window.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
                window.showNormal()
            window.show()
            window.raise_()
            window.activateWindow()
        # On Windows, raise_() often fails due to focus-stealing prevention.
        # Use the Win32 API to force the window to the foreground.
        try:
            hwnd = int(window.winId())
            user32 = ctypes.windll.user32
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
        except Exception:
            logger.debug("Best-effort foreground activation failed", exc_info=True)
        QTimer.singleShot(0, lambda: (window.raise_(), window.activateWindow()))

    def _setup_child_window(self, window, title):
        """Setup a child window with hide-on-close behavior"""
        window.setWindowTitle(f"SuiteView - {title}")
        window.setWindowIcon(self._build_suiteview_icon(32))
        
        # Override close event to hide instead of closing
        def hide_on_close(event):
            event.ignore()
            window.hide()
        window.closeEvent = hide_on_close
    
    def _add_resize_grips(self):
        """Add resize grips to all edges and corners for easier resizing"""
        
        # Bottom-right grip (visible, standard Qt grip)
        self.size_grip = QSizeGrip(self.window)
        self.size_grip.setStyleSheet("""
            QSizeGrip {
                background-color: transparent;
                width: 16px;
                height: 16px;
            }
        """)
        
        # Create edge resize widgets
        self.state.resize_widgets = []
        
        # Edge widget class for resize
        class ResizeEdge(QFrame):
            def __init__(self, parent, edge):
                super().__init__(parent)
                self.edge = edge
                self.parent_window = parent
                self.setMouseTracking(True)
                self.setCursor(self._get_cursor())
                self.setStyleSheet("background-color: transparent;")
                self._dragging = False
                self._start_pos = None
                self._start_geometry = None
                
            def _get_cursor(self):
                return cursor_for_resize_edge(self.edge) or Qt.CursorShape.ArrowCursor
                
            def mousePressEvent(self, event):
                # Block resize when docked compact or floating
                state = getattr(self.parent_window, "state", None)
                if state is not None and (state.is_compact_mode or state.is_floating_mode):
                    event.ignore()
                    return
                if event.button() == Qt.MouseButton.LeftButton:
                    self._dragging = True
                    self._start_pos = event.globalPosition().toPoint()
                    self._start_geometry = self.parent_window.geometry()
                    event.accept()
                    
            def mouseMoveEvent(self, event):
                state = getattr(self.parent_window, "state", None)
                if state is not None and (state.is_compact_mode or state.is_floating_mode):
                    event.ignore()
                    return
                if self._dragging and self._start_geometry:
                    delta = event.globalPosition().toPoint() - self._start_pos
                    self.parent_window.setGeometry(resize_geometry_for_edge(
                        self._start_geometry,
                        delta,
                        self.edge,
                        QSize(330, 46),
                    ))
                    event.accept()
                    
            def mouseReleaseEvent(self, event):
                self._dragging = False
                self._start_pos = None
                self._start_geometry = None
        
        for edge in ALL_RESIZE_EDGES:
            self.state.resize_widgets.append((edge, ResizeEdge(self.window, edge)))
        
    def resizeEvent(self, event):
        """Position the resize widgets on resize and collapse/expand UI elements"""
        QWidget.resizeEvent(_host_widget(self), event)
        margin = 6
        w, h = self.window.width(), self.window.height()
        
        # Collapse/expand UI elements based on window height
        # Header bar is ~38px, footer is ~24px, tab bar is ~30px
        if hasattr(self.chrome, 'footer_bar') and hasattr(self.chrome, 'tab_widget'):
            # Hide footer and tab content when window is very small (just header)
            if h < 70:
                self.chrome.footer_bar.hide()
                self.chrome.tab_widget.hide()
            elif h < 100:
                self.chrome.footer_bar.hide()
                self.chrome.tab_widget.show()
            else:
                self.chrome.footer_bar.show()
                self.chrome.tab_widget.show()
        
        if hasattr(self, 'size_grip'):
            self.size_grip.move(w - 16, h - 16)
            self.size_grip.raise_()
        
        if bool(self.state.resize_widgets):
            for edge_name, widget in self.state.resize_widgets:
                if edge_name == 'top':
                    widget.setGeometry(margin, 0, w - 2*margin, margin)
                elif edge_name == 'bottom':
                    widget.setGeometry(margin, h - margin, w - 2*margin, margin)
                elif edge_name == 'left':
                    widget.setGeometry(0, margin, margin, h - 2*margin)
                elif edge_name == 'right':
                    widget.setGeometry(w - margin, margin, margin, h - 2*margin)
                elif edge_name == 'top-left':
                    widget.setGeometry(0, 0, margin, margin)
                elif edge_name == 'top-right':
                    widget.setGeometry(w - margin, 0, margin, margin)
                elif edge_name == 'bottom-left':
                    widget.setGeometry(0, h - margin, margin, margin)
                elif edge_name == 'bottom-right':
                    widget.setGeometry(w - margin, h - margin, margin, margin)
                widget.raise_()


class AppLauncher(TaskbarCollaborator):
    """Named app-launching collaborator for the shell window.

    Launch/open methods currently share permission checks, tray state and
    child-window setup with ``SystemTray``. The separate collaborator instance
    keeps the ownership explicit and gives a future split a clear seam.
    """


    def _take_quick_screenshot(self, *args, **kwargs):
        return SystemTray._take_quick_screenshot(self, *args, **kwargs)

    def _capture_active_window(self, *args, **kwargs):
        return SystemTray._capture_active_window(self, *args, **kwargs)

    def _do_capture_excluding_suiteview(self, *args, **kwargs):
        return SystemTray._do_capture_excluding_suiteview(self, *args, **kwargs)

    def _open_agent_chat(self, *args, **kwargs):
        return SystemTray._open_agent_chat(self, *args, **kwargs)

    def _open_mainframe(self, *args, **kwargs):
        return SystemTray._open_mainframe(self, *args, **kwargs)

    def _open_screenshot(self, *args, **kwargs):
        return SystemTray._open_screenshot(self, *args, **kwargs)

    def _open_email_attachments(self, *args, **kwargs):
        return SystemTray._open_email_attachments(self, *args, **kwargs)

    def _open_polview(self, *args, **kwargs):
        return SystemTray._open_polview(self, *args, **kwargs)

    def _wire_polview_illustrator(self, *args, **kwargs):
        return SystemTray._wire_polview_illustrator(self, *args, **kwargs)

    def _wire_illustration_polview(self, *args, **kwargs):
        return SystemTray._wire_illustration_polview(self, *args, **kwargs)

    def _get_polview_window(self, *args, **kwargs):
        return SystemTray._get_polview_window(self, *args, **kwargs)

    def _polview_btn_clicked(self, *args, **kwargs):
        return SystemTray._polview_btn_clicked(self, *args, **kwargs)

    def _compact_policy(self, *args, **kwargs):
        return SystemTray._compact_policy(self, *args, **kwargs)

    def _compact_region(self, *args, **kwargs):
        return SystemTray._compact_region(self, *args, **kwargs)

    def _clear_compact_policy(self, *args, **kwargs):
        return SystemTray._clear_compact_policy(self, *args, **kwargs)

    def _open_polview_with_policy(self, *args, **kwargs):
        return SystemTray._open_polview_with_policy(self, *args, **kwargs)

    def _abrquote_btn_clicked(self, *args, **kwargs):
        return SystemTray._abrquote_btn_clicked(self, *args, **kwargs)

    def _illustration_btn_clicked(self, *args, **kwargs):
        return SystemTray._illustration_btn_clicked(self, *args, **kwargs)

    def _launch_illustration_with_policy(self, *args, **kwargs):
        return SystemTray._launch_illustration_with_policy(self, *args, **kwargs)

    def _launch_polview_with_policy(self, *args, **kwargs):
        return SystemTray._launch_polview_with_policy(self, *args, **kwargs)

    def _open_audit(self, *args, **kwargs):
        return SystemTray._open_audit(self, *args, **kwargs)

    def _open_abrquote(self, *args, **kwargs):
        return SystemTray._open_abrquote(self, *args, **kwargs)

    def _open_illustration(self, *args, **kwargs):
        return SystemTray._open_illustration(self, *args, **kwargs)

    def _open_rate_manager(self, *args, **kwargs):
        return SystemTray._open_rate_manager(self, *args, **kwargs)

    def _open_administrator(self, *args, **kwargs):
        return SystemTray._open_administrator(self, *args, **kwargs)

    def _open_db2_table_check(self, *args, **kwargs):
        return SystemTray._open_db2_table_check(self, *args, **kwargs)

    def _open_file_nav(self, *args, **kwargs):
        return SystemTray._open_file_nav(self, *args, **kwargs)

    def _open_app_data_location(self, *args, **kwargs):
        return SystemTray._open_app_data_location(self, *args, **kwargs)

    def _toggle_scratchpad_window(self, *args, **kwargs):
        return SystemTray._toggle_scratchpad_window(self, *args, **kwargs)

    def _toggle_file_open_history(self, *args, **kwargs):
        return SystemTray._toggle_file_open_history(self, *args, **kwargs)

    def _bring_to_front(self, *args, **kwargs):
        return SystemTray._bring_to_front(self, *args, **kwargs)

    def _setup_child_window(self, *args, **kwargs):
        return SystemTray._setup_child_window(self, *args, **kwargs)
