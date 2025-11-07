"""
TFM File Manager Integration
Adapter to integrate tmahlburg's tfm file manager into SuiteView
"""

import sys
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt

# Note: tfm uses PySide6, so we need to check if we can integrate it
# This is a wrapper to see if we can use it alongside PyQt6

class TFMFileManager(QWidget):
    """
    Wrapper for tfm file manager
    
    Note: tfm is built with PySide6, which may have compatibility issues
    when used alongside PyQt6 in the same application.
    
    For now, this is a placeholder to test if integration is possible.
    """
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        
        # Show message about tfm
        from PyQt6.QtWidgets import QLabel, QPushButton
        
        label = QLabel(
            "TFM File Manager\n\n"
            "tfm is a full-featured file manager built with PySide6.\n\n"
            "Note: tfm runs as a standalone application and uses PySide6,\n"
            "which may have compatibility issues when embedded in a PyQt6 application.\n\n"
            "You can run tfm separately using:\n"
            "python -m tfm"
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)
        
        # Button to launch tfm externally
        launch_btn = QPushButton("🚀 Launch TFM (External)")
        launch_btn.clicked.connect(self.launch_tfm_external)
        layout.addWidget(launch_btn)
        
    def launch_tfm_external(self):
        """Launch tfm as external process"""
        import subprocess
        subprocess.Popen([sys.executable, "-m", "tfm"])


# Test if we can import tfm components
def test_tfm_import():
    """Test if tfm can be imported"""
    try:
        import tfm
        print(f"✅ tfm imported successfully: {tfm.__version__ if hasattr(tfm, '__version__') else 'version unknown'}")
        return True
    except ImportError as e:
        print(f"❌ Cannot import tfm: {e}")
        return False
    except Exception as e:
        print(f"❌ Error with tfm: {e}")
        return False


if __name__ == '__main__':
    # Test import
    test_tfm_import()
