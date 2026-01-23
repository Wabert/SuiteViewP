"""Test to verify UI tree structure"""
import sys
from PyQt6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem
from PyQt6.QtCore import Qt

from suiteview.core.connection_manager import get_connection_manager

# Create minimal Qt app
app = QApplication(sys.argv)

# Get connections
conn_mgr = get_connection_manager()
connections = conn_mgr.get_connections()

print(f"\n=== Testing Tree Display Logic ===")
print(f"Found {len(connections)} connections\n")

# Create tree widget
tree = QTreeWidget()
tree.setHeaderLabel("Connections")

# Group connections by type
type_groups = {
    'ODBC': [],
    'SQL_SERVER': [],
    'DB2': [],
    'EXCEL': [],
    'ACCESS': [],
    'CSV': [],
    'FIXED_WIDTH': []
}

# Map connection types to display names
type_display_names = {
    'ODBC': 'ODBC',
    'SQL_SERVER': 'ODBC',
    'DB2': 'ODBC',
    'EXCEL': 'Excel',
    'ACCESS': 'MS Access',
    'CSV': 'CSV',
    'FIXED_WIDTH': 'Fixed Width File'
}

# Group connections
for conn in connections:
    conn_type = conn['connection_type']
    if conn_type in type_groups:
        type_groups[conn_type].append(conn)

print("Grouped connections:")
for group_type, group_conns in type_groups.items():
    if group_conns:
        print(f"  {group_type}: {len(group_conns)} connections")

# Create tree structure with groups
for group_type, group_conns in type_groups.items():
    # Create group header
    display_name = type_display_names.get(group_type, group_type)

    # For ODBC group, combine SQL_SERVER and DB2
    if group_type == 'ODBC':
        combined_conns = (type_groups.get('ODBC', []) +
                        type_groups.get('SQL_SERVER', []) +
                        type_groups.get('DB2', []))
        if not combined_conns:
            continue
        group_conns = combined_conns
        print(f"\nCreating ODBC group with {len(combined_conns)} connections")
    elif group_type in ['SQL_SERVER', 'DB2']:
        continue  # Already handled in ODBC group
    
    # Skip empty groups (check after combining for ODBC)
    if not group_conns:
        continue

    group_item = QTreeWidgetItem(tree)
    group_item.setText(0, display_name)
    group_item.setData(0, Qt.ItemDataRole.UserRole + 1, "group")
    group_item.setExpanded(True)
    
    print(f"Created group: {display_name}")

    # Add connections to group
    for conn in group_conns:
        conn_item = QTreeWidgetItem(group_item)
        conn_item.setText(0, conn['connection_name'])
        conn_item.setData(0, Qt.ItemDataRole.UserRole, conn['connection_id'])
        conn_item.setData(0, Qt.ItemDataRole.UserRole + 1, "connection")
        print(f"  - Added: {conn['connection_name']} (ID: {conn['connection_id']})")

print(f"\nTree has {tree.topLevelItemCount()} top-level items")
for i in range(tree.topLevelItemCount()):
    item = tree.topLevelItem(i)
    print(f"  Group {i}: {item.text(0)} with {item.childCount()} children")
    for j in range(item.childCount()):
        child = item.child(j)
        print(f"    - {child.text(0)}")

# Show the tree
tree.resize(400, 300)
tree.show()

print("\n=== Tree widget shown - check if connections appear ===")
print("Close the window to exit...")

sys.exit(app.exec())
