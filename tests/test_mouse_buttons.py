"""
Test script to detect mouse button clicks
This will show exactly which button events your Logitech MX Master 3 sends
"""

import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QTextEdit, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QMouseEvent


class MouseButtonTester(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mouse Button Tester - Click anywhere in this window")
        self.setGeometry(100, 100, 600, 400)
        
        # Create main widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        
        # Text area to show results
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet("font-family: Consolas; font-size: 11pt;")
        layout.addWidget(self.output)
        
        self.log("Mouse Button Tester Started")
        self.log("=" * 60)
        self.log("Click any mouse button in this window to see what event it generates")
        self.log("Try your Logitech MX Master 3 side buttons!")
        self.log("=" * 60)
        self.log("")
    
    def log(self, message):
        """Add a message to the output"""
        self.output.append(message)
        self.output.ensureCursorVisible()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events"""
        button = event.button()
        buttons = event.buttons()
        
        # Get button name
        button_names = {
            Qt.MouseButton.LeftButton: "LeftButton",
            Qt.MouseButton.RightButton: "RightButton",
            Qt.MouseButton.MiddleButton: "MiddleButton",
            Qt.MouseButton.BackButton: "BackButton",
            Qt.MouseButton.ForwardButton: "ForwardButton",
            Qt.MouseButton.XButton1: "XButton1",
            Qt.MouseButton.XButton2: "XButton2",
        }
        
        button_name = button_names.get(button, f"Unknown ({button})")
        
        self.log(f"🖱️  MOUSE PRESS EVENT:")
        self.log(f"   Button: {button_name}")
        self.log(f"   Button value: {button}")
        self.log(f"   Button enum value: {button.value}")
        self.log(f"   All buttons pressed: {buttons}")
        self.log(f"   Position: ({event.position().x():.0f}, {event.position().y():.0f})")
        self.log("")
        
        # Also check if it matches specific buttons
        if button == Qt.MouseButton.BackButton:
            self.log("   ✅ This is BackButton")
        if button == Qt.MouseButton.ForwardButton:
            self.log("   ✅ This is ForwardButton")
        if button == Qt.MouseButton.XButton1:
            self.log("   ✅ This is XButton1")
        if button == Qt.MouseButton.XButton2:
            self.log("   ✅ This is XButton2")
        
        self.log("-" * 60)
        self.log("")
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release events"""
        button = event.button()
        
        button_names = {
            Qt.MouseButton.LeftButton: "LeftButton",
            Qt.MouseButton.RightButton: "RightButton",
            Qt.MouseButton.MiddleButton: "MiddleButton",
            Qt.MouseButton.BackButton: "BackButton",
            Qt.MouseButton.ForwardButton: "ForwardButton",
            Qt.MouseButton.XButton1: "XButton1",
            Qt.MouseButton.XButton2: "XButton2",
        }
        
        button_name = button_names.get(button, f"Unknown ({button})")
        
        self.log(f"   [Released: {button_name}]")
        self.log("")
    
    def event(self, event: QEvent):
        """Catch all events to see if mouse buttons generate other events"""
        if event.type() == QEvent.Type.KeyPress:
            key_event = event
            self.log(f"🔑 KEY PRESS: {key_event.key()} - {key_event.text()}")
            self.log("")
        
        return super().event(event)


def main():
    app = QApplication(sys.argv)
    window = MouseButtonTester()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
