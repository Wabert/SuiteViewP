# File Explorer V3 - Features & Usage

## Overview
File Explorer V3 uses a custom tree model that shows OneDrive at the top level, just like Windows File Explorer's Quick Access.

## Key Features

### ⭐ Quick Access Section
- **OneDrive folders** appear at the very top (no more buried in C:\Users\...)
- **Deduplicated** - No duplicate OneDrive entries
- **Custom Quick Links** - Add any file or folder to Quick Access

### 💾 System Drives
- All drives (C:\, D:\, etc.) shown below Quick Access
- Standard file system browsing
- Lazy loading for performance

### 📌 Custom Quick Links
**How to add items to Quick Access:**
1. Right-click on any file or folder
2. Select "⭐ Add to Quick Access"
3. Item appears at the top with a 📌 icon

**How to remove items:**
1. Right-click on a Quick Access item (marked with 📌)
2. Select "❌ Remove from Quick Access"

**Persistence:**
- Quick links are saved to: `~/.suiteview/quick_links.json`
- Automatically loaded on startup
- Survive app restarts

### 🛠️ File Operations
- **Cut** (✂️) - Move files/folders
- **Copy** (📋) - Duplicate files/folders
- **Paste** (📌) - Paste cut/copied items
- **Rename** (✏️) - Rename files/folders
- **Delete** (🗑️) - Delete files/folders
- **Open in Explorer** (📂) - Open location in Windows Explorer

### 📄 File Preview
- Preview text files in the right panel
- Shows file content for supported types
- **Upload to Mainframe** button (ready for integration)

### 🎨 Visual Features
- **Icons:**
  - ⭐ OneDrive folders
  - 📌 Custom quick links (folders)
  - 📄 Custom quick links (files)
  - 💾 System drives
  - 📁 Regular folders
  - 📄 Text files
  - 🖼️ Images
  - 📦 Archives
  - ⚙️ Executables

- **Columns:**
  - Name (300px, adjustable)
  - Size (100px, adjustable)
  - Type (120px, adjustable)
  - Date Modified (150px, adjustable)

## Comparison: V2 vs V3

### File Explorer V2 (QFileSystemModel)
- ❌ OneDrive buried in C:\Users\username\
- ✅ Efficient lazy loading
- ❌ Cannot customize root structure
- ❌ No quick links support

### File Explorer V3 (Custom Model) ⭐
- ✅ OneDrive at top level
- ✅ Efficient lazy loading
- ✅ Fully customizable structure
- ✅ Custom quick links support
- ✅ Deduplicated entries

## Testing

```bash
# Standalone test
python test_file_explorer_v3.py

# Within SuiteView (after integration)
python -m suiteview.main
```

## Technical Details

### Architecture
- **Model:** `QStandardItemModel` (custom tree structure)
- **View:** `QTreeView` (with custom icons and formatting)
- **Lazy Loading:** Folders load children only when expanded
- **Persistence:** JSON file for quick links (~/.suiteview/quick_links.json)

### OneDrive Detection
1. Checks environment variables: `OneDrive`, `OneDriveCommercial`, `OneDriveConsumer`
2. Checks common paths: `~/OneDrive`, `~/OneDrive - Company Name`
3. Resolves to absolute paths and deduplicates
4. Shows only unique OneDrive folders

### Data Storage
```json
// ~/.suiteview/quick_links.json
[
  "C:\\Users\\username\\Documents\\Project1",
  "C:\\Users\\username\\OneDrive\\ImportantFiles",
  "D:\\Data\\Analysis"
]
```

## Next Steps

### Integration with SuiteView
Update `suiteview/ui/main_window.py`:
```python
from suiteview.ui.file_explorer_v3 import FileExplorerV3

# Replace file_explorer_v2 with file_explorer_v3
self.file_explorer = FileExplorerV3()
self.tab_widget.addTab(self.file_explorer, "📂 File Explorer")
```

### Future Enhancements
- [ ] Drag-and-drop to add quick links
- [ ] Reorder quick links
- [ ] Quick link categories/groups
- [ ] Search within file explorer
- [ ] File type filters
- [ ] Bookmarks/favorites syncing
- [ ] Integration with mainframe upload

## Known Issues
- Font warnings (harmless, Qt-related)
- Large directories may take a moment to load first time

## Credits
- Based on PyQt-File-Explorer by proaddy (MIT License)
- Enhanced with custom model for Quick Access functionality
- Adapted for SuiteView integration
