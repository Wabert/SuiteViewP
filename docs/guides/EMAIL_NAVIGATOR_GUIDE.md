# Email Navigator - User Guide

## Overview

The **Email Navigator** is a powerful email management system integrated into SuiteView that helps you browse, search, and organize your Outlook emails and attachments. It provides specialized tools for finding attachments, managing duplicates, and organizing your email data efficiently.

## Getting Started

### Prerequisites

1. **Install pywin32** (required for Outlook integration):
   ```powershell
   pip install pywin32
   ```

2. **Microsoft Outlook** must be installed and configured on your system

3. Launch SuiteView and click the 📧 button in the launcher toolbar

### First Time Setup

1. Click the 📧 **Email Navigator** button in the SuiteView launcher
2. The Email Navigator window will open and check your Outlook connection
3. If connected successfully, you'll see: ✅ Connected to Outlook
4. Click **🔄 Sync Emails + Attachments** to perform initial scan (this may take a few minutes)
5. Once sync is complete, you can launch the specialized tools

---

## Features

### 1. Email Navigator (Main Window)

The main launcher provides access to all email tools and sync functionality.

**Key Features:**
- **Outlook Connection Status**: Real-time connection monitoring
- **Sync Controls**: 
  - Sync Emails Only (faster, metadata only)
  - Sync Emails + Attachments (slower, includes attachment indexing with hash calculation)
- **Last Sync Info**: Shows when data was last updated
- **Tool Launchers**: Quick access to Attachment Manager and Email Browser

**Usage Tips:**
- Run "Sync Emails Only" daily for quick updates
- Run "Sync Emails + Attachments" weekly or when you need to find attachments
- Data is cached locally in SQLite for fast access

---

### 2. Attachment Manager 📎

The **Attachment Manager** is your solution for finding and organizing email attachments across your entire mailbox.

#### Main Features

##### **All Attachments Tab**
A comprehensive grid showing every attachment with these columns:
- **Email Subject**: Double-click to open email in Outlook
- **Sender**: Who sent the email
- **Date**: When the email was received
- **Attachment Name**: Double-click to open the attachment
- **Type**: File extension (.pdf, .xlsx, .jpg, etc.)
- **Size (MB)**: File size

**Built-in Filtering:**
- Use the search box at the top to filter across all columns instantly
- Click column headers to sort
- Use Excel-style column filters (dropdown arrows) for precise filtering

**Actions:**
- **📧 Open Email**: Open selected email in Outlook
- **📎 Open Attachment**: Open attachment with default application
- **👁 Preview**: Quick preview for images (PDF support coming)
- **💾 Copy to Downloads**: Copy selected attachments to your Downloads folder
- **📦 Archive...**: Archive attachments to a custom folder with manifest file

**Multi-Select:**
- Hold Ctrl to select multiple attachments
- Hold Shift to select a range
- Right-click for context menu (future enhancement)

##### **Duplicates Tab**
Automatically detects duplicate attachments by file hash (MD5).

Shows:
- **File Hash**: Unique identifier for the file content
- **Duplicate Count**: How many copies exist
- **Wasted Space (MB)**: Total space consumed by duplicates

**Usage:**
- Identify large duplicate files consuming mailbox space
- Click a row to see details about each duplicate
- Use this to clean up redundant attachments

##### **Timeline Tab**
Visual breakdown of attachment activity over time.

Shows:
- **Date**: Each day with attachments
- **Attachment Count**: Number of attachments received
- **Total Size (MB)**: Data volume for that day

**Usage:**
- Identify periods with heavy attachment activity
- Track attachment trends
- Find date ranges for targeted cleanup

---

### 3. Email Browser 📬

The **Email Browser** provides a traditional 3-panel email interface for browsing and managing emails.

#### Layout

```
┌─────────────────┬────────────────────────┬─────────────────┐
│   📁 Folders    │    Email List          │  📄 Preview     │
│                 │                        │                 │
│ - Inbox (523)   │ Subject | From | Date  │ Email details   │
│ - Sent Items    │ [Email 1]              │ and preview     │
│ - Drafts        │ [Email 2]              │                 │
│ - ...           │ [Email 3]              │                 │
└─────────────────┴────────────────────────┴─────────────────┘
```

#### Features

**Folder Tree (Left Panel):**
- Navigate all Outlook folders
- Shows item count and unread count per folder
- Supports nested folder structure

**Email List (Middle Panel):**
- **Columns**: 
  - 🔵 Unread indicator
  - Subject
  - From
  - Date
  - Size (KB)
  - Attachments count
- **Filtering**: Global search across all columns
- **Sorting**: Click any column header
- **Excel-style filters**: Dropdown on each column

**Toolbar Actions:**
- **📧 Open in Outlook**: Double-click or button to open email
- **✓ Mark Read**: Mark selected emails as read
- **✗ Mark Unread**: Mark selected emails as unread
- **Unread Only**: Checkbox to filter to unread emails only

**Preview Pane (Right Panel):**
- Shows email metadata (from, subject, date, size)
- Displays first 200 characters of email body
- Updates automatically when you select an email

---

## Common Workflows

### Finding a Lost Attachment

1. Open **Email Navigator** → **Attachment Manager**
2. In the search box, type keywords related to the file:
   - File name: "invoice"
   - Sender: "john@company.com"
   - File type: ".xlsx"
3. Results filter instantly
4. Sort by Date to find recent versions
5. Double-click **Attachment Name** to open the file
6. Or double-click **Email Subject** to see the full email context

### Cleaning Up Duplicate Attachments

1. Open **Attachment Manager** → **Duplicates** tab
2. Review the duplicate groups sorted by wasted space
3. Click a row to see all instances in the details list
4. Switch to **All Attachments** tab
5. Search for the filename to see all copies
6. Keep the newest/most relevant, note others for deletion

### Archiving Project Attachments

1. Open **Attachment Manager** → **All Attachments**
2. Use search to filter: "Project Alpha"
3. Select all relevant attachments (Ctrl+Click)
4. Click **📦 Archive...**
5. Choose destination folder
6. A timestamped folder is created with:
   - All selected attachments
   - `_MANIFEST.txt` with email details for each file

### Bulk Copy Attachments to Downloads

1. Search/filter to find the attachments you need
2. Select multiple attachments (Ctrl+Click or Shift+Click)
3. Click **💾 Copy to Downloads**
4. Files are saved to `C:\Users\YourName\Downloads`
5. Filename conflicts are handled automatically (appends `_1`, `_2`, etc.)

### Reviewing Email from Specific Sender

1. Open **Email Browser**
2. Navigate to **Inbox** (or other folder) in the left panel
3. Use the search box to type sender's name or email
4. Email list filters instantly
5. Click an email to preview
6. Double-click to open in Outlook

---

## Tips & Best Practices

### Performance Optimization

- **Sync Strategy**: 
  - Run "Emails Only" sync daily (takes ~30 seconds)
  - Run "Emails + Attachments" weekly (takes 3-5 minutes for 1000 emails)
  
- **Folder Scope**: 
  - Currently scans Inbox only (by design for v1)
  - To scan other folders, add them in a future update
  
- **Cache Management**:
  - Data is stored locally in SQLite
  - No impact on Outlook performance
  - Can work offline once synced

### Search Tips

- **Wildcards**: Not needed - search is substring-based
- **Multiple terms**: Space-separated terms are AND-ed
- **Column filters**: Use Excel-style filters for precise filtering
- **Case-insensitive**: All searches ignore case

### Data Privacy

- **Local Storage**: All data cached locally on your machine
- **No Cloud**: Nothing sent to external servers
- **Outlook Integration**: Read-only except for mark read/unread operations
- **Security**: Uses Windows Credential Manager for any stored credentials

---

## Architecture Overview

For developers or advanced users:

### Components

1. **OutlookManager** (`suiteview/core/outlook_manager.py`)
   - COM integration with Outlook via win32com
   - Provides email and attachment access
   - Handles open, save, mark read/unread operations

2. **EmailRepository** (`suiteview/data/repositories.py`)
   - SQLite-based local cache
   - Tables: `emails`, `email_attachments`, `email_sync_status`
   - Indexes for fast querying

3. **EmailNavigatorWindow** (`suiteview/ui/email_navigator_window.py`)
   - Main launcher window
   - Background sync thread
   - Progress tracking

4. **EmailAttachmentManager** (`suiteview/ui/email_attachment_manager.py`)
   - 3-tab interface for attachment management
   - Uses FilterTableView for grids
   - Image preview support

5. **EmailBrowserWindow** (`suiteview/ui/email_browser_window.py`)
   - 3-panel email browser
   - Folder tree navigation
   - Email preview pane

### Data Flow

```
Outlook (via COM)
     ↓
OutlookManager (read emails/attachments)
     ↓
EmailRepository (cache locally in SQLite)
     ↓
UI Components (FilterTableView grids)
     ↓
User Actions → OutlookManager → Outlook
```

### Database Schema

**emails table:**
- email_id (primary key, Outlook EntryID)
- subject, sender, sender_email
- received_date, size
- unread, has_attachments, attachment_count
- folder_path, body_preview
- last_synced

**email_attachments table:**
- attachment_id (auto-increment)
- email_id (foreign key)
- email_subject, email_sender, email_date
- attachment_name, attachment_type, attachment_size
- attachment_index (position in email)
- file_hash (MD5 for duplicate detection)
- last_synced

**email_sync_status table:**
- sync_id (auto-increment)
- folder_path (unique)
- last_sync_time
- email_count, attachment_count
- scan_complete (boolean)

---

## Troubleshooting

### "Not connected to Outlook"

**Causes:**
- Outlook not installed
- pywin32 not installed
- Outlook not running (some systems require it)

**Solutions:**
1. Install pywin32: `pip install pywin32`
2. Ensure Outlook is installed and configured
3. Try starting Outlook first, then Email Navigator
4. Check Windows Event Viewer for COM errors

### "No attachments found"

**Causes:**
- Haven't run sync yet
- Inbox has no attachments
- Sync failed silently

**Solutions:**
1. Run "Sync Emails + Attachments" from main window
2. Check status label for error messages
3. Verify Inbox has emails with attachments in Outlook

### Sync is slow

**Normal:**
- First sync with 1000+ emails takes 3-5 minutes
- Hash calculation adds ~50% overhead
- Large attachments take longer to process

**Optimization:**
- Close other applications
- Run "Emails Only" sync for quick updates
- Only run full attachment sync when needed

### Double-click doesn't open email/attachment

**Causes:**
- Email has been deleted/moved in Outlook
- Outlook COM permissions issue

**Solutions:**
1. Refresh/re-sync the folder
2. Try "Open Email" button instead
3. Restart Outlook and try again

---

## Future Enhancements (Planned)

Based on your requirements and architecture, here are planned features:

### Attachment Management
- [ ] PDF preview support (in addition to images)
- [ ] Video thumbnail preview
- [ ] Attachment extraction to organized folder structure
- [ ] Auto-delete duplicate attachments (with confirmation)
- [ ] Attachment rename/move operations
- [ ] Export attachment list to CSV/Excel

### Email Management
- [ ] Advanced search with regex support
- [ ] Email thread visualization
- [ ] Bulk operations (delete, move, categorize)
- [ ] Custom tagging system
- [ ] Email templates
- [ ] Scheduled reminders
- [ ] Rules engine for auto-organization

### Sync & Performance
- [ ] Multiple folder scanning (select which folders to index)
- [ ] Incremental sync (only new/changed emails)
- [ ] Background auto-sync on schedule
- [ ] Progress bar with ETA
- [ ] Pause/resume sync capability

### Analytics
- [ ] Sender statistics (top senders, email volume)
- [ ] Email volume trends over time
- [ ] Attachment type distribution charts
- [ ] Response time analytics
- [ ] Custom reports

---

## Keyboard Shortcuts (Future)

Planned shortcuts for power users:

- `Ctrl+F`: Focus search box
- `Ctrl+R`: Refresh current view
- `Enter`: Open selected email
- `Ctrl+Enter`: Open selected attachment
- `Delete`: Mark for cleanup (with confirmation)
- `Ctrl+A`: Select all
- `Ctrl+C`: Copy selected (for export)

---

## Support & Feedback

This is version 1.0 of the Email Navigator feature. As you use it, you'll discover additional needs and improvements.

**How to provide feedback:**
1. Document the workflow you're trying to accomplish
2. Note any pain points or missing features
3. Share examples of searches that didn't work well
4. Suggest improvements to the UI/UX

The system is designed to be extensible, so new features can be added incrementally based on your real-world usage patterns.

---

## Technical Notes

### Dependencies
- PyQt6 (UI framework)
- pandas (data manipulation)
- pywin32 (Outlook COM integration)
- SQLite (built into Python, no additional install)

### File Locations
- **Cache Database**: `%LOCALAPPDATA%\suiteview\suiteview.db`
- **Temp Previews**: `%TEMP%\SuiteView_Email_Previews\`
- **Settings**: `%USERPROFILE%\.suiteview\launcher_settings.json`

### Performance Stats
Based on typical mailbox (approximate):

| Operation | Emails | Time |
|-----------|--------|------|
| Sync Emails Only | 1000 | 30-45 sec |
| Sync with Attachments | 1000 | 3-5 min |
| Sync with Hashing | 1000 | 5-8 min |
| Search/Filter | Any | Instant |
| Load Attachment Grid | 5000 | < 1 sec |

### Limitations (v1.0)
- Scans Inbox only (additional folders require code change)
- Preview supports images only (PDF planned)
- No Exchange Online / Office 365 support (desktop Outlook only)
- Windows only (uses win32com and os.startfile)

---

**Ready to get started?** Click the 📧 button in your SuiteView launcher and run your first sync!
