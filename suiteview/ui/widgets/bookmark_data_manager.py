"""
Bookmark Data Manager - Unified storage for all bookmark bars

This module provides centralized data management for all BookmarkContainer instances.
It uses a single JSON file with a scalable structure that supports any number of
bookmark bars identified by integer IDs.

File structure:
~/.suiteview/bookmarks.json
{
    "bars": {
        "0": {
            "orientation": "horizontal",
            "metadata": {},
            "items": [...],
            "categories": {...},
            "category_colors": {...}
        },
        "1": {
            "orientation": "vertical",
            "metadata": {},
            "items": [...],
            "categories": {...},
            "category_colors": {...}
        }
    },
    "next_bar_id": 2,
    "version": 3
}

Usage:
    manager = get_bookmark_manager()
    data = manager.get_bar_data(0)
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
    - Integer bar IDs for simple, consistent identification
    - Scalable design supporting unlimited bookmark bars
    - Default initialization with two bars (horizontal + vertical)
    - Thread-safe save operations
    - Change notification callbacks
    """
    
    _instance = None
    _initialized = False
    
    # File path
    DATA_FILE = Path.home() / ".suiteview" / "bookmarks.json"
    
    # Current data version
    DATA_VERSION = 3
    
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
    
    def get_bar_data(self, bar_id: int) -> Dict[str, Any]:
        """
        Get the data dict for a specific bookmark bar.
        Returns a reference to the actual data (not a copy) so changes 
        are reflected in the manager's data.
        
        Args:
            bar_id: Integer identifier for the bookmark bar (0, 1, 2, ...)
        
        Returns:
            Dict with keys: 'orientation', 'metadata', 'items', 'categories', 'category_colors'
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
        """Create empty data structure for a new bar"""
        return {
            "orientation": orientation,
            "metadata": {},
            "items": [],
            "categories": {},
            "category_colors": {}
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
                    # Migrate from old format
                    self._migrate_from_v2(data)
                elif "bars" in data:
                    self._data = data
                    logger.info(f"Loaded bookmark data from {self.DATA_FILE}")
                else:
                    logger.warning("Invalid bookmark data format, initializing defaults")
                    self._initialize_defaults()
            else:
                # Fresh start - initialize with default bars
                logger.info("No existing bookmark data found, initializing defaults")
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
        logger.info("Migration complete")
    
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
