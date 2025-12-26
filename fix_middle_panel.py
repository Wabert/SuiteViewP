#!/usr/bin/env python
"""Fix ONLY the middle panel function in mydata_screen.py"""

with open('suiteview/ui/mydata_screen.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the exact function boundaries
start_marker = '    def _create_middle_panel(self) -> QWidget:'
end_marker = '    def _create_far_right_panel(self) -> QWidget:'

start = content.find(start_marker)
end = content.find(end_marker)

print(f"Found middle panel function at positions {start} to {end}")
print(f"Original function length: {end - start} chars")

# New EMPTY function - but we need dummy attributes for tables_tree and table_info_label
new_func = '''    def _create_middle_panel(self) -> QWidget:
        """Create middle panel - TOTALLY EMPTY FOR TESTING"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        
        # Create dummy widgets to prevent AttributeError elsewhere
        self.tables_search_box = QLineEdit()
        self.tables_search_box.hide()
        self.tables_tree = QTreeWidget()
        self.tables_tree.hide()
        self.table_info_label = QLabel("")
        self.table_info_label.hide()
        
        # COMPLETELY EMPTY VISIBLE PANEL
        panel_layout.addStretch()
        return panel

'''

# Replace only this function
new_content = content[:start] + new_func + content[end:]

with open('suiteview/ui/mydata_screen.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('File updated successfully!')

# Verify
with open('suiteview/ui/mydata_screen.py', 'r', encoding='utf-8') as f:
    c = f.read()
    s = c.find('def _create_middle_panel')
    e = c.find('def _create_far_right_panel')
    print('New function content:')
    print(c[s:e])
