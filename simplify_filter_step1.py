# Script to simplify FilterPopup - use multi-select list instead of checkboxes

with open(r'c:\Dev\SuiteViewP\suiteview\ui\widgets\filter_table_view.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the CheckableListModel class and remove it (it's no longer needed)
# Find FilterPopup class start
filterpopup_start = None
checkable_model_start = None

for i, line in enumerate(lines):
    if 'class CheckableListModel' in line:
        checkable_model_start = i
    if 'class FilterPopup' in line:
        filterpopup_start = i
        break

# Remove CheckableListModel class (from checkable_model_start to filterpopup_start-1)
if checkable_model_start is not None and filterpopup_start is not None:
    # Keep everything before CheckableListModel and after FilterPopup start
    new_lines = lines[:checkable_model_start] + lines[filterpopup_start:]
    print(f"✓ Removed CheckableListModel class (lines {checkable_model_start}-{filterpopup_start})")
else:
    new_lines = lines
    print("✗ Could not find class boundaries")

content = ''.join(new_lines)

# Update imports - add QListWidget, remove QListView
content = content.replace(
    'from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableView, QListView,',
    'from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableView, QListWidget,'
)

# Remove QAbstractListModel from imports since we don't need it anymore
content = content.replace(
    'from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, pyqtSignal, QRect, QPoint, QAbstractListModel, QTimer',
    'from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, pyqtSignal, QRect, QPoint, QTimer'
)

print("✓ Updated imports")

# Write the updated content
with open(r'c:\Dev\SuiteViewP\suiteview\ui\widgets\filter_table_view.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("\n✓ Step 1 complete: Removed CheckableListModel and updated imports")
