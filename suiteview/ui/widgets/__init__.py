"""
UI Widgets Package

Reusable UI components for SuiteView application.
"""
from .cascading_menu import CascadingMenuWidget
from .bookmark_widgets import (
    CategoryButton, CategoryPopup, CategoryBookmarkButton, 
    BookmarkContainer, BookmarkContainerRegistry, StandaloneBookmarkButton,
    CATEGORY_BUTTON_STYLE, CATEGORY_BUTTON_STYLE_SIDEBAR,
    BOOKMARK_BUTTON_STYLE, POPUP_STYLE, CONTEXT_MENU_STYLE
)
from .bookmark_data_manager import BookmarkDataManager, get_bookmark_manager

__all__ = [
    'CascadingMenuWidget',
    # Bookmark widgets
    'BookmarkContainer',
    'BookmarkContainerRegistry',
    'CategoryButton', 
    'CategoryPopup', 
    'CategoryBookmarkButton',
    'StandaloneBookmarkButton',
    # Bookmark data manager
    'BookmarkDataManager',
    'get_bookmark_manager',
    # Styles
    'CATEGORY_BUTTON_STYLE',
    'CATEGORY_BUTTON_STYLE_SIDEBAR', 
    'BOOKMARK_BUTTON_STYLE',
    'POPUP_STYLE',
    'CONTEXT_MENU_STYLE'
]
