# Code Smell Analysis & Refactoring Opportunities

**Date**: November 10, 2025  
**Analysis Type**: Systematic code review for technical debt and improvement opportunities

---

## Executive Summary

After reviewing the codebase, I've identified **7 major code smell categories** with specific refactoring recommendations. These range from quick wins (helper functions) to larger architectural improvements (screen decomposition).

**Priority Classification:**
- 🔴 **High Priority**: Causes bugs or severely impacts maintainability
- 🟡 **Medium Priority**: Makes code harder to maintain or extend
- 🟢 **Low Priority**: Nice-to-have improvements

---

## 1. 🔴 Duplicate Folder State Management (HIGH PRIORITY)

### Problem: Copy-Paste Code Smell
The code for saving/restoring folder expanded state is duplicated across multiple methods:

**Location**: `dbquery_screen.py` and `xdbquery_screen.py`
- `_copy_query()` - lines 1203-1207, 1228-1233
- `_delete_query()` - lines 1262-1267, 1288-1293
- `_rename_query()` - similar pattern

**Code Smell**:
```python
# This exact pattern appears 6+ times:
expanded_folders = set()
for i in range(self.db_queries_tree.topLevelItemCount()):
    folder_item = self.db_queries_tree.topLevelItem(i)
    if folder_item.isExpanded():
        folder_id = folder_item.data(0, Qt.ItemDataRole.UserRole + 1)
        expanded_folders.add(folder_id)

# ... do something ...

# Then restore
for i in range(self.db_queries_tree.topLevelItemCount()):
    folder_item = self.db_queries_tree.topLevelItem(i)
    folder_id = folder_item.data(0, Qt.ItemDataRole.UserRole + 1)
    if folder_id in expanded_folders:
        folder_item.setExpanded(True)
```

### Impact
- **14+ lines duplicated 6 times** = 84 lines of duplicate code
- Any bug fix must be applied in 6 places
- Easy to forget to update all locations

### Solution: Extract Helper Methods

```python
# Add to DBQueryScreen class:

def _save_folder_expanded_states(self, tree_widget: QTreeWidget) -> set:
    """Save which folders are currently expanded"""
    expanded_folders = set()
    for i in range(tree_widget.topLevelItemCount()):
        folder_item = tree_widget.topLevelItem(i)
        if folder_item.isExpanded():
            folder_id = folder_item.data(0, Qt.ItemDataRole.UserRole + 1)
            expanded_folders.add(folder_id)
    return expanded_folders

def _restore_folder_expanded_states(self, tree_widget: QTreeWidget, expanded_folders: set):
    """Restore which folders should be expanded"""
    for i in range(tree_widget.topLevelItemCount()):
        folder_item = tree_widget.topLevelItem(i)
        folder_id = folder_item.data(0, Qt.ItemDataRole.UserRole + 1)
        if folder_id in expanded_folders:
            folder_item.setExpanded(True)
```

**Usage**:
```python
def _copy_query(self, query_id: int, query_name: str, query_type: str = 'DB'):
    # Save state
    expanded_folders = self._save_folder_expanded_states(self.db_queries_tree)
    
    # ... do the work ...
    
    # Restore state
    self._restore_folder_expanded_states(self.db_queries_tree, expanded_folders)
```

**Benefits**:
- Reduces 84 lines to ~20 lines
- Single place to fix bugs
- Reusable across all query management methods
- Can apply same pattern to MyDataScreen

**Effort**: 1-2 hours  
**Risk**: Low (pure refactoring, no behavior change)

---

## 2. 🟡 Large Screen Classes - "God Object" Smell (MEDIUM PRIORITY)

### Problem: Classes Too Large
Several screen classes have grown beyond reasonable size:

| File | Lines | Issue |
|------|-------|-------|
| `dbquery_screen.py` | **4,591** | Too many responsibilities |
| `mydata_screen.py` | **2,421** | Mixed concerns |
| `xdbquery_screen.py` | **2,388** | Duplicate structure with dbquery_screen |

**Rule of Thumb**: Classes over 500 lines usually have too many responsibilities.

### Code Smell: Violates Single Responsibility Principle
`DBQueryScreen` handles:
1. UI layout and widgets (200+ lines)
2. Query building logic
3. Data loading from connections
4. Filter widget management
5. Display field management
6. Join management
7. Query persistence
8. Folder management
9. Query CRUD operations

That's **at least 9 distinct responsibilities** in one class!

### Solution: Extract Classes

#### Option A: Extract Query Management
```python
# New file: ui/helpers/query_manager.py
class QueryManager:
    """Handles query CRUD operations and folder management"""
    
    def __init__(self, query_repo, tree_widget):
        self.query_repo = query_repo
        self.tree_widget = tree_widget
    
    def copy_query(self, query_id: int, query_name: str) -> int:
        """Copy query with folder state preservation"""
        # Moves _copy_query logic here
        
    def delete_query(self, query_id: int) -> bool:
        """Delete query with folder state preservation"""
        # Moves _delete_query logic here
    
    def rename_query(self, query_id: int, new_name: str) -> bool:
        """Rename query"""
        # Moves _rename_query logic here
    
    # ... folder methods ...
```

**Usage in DBQueryScreen**:
```python
class DBQueryScreen(QWidget):
    def __init__(self):
        # ...
        self.query_manager = QueryManager(self.query_repo, self.db_queries_tree)
    
    def _copy_query(self, query_id: int, query_name: str):
        new_query_id = self.query_manager.copy_query(query_id, query_name)
        if new_query_id:
            self.queries_changed.emit()
```

#### Option B: Extract Widget Managers
```python
# ui/helpers/filter_manager.py
class FilterManager:
    """Manages criteria filter widgets"""
    # Moves criteria widget logic here
    
# ui/helpers/display_field_manager.py
class DisplayFieldManager:
    """Manages display field widgets"""
    # Moves display field logic here
```

### Benefits
- **Reusability**: QueryManager can be shared between DB and XDB screens
- **Testability**: Easier to write unit tests for isolated components
- **Clarity**: Each class has one clear purpose
- **Maintainability**: Easier to find and fix bugs

**Effort**: 2-3 days (significant refactoring)  
**Risk**: Medium (requires careful testing)  
**Recommendation**: Start with QueryManager (highest duplication)

---

## 3. 🟡 Duplicate CascadingMenuWidget (MEDIUM PRIORITY)

### Problem: Identical Classes in Different Files

**Locations**:
- `dbquery_screen.py` lines 120-244 (125 lines)
- `xdbquery_screen.py` lines 23-147 (125 lines)

These are **identical classes** copied between files.

### Solution: Extract to Shared Module

```python
# Create: ui/widgets/cascading_menu_widget.py
class CascadingMenuWidget(QWidget):
    """Reusable cascading menu for connection selection"""
    # Move the class here
```

**Update both screens**:
```python
from suiteview.ui.widgets.cascading_menu_widget import CascadingMenuWidget
```

### Benefits
- Eliminates 125 lines of duplication
- Bug fixes apply to both screens automatically
- Easier to enhance the widget

**Effort**: 30 minutes  
**Risk**: Very Low  
**Recommendation**: Quick win - do this first!

---

## 4. 🟢 Magic Numbers in Widget Dimensions (LOW PRIORITY)

### Problem: Hard-Coded Numbers Throughout Code

**Examples**:
```python
# dbquery_screen.py
self.setFixedWidth(320)  # Why 320?
self.setFixedWidth(200)  # Why 200?
self.setFixedHeight(95)  # Why 95?
self.collapsed_height = 50  # Why 50?
self.expanded_height = 115  # Why 115?
```

### Code Smell: Magic Numbers Reduce Maintainability
When you need to adjust widget sizes, you must hunt through the code to find all related dimensions.

### Solution: Define Constants

```python
# ui/constants.py (new file)
class WidgetSizes:
    """Standard widget dimensions"""
    # Filter widgets
    CRITERIA_FILTER_WIDTH = 200
    CRITERIA_FILTER_MIN_HEIGHT = 100
    
    # Display field widgets
    DISPLAY_FIELD_WIDTH = 200
    DISPLAY_FIELD_COLLAPSED_HEIGHT = 50
    DISPLAY_FIELD_EXPANDED_HEIGHT = 115
    
    # Buttons
    GOLD_BUTTON_MIN_WIDTH = 120
    HEADER_BUTTON_MIN_WIDTH = 60
    
    # Dialogs
    MIN_DIALOG_WIDTH = 1000
    MIN_DIALOG_HEIGHT = 600
```

**Usage**:
```python
from suiteview.ui.constants import WidgetSizes

self.setFixedWidth(WidgetSizes.DISPLAY_FIELD_WIDTH)
self.collapsed_height = WidgetSizes.DISPLAY_FIELD_COLLAPSED_HEIGHT
```

### Benefits
- Central place to adjust UI dimensions
- Self-documenting code (names explain purpose)
- Easier to maintain consistent UI appearance

**Effort**: 2-3 hours  
**Risk**: Very Low  
**Recommendation**: Good for UI polish iteration

---

## 5. 🟡 Inconsistent Error Handling Patterns (MEDIUM PRIORITY)

### Problem: Three Different Error Handling Styles

**Style 1: Try-Except with QMessageBox**
```python
try:
    # do something
except Exception as e:
    logger.error(f"Error: {e}")
    QMessageBox.critical(self, "Error", f"Failed:\n{str(e)}")
```

**Style 2: Try-Except without QMessageBox**
```python
try:
    # do something
except Exception as e:
    logger.error(f"Error: {e}")
    raise  # Let caller handle it
```

**Style 3: No Try-Except**
```python
# Just do it, let exceptions bubble up
result = risky_operation()
```

### Solution: Standardize Error Handling Decorator

```python
# utils/error_handling.py
from functools import wraps
from PyQt6.QtWidgets import QMessageBox

def handle_errors(title="Error", show_dialog=True):
    """Decorator for consistent error handling in UI methods"""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
                if show_dialog:
                    QMessageBox.critical(
                        self, 
                        title,
                        f"An error occurred:\n{str(e)}"
                    )
                return None
        return wrapper
    return decorator
```

**Usage**:
```python
@handle_errors(title="Copy Query Failed")
def _copy_query(self, query_id: int, query_name: str):
    # No try-except needed - decorator handles it
    query_record = self.query_repo.get_query(query_id)
    # ... rest of method ...
```

### Benefits
- Consistent user experience
- Less boilerplate code
- Centralized error logging
- Easy to add error tracking/reporting later

**Effort**: 1 day  
**Risk**: Low  
**Recommendation**: Improves code quality significantly

---

## 6. 🟡 Long Parameter Lists (MEDIUM PRIORITY)

### Problem: Methods with Many Parameters

**Examples**:
```python
# query_executor.py
def _build_where_clause(self, criterion: Dict[str, Any], has_joins: bool = False) -> str:

# connections_screen.py  
def _show_table_data(self, limit: int = None):

# dbquery_screen.py
def _create_data_map_widget(self, row: int, column_name: str, connection_id: int, 
                            table_name: str, schema_name: str):
```

### Code Smell: Parameter Objects Needed
When methods have 4+ parameters, they usually need an object to group related data.

### Solution: Use Data Classes

```python
from dataclasses import dataclass

@dataclass
class TableReference:
    """Represents a database table"""
    connection_id: int
    table_name: str
    schema_name: str = None
    
@dataclass
class QueryFilter:
    """Represents a WHERE clause filter"""
    field_name: str
    table_name: str
    data_type: str
    operator: str = '='
    value: Any = None
    match_type: str = 'exact'
```

**Before**:
```python
def _create_data_map_widget(self, row: int, column_name: str, connection_id: int, 
                            table_name: str, schema_name: str):
```

**After**:
```python
def _create_data_map_widget(self, row: int, column_name: str, table_ref: TableReference):
```

### Benefits
- Clearer method signatures
- Type safety with dataclasses
- Easier to add new fields later
- Better IDE autocomplete

**Effort**: 1-2 days  
**Risk**: Medium (requires changing many call sites)  
**Recommendation**: Do incrementally as you touch code

---

## 7. 🟢 Missing Type Hints (LOW PRIORITY)

### Problem: Inconsistent Type Annotations

Some methods have complete type hints:
```python
def execute_raw_sql(self, connection_id: int, table_name: str, 
                   schema_name: str = None, limit: int = None) -> pd.DataFrame:
```

Others have none:
```python
def _show_table_data(self, limit=None):  # What type is limit? What does it return?
```

### Solution: Add Type Hints Progressively

**Use mypy for type checking**:
```bash
pip install mypy
mypy suiteview/
```

**Add type hints to new code**:
```python
from typing import Optional

def _show_table_data(self, limit: Optional[int] = None) -> None:
    """Show table data with optional row limit"""
```

### Benefits
- Better IDE support (autocomplete, refactoring)
- Catch type errors before runtime
- Self-documenting code
- Easier onboarding for new developers

**Effort**: Ongoing (add to new code, gradually improve old code)  
**Risk**: Very Low  
**Recommendation**: Adopt as coding standard going forward

---

## Priority Ranking & Roadmap

### Quick Wins (1-2 days effort)
1. ✅ **Extract CascadingMenuWidget** (30 min) - Eliminates 125 lines duplication
2. ✅ **Extract Folder State Helpers** (2 hours) - Eliminates 84 lines duplication
3. ✅ **Add Error Handling Decorator** (1 day) - Improves code quality

**Total savings**: ~200+ lines of duplicate code eliminated

### Medium-Term Improvements (1-2 weeks)
4. **Extract QueryManager** (2-3 days) - Reduces screen class sizes by ~500 lines
5. **Standardize Error Handling** (1 day) - Apply decorator throughout codebase
6. **Add Parameter Objects** (2 days) - Improve method signatures

### Long-Term Goals (ongoing)
7. **Decompose Large Screens** (ongoing) - Keep classes under 500 lines
8. **Add Type Hints** (ongoing) - Gradually improve type coverage
9. **Define UI Constants** (as needed) - Eliminate magic numbers

---

## Code Quality Metrics

### Current State
- **Largest class**: `DBQueryScreen` - 4,591 lines (too large!)
- **Code duplication**: ~300+ lines identified
- **Type hint coverage**: ~40% (estimated)
- **Test coverage**: Unknown (no unit tests found)

### Target State
- **Max class size**: 500 lines per class
- **Code duplication**: < 50 lines total
- **Type hint coverage**: > 80%
- **Test coverage**: > 60% for business logic

---

## Additional Observations

### Positive Patterns Found ✅
1. **Good separation** between UI, business logic, and data layers
2. **Consistent use** of PyQt signals for component communication
3. **Centralized connection management** with ConnectionManager
4. **Good logging** throughout the codebase
5. **Recent refactoring** (execute_raw_sql) shows awareness of code quality

### Areas for Future Consideration
1. **Unit testing**: No test files found for business logic
2. **Configuration management**: Some hard-coded values could be configurable
3. **Documentation**: Add docstrings to complex methods
4. **Performance**: Consider caching for frequently-accessed data

---

## Recommendations

### Start Here (This Week)
1. **Extract CascadingMenuWidget** - Immediate 125-line reduction
2. **Extract folder state helpers** - Fixes bug-prone duplication
3. **Create error handling decorator** - Quality of life improvement

### Next Sprint
4. **Extract QueryManager** - Major architectural improvement
5. **Begin adding type hints** - Start with new code
6. **Document refactoring standards** - Team alignment

### Ongoing Practice
- Keep new classes under 500 lines
- Extract helpers when code is duplicated 2+ times
- Add type hints to all new methods
- Consider testability when designing new features

---

## Conclusion

The codebase shows **good architectural foundations** but has accumulated technical debt through rapid feature development. The identified code smells are **typical and fixable**. 

**Most importantly**: The recent `execute_raw_sql()` refactoring demonstrates the team's commitment to code quality. These recommendations follow the same principles - identify duplication, extract reusable components, and improve maintainability.

**Recommended approach**: Tackle the quick wins first (1-2 days of work) to build momentum, then address larger refactorings incrementally over time.
