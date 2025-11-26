# Bookmarks Feature Documentation

## Overview

The Bookmarks feature provides a browser-like bookmarks system for the File Explorer, allowing users to save quick access links to folders, files, SharePoint sites, and web URLs organized by custom categories.

## Features

### 1. Bookmarks Button
- **Location**: First button in the File Explorer toolbar
- **Icon**: 📌 Bookmarks
- **Action**: Opens the compact Bookmarks panel

### 2. Bookmarks Panel

A compact, vertical popup panel with:
- **Width**: 250px (narrow vertical panel)
- **Height**: 600px (scrollable)
- **Style**: Frameless popup window with blue header
- **Auto-close**: Closes when clicking a bookmark or clicking outside

#### Panel Layout
```
┌────────────────────┐
│ 📌 Bookmarks [+][🔗]│ ← Blue header
├────────────────────┤
│┌─ General ────── ✕│
││ [📁 Documents]    │
││ [📁 Downloads]    │
│└──────────────────┘│
│┌─ Work ────────  ✕│
││ [📄 Report.xlsx]  │
││ [🔗 SharePoint]   │
│└──────────────────┘│
│                    │ ← Auto-scrolls
└────────────────────┘
```

### 3. Category Management

**Adding Categories:**
1. Click the "+" button in the header
2. Enter a category name
3. New category panel appears

**Removing Categories:**
1. Click the "✕" button on category header
2. Confirm deletion (all bookmarks in category are deleted)

**Built-in Categories:**
- General (protected from deletion)
- Favorites (protected from deletion)

### 4. Bookmark Types

| Type | Icon | Description | Example |
|------|------|-------------|---------|
| Folder | 📁 | Directory path | `C:\Users\Documents` |
| File | 📄 | File path | `C:\report.xlsx` |
| URL | 🌐 | Web URL | `https://google.com` |
| SharePoint | 🔗 | SharePoint link | `https://company.sharepoint.com/...` |
| Path | 📍 | Network or other path | `\\network\share` |

### 5. Adding Bookmarks

**Method 1: Manual Entry (+ Link button)**
1. Click "🔗" button in header
2. Fill in Name, Path/URL, and Category
3. Click Save

**Method 2: Context Menu (Easiest)**
1. Right-click any file/folder in File Explorer
2. Select "⭐ Add to Bookmarks"
3. Choose category from dropdown
4. Bookmark added automatically

### 6. Using Bookmarks

- **Click** any bookmark button to open it
- **Hover** for tooltip showing full path
- **Right-click** for "Remove from Bookmarks" option

Opening behavior:
- **Folders**: Opens in File Explorer
- **Files**: Opens with default application
- **URLs/SharePoint**: Opens in default web browser

## Data Storage

Bookmarks are stored in JSON format:
- **Location**: `~/.suiteview/bookmarks.json`
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
    "Work": [
      {
        "name": "Team SharePoint",
        "path": "https://company.sharepoint.com/site",
        "type": "sharepoint",
        "category": "Work"
      }
    ]
  }
}
```

## Auto-Close Behavior

**Closes When:**
- User clicks any bookmark
- User clicks outside the panel
- Panel loses focus

**Stays Open When:**
- User clicks "+" (add category)
- User clicks "🔗" (add bookmark)
- User right-clicks a bookmark
- User clicks "✕" (remove category)

## Quick Reference

| Action | How To |
|--------|--------|
| Open Bookmarks | Click **📌 Bookmarks** in toolbar |
| Add Category | Click **+** in header |
| Add Bookmark Manually | Click **🔗** in header |
| Add from Context Menu | Right-click → **⭐ Add to Bookmarks** |
| Open a Bookmark | Click the bookmark button |
| Remove Bookmark | Right-click bookmark → **🗑️ Remove** |
| Remove Category | Click **✕** on category header |

## Technical Details

### Files
- **Dialog**: `suiteview/ui/dialogs/shortcuts_dialog.py` (contains BookmarksDialog class)
- **Integration**: `suiteview/ui/file_explorer_core.py`

### Window Flags
```python
Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
```
- **Popup**: Enables click-outside-to-close
- **FramelessWindowHint**: Removes title bar and borders

## Tips

1. **Use Quick Links for frequent folders** - Always visible in tree panel
2. **Use Bookmarks for everything else** - Files, URLs, SharePoint, less-frequent folders
3. **Create meaningful categories** - Organize by project, type, or frequency
4. **Use descriptive names** - "Q4 Sales Report" not "Document1"
