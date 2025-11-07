# Enhanced File Explorer V2

## Overview
This is an enhanced file explorer based on the excellent **PyQt-File-Explorer** by proaddy (MIT License).
We've adapted it from PySide6 to PyQt6 for integration with SuiteView.

## Original Source
- **GitHub:** https://github.com/proaddy/PyQT-File-Explorer
- **License:** MIT License
- **Author:** Adarsh Vishwakarma (proaddy)

## Features

### Core Features (from proaddy's implementation)
- ✅ **Tree View** - Uses QFileSystemModel for efficient file browsing
- ✅ **Cut, Copy, Paste** - Full clipboard support with Ctrl+X, Ctrl+C, Ctrl+V
- ✅ **Rename** - Press F2 or use context menu to rename files/folders
- ✅ **Open in Explorer** - Quickly open the selected file/folder in Windows Explorer
- ✅ **Context Menu** - Right-click for quick access to operations
- ✅ **Keyboard Shortcuts** - Standard Windows shortcuts work

### SuiteView Enhancements
- 📤 **File Preview Pane** - Preview text files before uploading
- 📤 **Mainframe Upload** - Upload files to mainframe (in progress)
- 🎨 **Styled UI** - Matches SuiteView's visual design
- 🔄 **Refresh (F5)** - Reload file system view

## How to Use

### In SuiteView
1. Launch SuiteView
2. Click on the **"📂 File Explorer"** tab
3. Browse your file system
4. Use the toolbar or context menu for operations

### Standalone Test
Run the test script:
```bash
python test_file_explorer_v2.py
```

## Keyboard Shortcuts
- **Ctrl+C** - Copy selected file/folder
- **Ctrl+X** - Cut selected file/folder
- **Ctrl+V** - Paste to selected directory
- **F2** - Rename selected item
- **F5** - Refresh view
- **Right-click** - Show context menu

## Operations

### Cut/Copy/Paste
1. Select a file or folder
2. Press Ctrl+C (copy) or Ctrl+X (cut)
3. Navigate to destination folder
4. Select the destination folder
5. Press Ctrl+V to paste

### Rename
1. Select a file or folder
2. Press F2 or use context menu
3. Enter new name
4. Press OK

### Delete
1. Select a file or folder
2. Right-click → Delete
3. Confirm deletion

### Open in Explorer
1. Select a file or folder
2. Click "📂 Open in Explorer" button
3. Windows Explorer will open with the item selected

## Technical Details

### Key Components
- **QFileSystemModel** - Efficient model for file system data
- **QTreeView** - Tree view widget for displaying files/folders
- **Clipboard Operations** - Uses dictionary to store cut/copy operations
- **OS Integration** - Uses subprocess for Explorer integration

### File Structure
```
suiteview/ui/
  ├── file_explorer_v2.py      # New enhanced explorer
  └── file_explorer_screen.py  # Original basic explorer
```

## Credits
- **Original Implementation:** proaddy (https://github.com/proaddy)
- **Adaptation:** SuiteView Team
- **License:** MIT License (allows free use, modification, and distribution)

## Future Enhancements
- [ ] Multiple file selection
- [ ] Drag and drop
- [ ] Advanced search
- [ ] Custom thumbnails for images
- [ ] Archive operations (zip/unzip)
- [ ] FTP integration for mainframe
