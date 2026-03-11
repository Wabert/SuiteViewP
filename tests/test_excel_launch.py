"""
Simple test to diagnose Excel COM issues
"""
import sys
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QTextEdit, QMessageBox


class ExcelTestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Excel Launch Test")
        self.setGeometry(100, 100, 500, 400)
        
        layout = QVBoxLayout()
        
        # Test button
        self.test_btn = QPushButton("Launch Excel (Empty Workbook)")
        self.test_btn.clicked.connect(self.launch_excel)
        layout.addWidget(self.test_btn)
        
        # Log output
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        
        self.setLayout(layout)
        
    def launch_excel(self):
        """Try to launch Excel with different methods"""
        self.log.append("="*50)
        self.log.append("Attempting to launch Excel...")
        
        # First, try to clear the corrupted gen_py cache
        try:
            self.log.append("\n[Cleanup] Clearing win32com gen_py cache...")
            import win32com
            import shutil
            import os
            import tempfile
            
            # Try multiple possible cache locations
            cleared = False
            
            # Location 1: win32com.__gen_path__
            if hasattr(win32com, '__gen_path__'):
                cache_path = os.path.join(win32com.__gen_path__, 'win32com', 'gen_py')
                if os.path.exists(cache_path):
                    shutil.rmtree(cache_path, ignore_errors=True)
                    self.log.append(f"  Cleared: {cache_path}")
                    cleared = True
            
            # Location 2: Temp directory
            temp_gen_py = os.path.join(tempfile.gettempdir(), 'gen_py')
            if os.path.exists(temp_gen_py):
                shutil.rmtree(temp_gen_py, ignore_errors=True)
                self.log.append(f"  Cleared: {temp_gen_py}")
                cleared = True
            
            # Location 3: User AppData
            appdata = os.environ.get('LOCALAPPDATA', '')
            if appdata:
                appdata_gen_py = os.path.join(appdata, 'Temp', 'gen_py')
                if os.path.exists(appdata_gen_py):
                    shutil.rmtree(appdata_gen_py, ignore_errors=True)
                    self.log.append(f"  Cleared: {appdata_gen_py}")
                    cleared = True
            
            if cleared:
                self.log.append("✓ Cache cleared successfully")
                # Force reimport of win32com to use clean state
                import sys
                mods_to_remove = [m for m in sys.modules if m.startswith('win32com')]
                for mod in mods_to_remove:
                    del sys.modules[mod]
                self.log.append("✓ Reimported win32com modules")
            else:
                self.log.append("  No cache found to clear")
                
        except Exception as e:
            self.log.append(f"  Cache clear failed: {e}")
        
        # Method 1: Try dynamic dispatch
        try:
            self.log.append("\n[Method 1] Trying win32com.client.dynamic.Dispatch...")
            from win32com.client import dynamic
            excel = dynamic.Dispatch('Excel.Application')
            excel.Visible = True
            wb = excel.Workbooks.Add()
            self.log.append("✓ SUCCESS with dynamic.Dispatch!")
            QMessageBox.information(self, "Success", "Excel opened successfully with dynamic.Dispatch!")
            return
        except Exception as e:
            self.log.append(f"✗ FAILED: {e}")
        
        # Method 2: Try DispatchEx
        try:
            self.log.append("\n[Method 2] Trying win32com.client.DispatchEx...")
            import win32com.client as win32
            excel = win32.DispatchEx('Excel.Application')
            excel.Visible = True
            wb = excel.Workbooks.Add()
            self.log.append("✓ SUCCESS with DispatchEx!")
            QMessageBox.information(self, "Success", "Excel opened successfully with DispatchEx!")
            return
        except Exception as e:
            self.log.append(f"✗ FAILED: {e}")
        
        # Method 3: Try basic Dispatch
        try:
            self.log.append("\n[Method 3] Trying win32com.client.Dispatch...")
            import win32com.client as win32
            excel = win32.Dispatch('Excel.Application')
            excel.Visible = True
            wb = excel.Workbooks.Add()
            self.log.append("✓ SUCCESS with Dispatch!")
            QMessageBox.information(self, "Success", "Excel opened successfully with Dispatch!")
            return
        except Exception as e:
            self.log.append(f"✗ FAILED: {e}")
        
        # Method 4: Try with pythoncom CoInitialize
        try:
            self.log.append("\n[Method 4] Trying with pythoncom.CoInitialize...")
            import pythoncom
            import win32com.client as win32
            pythoncom.CoInitialize()
            excel = win32.Dispatch('Excel.Application')
            excel.Visible = True
            wb = excel.Workbooks.Add()
            self.log.append("✓ SUCCESS with CoInitialize + Dispatch!")
            QMessageBox.information(self, "Success", "Excel opened successfully with CoInitialize!")
            return
        except Exception as e:
            self.log.append(f"✗ FAILED: {e}")
        
        # All methods failed
        self.log.append("\n" + "="*50)
        self.log.append("ALL METHODS FAILED!")
        self.log.append("Excel may not be installed or COM is broken.")
        QMessageBox.critical(self, "All Methods Failed", 
                           "Could not launch Excel with any method.\n\n"
                           "Check the log for details.")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ExcelTestWindow()
    window.show()
    sys.exit(app.exec())
