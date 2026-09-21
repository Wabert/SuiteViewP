"""Opaque per-tab progress/error surface so old policy data is never exposed."""

from PyQt6.QtCore import QEvent, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class TabLoadingOverlay(QWidget):
    retry_requested = pyqtSignal(str)

    def __init__(self, page: QWidget, stage: str):
        super().__init__(page)
        self.stage = stage
        self._enabled_controls = []
        self.setObjectName("PolViewLoadingOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            QWidget#PolViewLoadingOverlay { background: #F0F0F0; }
            QLabel { color: #465246; background: transparent; font-size: 12px; }
            QPushButton { padding: 4px 12px; }
        """)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(self)
        layout.addStretch()
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.message)
        self.retry_button = QPushButton("Retry")
        self.retry_button.clicked.connect(self._retry)
        layout.addWidget(self.retry_button, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        page.installEventFilter(self)
        self.hide()

    def display(self, message: str, *, failed: bool = False):
        if not self._enabled_controls:
            self._enabled_controls = [
                (child, child.isEnabled())
                for child in self.parentWidget().findChildren(
                    QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly,
                )
                if child is not self
            ]
            for child, _enabled in self._enabled_controls:
                child.setEnabled(False)
        self.message.setText(message)
        self.retry_button.setVisible(failed)
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        if self.parentWidget().isVisible():
            self.setFocus()

    def release_controls(self):
        for child, enabled in self._enabled_controls:
            child.setEnabled(enabled)
        self._enabled_controls.clear()

    def hide(self):
        self.release_controls()
        super().hide()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.setGeometry(watched.rect())
        return super().eventFilter(watched, event)

    @pyqtSlot()
    def _retry(self):
        self.retry_requested.emit(self.stage)
