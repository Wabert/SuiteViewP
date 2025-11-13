# SuiteView Data Manager - Improvements Roadmap

## ✅ Completed Improvements

### 1. Extract Magic Strings to Constants (#18)
**Status:** COMPLETE
**File:** `suiteview/utils/constants.py`
**Impact:** Code maintainability and consistency

Created centralized constants for:
- Query types (DB, XDB)
- Item types (query_folder, query, connection, table, field, etc.)
- Connection types (SQL_SERVER, DB2, ORACLE, ACCESS, EXCEL, CSV, etc.)
- Filter types and match types
- UI colors
- Query complexity levels
- Settings keys

**Benefits:**
- No more scattered string literals
- IDE autocomplete for constants
- Single source of truth
- Easier refactoring

---

### 2. Query Notes Database Migration (#13 - Partial)
**Status:** COMPLETE (DB layer only, UI pending)
**File:** `suiteview/data/database.py` (Migration 5)
**Impact:** Foundation for feature #13

Added `notes` TEXT column to `saved_queries` table via automatic migration.

**Next Steps for Full Feature:**
- Add "Edit Notes" button in My Data screen query details panel
- Show notes in query metadata display
- Add notes field to query save dialog

---

## 🎯 High-Priority Features (Ready to Implement)

### 3. SQL View Mode (#25) - HIGHEST VALUE
**Complexity:** Medium
**Time Estimate:** 2-3 hours
**Files to Modify:**
- `suiteview/ui/dbquery_screen.py`
- `suiteview/ui/xdbquery_screen.py`

**Implementation Plan:**
1. Add "View SQL" button to toolbar (next to Run Query/Save Query)
2. Create `_show_sql_dialog()` method that:
   - Calls `query_executor._build_sql(query)`
   - Shows SQL in QTextEdit with read-only mode
   - Add "Copy to Clipboard" button
   - Add syntax highlighting (optional)

**Code Sketch:**
```python
def _show_sql_dialog(self):
    """Show generated SQL in a dialog"""
    try:
        # Build current query from UI state
        query = self._build_query_from_ui()

        # Generate SQL
        sql = self.query_executor._build_sql(query)

        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Generated SQL")
        dialog.setMinimumSize(600, 400)

        layout = QVBoxLayout(dialog)

        # SQL display
        sql_text = QTextEdit()
        sql_text.setPlainText(sql)
        sql_text.setReadOnly(True)
        sql_text.setFont(QFont("Courier New", 10))
        layout.addWidget(sql_text)

        # Buttons
        button_layout = QHBoxLayout()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(sql))
        button_layout.addWidget(copy_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)
        dialog.exec()

    except Exception as e:
        QMessageBox.warning(self, "SQL Generation Failed", str(e))
```

---

### 4. Query Change Detection (#15) - IMPORTANT
**Complexity:** Medium
**Time Estimate:** 3-4 hours
**Files to Modify:**
- `suiteview/ui/dbquery_screen.py`
- `suiteview/ui/xdbquery_screen.py`
- `suiteview/ui/main_window.py`

**Implementation Plan:**
1. Add `_original_query_definition` attribute to store loaded query state
2. Create `_has_unsaved_changes()` method that compares current UI to original
3. Update window title with asterisk (*) when dirty
4. Prompt on tab switch if unsaved changes
5. Update "Reset" button to revert to `_original_query_definition`

**Key Methods:**
```python
def _mark_query_dirty(self):
    """Mark query as having unsaved changes"""
    if not self._is_dirty and self.current_query_id:
        self._is_dirty = True
        self._update_window_title()

def _has_unsaved_changes(self) -> bool:
    """Check if current query differs from saved version"""
    if not self.current_query_id:
        return False  # New query, not dirty until saved

    current = self._build_query_from_ui().to_dict()
    return current != self._original_query_definition

def _update_window_title(self):
    """Update window title to show dirty state"""
    query_name = self.query_name_label.text()
    if self._is_dirty:
        self.parent().setWindowTitle(f"SuiteView - {query_name}*")
    else:
        self.parent().setWindowTitle(f"SuiteView - {query_name}")
```

Connect dirty tracking to all UI changes:
- Criteria added/removed/changed
- Display fields changed
- Joins modified
- FROM table changed

---

### 5. Query Preview Mode (#11) - SAFETY FEATURE
**Complexity:** Low
**Time Estimate:** 1-2 hours
**Files to Modify:**
- `suiteview/ui/dbquery_screen.py`
- `suiteview/core/query_executor.py`

**Implementation Plan:**
1. Add "Preview (100 rows)" button next to "Run Query"
2. Modify `execute_db_query()` to accept optional `limit` parameter
3. Wrap SQL with LIMIT clause (or TOP for SQL Server)

**Code Sketch:**
```python
# In dbquery_screen.py
def _preview_query(self):
    """Run query with 100 row limit for preview"""
    try:
        query = self._build_query_from_ui()

        # Show progress
        progress = QProgressDialog("Previewing first 100 rows...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()

        # Execute with limit
        df = self.query_executor.execute_db_query(query, limit=100)

        progress.close()

        # Show results
        self._show_results_dialog(df, preview_mode=True)

    except Exception as e:
        QMessageBox.critical(self, "Preview Failed", str(e))

# In query_executor.py
def execute_db_query(self, query: Query, limit: int = None) -> pd.DataFrame:
    """Execute query with optional row limit"""
    sql = self._build_sql(query)

    if limit:
        # Add LIMIT clause based on database type
        if connection_type == 'SQL_SERVER':
            # SQL Server uses TOP
            sql = sql.replace("SELECT", f"SELECT TOP {limit}", 1)
        else:
            # Most others use LIMIT
            sql = f"{sql} LIMIT {limit}"

    # ... rest of execution
```

---

### 6. Field Search in Trees (#14) - HIGH USABILITY
**Complexity:** Low
**Time Estimate:** 2 hours
**Files to Modify:**
- `suiteview/ui/dbquery_screen.py`
- `suiteview/ui/xdbquery_screen.py`

**Implementation Plan:**
1. Add QLineEdit search box above fields tree
2. Filter tree items on text change (case-insensitive)
3. Show only matching fields + their parent tables
4. Clear button to reset filter

**Code Sketch:**
```python
# Add to _create_fields_panel()
search_layout = QHBoxLayout()
self.field_search_input = QLineEdit()
self.field_search_input.setPlaceholderText("Search fields...")
self.field_search_input.textChanged.connect(self._filter_fields_tree)

clear_btn = QPushButton("×")
clear_btn.setFixedSize(20, 20)
clear_btn.clicked.connect(lambda: self.field_search_input.clear())

search_layout.addWidget(self.field_search_input)
search_layout.addWidget(clear_btn)
panel_layout.addLayout(search_layout)

def _filter_fields_tree(self, search_text: str):
    """Filter fields tree based on search text"""
    search_text = search_text.lower()

    # Iterate through all top-level items (tables)
    for i in range(self.fields_tree.topLevelItemCount()):
        table_item = self.fields_tree.topLevelItem(i)
        has_matching_child = False

        # Check each field under the table
        for j in range(table_item.childCount()):
            field_item = table_item.child(j)
            field_name = field_item.text(0).lower()

            # Show/hide based on match
            matches = search_text in field_name
            field_item.setHidden(not matches)

            if matches:
                has_matching_child = True

        # Show table if it has matching children, or if search is empty
        table_item.setHidden(not has_matching_child and search_text != "")
```

---

## 📋 Medium-Priority Features (Implement Next)

### 7. Query Validation Before Run (#4)
**Files:** `suiteview/ui/dbquery_screen.py`, `suiteview/core/query_builder.py`
**Time:** 2 hours

Add validation warnings:
- No display fields selected
- No FROM table selected
- Invalid JOIN conditions (missing fields)
- Criteria without values

### 8. Smart Field Suggestions for JOINs (#7)
**Files:** `suiteview/ui/dbquery_screen.py`
**Time:** 3 hours

Enhance auto-match with fuzzy matching:
- "CustID" suggests "CustomerID"
- "AcctNum" suggests "AccountNumber"
- Use `difflib.SequenceMatcher` for similarity scoring

### 9. Bulk Operations on Queries (#10)
**Files:** `suiteview/ui/mydata_screen.py`
**Time:** 4 hours

Enable multi-select in query tree:
- Ctrl+Click for multi-select
- Right-click → "Move Selected to Folder..."
- Right-click → "Delete Selected..."
- Right-click → "Export Selected..."

### 10. Recent Queries Section (#1)
**Files:** `suiteview/ui/mydata_screen.py`, `suiteview/data/repositories.py`
**Time:** 3 hours

Add collapsible "Recent" section at top of DB Queries tree showing last 10 executed queries.

---

## 🎨 Polish Features (Lower Priority)

### 11. Better Empty States (#21)
Show helpful images and CTAs when trees are empty.

### 12. Query Complexity Indicator (#22)
Show colored badges (🟢🟡🔴) based on query complexity score.

### 13. Progress Bars (#23)
Consistent QProgressDialog for all long operations.

### 14. Animated Transitions (#24)
QPropertyAnimation for smooth add/remove of criteria widgets.

---

## 🔧 Code Quality Improvements

### 15. Consolidate Duplicate Code (#16)
Extract `_load_db_queries()` to shared `QueryTreeService` class.

### 16. Add Type Hints (#17)
Add return type hints to all methods lacking them.

---

## 📊 Implementation Priority Matrix

| Feature | Impact | Effort | Priority | Status |
|---------|--------|--------|----------|--------|
| #18 Constants | High | Low | 1 | ✅ DONE |
| #13 Notes (DB) | Medium | Low | 2 | ✅ DONE |
| #25 SQL View | Very High | Medium | 3 | 🎯 NEXT |
| #15 Change Detection | High | Medium | 4 | 🎯 NEXT |
| #11 Preview Mode | High | Low | 5 | 🎯 NEXT |
| #14 Field Search | High | Low | 6 | 🎯 NEXT |
| #4 Validation | Medium | Low | 7 | 📋 Later |
| #7 Smart Suggestions | Medium | Medium | 8 | 📋 Later |
| #10 Bulk Operations | Medium | Medium | 9 | 📋 Later |
| #1 Recent Queries | Medium | Medium | 10 | 📋 Later |

---

## 🚀 Next Session Goals

**Recommended order for next implementation session:**

1. **SQL View Mode** (2-3 hrs) - Huge value, relatively straightforward
2. **Query Preview** (1-2 hrs) - Safety feature, quick win
3. **Field Search** (2 hrs) - High usability impact
4. **Change Detection** (3-4 hrs) - Important but more complex

**Total: 8-11 hours** for core high-value features.

---

## 📝 Notes

- All features are backwards compatible with existing saved queries
- Constants file is ready to use - just import where needed
- Database migrations run automatically on startup
- Focus on user-facing features first, then code quality

**Generated:** 2025-01-13
**Author:** Claude Code Assistant
