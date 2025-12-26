# Script to add checkbox click handling to FilterPopup

with open(r'c:\Dev\SuiteViewP\suiteview\ui\widgets\filter_table_view.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the list view creation section
old_listview = '''        # Create list view
        self.list_view = QListView()
        self.list_view.setModel(self.proxy_model)
        self.list_view.setEditTriggers(QListView.EditTrigger.NoEditTriggers)'''

new_listview = '''        # Create list view
        self.list_view = QListView()
        self.list_view.setModel(self.proxy_model)
        self.list_view.clicked.connect(self.on_item_clicked)  # Handle checkbox toggling'''

if old_listview in content:
    content = content.replace(old_listview, new_listview)
    print("✓ Added click handler")
else:
    print("✗ Could not find list view creation")

# Add the on_item_clicked method after the apply_filter method
old_apply = '''    def get_selected_values(self) -> Set[str]:
        """Get currently selected values"""
        return self.model.get_checked_values()'''

new_apply = '''    def get_selected_values(self) -> Set[str]:
        """Get currently selected values"""
        return self.model.get_checked_values()
    
    def on_item_clicked(self, index: QModelIndex):
        """Toggle checkbox when item is clicked"""
        if not index.isValid():
            return
        
        # Map proxy index to source index
        source_index = self.proxy_model.mapToSource(index)
        
        # Get current check state
        current_state = self.model.data(source_index, Qt.ItemDataRole.CheckStateRole)
        
        # Toggle the check state
        new_state = Qt.CheckState.Unchecked if current_state == Qt.CheckState.Checked else Qt.CheckState.Checked
        self.model.setData(source_index, new_state, Qt.ItemDataRole.CheckStateRole)'''

if old_apply in content:
    content = content.replace(old_apply, new_apply)
    print("✓ Added on_item_clicked method")
else:
    print("✗ Could not find get_selected_values method")

# Write the updated content
with open(r'c:\Dev\SuiteViewP\suiteview\ui\widgets\filter_table_view.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("\n✓ Successfully added checkbox click handling")
