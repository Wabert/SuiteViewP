# Shortcuts Feature - Quick Start Guide

## 🚀 Getting Started in 3 Steps

### Step 1: Open Shortcuts
Click the **📌 Shortcuts** button in the toolbar (top-left, first button)

### Step 2: Create a Category
1. Click **+ Category**
2. Enter name (e.g., "Work Files", "Personal", "Projects")
3. Click OK

### Step 3: Add Links
**Method A - Using the "+ Link" button:**
1. Click **+ Link** in Shortcuts dialog
2. Fill in:
   - Name: "My Report"
   - Path/URL: `C:\Users\Documents\report.xlsx`
   - Category: Select from dropdown
3. Click Save

**Method B - Right-click (Easiest!):**
1. Navigate to any folder/file in File Explorer
2. Right-click it
3. Select **⭐ Add to Shortcuts**
4. Choose category
5. Done!

---

## 📌 What Can You Add?

### ✅ Folders
- `C:\Users\Documents\Projects`
- `\\server\shared\department`

### ✅ Files  
- `C:\Reports\Q4_Report.xlsx`
- `C:\Documents\Meeting_Notes.docx`

### ✅ Web URLs
- `https://google.com`
- `https://github.com`

### ✅ SharePoint Sites
- `https://company.sharepoint.com/sites/team`
- `https://company.sharepoint.com/Shared Documents`

---

## 💡 Usage Tips

### Tip 1: Organize by Project
```
📁 Project Alpha
   📁 Source Code
   📄 Specification.docx
   🔗 Team SharePoint
   🌐 Project Wiki

📁 Project Beta
   📁 Design Files
   📄 Budget.xlsx
   🔗 Client Portal
```

### Tip 2: Keep Related Resources Together
Create categories like:
- **Daily Tasks** - Files you access every day
- **Templates** - Document templates you reuse
- **References** - Documentation and guides
- **Team Resources** - SharePoint sites and shared drives

### Tip 3: Use Descriptive Names
❌ Bad: "Document1", "Link", "Folder"  
✅ Good: "Q4 Sales Report", "Team SharePoint", "Project Files"

---

## 🎯 Common Workflows

### Workflow: Accessing Shared Drives
1. Click Shortcuts button
2. Create "Network Shares" category
3. Right-click network folder in tree view
4. Add to Shortcuts → Select "Network Shares"
5. Next time: Click shortcut to open instantly!

### Workflow: Frequently Edited Files
1. Create "Active Documents" category
2. As you work on files, right-click → Add to Shortcuts
3. Access any active document with one click
4. Remove when project is complete

### Workflow: SharePoint Organization
1. Create categories for each team/project
2. Use "+ Link" to add SharePoint URLs
3. Add both site URLs and direct document library links
4. Access all team resources from one place

---

## 🔧 Managing Your Shortcuts

### To Remove a Shortcut:
1. Open Shortcuts dialog
2. Right-click the shortcut button
3. Select "🗑️ Remove from Shortcuts"

### To Remove a Category:
1. Open Shortcuts dialog
2. Click the **✕** button on category header
3. Confirm deletion (all shortcuts in category are removed)

### To Reorganize:
- You can add shortcuts to different categories
- Create new categories as your needs change
- Remove outdated categories and shortcuts

---

## ⚡ Quick Reference

| Action | How To |
|--------|--------|
| Open Shortcuts | Click **📌 Shortcuts** in toolbar |
| Add Category | Click **+ Category** in dialog |
| Add Link Manually | Click **+ Link** in dialog |
| Add from Context Menu | Right-click → **⭐ Add to Shortcuts** |
| Open Shortcut | Click the shortcut button |
| Remove Shortcut | Right-click → **🗑️ Remove from Shortcuts** |
| Remove Category | Click **✕** on category header |

---

## 📂 Where Are Shortcuts Stored?

Your shortcuts are saved in:
```
C:\Users\YourName\.suiteview\shortcuts.json
```

This file persists between sessions, so your shortcuts are always available!

---

## 🆚 Shortcuts vs Quick Links

**Use Quick Links when:**
- You need instant access (always visible in tree)
- You navigate to the folder frequently
- It's a folder (not files or URLs)

**Use Shortcuts when:**
- You want organized categories
- You need to save files, URLs, or SharePoint links
- You have many items to organize
- You want to keep the tree view uncluttered

**Pro Tip:** Use both! Quick Links for your top 3-5 folders, Shortcuts for everything else!

---

## 🎨 Visual Guide

### Toolbar with Shortcuts Button:
```
┌─────────────────────────────────────────────┐
│ [📌 Shortcuts] │ [🔄 Refresh] [📂 Open...] │
└─────────────────────────────────────────────┘
```

### Shortcuts Dialog Layout:
```
┌──────────────────────────────────────────────┐
│ 📌 Shortcuts          [+ Category] [+ Link]  │
├──────────────────────────────────────────────┤
│ ┌─ Work Files ────────────────────────── ✕  │
│ │  [📁 Current Project]  [📄 Status.xlsx]   │
│ │  [🔗 Team SharePoint]                      │
│ └────────────────────────────────────────── │
│                                               │
│ ┌─ References ────────────────────────── ✕  │
│ │  [🌐 Python Docs]  [🌐 Stack Overflow]   │
│ └────────────────────────────────────────── │
│                                               │
│                                    [Close]    │
└──────────────────────────────────────────────┘
```

### Context Menu with Add to Shortcuts:
```
Right-click any file/folder:
┌──────────────────────────┐
│ 📄 Open                  │
│ ───────────────────────  │
│ ✂️ Cut                   │
│ 📋 Copy                  │
│ ───────────────────────  │
│ 📌 Add to Quick Links    │
│ ⭐ Add to Shortcuts  ← ! │
│ ───────────────────────  │
│ 🔄 Refresh               │
└──────────────────────────┘
```

---

## 🎉 You're Ready!

Start organizing your resources with Shortcuts today:
1. Click **📌 Shortcuts**
2. Create your first category
3. Add some shortcuts
4. Enjoy organized access to all your resources!

**Happy organizing! 🚀**
