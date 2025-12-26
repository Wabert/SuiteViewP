# FilterTableView Performance Optimization Guide

## Overview
The `FilterTableView` widget provides Excel-style filtering for large datasets (100k+ rows). This document details the critical optimizations required to achieve sub-second performance when opening filter popups with 50,000+ unique values.

## Architecture

### Core Components
1. **PandasTableModel**: Qt model for displaying pandas DataFrames
2. **FilterPopup**: QMenu-based popup for column filtering
3. **FilterTableView**: Main widget combining table view with filter functionality

## Critical Performance Optimizations

### 1. Virtual Rendering with QListView (NOT QListWidget)

**Problem**: Creating 50,000 QListWidgetItem objects takes 2-5 seconds and consumes massive memory.

**Solution**: Use QListView + QStringListModel + QSortFilterProxyModel

```python
# WRONG - Creates 50k widget objects
self.list_widget = QListWidget()
for value in unique_values:  # 50k iterations!
    item = QListWidgetItem(str(value))
    self.list_widget.addItem(item)

# CORRECT - Virtual rendering, only ~30 visible items created
self.string_model = QStringListModel(unique_values)  # ~14ms
self.proxy_model = QSortFilterProxyModel()
self.proxy_model.setSourceModel(self.string_model)
self.list_view = QListView()
self.list_view.setModel(self.proxy_model)  # ~1ms
```

**Impact**: Reduces widget creation from 2000ms to 15ms (130x faster)

### 2. Uniform Item Sizes

**Problem**: Qt calculates height for each of 50k items during scrollbar layout (~2000ms).

**Solution**: Enable uniform item sizes so Qt uses mathematical calculation instead of measuring.

```python
self.list_view.setUniformItemSizes(True)  # CRITICAL!
```

**Impact**: Reduces initial render from 2000ms to <50ms (40x faster)

### 3. Widget-First Model-After Pattern

**Problem**: Adding a QListView with 50k-item model to layout triggers expensive layout calculations (500ms).

**Solution**: Add empty widget to layout first, THEN set the model.

```python
# WRONG - addWidget triggers layout calculation with 50k items
self.list_view.setModel(self.proxy_model)
layout.addWidget(self.list_view)  # 500ms delay!

# CORRECT - Add empty widget, then populate
layout.addWidget(self.list_view)  # <1ms
self.list_view.setModel(self.proxy_model)  # <2ms
```

**Impact**: Reduces layout time from 500ms to <1ms (500x faster)

### 4. No Stylesheets on Large Lists

**Problem**: QListView stylesheets with item selectors are applied to all 50k items (510ms).

**Solution**: Remove stylesheets and use default Qt styling.

```python
# WRONG - 510ms with 50k items
self.list_view.setStyleSheet("""
    QListView::item {
        padding: 2px;
    }
    QListView::item:selected {
        background-color: #3498db;
    }
""")

# CORRECT - Use defaults (instant)
# No stylesheet needed - Qt default styling is perfectly fine
```

**Impact**: Removes 510ms delay entirely

### 5. Vectorized Pandas Operations

**Problem**: `apply(lambda)` on 100k rows is extremely slow.

**Solution**: Use vectorized pandas operations.

```python
# WRONG - 1000ms+
filtered = df[df[column].apply(lambda x: str(x) in selected_values)]

# CORRECT - 50ms
string_col = df[column].fillna("(Blanks)").astype(str)
filtered_indices = string_col.isin(selected_values)
```

**Impact**: 20x faster filtering operations

### 6. Pre-computation and Caching

**Problem**: Converting columns to strings and getting unique values on every filter operation.

**Solution**: Pre-compute string columns and unique values once in `set_dataframe()`.

```python
def set_dataframe(self, df: pd.DataFrame):
    # Pre-compute string versions of all columns (~11 seconds upfront)
    self._string_columns_cache = {}
    for col in df.columns:
        self._string_columns_cache[col] = (
            df[col].fillna("(Blanks)").astype(str)
        )
    
    # Pre-compute unique values for all columns
    self._all_unique_values = {}
    for col in df.columns:
        self._all_unique_values[col] = (
            self._string_columns_cache[col].unique()
        )
```

**Impact**: Filter popup opens in 0.03ms (cached) vs 500ms (computed)

### 7. Index-Based Filtering (Not DataFrame Copies)

**Problem**: Creating filtered DataFrame copies consumes massive memory (90% of RAM).

**Solution**: Store pd.Index objects and use iloc[] for row access.

```python
# WRONG - Creates DataFrame copies
self._filtered_df = self._original_df[mask]
self._display_df = self._filtered_df.head(MAX_ROWS)

# CORRECT - Store indices only
self._filtered_indices = self._original_df.index[mask]
self._display_indices = self._filtered_indices[:MAX_ROWS]

# Access data on-demand
def data(self, index, role):
    row_idx = self._display_indices[index.row()]
    return self._original_df.iloc[row_idx, index.column()]
```

**Impact**: 90% memory reduction, enables 100k+ row datasets

### 8. Background Search with Debouncing

**Problem**: Search filter blocks UI thread.

**Solution**: Use QThread with 300ms debounce.

```python
class SearchWorker(QThread):
    def run(self):
        self.proxy_model.setFilterFixedString(self.search_text)

# Debounce search with QTimer
self._search_timer = QTimer()
self._search_timer.setSingleShot(True)
self._search_timer.timeout.connect(self._execute_search)
self.search_box.textChanged.connect(
    lambda: self._search_timer.start(300)
)
```

**Impact**: Smooth typing experience with instant visual feedback

### 9. Direct Value Emission for Clear Filter

**Problem**: Selecting 50k items in UI to emit "all values" takes 148 seconds.

**Solution**: Emit all values directly without UI selection.

```python
# WRONG - Loops through 50k UI items
def clear_filter(self):
    for i in range(self.list_view.model().rowCount()):
        index = self.list_view.model().index(i, 0)
        self.list_view.selectionModel().select(index, ...)  # 148 seconds!

# CORRECT - Emit values directly
def clear_filter(self):
    all_values_set = set(self.all_unique_values)
    self.filter_changed.emit(self.column_name, all_values_set)  # <1ms
```

**Impact**: Clear filter from 148 seconds to <1ms (148,000x faster)

## Performance Benchmarks

### Before Optimization
- Filter popup open: 5000ms (5 seconds)
- Clear filter: 148,500ms (2.5 minutes!)
- Apply filter: 2000ms
- Memory usage: 8GB for 100k rows

### After All Optimizations
- Filter popup open: 50ms (100x faster)
- Clear filter: <1ms (148,000x faster)
- Apply filter: 50ms (40x faster)
- Memory usage: 800MB (90% reduction)

## Timing Breakdown (50,000 unique values)

```
[FILTER] FilterPopup.__init__ started for TCH_POL_ID with 49875 values
[FILTER]   - Sort 49875 values: 29.46ms
[FILTER]   - QStringListModel created with 49875 items in 16.09ms
[FILTER]   - Proxy model created: 0.73ms
[FILTER]   - QListView created: 0.65ms
[FILTER]   - addWidget(empty list_view) to layout: 0.16ms
[FILTER]   - setModel() called AFTER addWidget: 1.35ms
[FILTER]   - init_ui completed: 48.87ms
[FILTER] TOTAL FilterPopup creation time: 48.49ms
[FILTER] TOTAL time to open filter box: 50.03ms
```

## Implementation Checklist

When implementing FilterTableView from scratch:

- ✅ Use QListView + QStringListModel (NOT QListWidget)
- ✅ Enable `setUniformItemSizes(True)` on QListView
- ✅ Add widget to layout BEFORE setting model
- ✅ Do NOT use stylesheets on QListView with large datasets
- ✅ Pre-compute string columns in set_dataframe()
- ✅ Pre-compute unique values in set_dataframe()
- ✅ Use vectorized pandas operations (isin, fillna, astype)
- ✅ Store indices (pd.Index) not DataFrame copies
- ✅ Implement background search with QThread + debouncing
- ✅ Emit values directly, don't select UI items for bulk operations
- ✅ Add MAX_DISPLAY_ROWS limit with user prompt

## Code Location

Primary implementation: `suiteview/ui/widgets/filter_table_view.py`

Key classes:
- `PandasTableModel` (lines 25-288)
- `FilterPopup` (lines 293-635)
- `FilterTableView` (lines 640-1100)

## Common Pitfalls

### ❌ Using QListWidget instead of QListView
Creates widget objects for every item - extremely slow with 10k+ items.

### ❌ Forgetting setUniformItemSizes(True)
Qt calculates height for each item during layout - adds 2+ seconds.

### ❌ Setting model before adding to layout
Triggers expensive layout calculations with large models.

### ❌ Using item stylesheets
QSS selectors like `QListView::item` are evaluated for every item.

### ❌ DataFrame copies for filtering
Uses massive memory and slows down filter operations.

### ❌ Synchronous search
Blocks UI during typing, poor user experience.

## Testing Performance

Add timing instrumentation:

```python
import time

start = time.perf_counter()
# ... operation ...
end = time.perf_counter()
print(f"Operation took: {(end - start)*1000:.2f}ms")
```

Target benchmarks:
- Filter popup open: <100ms
- Clear filter: <10ms
- Apply filter: <200ms
- Search filter: <50ms per keystroke

## Future Optimizations

Potential improvements not yet implemented:

1. **Lazy sorting**: Sort only visible portion initially
2. **Incremental model loading**: Add items in batches
3. **Native filters**: Push filtering to database query level
4. **Column type detection**: Optimize string conversion based on dtype

## Conclusion

The key insight is that Qt's Model/View architecture with virtual rendering is extremely fast IF you avoid forcing Qt to instantiate widgets or perform expensive calculations. The combination of QListView virtual rendering, uniform item sizes, and proper initialization order achieves 100-500x performance improvements over naive implementations.
