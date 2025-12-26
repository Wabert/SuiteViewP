# Script to add visual checkbox indicators

with open(r'c:\Dev\SuiteViewP\suiteview\ui\widgets\filter_table_view.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the data() method to add checkbox indicators
old_data = '''    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._values):
            return None
        
        value = self._values[index.row()]
        
        if role == Qt.ItemDataRole.DisplayRole:
            return value
        elif role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if value in self._checked else Qt.CheckState.Unchecked
        
        return None'''

new_data = '''    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._values):
            return None
        
        value = self._values[index.row()]
        
        if role == Qt.ItemDataRole.DisplayRole:
            # Add visual checkbox indicator
            checkbox = "☑ " if value in self._checked else "☐ "
            return checkbox + value
        elif role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if value in self._checked else Qt.CheckState.Unchecked
        
        return None'''

if old_data in content:
    content = content.replace(old_data, new_data)
    print("✓ Added visual checkbox indicators")
else:
    print("✗ Could not find data() method")

# Write the updated content
with open(r'c:\Dev\SuiteViewP\suiteview\ui\widgets\filter_table_view.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("\n✓ Successfully updated data() method with visual checkboxes")
