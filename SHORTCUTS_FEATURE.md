# Shortcuts Feature Documentation

## Overview
The Shortcuts feature provides a browser-like bookmarks system for the File Explorer, allowing users to save quick access links to folders, files, SharePoint sites, and web URLs organized by custom categories.

## Features

### 1. **Shortcuts Button**
- Located prominently at the start of the File Explorer toolbar
- Icon: 📌 Shortcuts
- Click to open the Shortcuts panel dialog

### 2. **Shortcuts Panel Dialog**
A comprehensive dialog with the following capabilities:

#### Main Components:
- **+ Category Button**: Add new custom categories
- **+ Link Button**: Add new shortcuts
- **Category Panels**: Display shortcuts organized by category
- **Close Button**: Close the dialog

#### Built-in Categories:
- **General**: Default category for miscellaneous shortcuts
- **Favorites**: For frequently accessed items

### 3. **Category Management**

#### Adding Categories:
1. Click the "+ Category" button
2. Enter a category name
3. The new category panel appears immediately

#### Removing Categories:
1. Click the "✕" button on any custom category panel header
2. Confirm deletion (built-in categories like "General" and "Favorites" cannot be removed)
3. All shortcuts in that category are deleted

### 4. **Shortcut Management**

#### Adding Shortcuts Manually:
1. Click the "+ Link" button in the Shortcuts dialog
2. Fill in the Add Shortcut form:
   - **Name**: Display name for the shortcut
   - **Path/URL**: File path, folder path, URL, or SharePoint link
   - **Category**: Select from existing categories
3. Click "Save"

#### Adding Shortcuts via Context Menu:
**From Tree View (Left Panel):**
- Right-click any folder
- Select "⭐ Add to Shortcuts"
- Choose a category from the dropdown
- Shortcut is added automatically

**From Details View (Right Panel):**
- Right-click any file or folder
- Select "⭐ Add to Shortcuts"
- Choose a category from the dropdown
- Shortcut is added automatically

#### Removing Shortcuts:
1. Right-click any shortcut button in the Shortcuts panel
2. Select "🗑️ Remove from Shortcuts"
3. The shortcut is immediately removed

### 5. **Shortcut Types**

The system automatically detects and categorizes shortcuts:

| Type | Icon | Description | Example |
|------|------|-------------|---------|
| **Folder** | 📁 | Directory path | `C:\Users\Documents` |
| **File** | 📄 | File path | `C:\report.xlsx` |
| **URL** | 🌐 | Web URL | `https://google.com` |
| **SharePoint** | 🔗 | SharePoint link | `https://company.sharepoint.com/...` |
| **Path** | 📍 | Network or other path | `\\network\share` |

### 6. **Opening Shortcuts**

Click any shortcut button to open it:
- **Folders**: Opens in File Explorer
- **Files**: Opens with default application
- **URLs**: Opens in default web browser
- **SharePoint**: Opens in default web browser

### 7. **Data Storage**

Shortcuts are stored in JSON format:
- **Location**: `~/.suiteview/shortcuts.json`
- **Format**:
```json
{
  "categories": {
    "General": [
      {
        "name": "My Documents",
        "path": "C:\\Users\\Documents",
        "type": "folder",
        "category": "General"
      }
    ],
    "Favorites": [],
    "Work Projects": [
      {
        "name": "SharePoint Site",
        "path": "https://company.sharepoint.com/site",
        "type": "sharepoint",
        "category": "Work Projects"
      }
    ]
  }
}
```

## User Workflows

### Workflow 1: Organize Project Links
1. Click "📌 Shortcuts" in toolbar
2. Click "+ Category" and create "Current Project"
3. Navigate to project folder in File Explorer
4. Right-click folder → "⭐ Add to Shortcuts"
5. Select "Current Project" category
6. Add related SharePoint site via "+ Link" button
7. All project resources now accessible from one category

### Workflow 2: Quick Access to Documents
1. Open Shortcuts dialog
2. Add shortcuts to frequently used documents
3. Organize by type (Reports, Invoices, Templates)
4. Click shortcuts to open documents instantly

### Workflow 3: Web Resources
1. Use "+ Link" to add web URLs
2. Create categories like "Tools", "Documentation", "References"
3. Add SharePoint sites, internal portals, external resources
4. Access directly from File Explorer

## UI Layout

```
┌─────────────────────────────────────────────────────┐
│  📌 Shortcuts                            [Dialog]    │
├─────────────────────────────────────────────────────┤
│  [+ Category]  [+ Link]                              │
├─────────────────────────────────────────────────────┤
│  ┌─ General ─────────────────────────────────── ✕   │
│  │ [📁 My Documents]  [📄 Report.xlsx]              │
│  └─────────────────────────────────────────────────┤
│  ┌─ Favorites ────────────────────────────────── ✕  │
│  │ [🌐 Google]  [🔗 SharePoint]                    │
│  └─────────────────────────────────────────────────┤
│  ┌─ Work Projects ────────────────────────────── ✕  │
│  │ [📁 Project Folder]  [🔗 Team Site]             │
│  └─────────────────────────────────────────────────┤
│                                                      │
│                                          [Close]     │
└─────────────────────────────────────────────────────┘
```

## Context Menu Integration

### Tree View Context Menu:
```
📂 Open in File Explorer
──────────────────────
📌 Add to Quick Links
⭐ Add to Shortcuts    ← NEW
──────────────────────
🔄 Refresh
```

### Details View Context Menu:
```
📄 Open
──────────────────────
✂️ Cut
📋 Copy
──────────────────────
✏️ Rename
🗑️ Delete
──────────────────────
📌 Add to Quick Links
⭐ Add to Shortcuts    ← NEW
──────────────────────
⬆️ Upload to Mainframe
```

## Technical Details

### Files Modified:
1. **suiteview/ui/file_explorer_v3.py**
   - Added Shortcuts button to toolbar
   - Added "Add to Shortcuts" to context menus
   - Implemented `open_shortcuts_dialog()` method
   - Implemented `add_to_shortcuts()` method
   - Implemented `add_to_quick_links()` method (for standalone use)

2. **suiteview/ui/dialogs/shortcuts_dialog.py** (NEW)
   - `ShortcutsDialog`: Main dialog class
   - `CategoryPanel`: Individual category display
   - `ShortcutButton`: Individual shortcut button
   - `AddShortcutDialog`: Dialog for adding new shortcuts

### Dependencies:
- PyQt6 (QDialog, QVBoxLayout, QHBoxLayout, etc.)
- Standard library: os, sys, json, subprocess, webbrowser, pathlib

## Comparison with Quick Links

| Feature | Quick Links | Shortcuts |
|---------|-------------|-----------|
| **Location** | Left tree panel | Separate dialog |
| **Organization** | Flat list at top | Categorized panels |
| **Item Types** | Folders only | Folders, files, URLs, SharePoint |
| **Visibility** | Always visible | On-demand dialog |
| **Use Case** | Fast folder navigation | Organized resource library |
| **Capacity** | Limited by panel height | Unlimited scrollable |
| **Categories** | None | User-defined |

## Best Practices

1. **Keep Quick Links for Frequent Folders**: Use Quick Links for your most-accessed folders that you navigate to constantly
2. **Use Shortcuts for Everything Else**: Use Shortcuts for files, URLs, and less-frequently accessed folders
3. **Create Meaningful Categories**: Organize by project, type, or department
4. **Regular Maintenance**: Remove outdated shortcuts and categories
5. **Descriptive Names**: Use clear, descriptive names for shortcuts

## Future Enhancements (Potential)

- [ ] Drag-and-drop to reorder shortcuts within categories
- [ ] Export/import shortcuts configuration
- [ ] Shortcut icons based on file type
- [ ] Search/filter shortcuts
- [ ] Recent shortcuts history
- [ ] Keyboard shortcuts to open Shortcuts panel
- [ ] Pin shortcuts to toolbar
- [ ] Sync shortcuts across machines

## Troubleshooting

### Shortcuts Not Saving
- Check file permissions for `~/.suiteview/` directory
- Ensure JSON file is not corrupted
- Check application logs for errors

### Shortcut Won't Open
- Verify the path/URL is still valid
- Check file/folder still exists
- Ensure proper permissions for network paths
- Verify SharePoint URLs are accessible

### Missing Shortcuts Button
- Ensure using FileExplorerV3 or FileExplorerV4
- Check toolbar initialization code
- Verify shortcuts_dialog.py is in dialogs folder
