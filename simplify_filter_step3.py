# Script to update FilterPopup methods for QListWidget

with open(r'c:\Dev\SuiteViewP\suiteview\ui\widgets\filter_table_view.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace filter_list method
old_filter = '''    def filter_list(self, search_text: str):
        """Filter the list based on search text"""
        self.proxy_model.setFilterFixedString(search_text)
        
        # Update info label
        visible_count = self.proxy_model.rowCount()
        if search_text:
            self.info_label.setText(f"Showing {visible_count:,} of {len(self.all_unique_values):,} values")
            # Auto-check matching items when typing
            if visible_count > 0:
                self.model.check_visible_items(self.proxy_model)
        else:
            self.info_label.setText(f"Showing all {len(self.all_unique_values):,} values")'''

new_filter = '''    def filter_list(self, search_text: str):
        """Filter the list based on search text"""
        search_lower = search_text.lower()
        visible_count = 0
        
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            # Show/hide items based on search
            matches = search_lower in item.text().lower()
            item.setHidden(not matches)
            if matches:
                visible_count += 1
        
        # Update info label
        if search_text:
            self.info_label.setText(f"Showing {visible_count:,} of {len(self.all_unique_values):,} values")
        else:
            self.info_label.setText(f"Showing all {len(self.all_unique_values):,} values")'''

content = content.replace(old_filter, new_filter)
print("✓ Updated filter_list method")

# Replace clear_filter method
old_clear = '''    def clear_filter(self):
        """Clear the filter (select all and apply)"""
        self.model.set_all_checked(True)
        self.apply_filter()'''

new_clear = '''    def clear_filter(self):
        """Clear the filter (select all and apply)"""
        self.select_all()
        self.apply_filter()'''

content = content.replace(old_clear, new_clear)
print("✓ Updated clear_filter method")

# Replace select_all method
old_select_all = '''    def select_all(self):
        """Select all items"""
        self.model.set_all_checked(True)'''

new_select_all = '''    def select_all(self):
        """Select all visible items"""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if not item.isHidden():
                item.setSelected(True)'''

content = content.replace(old_select_all, new_select_all)
print("✓ Updated select_all method")

# Replace deselect_all method
old_deselect = '''    def deselect_all(self):
        """Deselect all items"""
        self.model.set_all_checked(False)'''

new_deselect = '''    def deselect_all(self):
        """Deselect all items"""
        self.list_widget.clearSelection()'''

content = content.replace(old_deselect, new_deselect)
print("✓ Updated deselect_all method")

# Replace apply_filter method
old_apply = '''    def apply_filter(self):
        """Apply the filter and emit signal"""
        checked_values = self.model.get_checked_values()
        self.filter_changed.emit(self.column_name, checked_values)
        self.close()'''

new_apply = '''    def apply_filter(self):
        """Apply the filter and emit signal"""
        # Get selected items
        selected_values = set()
        for item in self.list_widget.selectedItems():
            selected_values.add(item.text())
        
        # If nothing is selected, select all (clear filter)
        if not selected_values:
            selected_values = set(self.all_unique_values)
        
        self.filter_changed.emit(self.column_name, selected_values)
        self.close()'''

content = content.replace(old_apply, new_apply)
print("✓ Updated apply_filter method")

# Replace get_selected_values method and remove on_item_clicked if it exists
old_get_selected = '''    def get_selected_values(self) -> Set[str]:
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

new_get_selected = '''    def get_selected_values(self) -> Set[str]:
        """Get currently selected values"""
        selected_values = set()
        for item in self.list_widget.selectedItems():
            selected_values.add(item.text())
        return selected_values if selected_values else set(self.all_unique_values)'''

if old_get_selected in content:
    content = content.replace(old_get_selected, new_get_selected)
    print("✓ Updated get_selected_values and removed on_item_clicked")
else:
    # Try without on_item_clicked
    old_get_selected2 = '''    def get_selected_values(self) -> Set[str]:
        """Get currently selected values"""
        return self.model.get_checked_values()'''
    content = content.replace(old_get_selected2, new_get_selected)
    print("✓ Updated get_selected_values")

# Write updated file
with open(r'c:\Dev\SuiteViewP\suiteview\ui\widgets\filter_table_view.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("\n✓ All methods updated for QListWidget multi-select")
