"""
Bookmark Data Manager - Unified storage for all bookmark bars

This module provides centralized data management for all BookmarkContainer instances.
It uses a single JSON file with a scalable structure that supports any number of
bookmark bars identified by unique string IDs.

File structure:
~/.suiteview/bookmarks.json
{
    "bars": {
        "bar_id_1": {
            "items": [...],
            "categories": {...},
            "category_colors": {...}
        },
        "bar_id_2": {
            "items": [...],
            "categories": {...},
            "category_colors": {...}
        }
    },
    "version": 2
}

Usage:
    manager = BookmarkDataManager.instance()
    data = manager.get_bar_data('my_bar_id')
    manager.save()
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable

logger = logging.getLogger(__name__)


class BookmarkDataManager:
    """
    Singleton manager for all bookmark bar data.
    
    Features:
    - Single unified JSON file for all bookmark bars
    - Scalable design supporting unlimited bookmark bars
    - Automatic migration from legacy two-file format
    - Thread-safe save operations
    - Change notification callbacks
    """
    
    _instance = None
    _initialized = False
    
    # File paths
    DATA_FILE = Path.home() / ".suiteview" / "bookmarks.json"
    LEGACY_BAR_FILE = Path.home() / ".suiteview" / "bookmarks.json"  # Old top bar file
    LEGACY_SIDEBAR_FILE = Path.home() / ".suiteview" / "quick_links.json"  # Old sidebar file
    BACKUP_DIR = Path.home() / ".suiteview" / "backups"
    
    # Current data version
    DATA_VERSION = 2
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if BookmarkDataManager._initialized:
            return
        
        BookmarkDataManager._initialized = True
        
        # The data store: {"bars": {bar_id: {items, categories, category_colors}}, "version": 2}
        self._data: Dict[str, Any] = {"bars": {}, "version": self.DATA_VERSION}
        
        # Callbacks for save notifications (bar_id -> list of callbacks)
        self._save_callbacks: Dict[str, List[Callable]] = {}
        
        # Load data (with migration if needed)
        self._load()
    
    @classmethod
    def instance(cls) -> 'BookmarkDataManager':
        """Get the singleton instance"""
        return cls()
    
    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------
    
    def get_bar_data(self, bar_id: str) -> Dict[str, Any]:
        """
        Get the data dict for a specific bookmark bar.
        Returns a reference to the actual data (not a copy) so changes 
        are reflected in the manager's data.
        
        Args:
            bar_id: Unique identifier for the bookmark bar
                    Examples: 'top_bar', 'sidebar', 'top_bar_2', 'quick_access'
        
        Returns:
            Dict with keys: 'items', 'categories', 'category_colors'
        """
        if bar_id not in self._data["bars"]:
            self._data["bars"][bar_id] = self._create_empty_bar_data()
        return self._data["bars"][bar_id]
    
    def set_bar_data(self, bar_id: str, data: Dict[str, Any]):
        """
        Set the data for a specific bookmark bar.
        
        Args:
            bar_id: Unique identifier for the bookmark bar
            data: Dict with keys: 'items', 'categories', 'category_colors'
        """
        self._data["bars"][bar_id] = data
    
    def get_all_bar_ids(self) -> List[str]:
        """Get list of all bar IDs that have data"""
        return list(self._data["bars"].keys())
    
    def remove_bar(self, bar_id: str):
        """Remove a bookmark bar's data entirely"""
        if bar_id in self._data["bars"]:
            del self._data["bars"][bar_id]
    
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
    
    def register_save_callback(self, bar_id: str, callback: Callable):
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
    
    def unregister_save_callback(self, bar_id: str, callback: Callable):
        """Unregister a save callback"""
        if bar_id in self._save_callbacks:
            if callback in self._save_callbacks[bar_id]:
                self._save_callbacks[bar_id].remove(callback)
    
    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------
    
    def _create_empty_bar_data(self) -> Dict[str, Any]:
        """Create empty data structure for a new bar"""
        return {
            "items": [],
            "categories": {},
            "category_colors": {}
        }
    
    def _load(self):
        """Load data from file, migrating from legacy format if needed"""
        try:
            if self.DATA_FILE.exists():
                with open(self.DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Check if this is new format (version 2+) or legacy
                if "version" in data and data["version"] >= 2:
                    # New unified format
                    self._data = data
                    logger.info(f"Loaded bookmark data v{data['version']} from {self.DATA_FILE}")
                else:
                    # Legacy top bar format - migrate
                    logger.info("Detected legacy top bar format, migrating...")
                    self._migrate_from_legacy(top_bar_data=data)
            elif self.LEGACY_SIDEBAR_FILE.exists():
                # Only sidebar file exists - migrate
                logger.info("Detected legacy sidebar file only, migrating...")
                self._migrate_from_legacy()
            else:
                # Fresh start
                logger.info("No existing bookmark data found, starting fresh")
                self._data = {"bars": {}, "version": self.DATA_VERSION}
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse bookmark data: {e}")
            self._data = {"bars": {}, "version": self.DATA_VERSION}
        except Exception as e:
            logger.error(f"Failed to load bookmark data: {e}")
            self._data = {"bars": {}, "version": self.DATA_VERSION}
    
    def _migrate_from_legacy(self, top_bar_data: Optional[Dict] = None):
        """
        Migrate from legacy two-file format to unified format.
        
        Legacy format:
        - bookmarks.json: {bar_items, categories, category_colors} for top bar
        - quick_links.json: {items, categories, category_colors} for sidebar
        
        New format:
        - bookmarks.json: {bars: {bar_id: {...}}, version: 2}
        """
        try:
            # Create backup directory
            self.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            
            # Initialize new data structure
            new_data = {"bars": {}, "version": self.DATA_VERSION}
            
            # Migrate top bar data
            if top_bar_data:
                bar_data = self._normalize_legacy_bar_data(top_bar_data, is_top_bar=True)
                new_data["bars"]["top_bar"] = bar_data
                logger.info(f"Migrated top bar: {len(bar_data.get('items', []))} items")
                
                # Backup the old file
                backup_path = self.BACKUP_DIR / "bookmarks_legacy_backup.json"
                shutil.copy2(self.DATA_FILE, backup_path)
                logger.info(f"Backed up legacy top bar to {backup_path}")
            
            # Migrate sidebar data
            if self.LEGACY_SIDEBAR_FILE.exists():
                try:
                    with open(self.LEGACY_SIDEBAR_FILE, 'r', encoding='utf-8') as f:
                        sidebar_data = json.load(f)
                    
                    bar_data = self._normalize_legacy_bar_data(sidebar_data, is_top_bar=False)
                    new_data["bars"]["sidebar"] = bar_data
                    logger.info(f"Migrated sidebar: {len(bar_data.get('items', []))} items")
                    
                    # Backup and remove old sidebar file
                    backup_path = self.BACKUP_DIR / "quick_links_legacy_backup.json"
                    shutil.copy2(self.LEGACY_SIDEBAR_FILE, backup_path)
                    logger.info(f"Backed up legacy sidebar to {backup_path}")
                    
                    # Remove the old file after successful migration
                    self.LEGACY_SIDEBAR_FILE.unlink()
                    logger.info(f"Removed legacy sidebar file: {self.LEGACY_SIDEBAR_FILE}")
                    
                except Exception as e:
                    logger.error(f"Failed to migrate sidebar data: {e}")
            
            self._data = new_data
            
            # Save the migrated data
            self.save()
            logger.info("Migration to unified bookmark format complete")
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            # Fall back to empty data
            self._data = {"bars": {}, "version": self.DATA_VERSION}
    
    def _normalize_legacy_bar_data(self, data: Dict, is_top_bar: bool) -> Dict[str, Any]:
        """
        Normalize legacy data to the standard format.
        
        Legacy top bar used 'bar_items' as key, sidebar used 'items'.
        Both should use 'items' in new format.
        """
        result = self._create_empty_bar_data()
        
        # Handle items list (different key names in legacy format)
        if is_top_bar and 'bar_items' in data:
            result['items'] = data['bar_items']
        elif 'items' in data:
            result['items'] = data['items']
        
        # Copy categories and colors if present
        if 'categories' in data:
            result['categories'] = data['categories']
        if 'category_colors' in data:
            result['category_colors'] = data['category_colors']
        
        return result
    
    def _notify_callbacks(self):
        """Notify all registered callbacks that data was saved"""
        for bar_id, callbacks in self._save_callbacks.items():
            for callback in callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error in save callback for {bar_id}: {e}")


# Convenience function for getting the singleton
def get_bookmark_manager() -> BookmarkDataManager:
    """Get the singleton BookmarkDataManager instance"""
    return BookmarkDataManager.instance()
