"""
Tree State Manager

Utility for managing QTreeWidget state (expansion, selection, etc).
"""
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
from PyQt6.QtCore import Qt
from typing import Set, Optional


class TreeStateManager:
    """Manages state preservation for QTreeWidget"""
    
    @staticmethod
    def save_expanded_folders(tree_widget: QTreeWidget) -> Set[int]:
        """
        Save the expansion state of all folder items in a tree widget.
        
        Args:
            tree_widget: The QTreeWidget to save state from
            
        Returns:
            Set of folder IDs that are currently expanded
        """
        expanded_folders = set()
        
        def check_item(item: QTreeWidgetItem):
            folder_id = item.data(0, Qt.ItemDataRole.UserRole)
            if folder_id and isinstance(folder_id, int) and folder_id < 0:  # Folder ID
                if item.isExpanded():
                    expanded_folders.add(folder_id)
            
            # Recursively check children
            for i in range(item.childCount()):
                check_item(item.child(i))
        
        # Check all top-level items
        for i in range(tree_widget.topLevelItemCount()):
            check_item(tree_widget.topLevelItem(i))
        
        return expanded_folders
    
    @staticmethod
    def restore_expanded_folders(tree_widget: QTreeWidget, expanded_folders: Set[int]):
        """
        Restore the expansion state of folder items in a tree widget.
        
        Args:
            tree_widget: The QTreeWidget to restore state to
            expanded_folders: Set of folder IDs that should be expanded
        """
        def restore_item(item: QTreeWidgetItem):
            folder_id = item.data(0, Qt.ItemDataRole.UserRole)
            if folder_id and isinstance(folder_id, int) and folder_id < 0:  # Folder ID
                if folder_id in expanded_folders:
                    item.setExpanded(True)
            
            # Recursively restore children
            for i in range(item.childCount()):
                restore_item(item.child(i))
        
        # Restore all top-level items
        for i in range(tree_widget.topLevelItemCount()):
            restore_item(tree_widget.topLevelItem(i))
    
    @staticmethod
    def get_selected_item_data(tree_widget: QTreeWidget, role: Qt.ItemDataRole = Qt.ItemDataRole.UserRole) -> Optional[any]:
        """
        Get data from the currently selected tree item.
        
        Args:
            tree_widget: The QTreeWidget to query
            role: The data role to retrieve (default: UserRole)
            
        Returns:
            The data stored in the selected item, or None if nothing is selected
        """
        selected_items = tree_widget.selectedItems()
        if not selected_items:
            return None
        return selected_items[0].data(0, role)
    
    @staticmethod
    def find_item_by_data(tree_widget: QTreeWidget, data: any, role: Qt.ItemDataRole = Qt.ItemDataRole.UserRole) -> Optional[QTreeWidgetItem]:
        """
        Find a tree item by its stored data.
        
        Args:
            tree_widget: The QTreeWidget to search
            data: The data value to find
            role: The data role to check (default: UserRole)
            
        Returns:
            The QTreeWidgetItem if found, otherwise None
        """
        def search_item(item: QTreeWidgetItem) -> Optional[QTreeWidgetItem]:
            if item.data(0, role) == data:
                return item
            
            for i in range(item.childCount()):
                result = search_item(item.child(i))
                if result:
                    return result
            
            return None
        
        for i in range(tree_widget.topLevelItemCount()):
            result = search_item(tree_widget.topLevelItem(i))
            if result:
                return result
        
        return None
