"""
Bookmark Data Manager

This module provides centralized data management for all BookmarkContainer instances.
Uses a recursive tree structure where categories can contain bookmarks or other categories.

File structure:
~/.suiteview/bookmarks.json
{
    "next_bar_id": 2,
    "next_item_id": 7,
    "bars": {
        "0": {
            "orientation": "horizontal",
            "items": [
                {"id": 1, "type": "bookmark", "name": "Project", "path": "C:/..."},
                {"id": 2, "type": "category", "name": "Work", "color": "#FF6B6B", "items": [
                    {"id": 3, "type": "bookmark", "name": "Reports", "path": "C:/..."},
                    {"id": 4, "type": "category", "name": "Archives", "color": "#4CAF50", "items": [...]}
                ]}
            ]
        },
        "1": {
            "orientation": "vertical",
            "items": [...]
        }
    }
}

Key principles:
- Bookmarks and categories are both "items" with a type field
- Categories have an "items" array that can contain anything (recursive)
- Color is stored directly on category items
- Each item has a unique integer ID
- Moving items = remove from source array, insert into target array

Usage:
    manager = get_bookmark_manager()
    bar_items = manager.get_bar_items(0)
    manager.add_bookmark(bar_id=0, name="My File", path="C:/path")
    manager.add_category(bar_id=0, name="Work", color="#FF6B6B")
    manager.move_item(item_id=3, target_bar_id=1, target_index=0)
    manager.save()
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Callable, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class BookmarkDataManager:
    """
    Singleton manager for all bookmark bar data.
    
    Features:
    - Single unified JSON file for all bookmark bars
    - Recursive tree structure (categories contain items)
    - Integer IDs for all items (bookmarks and categories)
    - Simple move operations (just array manipulation)
    - Default initialization with two bars (horizontal + vertical)
    - Change notification callbacks
    """
    
    _instance = None
    _initialized = False
    
    # File path
    DATA_FILE = Path.home() / ".suiteview" / "bookmarks.json"
    
    # Default bar configurations
    DEFAULT_BARS = {
        0: {"orientation": "horizontal"},  # Top bar
        1: {"orientation": "vertical"},    # Side bar
    }
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if BookmarkDataManager._initialized:
            return
        
        BookmarkDataManager._initialized = True
        
        # The data store
        self._data: Dict[str, Any] = {
            "next_bar_id": 2,
            "next_item_id": 1,
            "bars": {}
        }
        
        # Callbacks for save notifications (bar_id -> list of callbacks)
        self._save_callbacks: Dict[int, List[Callable]] = {}
        
        # Load data
        self._load()
    
    @classmethod
    def instance(cls) -> 'BookmarkDataManager':
        """Get the singleton instance"""
        return cls()
    
    @classmethod
    def reset_instance(cls):
        """Reset the singleton (useful for testing)"""
        cls._instance = None
        cls._initialized = False
    
    # =========================================================================
    # ID Generation
    # =========================================================================
    
    def generate_item_id(self) -> int:
        """Get next item ID and increment counter"""
        new_id = self._data.get('next_item_id', 1)
        self._data['next_item_id'] = new_id + 1
        return new_id
    
    def generate_bar_id(self) -> int:
        """Get next bar ID and increment counter"""
        new_id = self._data.get('next_bar_id', 1)
        self._data['next_bar_id'] = new_id + 1
        return new_id
    
    def _find_max_item_id(self) -> int:
        """Scan all items recursively and find the highest ID"""
        max_id = 0
        
        def scan_items(items):
            nonlocal max_id
            for item in items:
                if 'id' in item and isinstance(item['id'], int):
                    max_id = max(max_id, item['id'])
                if item.get('type') == 'category' and 'items' in item:
                    scan_items(item['items'])
        
        for bar_data in self._data.get('bars', {}).values():
            scan_items(bar_data.get('items', []))
        
        return max_id
    
    def _find_max_bar_id(self) -> int:
        """Find the highest bar ID"""
        max_id = 0
        for bar_id in self._data.get('bars', {}).keys():
            try:
                max_id = max(max_id, int(bar_id))
            except ValueError:
                pass
        return max_id
    
    def repair_id_counters(self):
        """Repair ID counters by scanning for highest existing IDs"""
        self._data['next_item_id'] = self._find_max_item_id() + 1
        self._data['next_bar_id'] = self._find_max_bar_id() + 1
        logger.info(f"Repaired ID counters: next_item_id={self._data['next_item_id']}, "
                   f"next_bar_id={self._data['next_bar_id']}")
    
    def _cleanup_legacy_categories_in_bars(self):
        """Remove legacy 'categories' dict from bar data (categories are now inline items)"""
        needs_save = False
        for bar_id, bar_data in self._data.get('bars', {}).items():
            if 'categories' in bar_data:
                del bar_data['categories']
                logger.info(f"Removed legacy 'categories' dict from bar {bar_id}")
                needs_save = True
            if 'category_colors' in bar_data:
                del bar_data['category_colors']
                logger.info(f"Removed legacy 'category_colors' dict from bar {bar_id}")
                needs_save = True
        if needs_save:
            self.save()
    
    # =========================================================================
    # Bar Operations
    # =========================================================================
    
    def get_all_bar_ids(self) -> List[int]:
        """Get list of all bar IDs that have data"""
        return sorted([int(k) for k in self._data.get('bars', {}).keys()])
    
    def get_bar_data(self, bar_id: int) -> Dict[str, Any]:
        """
        Get the full data dict for a bar.
        Returns a reference (not a copy).
        """
        key = str(bar_id)
        if key not in self._data['bars']:
            orientation = self.DEFAULT_BARS.get(bar_id, {}).get('orientation', 'horizontal')
            self._data['bars'][key] = {
                'orientation': orientation,
                'items': []
            }
        return self._data['bars'][key]
    
    def get_bar_items(self, bar_id: int) -> List[Dict[str, Any]]:
        """Get the items list for a bar (reference, not copy)"""
        return self.get_bar_data(bar_id).get('items', [])
    
    def get_bar_orientation(self, bar_id: int) -> str:
        """Get the orientation of a bar ('horizontal' or 'vertical')"""
        return self.get_bar_data(bar_id).get('orientation', 'horizontal')
    
    def set_bar_orientation(self, bar_id: int, orientation: str):
        """Set the orientation of a bar"""
        self.get_bar_data(bar_id)['orientation'] = orientation
    
    def create_bar(self, orientation: str = 'horizontal') -> int:
        """Create a new bar and return its ID"""
        new_id = self.generate_bar_id()
        self._data['bars'][str(new_id)] = {
            'orientation': orientation,
            'items': []
        }
        return new_id
    
    def delete_bar(self, bar_id: int) -> bool:
        """Delete a bar. Returns True if deleted, False if not found."""
        key = str(bar_id)
        if key in self._data['bars']:
            del self._data['bars'][key]
            if bar_id in self._save_callbacks:
                del self._save_callbacks[bar_id]
            return True
        return False
    
    # =========================================================================
    # Item Creation
    # =========================================================================
    
    def create_bookmark(self, name: str, path: str) -> Dict[str, Any]:
        """Create a new bookmark dict (does not add to any bar)"""
        return {
            'id': self.generate_item_id(),
            'type': 'bookmark',
            'name': name,
            'path': path
        }
    
    def create_category(self, name: str, color_or_items = None, color: str = None) -> Union[Dict[str, Any], bool]:
        """
        Create a new category.
        
        Two calling conventions supported:
        - create_category(name, color) -> returns dict (doesn't add anywhere)
        - create_category(name, items, color) -> returns bool (adds to bar 0)
        
        Detection: if color_or_items is a list, adds to bar 0.
        """
        # Detect items list calling convention: create_category(name, items_list, color)
        if isinstance(color_or_items, list):
            # Items provided - add to bar 0
            items_list = color_or_items
            actual_color = color
            
            if self.category_name_exists(name):
                return False
            
            # Create category dict
            category = {
                'id': self.generate_item_id(),
                'type': 'category',
                'name': name,
                'items': []
            }
            if actual_color:
                category['color'] = actual_color
            
            # Add bookmark items if provided
            if items_list:
                for item in items_list:
                    if isinstance(item, dict):
                        bookmark = self.create_bookmark(
                            item.get('name', ''),
                            item.get('path', '')
                        )
                        category['items'].append(bookmark)
            
            # Add to bar 0
            bar_items = self.get_bar_items(0)
            bar_items.append(category)
            
            return True
        else:
            # Just create and return the dict
            actual_color = color_or_items  # Second param is color
            # Always include color - use default purple if not specified
            DEFAULT_COLOR = "#CE93D8"
            category = {
                'id': self.generate_item_id(),
                'type': 'category',
                'name': name,
                'color': actual_color or DEFAULT_COLOR,
                'items': []
            }
            return category
    
    # =========================================================================
    # Item Addition
    # =========================================================================
    
    def add_bookmark_to_bar(self, bar_id: int, name: str, path: str, 
                            index: int = None) -> Dict[str, Any]:
        """Add a new bookmark to a bar at the given index (None = end)"""
        bookmark = self.create_bookmark(name, path)
        items = self.get_bar_items(bar_id)
        if index is not None and 0 <= index <= len(items):
            items.insert(index, bookmark)
        else:
            items.append(bookmark)
        return bookmark
    
    def add_category_to_bar(self, bar_id: int, name: str, color: str = None,
                            index: int = None) -> Dict[str, Any]:
        """Add a new category to a bar at the given index (None = end)"""
        category = self.create_category(name, color)
        items = self.get_bar_items(bar_id)
        if index is not None and 0 <= index <= len(items):
            items.insert(index, category)
        else:
            items.append(category)
        return category
    
    def add_bookmark_to_category(self, category_id: int, name: str, path: str,
                                  index: int = None) -> Optional[Dict[str, Any]]:
        """Add a new bookmark inside a category"""
        category = self.find_item_by_id(category_id)
        if not category or category.get('type') != 'category':
            return None
        
        bookmark = self.create_bookmark(name, path)
        items = category.setdefault('items', [])
        if index is not None and 0 <= index <= len(items):
            items.insert(index, bookmark)
        else:
            items.append(bookmark)
        return bookmark
    
    def add_category_to_category(self, parent_id: int, name: str, color: str = None,
                                  index: int = None) -> Optional[Dict[str, Any]]:
        """Add a new subcategory inside a category"""
        parent = self.find_item_by_id(parent_id)
        if not parent or parent.get('type') != 'category':
            return None
        
        category = self.create_category(name, color)
        items = parent.setdefault('items', [])
        if index is not None and 0 <= index <= len(items):
            items.insert(index, category)
        else:
            items.append(category)
        return category
    
    # =========================================================================
    # Item Finding
    # =========================================================================
    
    def find_item_by_id(self, item_id: int) -> Optional[Dict[str, Any]]:
        """Find an item by ID anywhere in the tree"""
        def search(items):
            for item in items:
                if item.get('id') == item_id:
                    return item
                if item.get('type') == 'category':
                    found = search(item.get('items', []))
                    if found:
                        return found
            return None
        
        for bar_data in self._data.get('bars', {}).values():
            found = search(bar_data.get('items', []))
            if found:
                return found
        return None
    
    def find_item_location(self, item_id: int) -> Optional[Tuple[List, int]]:
        """
        Find where an item lives.
        Returns (parent_items_list, index) or None if not found.
        The parent_items_list is a reference, so you can modify it.
        """
        def search(items):
            for i, item in enumerate(items):
                if item.get('id') == item_id:
                    return (items, i)
                if item.get('type') == 'category':
                    found = search(item.get('items', []))
                    if found:
                        return found
            return None
        
        for bar_data in self._data.get('bars', {}).values():
            found = search(bar_data.get('items', []))
            if found:
                return found
        return None
    
    def find_category_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a category by name (searches entire tree)"""
        def search(items):
            for item in items:
                if item.get('type') == 'category' and item.get('name') == name:
                    return item
                if item.get('type') == 'category':
                    found = search(item.get('items', []))
                    if found:
                        return found
            return None
        
        for bar_data in self._data.get('bars', {}).values():
            found = search(bar_data.get('items', []))
            if found:
                return found
        return None
    
    def category_name_exists(self, name: str) -> bool:
        """Check if a category with this name exists anywhere"""
        return self.find_category_by_name(name) is not None
    
    def get_category_names_in_bar(self, bar_id: int) -> List[str]:
        """Get all category names in a specific bar (non-recursive, top-level only)"""
        bar_data = self.get_bar_data(bar_id)
        return [item.get('name') for item in bar_data.get('items', []) 
                if item.get('type') == 'category']
    
    def get_all_category_names(self) -> List[str]:
        """Get all category names from all bars"""
        names = set()
        for bar_data in self._data.get('bars', {}).values():
            for item in bar_data.get('items', []):
                if item.get('type') == 'category':
                    names.add(item.get('name'))
        return sorted(names, key=str.lower)
    
    def add_bookmark_to_category_by_name(self, category_name: str, name: str, path: str,
                                          index: int = None) -> Optional[Dict[str, Any]]:
        """Add a bookmark to a category by category name"""
        category = self.find_category_by_name(category_name)
        if not category:
            return None
        
        # Check for duplicate path
        for item in category.get('items', []):
            if item.get('path') == path:
                return None  # Already exists
        
        bookmark = self.create_bookmark(name, path)
        items = category.setdefault('items', [])
        if index is not None and 0 <= index <= len(items):
            items.insert(index, bookmark)
        else:
            items.append(bookmark)
        return bookmark
    
    def remove_bookmark_from_category_by_name(self, category_name: str, path: str) -> bool:
        """Remove a bookmark from a category by path"""
        category = self.find_category_by_name(category_name)
        if not category:
            return False
        
        items = category.get('items', [])
        for i, item in enumerate(items):
            if item.get('type') == 'bookmark' and item.get('path') == path:
                items.pop(i)
                return True
        return False
    
    def remove_bookmark_from_category_by_id(self, category_id: int, path: str) -> bool:
        """Remove a bookmark from a category by category ID and bookmark path"""
        category = self.find_item_by_id(category_id)
        if not category or category.get('type') != 'category':
            return False
        
        items = category.get('items', [])
        for i, item in enumerate(items):
            if item.get('type') == 'bookmark' and item.get('path') == path:
                items.pop(i)
                return True
        return False
    
    # =========================================================================
    # Item Modification
    # =========================================================================
    
    def update_bookmark(self, item_id: int, name: str = None, path: str = None) -> bool:
        """Update a bookmark's name and/or path"""
        item = self.find_item_by_id(item_id)
        if not item or item.get('type') != 'bookmark':
            return False
        if name is not None:
            item['name'] = name
        if path is not None:
            item['path'] = path
        return True
    
    def update_category(self, item_id: int, name: str = None, color: str = None) -> bool:
        """Update a category's name and/or color"""
        item = self.find_item_by_id(item_id)
        if not item or item.get('type') != 'category':
            return False
        if name is not None:
            item['name'] = name
        if color is not None:
            item['color'] = color
        elif color == '':
            # Empty string means remove color (use default)
            item.pop('color', None)
        return True
    
    def set_category_color(self, item_id: int, color: str) -> bool:
        """Set a category's color"""
        return self.update_category(item_id, color=color)
    
    def rename_category(self, item_id: int, new_name: str) -> bool:
        """Rename a category"""
        return self.update_category(item_id, name=new_name)
    
    # =========================================================================
    # Item Removal
    # =========================================================================
    
    def remove_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        """
        Remove an item by ID and return it.
        Returns the removed item, or None if not found.
        """
        location = self.find_item_location(item_id)
        if not location:
            return None
        
        items_list, index = location
        return items_list.pop(index)
    
    def delete_item(self, item_id: int) -> bool:
        """Delete an item by ID. Returns True if deleted."""
        return self.remove_item(item_id) is not None
    
    # =========================================================================
    # Item Moving
    # =========================================================================
    
    def move_item(self, item_id: int, target_bar_id: int = None, 
                  target_category_id: int = None, target_index: int = None) -> bool:
        """
        Move an item to a new location.
        
        Specify either target_bar_id (top level of a bar) or target_category_id 
        (inside a category), but not both.
        
        Args:
            item_id: ID of the item to move
            target_bar_id: Move to top level of this bar
            target_category_id: Move inside this category
            target_index: Index in target (None = append to end)
        
        Returns:
            True if moved successfully
        """
        # Remove from current location
        item = self.remove_item(item_id)
        if not item:
            return False
        
        # Determine target items list
        if target_category_id is not None:
            target_category = self.find_item_by_id(target_category_id)
            if not target_category or target_category.get('type') != 'category':
                # Can't find target - try to put item back (best effort)
                # This is a fallback, shouldn't normally happen
                logger.error(f"Move failed: target category {target_category_id} not found")
                return False
            target_items = target_category.setdefault('items', [])
        elif target_bar_id is not None:
            target_items = self.get_bar_items(target_bar_id)
        else:
            logger.error("Move failed: no target specified")
            return False
        
        # Insert at target
        if target_index is not None and 0 <= target_index <= len(target_items):
            target_items.insert(target_index, item)
        else:
            target_items.append(item)
        
        return True
    
    def reorder_item(self, item_id: int, new_index: int) -> bool:
        """
        Move an item within its current parent to a new index.
        """
        location = self.find_item_location(item_id)
        if not location:
            return False
        
        items_list, current_index = location
        
        if new_index < 0 or new_index > len(items_list):
            return False
        
        if current_index == new_index:
            return True  # Already there
        
        # Remove and reinsert
        item = items_list.pop(current_index)
        # Adjust index if we removed before the target
        if current_index < new_index:
            new_index -= 1
        items_list.insert(new_index, item)
        
        return True
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def get_all_items_flat(self) -> List[Dict[str, Any]]:
        """Get all items as a flat list (for searching, etc.)"""
        result = []
        
        def collect(items):
            for item in items:
                result.append(item)
                if item.get('type') == 'category':
                    collect(item.get('items', []))
        
        for bar_data in self._data.get('bars', {}).values():
            collect(bar_data.get('items', []))
        
        return result
    
    def get_all_categories(self) -> List[Dict[str, Any]]:
        """Get all categories as a flat list"""
        return [item for item in self.get_all_items_flat() 
                if item.get('type') == 'category']
    
    def get_all_bookmarks(self) -> List[Dict[str, Any]]:
        """Get all bookmarks as a flat list"""
        return [item for item in self.get_all_items_flat() 
                if item.get('type') == 'bookmark']
    
    def is_path_in_bar(self, bar_id: int, path: str) -> bool:
        """Check if a path exists in a bar (at top level or in any category)"""
        items = self.get_bar_items(bar_id)
        
        def check_items(items_list):
            for item in items_list:
                if item.get('type') == 'bookmark' and item.get('path') == path:
                    return True
                if item.get('type') == 'category':
                    if check_items(item.get('items', [])):
                        return True
            return False
        
        return check_items(items)
    
    def remove_bookmark_by_path(self, bar_id: int, path: str) -> bool:
        """Remove a bookmark from a bar by its path (searches recursively)"""
        items = self.get_bar_items(bar_id)
        
        def remove_from_list(items_list):
            for i, item in enumerate(items_list):
                if item.get('type') == 'bookmark' and item.get('path') == path:
                    items_list.pop(i)
                    return True
                if item.get('type') == 'category':
                    if remove_from_list(item.get('items', [])):
                        return True
            return False
        
        return remove_from_list(items)
    
    # =========================================================================
    # Persistence
    # =========================================================================
    
    def save(self):
        """Save all data to the JSON file"""
        try:
            self.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            
            # Write to temp file first, then rename (atomic)
            temp_file = self.DATA_FILE.with_suffix('.json.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            
            temp_file.replace(self.DATA_FILE)
            logger.debug(f"Saved bookmark data to {self.DATA_FILE}")
            
            self._notify_callbacks()
            
        except Exception as e:
            logger.error(f"Failed to save bookmark data: {e}")
    
    def _load(self):
        """Load data from file or initialize with defaults"""
        try:
            if self.DATA_FILE.exists():
                with open(self.DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Check if this is old format (has 'categories' at top level)
                if 'categories' in data and 'bars' in data:
                    # Old format - migrate to current structure
                    self._data = data
                    self._migrate_legacy_data()
                else:
                    self._data = data
                    # Ensure ID counters are valid
                    if 'next_item_id' not in self._data or 'next_bar_id' not in self._data:
                        self.repair_id_counters()
                    # Clean up legacy categories dict in bars
                    self._cleanup_legacy_categories_in_bars()
                    logger.info(f"Loaded bookmark data from {self.DATA_FILE}")
            else:
                logger.info("No bookmark data found, initializing defaults")
                self._initialize_defaults()
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse bookmark data: {e}")
            self._initialize_defaults()
        except Exception as e:
            logger.error(f"Failed to load bookmark data: {e}")
            self._initialize_defaults()
    
    def _initialize_defaults(self):
        """Initialize with default two bars"""
        self._data = {
            'next_bar_id': 2,
            'next_item_id': 1,
            'bars': {
                '0': {'orientation': 'horizontal', 'items': []},
                '1': {'orientation': 'vertical', 'items': []}
            }
        }
    
    def _migrate_legacy_data(self):
        """
        Migrate from legacy data format to current structure.
        
        Legacy format:
        - Global "categories" dict with category data
        - Global "category_colors" dict
        - Bar items contain references like {"type": "category", "name": "Work"}
        
        Current format:
        - Categories are inline with their items (recursive)
        - Color stored directly on category
        - Each item has a unique integer ID
        """
        logger.info("Migrating legacy bookmark data to current format")
        
        # Get old category data
        old_categories = self._data.get('categories', {})
        old_colors = self._data.get('category_colors', {})
        old_bars = self._data.get('bars', {})
        
        # Start fresh structure
        new_data = {
            'next_bar_id': self._data.get('next_bar_id', 2),
            'next_item_id': 1,
            'bars': {}
        }
        
        # Helper to generate IDs
        def next_id():
            id_val = new_data['next_item_id']
            new_data['next_item_id'] = id_val + 1
            return id_val
        
        # Helper to convert a category (recursive for subcategories)
        def convert_category(name: str, visited: set = None) -> Optional[Dict[str, Any]]:
            if visited is None:
                visited = set()
            
            if name in visited:
                logger.warning(f"Circular reference detected for category '{name}'")
                return None
            visited.add(name)
            
            cat_data = old_categories.get(name, {})
            if isinstance(cat_data, list):
                cat_data = {'items': cat_data, 'subcategories': []}
            
            color = old_colors.get(name)
            
            new_cat = {
                'id': next_id(),
                'type': 'category',
                'name': name,
                'items': []
            }
            if color:
                new_cat['color'] = color
            
            # Convert bookmark items
            for item in cat_data.get('items', []):
                if isinstance(item, dict):
                    new_bookmark = {
                        'id': next_id(),
                        'type': 'bookmark',
                        'name': item.get('name', ''),
                        'path': item.get('path', '')
                    }
                    new_cat['items'].append(new_bookmark)
            
            # Convert subcategories (recursive)
            for subcat_name in cat_data.get('subcategories', []):
                subcat = convert_category(subcat_name, visited.copy())
                if subcat:
                    new_cat['items'].append(subcat)
            
            return new_cat
        
        # Convert each bar
        for bar_id_str, bar_data in old_bars.items():
            new_bar = {
                'orientation': bar_data.get('orientation', 'horizontal'),
                'items': []
            }
            
            for item in bar_data.get('items', []):
                if item.get('type') == 'category':
                    cat_name = item.get('name', '')
                    converted = convert_category(cat_name)
                    if converted:
                        new_bar['items'].append(converted)
                elif item.get('type') == 'bookmark':
                    new_bookmark = {
                        'id': next_id(),
                        'type': 'bookmark',
                        'name': item.get('name', ''),
                        'path': item.get('path', '')
                    }
                    new_bar['items'].append(new_bookmark)
            
            new_data['bars'][bar_id_str] = new_bar
        
        # Ensure default bars exist
        if '0' not in new_data['bars']:
            new_data['bars']['0'] = {'orientation': 'horizontal', 'items': []}
        if '1' not in new_data['bars']:
            new_data['bars']['1'] = {'orientation': 'vertical', 'items': []}
        
        # Update next_bar_id if needed
        max_bar = max(int(k) for k in new_data['bars'].keys())
        if new_data['next_bar_id'] <= max_bar:
            new_data['next_bar_id'] = max_bar + 1
        
        self._data = new_data
        self.save()
        logger.info("Migration from legacy format complete")
    
    # =========================================================================
    # Callbacks
    # =========================================================================
    
    def register_save_callback(self, bar_id: int, callback: Callable):
        """Register a callback to be called after save"""
        if bar_id not in self._save_callbacks:
            self._save_callbacks[bar_id] = []
        if callback not in self._save_callbacks[bar_id]:
            self._save_callbacks[bar_id].append(callback)
    
    def unregister_save_callback(self, bar_id: int, callback: Callable):
        """Unregister a save callback"""
        if bar_id in self._save_callbacks:
            if callback in self._save_callbacks[bar_id]:
                self._save_callbacks[bar_id].remove(callback)
    
    def _notify_callbacks(self):
        """Notify all registered callbacks"""
        for bar_id, callbacks in self._save_callbacks.items():
            for callback in callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error in save callback for bar {bar_id}: {e}")
    
    # =========================================================================
    # Utility Methods for Flat Category Access
    # These methods provide a flattened view of the recursive category structure
    # =========================================================================
    
    def get_global_categories(self) -> Dict[str, Any]:
        """
        Returns a flattened dict-like view of all categories.
        
        Categories are stored inline recursively. This method builds
        a flattened view for easier lookups by name.
        
        Returns dict like: {"Work": {"items": [...], "subcategories": [...]}, ...}
        """
        result = {}
        
        def extract_categories(items):
            for item in items:
                if item.get('type') == 'category':
                    name = item.get('name', '')
                    # Build flattened category data
                    cat_items = []
                    subcats = []
                    for child in item.get('items', []):
                        if child.get('type') == 'bookmark':
                            cat_items.append({
                                'name': child.get('name', ''),
                                'path': child.get('path', ''),
                                'id': child.get('id')
                            })
                        elif child.get('type') == 'category':
                            subcats.append(child.get('name', ''))
                    
                    result[name] = {
                        'items': cat_items,
                        'subcategories': subcats,
                        '_item_id': item.get('id')  # Store ID for lookups
                    }
                    # Recurse into nested categories
                    extract_categories(item.get('items', []))
        
        for bar_data in self._data.get('bars', {}).values():
            extract_categories(bar_data.get('items', []))
        
        return result
    
    def get_global_colors(self) -> Dict[str, str]:
        """
        Returns a dict of category name -> color.
        
        Colors are stored on category items directly; this provides
        a flattened view for easier lookups.
        """
        result = {}
        
        def extract_colors(items):
            for item in items:
                if item.get('type') == 'category':
                    name = item.get('name', '')
                    color = item.get('color')
                    if color:
                        result[name] = color
                    extract_colors(item.get('items', []))
        
        for bar_data in self._data.get('bars', {}).values():
            extract_colors(bar_data.get('items', []))
        
        return result
    
    def category_exists(self, name: str) -> bool:
        """Check if a category name exists (alias for category_name_exists)"""
        return self.category_name_exists(name)
    
    def rename_category(self, old_name: str, new_name: str) -> bool:
        """
        Rename a category by name.
        
        Alternative: use update_category(item_id, name=new_name) with ID.
        """
        if self.category_name_exists(new_name):
            return False
        
        category = self.find_category_by_name(old_name)
        if not category:
            return False
        
        category['name'] = new_name
        return True
    
    def delete_category(self, name: str, recursive: bool = True) -> bool:
        """
        Delete a category by name.
        
        Alternative: use delete_item(item_id) with ID.
        """
        category = self.find_category_by_name(name)
        if not category:
            return False
        
        return self.delete_item(category.get('id'))
    
    def make_subcategory(self, category_name: str, parent_name: str, 
                          source_bar_id: int = None) -> bool:
        """
        Make a category a subcategory of another.
        
        Alternative: use move_item() with IDs.
        """
        category = self.find_category_by_name(category_name)
        parent = self.find_category_by_name(parent_name)
        
        if not category or not parent:
            return False
        
        if category.get('id') == parent.get('id'):
            return False  # Can't be own parent
        
        # Move the category into the parent
        return self.move_item(
            category.get('id'),
            target_category_id=parent.get('id')
        )
    
    def promote_to_toplevel(self, category_name: str, parent_name: str,
                            target_bar_id: int, insert_at: int = None) -> bool:
        """
        Move a subcategory to top level of a bar.
        
        Alternative: use move_item() with IDs.
        """
        category = self.find_category_by_name(category_name)
        if not category:
            return False
        
        return self.move_item(
            category.get('id'),
            target_bar_id=target_bar_id,
            target_index=insert_at
        )
    
    def move_category_to_bar(self, category_name: str, target_bar_id: int,
                              source_bar_id: int = None, insert_at: int = None) -> bool:
        """
        Move a category to a different bar.
        
        Alternative: use move_item() with IDs.
        """
        category = self.find_category_by_name(category_name)
        if not category:
            return False
        
        return self.move_item(
            category.get('id'),
            target_bar_id=target_bar_id,
            target_index=insert_at
        )


# Convenience function
def get_bookmark_manager() -> BookmarkDataManager:
    """Get the singleton BookmarkDataManager instance"""
    return BookmarkDataManager.instance()
