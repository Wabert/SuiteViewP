"""
Bookmark Data Manager - Unified storage for all bookmark bars

This module provides centralized data management for all BookmarkContainer instances.
It uses a single JSON file with a scalable structure that supports any number of
bookmark bars identified by integer IDs.

Categories are stored GLOBALLY (not per-bar) to enable seamless cross-bar moves.
Category names must be unique across all bars. Each bar's items list contains
references to category names, not the category data itself.

File structure:
~/.suiteview/bookmarks.json
{
    "categories": {
        "Work": {"items": [...], "subcategories": ["Projects"]},
        "Projects": {"items": [...], "subcategories": []},
        "Personal": {"items": [...], "subcategories": []}
    },
    "category_colors": {
        "Work": "#FF6B6B",
        "Projects": "#4CAF50"
    },
    "bars": {
        "0": {
            "orientation": "horizontal",
            "metadata": {},
            "items": [
                {"type": "category", "name": "Work"},
                {"type": "bookmark", "name": "...", "path": "..."}
            ]
        },
        "1": {
            "orientation": "vertical",
            "metadata": {},
            "items": [
                {"type": "category", "name": "Personal"}
            ]
        }
    },
    "next_bar_id": 2,
    "version": 4
}

Usage:
    manager = get_bookmark_manager()
    data = manager.get_bar_data(0)
    categories = manager.get_global_categories()
    manager.save()
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Callable, Optional

logger = logging.getLogger(__name__)


class BookmarkDataManager:
    """
    Singleton manager for all bookmark bar data.
    
    Features:
    - Single unified JSON file for all bookmark bars
    - GLOBAL categories and colors (shared across all bars)
    - Integer bar IDs for simple, consistent identification
    - Scalable design supporting unlimited bookmark bars
    - Default initialization with two bars (horizontal + vertical)
    - Thread-safe save operations
    - Change notification callbacks
    
    Categories are stored globally to enable seamless cross-bar moves.
    Moving a category between bars only requires updating references.
    """
    
    _instance = None
    _initialized = False
    
    # File path
    DATA_FILE = Path.home() / ".suiteview" / "bookmarks.json"
    
    # Current data version (4 = global categories)
    DATA_VERSION = 4
    
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
        
        # The data store - now with global categories at top level
        self._data: Dict[str, Any] = {
            "categories": {},       # Global categories (shared across all bars)
            "category_colors": {},  # Global category colors
            "bars": {},
            "next_bar_id": 2,
            "version": self.DATA_VERSION
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
    # Public API
    # =========================================================================
    
    # -------------------------------------------------------------------------
    # Global Categories (shared across all bars)
    # -------------------------------------------------------------------------
    
    def get_global_categories(self) -> Dict[str, Any]:
        """
        Get the global categories dict (shared across all bars).
        Returns a reference to the actual data (not a copy).
        
        Returns:
            Dict mapping category names to their data:
            {"Work": {"items": [...], "subcategories": [...]}, ...}
        """
        return self._data.setdefault("categories", {})
    
    def get_global_colors(self) -> Dict[str, str]:
        """
        Get the global category colors dict.
        Returns a reference to the actual data (not a copy).
        
        Returns:
            Dict mapping category names to hex colors: {"Work": "#FF6B6B", ...}
        """
        return self._data.setdefault("category_colors", {})
    
    def category_exists(self, name: str) -> bool:
        """Check if a category name already exists globally."""
        return name in self.get_global_categories()
    
    def create_category(self, name: str, items: List = None, color: str = None) -> bool:
        """
        Create a new global category.
        
        Args:
            name: Category name (must be unique)
            items: Initial bookmark items (optional)
            color: Hex color string (optional)
        
        Returns:
            True if created, False if name already exists
        """
        categories = self.get_global_categories()
        if name in categories:
            return False
        
        categories[name] = {
            "items": items or [],
            "subcategories": []
        }
        
        if color:
            self.get_global_colors()[name] = color
        
        return True
    
    def rename_category(self, old_name: str, new_name: str) -> bool:
        """
        Rename a category globally. Updates all references in all bars.
        
        Args:
            old_name: Current category name
            new_name: New category name (must be unique)
        
        Returns:
            True if renamed, False if old doesn't exist or new already exists
        """
        categories = self.get_global_categories()
        colors = self.get_global_colors()
        
        if old_name not in categories or new_name in categories:
            return False
        
        # Rename in categories dict
        categories[new_name] = categories.pop(old_name)
        
        # Transfer color
        if old_name in colors:
            colors[new_name] = colors.pop(old_name)
        
        # Update references in all bars
        for bar_id in self.get_all_bar_ids():
            bar_data = self.get_bar_data(bar_id)
            for item in bar_data.get("items", []):
                if item.get("type") == "category" and item.get("name") == old_name:
                    item["name"] = new_name
        
        # Update parent category references (subcategories lists and item_order)
        for cat_data in categories.values():
            if isinstance(cat_data, dict):
                subcats = cat_data.get("subcategories", [])
                for i, subcat in enumerate(subcats):
                    if subcat == old_name:
                        subcats[i] = new_name
                # Also update item_order if present
                item_order = cat_data.get("item_order", [])
                for order_item in item_order:
                    if order_item.get("type") == "subcategory" and order_item.get("name") == old_name:
                        order_item["name"] = new_name
        
        return True
    
    def delete_category(self, name: str, recursive: bool = True) -> bool:
        """
        Delete a category globally.
        
        Args:
            name: Category name to delete
            recursive: If True, also delete all subcategories recursively
        
        Returns:
            True if deleted, False if not found
        """
        categories = self.get_global_categories()
        colors = self.get_global_colors()
        
        if name not in categories:
            return False
        
        # Get subcategories before deleting
        cat_data = categories[name]
        subcats = []
        if isinstance(cat_data, dict):
            subcats = cat_data.get("subcategories", [])
        
        # Delete the category
        del categories[name]
        if name in colors:
            del colors[name]
        
        # Remove from all bars' items lists
        for bar_id in self.get_all_bar_ids():
            bar_data = self.get_bar_data(bar_id)
            items = bar_data.get("items", [])
            bar_data["items"] = [
                item for item in items
                if not (item.get("type") == "category" and item.get("name") == name)
            ]
        
        # Remove from any parent's subcategories list and item_order
        for cat_data in categories.values():
            if isinstance(cat_data, dict):
                subcats_list = cat_data.get("subcategories", [])
                if name in subcats_list:
                    subcats_list.remove(name)
                # Also remove from item_order if present
                item_order = cat_data.get("item_order", [])
                cat_data["item_order"] = [
                    i for i in item_order
                    if not (i.get("type") == "subcategory" and i.get("name") == name)
                ]
        
        # Recursively delete subcategories if requested
        if recursive:
            for subcat in subcats:
                self.delete_category(subcat, recursive=True)
        
        return True
    
    def move_category_to_bar(self, category_name: str, target_bar_id: int, 
                              source_bar_id: int = None, insert_at: int = None) -> bool:
        """
        Move a category reference from one bar to another.
        Since categories are global, this only moves the reference.
        
        Args:
            category_name: Name of category to move
            target_bar_id: Bar ID to move to
            source_bar_id: Bar ID to move from (if None, just adds to target)
            insert_at: Index to insert at in target bar (None = append)
        
        Returns:
            True if successful
        """
        if not self.category_exists(category_name):
            return False
        
        target_data = self.get_bar_data(target_bar_id)
        target_items = target_data.setdefault("items", [])
        
        # Check if already in target
        for item in target_items:
            if item.get("type") == "category" and item.get("name") == category_name:
                return False  # Already there
        
        # Remove from source bar if specified
        if source_bar_id is not None:
            source_data = self.get_bar_data(source_bar_id)
            source_items = source_data.get("items", [])
            source_data["items"] = [
                item for item in source_items
                if not (item.get("type") == "category" and item.get("name") == category_name)
            ]
        
        # Add to target bar
        new_item = {"type": "category", "name": category_name}
        if insert_at is not None and 0 <= insert_at <= len(target_items):
            target_items.insert(insert_at, new_item)
        else:
            target_items.append(new_item)
        
        return True
    
    def make_subcategory(self, category_name: str, parent_name: str, 
                          source_bar_id: int = None) -> bool:
        """
        Make a category a subcategory of another category.
        Removes from bar's top-level items if present.
        
        Args:
            category_name: Category to make a subcategory
            parent_name: Parent category name
            source_bar_id: If provided, removes from this bar's items list
        
        Returns:
            True if successful
        """
        categories = self.get_global_categories()
        
        if category_name not in categories or parent_name not in categories:
            return False
        
        if category_name == parent_name:
            return False  # Can't be own parent
        
        # Check for circular reference
        if self._is_ancestor_of(category_name, parent_name):
            return False
        
        parent_data = categories[parent_name]
        if isinstance(parent_data, list):
            # Migrate old format
            categories[parent_name] = {"items": parent_data, "subcategories": []}
            parent_data = categories[parent_name]
        
        subcats = parent_data.setdefault("subcategories", [])
        
        if category_name in subcats:
            return False  # Already a subcategory
        
        subcats.append(category_name)
        
        # Also add to item_order if it exists (at the end)
        item_order = parent_data.get("item_order", None)
        if item_order is not None:
            item_order.append({"type": "subcategory", "name": category_name})
        
        # Remove from source bar's items list
        if source_bar_id is not None:
            bar_data = self.get_bar_data(source_bar_id)
            items = bar_data.get("items", [])
            bar_data["items"] = [
                item for item in items
                if not (item.get("type") == "category" and item.get("name") == category_name)
            ]
        
        # Also remove from any other bar's items list (it's now nested)
        for bar_id in self.get_all_bar_ids():
            bar_data = self.get_bar_data(bar_id)
            items = bar_data.get("items", [])
            bar_data["items"] = [
                item for item in items
                if not (item.get("type") == "category" and item.get("name") == category_name)
            ]
        
        return True
    
    def promote_to_toplevel(self, category_name: str, parent_name: str, 
                            target_bar_id: int, insert_at: int = None) -> bool:
        """
        Promote a subcategory to top-level on a bar.
        
        Args:
            category_name: Subcategory to promote
            parent_name: Current parent category
            target_bar_id: Bar to add it to
            insert_at: Index to insert at (None = append)
        
        Returns:
            True if successful
        """
        categories = self.get_global_categories()
        
        if category_name not in categories:
            return False
        
        # Remove from parent's subcategories list and item_order
        if parent_name and parent_name in categories:
            parent_data = categories[parent_name]
            if isinstance(parent_data, dict):
                subcats = parent_data.get("subcategories", [])
                if category_name in subcats:
                    subcats.remove(category_name)
                # Also remove from item_order if present
                item_order = parent_data.get("item_order", [])
                parent_data["item_order"] = [
                    i for i in item_order
                    if not (i.get("type") == "subcategory" and i.get("name") == category_name)
                ]
        
        # Add to target bar
        return self.move_category_to_bar(category_name, target_bar_id, 
                                          source_bar_id=None, insert_at=insert_at)
    
    def _is_ancestor_of(self, potential_ancestor: str, category: str) -> bool:
        """Check if potential_ancestor is an ancestor of category (prevents circular refs)."""
        categories = self.get_global_categories()
        
        def check(cat_name):
            cat_data = categories.get(cat_name, {})
            if isinstance(cat_data, dict):
                subcats = cat_data.get("subcategories", [])
                if category in subcats:
                    return True
                for subcat in subcats:
                    if check(subcat):
                        return True
            return False
        
        return check(potential_ancestor)
    
    # -------------------------------------------------------------------------
    # Bar Data
    # -------------------------------------------------------------------------
    
    def get_bar_data(self, bar_id: int) -> Dict[str, Any]:
        """
        Get the data dict for a specific bookmark bar.
        Returns a reference to the actual data (not a copy) so changes 
        are reflected in the manager's data.
        
        NOTE: In v4+, categories and colors are stored globally, not per-bar.
        Use get_global_categories() and get_global_colors() to access them.
        
        Args:
            bar_id: Integer identifier for the bookmark bar (0, 1, 2, ...)
        
        Returns:
            Dict with keys: 'orientation', 'metadata', 'items'
            (categories and category_colors are now global)
        """
        key = str(bar_id)
        if key not in self._data["bars"]:
            # Create with default orientation if it's a known default bar
            orientation = self.DEFAULT_BARS.get(bar_id, {}).get("orientation", "horizontal")
            self._data["bars"][key] = self._create_empty_bar_data(orientation)
        return self._data["bars"][key]
    
    def get_bar_orientation(self, bar_id: int) -> str:
        """Get the orientation of a bar ('horizontal' or 'vertical')"""
        data = self.get_bar_data(bar_id)
        return data.get("orientation", "horizontal")
    
    def set_bar_data(self, bar_id: int, data: Dict[str, Any]):
        """
        Set the data for a specific bookmark bar.
        
        Args:
            bar_id: Integer identifier for the bookmark bar
            data: Dict with bar data
        """
        self._data["bars"][str(bar_id)] = data
    
    def get_all_bar_ids(self) -> List[int]:
        """Get list of all bar IDs that have data"""
        return [int(k) for k in self._data["bars"].keys()]
    
    def create_bar(self, orientation: str = "horizontal") -> int:
        """
        Create a new bookmark bar.
        
        Args:
            orientation: 'horizontal' or 'vertical'
        
        Returns:
            The new bar's integer ID
        """
        new_id = self._data.get("next_bar_id", 2)
        self._data["bars"][str(new_id)] = self._create_empty_bar_data(orientation)
        self._data["next_bar_id"] = new_id + 1
        return new_id
    
    def delete_bar(self, bar_id: int) -> bool:
        """
        Delete a bookmark bar.
        
        Args:
            bar_id: Integer identifier for the bookmark bar
        
        Returns:
            True if bar was deleted, False if it didn't exist
        """
        key = str(bar_id)
        if key in self._data["bars"]:
            del self._data["bars"][key]
            # Also remove any callbacks
            if bar_id in self._save_callbacks:
                del self._save_callbacks[bar_id]
            return True
        return False
    
    def get_bar_metadata(self, bar_id: int) -> Dict[str, Any]:
        """Get the metadata dict for a bar (for future customization)"""
        data = self.get_bar_data(bar_id)
        return data.get("metadata", {})
    
    def set_bar_metadata(self, bar_id: int, metadata: Dict[str, Any]):
        """Set the metadata for a bar"""
        data = self.get_bar_data(bar_id)
        data["metadata"] = metadata
    
    def save(self):
        """Save all data to the unified JSON file"""
        try:
            # Ensure directory exists
            self.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            
            # Write to temp file first, then rename (atomic on most systems)
            temp_file = self.DATA_FILE.with_suffix('.json.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            
            # Rename temp to actual file
            temp_file.replace(self.DATA_FILE)
            
            logger.debug(f"Saved bookmark data to {self.DATA_FILE}")
            
            # Notify all callbacks
            self._notify_callbacks()
            
        except Exception as e:
            logger.error(f"Failed to save bookmark data: {e}")
    
    def register_save_callback(self, bar_id: int, callback: Callable):
        """
        Register a callback to be notified when data is saved.
        
        Args:
            bar_id: The bar ID this callback is associated with
            callback: Function to call after save (no arguments)
        """
        if bar_id not in self._save_callbacks:
            self._save_callbacks[bar_id] = []
        if callback not in self._save_callbacks[bar_id]:
            self._save_callbacks[bar_id].append(callback)
    
    def unregister_save_callback(self, bar_id: int, callback: Callable):
        """Unregister a save callback"""
        if bar_id in self._save_callbacks:
            if callback in self._save_callbacks[bar_id]:
                self._save_callbacks[bar_id].remove(callback)
    
    # =========================================================================
    # Private Methods
    # =========================================================================
    
    def _create_empty_bar_data(self, orientation: str = "horizontal") -> Dict[str, Any]:
        """Create empty data structure for a new bar (v4: no per-bar categories)"""
        return {
            "orientation": orientation,
            "metadata": {},
            "items": []
            # NOTE: categories and category_colors are now global, not per-bar
        }
    
    def _load(self):
        """Load data from file, or initialize with defaults"""
        try:
            if self.DATA_FILE.exists():
                with open(self.DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Check version and migrate if needed
                version = data.get("version", 1)
                
                if version < 3:
                    # Migrate from old format (v1/v2) to v3, then v3 to v4
                    self._migrate_from_v2(data)
                    self._migrate_from_v3_to_v4()
                elif version == 3:
                    # Migrate from v3 (per-bar categories) to v4 (global categories)
                    self._data = data
                    self._migrate_from_v3_to_v4()
                elif "bars" in data:
                    self._data = data
                    # Ensure global categories exist
                    self._data.setdefault("categories", {})
                    self._data.setdefault("category_colors", {})
                    
                    # Check if migration is still needed (version 4 but per-bar categories exist)
                    needs_migration = False
                    for bar_id, bar_data in self._data.get("bars", {}).items():
                        if "categories" in bar_data and bar_data["categories"]:
                            needs_migration = True
                            break
                    
                    if needs_migration:
                        logger.info("Detected per-bar categories in v4 data, running migration")
                        self._migrate_from_v3_to_v4()
                    else:
                        logger.info(f"Loaded bookmark data from {self.DATA_FILE}")
                else:
                    logger.warning("Invalid bookmark data format, initializing defaults")
                    self._initialize_defaults()
            else:
                # Fresh start - initialize with default bars
                logger.info("No existing bookmark data found, initializing defaults")
                self._initialize_defaults()
                self._initialize_defaults()
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse bookmark data: {e}")
            self._initialize_defaults()
        except Exception as e:
            logger.error(f"Failed to load bookmark data: {e}")
            self._initialize_defaults()
    
    def _initialize_defaults(self):
        """Initialize with default two bars and global categories"""
        self._data = {
            "categories": {},
            "category_colors": {},
            "bars": {
                "0": self._create_empty_bar_data("horizontal"),
                "1": self._create_empty_bar_data("vertical"),
            },
            "next_bar_id": 2,
            "version": self.DATA_VERSION
        }
    
    def _migrate_from_v2(self, old_data: Dict[str, Any]):
        """Migrate from version 2 (string IDs) to version 3 (integer IDs)"""
        logger.info("Migrating bookmark data from v2 to v3")
        
        old_bars = old_data.get("bars", {})
        new_bars = {}
        
        # Map old string IDs to new integer IDs
        id_mapping = {
            "top_bar": "0",
            "bar": "0",
            "sidebar": "1",
            "quick_links": "1",
        }
        
        for old_id, bar_data in old_bars.items():
            # Determine new ID
            new_id = id_mapping.get(old_id.lower())
            if new_id is None:
                # Unknown bar - try to parse as int or assign next available
                try:
                    new_id = str(int(old_id))
                except ValueError:
                    new_id = str(len(new_bars) + 2)  # Start from 2 for unknown bars
            
            # Determine orientation from old ID if not present
            if "orientation" not in bar_data:
                if old_id.lower() in ("sidebar", "quick_links"):
                    bar_data["orientation"] = "vertical"
                else:
                    bar_data["orientation"] = "horizontal"
            
            # Ensure metadata exists
            if "metadata" not in bar_data:
                bar_data["metadata"] = {}
            
            # Handle old key names
            if "bar_items" in bar_data and "items" not in bar_data:
                bar_data["items"] = bar_data.pop("bar_items")
            
            new_bars[new_id] = bar_data
        
        # Ensure default bars exist
        if "0" not in new_bars:
            new_bars["0"] = self._create_empty_bar_data("horizontal")
        if "1" not in new_bars:
            new_bars["1"] = self._create_empty_bar_data("vertical")
        
        self._data = {
            "bars": new_bars,
            "next_bar_id": max(int(k) for k in new_bars.keys()) + 1,
            "version": self.DATA_VERSION
        }
        
        # Save migrated data
        self.save()
        logger.info("Migration to v3 complete")
    
    def _migrate_from_v3_to_v4(self):
        """
        Migrate from v3 (per-bar categories) to v4 (global categories).
        
        Strategy:
        1. Collect all categories from all bars
        2. Handle name collisions by appending bar ID suffix
        3. Move to global categories dict
        4. Update all bar items to use references only
        """
        logger.info("Migrating bookmark data from v3 to v4 (global categories)")
        
        # Create global categories and colors dicts
        global_categories = {}
        global_colors = {}
        
        # Track name mappings for collision handling
        # {(bar_id, old_name): new_name}
        name_mappings = {}
        
        old_bars = self._data.get("bars", {})
        
        # First pass: collect all categories and handle collisions
        for bar_id_str, bar_data in old_bars.items():
            bar_categories = bar_data.get("categories", {})
            bar_colors = bar_data.get("category_colors", {})
            
            for cat_name, cat_data in bar_categories.items():
                final_name = cat_name
                
                # Check for collision
                if cat_name in global_categories:
                    # Append bar ID to make unique
                    suffix = 1
                    while f"{cat_name} ({suffix})" in global_categories:
                        suffix += 1
                    final_name = f"{cat_name} ({suffix})"
                    logger.warning(f"Category name collision: '{cat_name}' in bar {bar_id_str} "
                                   f"renamed to '{final_name}'")
                
                name_mappings[(bar_id_str, cat_name)] = final_name
                
                # Copy category data
                if isinstance(cat_data, dict):
                    global_categories[final_name] = {
                        "items": cat_data.get("items", []),
                        "subcategories": cat_data.get("subcategories", [])
                    }
                elif isinstance(cat_data, list):
                    global_categories[final_name] = {
                        "items": cat_data,
                        "subcategories": []
                    }
                else:
                    global_categories[final_name] = {"items": [], "subcategories": []}
                
                # Copy color
                if cat_name in bar_colors:
                    global_colors[final_name] = bar_colors[cat_name]
        
        # Second pass: update subcategory references with new names
        for bar_id_str, bar_data in old_bars.items():
            for cat_name in bar_data.get("categories", {}).keys():
                final_name = name_mappings.get((bar_id_str, cat_name), cat_name)
                cat_data = global_categories.get(final_name, {})
                
                if isinstance(cat_data, dict):
                    old_subcats = cat_data.get("subcategories", [])
                    new_subcats = []
                    for subcat in old_subcats:
                        # Find the mapped name for this subcategory
                        mapped_name = name_mappings.get((bar_id_str, subcat), subcat)
                        new_subcats.append(mapped_name)
                    cat_data["subcategories"] = new_subcats
        
        # Third pass: update bar items to use new names and remove per-bar categories
        for bar_id_str, bar_data in old_bars.items():
            # Update item references
            items = bar_data.get("items", [])
            for item in items:
                if item.get("type") == "category":
                    old_name = item.get("name", "")
                    new_name = name_mappings.get((bar_id_str, old_name), old_name)
                    item["name"] = new_name
            
            # Remove per-bar categories and colors
            if "categories" in bar_data:
                del bar_data["categories"]
            if "category_colors" in bar_data:
                del bar_data["category_colors"]
        
        # Set global categories and colors
        self._data["categories"] = global_categories
        self._data["category_colors"] = global_colors
        self._data["version"] = self.DATA_VERSION
        
        # Save migrated data
        self.save()
        logger.info(f"Migration to v4 complete: {len(global_categories)} categories migrated")
    
    def _notify_callbacks(self):
        """Notify all registered callbacks that data was saved"""
        for bar_id, callbacks in self._save_callbacks.items():
            for callback in callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error in save callback for bar {bar_id}: {e}")


# Convenience function for getting the singleton
def get_bookmark_manager() -> BookmarkDataManager:
    """Get the singleton BookmarkDataManager instance"""
    return BookmarkDataManager.instance()
