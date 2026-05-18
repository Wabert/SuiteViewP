# TaskTracker — Developer Specification for SuiteView Integration

**Version:** 1.0  
**Date:** February 8, 2026  
**Author:** Robert (Business Analyst Manager)  
**Target Developer:** Claude Opus 4.6 (Claude Code / VS Code)  
**Target Platform:** Windows 11, Python, SuiteView Desktop App

---

## 1. Project Context

### 1.1 What is SuiteView?

SuiteView is an existing Python desktop application that runs as a custom taskbar on Windows 11. It sits above the Windows taskbar, adjusts the desktop working area, and provides quick-access tools for a business analyst team at a life insurance company.

**Current SuiteView tech stack:**
- Python 3.x
- tkinter (primary UI framework — the app originally used tkinter; some modules may use PyQt6)
- ctypes for Windows API integration (SystemParametersInfo for desktop work area adjustment)
- SQLite for internal data storage
- JSON config files stored in `~/.suiteview/`
- pyodbc for DB2 database connectivity
- openpyxl/pandas for Excel integration

**SuiteView project location:** The project lives on the developer's machine. Before starting, the AI developer should ask Robert for the current project path and inspect the existing folder structure to understand where to add the TaskTracker module.

### 1.2 What is TaskTracker?

TaskTracker is a new feature/module being added to SuiteView. It is a lightweight task management tool designed for a manager overseeing 7 business analysts. Its core purpose is to:

1. Rapidly capture tasks with auto-generated IDs
2. Assign tasks to one or more team members
3. Send task emails through Outlook with trackable subject lines
4. Monitor Outlook inbox/outbox for replies matching task IDs
5. Provide an email thread view per task
6. Give visual indicators when a team member has replied and action is needed

TaskTracker is intentionally minimal — no priority levels, no due dates, no Gantt charts. It is designed for speed and low friction.

---

## 2. Data Model

### 2.1 Task Schema

```python
class Task:
    id: str              # Auto-generated, format "TSK-001", "TSK-002", etc.
    title: str           # Free-text description (the task itself)
    status: str          # "open" or "closed"
    created_date: str    # ISO format date string "YYYY-MM-DD"
    assignees: list      # List of dicts: [{"name": str, "email": str}, ...]
    email_sent: bool     # Whether initial task email has been sent
    last_activity: str   # Human-readable timestamp ("2h ago", "1d ago", etc.)
    last_activity_sort: float  # Numeric value for sorting (hours since activity)
    last_activity_from: str    # Name of person who last acted ("You" or assignee name)
    emails: list         # List of Email objects associated with this task
```

### 2.2 Email Schema

```python
class Email:
    from_addr: str       # Sender display name ("You" or person name)
    to_addr: str         # Recipient email address
    date: str            # Human-readable date ("Feb 3, 2:15 PM")
    date_sort: float     # Numeric for sorting (e.g., 20260203.1415)
    subject: str         # Email subject line (includes [TSK-XXX] prefix)
    body: str            # Email body text (plain text)
    type: str            # "sent" or "received"
    has_attachment: bool  # Whether the email has attachments (display only, don't store files)
```

### 2.3 Contact Schema

```python
class Contact:
    name: str            # Display name ("John Martinez")
    email: str           # Email address ("john.martinez@company.com")
```

### 2.4 Storage

Use SQLite for persistent storage. Store tasks, emails, and contacts in separate tables. The database file should live in the SuiteView config directory (e.g., `~/.suiteview/tasktracker.db`).

**Pre-loaded contacts (Robert's team of 7):**
- John Martinez — john.martinez@company.com
- Sarah Chen — sarah.chen@company.com
- Mike Thompson — mike.thompson@company.com
- Lisa Patel — lisa.patel@company.com
- David Kim — david.kim@company.com
- Rachel Woods — rachel.woods@company.com
- James Taylor — james.taylor@company.com

These should be seed data. Users can add more contacts dynamically.

---

## 3. UI Layout Specification

The TaskTracker window is a two-panel layout: a task list on the left and a detail panel on the right. The detail panel appears when a task is clicked and can be resized.

### 3.1 Color Palette

| Token | Hex | Usage |
|-------|-----|-------|
| `blue` | `#1a3a7a` | Primary brand, header gradient start, text accents |
| `blueLight` | `#2a4fa0` | Header gradient end |
| `bluePale` | `#e8edf6` | Filter bar background, column headers |
| `blueListBg` | `#1e3d6f` | **Task list area background** (dark royal blue) |
| `gold` | `#c8a415` | Accent buttons, borders, selection indicators |
| `goldPale` | `#faf6e8` | Quick-add bar background |
| `goldBorder` | `#d4be5a` | Quick-add bar border |
| `white` | `#ffffff` | Normal task card background, detail panel sections |
| `redCard` | `#f9d4d4` | "Needs attention" task card background |
| `redBorder` | `#e8a0a0` | "Needs attention" card border |
| `redDark` | `#b91c1c` | "Needs attention" left border |
| `red` | `#c53030` | OPEN status button, delete actions |
| `green` | `#1a8a4a` | Activity dot (reply received), email sent confirmation |
| `greenDot` | `#1a8a4a` | Dot indicator: reply received from assignee |
| `yellowDot` | `#d4a017` | Dot indicator: awaiting reply |
| `text` | `#1a2332` | Primary text |
| `textMid` | `#4a5568` | Secondary text, descriptions |
| `textLight` | `#7a8599` | Tertiary text, timestamps |
| `border` | `#c5cee0` | General borders on light backgrounds |
| `borderOnDark` | `#3d6098` | Borders on the dark blue background |

### 3.2 Typography

| Context | Font | Size | Weight |
|---------|------|------|--------|
| Body text | Segoe UI, Tahoma, sans-serif | 14-16px | Normal |
| Task IDs | Cascadia Code, Consolas, monospace | 14px | Bold |
| Headers | Segoe UI | 18-20px | Bold |
| Column headers | Segoe UI | 12px | Bold, uppercase |
| Small labels | Segoe UI | 11-13px | Normal |

---

## 4. Left Panel — Task List

### 4.1 Header Bar

- Background: Linear gradient from `blue` to `blueLight` (135deg)
- Content: Gold "T" logo badge (28x28px, gold background, blue text) + "TaskTracker" in white 20px bold + "SuiteView" in gold 12px
- No buttons in the header

### 4.2 Quick-Add Bar (Always Visible)

Sits directly below the header. This is the primary way to create tasks.

- Background: `goldPale` with `goldBorder` bottom border
- Layout: **[+] button on the LEFT** → text input on the right (flex)
- [+] button: 36x36px, gold background, blue "+" text, 20px bold
- Input placeholder: "New task — type and press Enter or click [+]"
- Input has `gold` border, 15px font
- Pressing Enter or clicking [+] creates the task immediately
- Auto-generates next Task ID (TSK-001, TSK-002, etc., always incrementing from highest existing)
- New task starts as status "open", no assignees, no emails
- Input clears after creation

### 4.3 Filter Bar

- Background: `bluePale`
- Layout: Status tabs (left) + Search input (right, flex)
- **Status tabs:** Only two options — "Open" and "Closed"
  - Toggle button group style (connected buttons with shared borders)
  - Active: `blue` background, white text
  - Inactive: white background, `textMid` text
  - No counts displayed on the tabs
- **Search input:** Filters tasks in real-time by ID, description, or assignee name
  - 14px font, placeholder "Search tasks..."

### 4.4 Column Headers (Sortable)

- Background: `bluePale`, sits below filter bar
- Uppercase, 12px bold, `blue` color, 0.5px letter-spacing
- Columns: **TASK ID** (80px) | **CREATED** (100px) | **ACTIVITY** (110px) | **ASSIGNEE** (flex)
- Clicking a column header sorts ascending; clicking again toggles descending
- Show ▲/▼ arrow on active sort column
- Show faint ⇅ on inactive sortable columns
- The "Details" column from earlier mockups has been **removed** — clicking the card opens details

### 4.5 Task Cards

The task list area has a **dark royal blue background** (`#1e3d6f`). Cards float on top of this.

**Card layout (2 lines):**

**Line 1** (columnar, fixed widths matching headers):
- Task ID: monospace font, 14px bold, `blue` color
- Created date: 14px, `text` color, font-weight 600
- Activity: Activity dot + human-readable time ("2h ago", "Just now", "—")
  - Green dot = reply received from someone else
  - Yellow dot = awaiting reply (email sent, no reply yet)
  - No dot = no email sent
- Assignees: Each assignee shown as a separate chip/badge
  - Chip style: 12px, `blue` text, semi-transparent white background, light blue border, rounded
  - If no assignees, show em-dash "—" in italic

**Line 2:**
- Task description text, 15px, `textMid` color
- Truncated to ~95 characters with ellipsis
- Full text shown in detail panel

**Card styling:**
- Border-radius: 4px
- 4px solid left border (color varies by state)
- Margin-bottom: 5px
- Subtle drop shadow: `0 1px 3px rgba(0,0,0,0.15)`
- Cursor: pointer
- Hover: increased shadow `0 2px 8px rgba(0,0,0,0.25)`
- Closed tasks: opacity 0.7

**Card color logic (IMPORTANT — this was heavily iterated):**

| Condition | Background | Left Border | Card Border |
|-----------|-----------|-------------|-------------|
| Last activity from someone else (needs attention) | `#f9d4d4` (pink/red) | `#b91c1c` (dark red) | `#e8a0a0` (red border) |
| Selected (clicked to open details) | Same as above colors based on state + gold outline glow (`0 0 0 2px gold`) | `gold` | `gold` |
| Normal (all other open tasks) | `white` | `rgba(200,164,21,0.6)` (translucent gold) | `rgba(255,255,255,0.25)` |
| Closed | `rgba(255,255,255,0.6)` | `#8ac4a0` (green) | `rgba(255,255,255,0.25)` |

**CRITICAL:** The red "needs attention" background must persist even when the task card is selected/clicked. Selection is indicated by a gold outline glow, NOT by changing the background color. This was a specific design decision.

### 4.6 Footer

- Background: `rgba(0,0,0,0.15)` (dark overlay on the blue)
- Text color: `rgba(255,255,255,0.6)` (semi-transparent white)
- Layout: Task count (left) | Legend (center) | "TaskTracker v1.0" (right)
- Legend shows: White swatch = "Normal", Red swatch = "Needs Attention"

---

## 5. Right Panel — Task Details

### 5.1 Resize Handle

- A 6px wide vertical bar between the two panels
- Background: Linear gradient from `gold` (top) to `blue` (bottom)
- Contains a small white indicator line (2px wide, 40px tall, centered)
- Cursor: col-resize
- Draggable to resize the detail panel between 320px and 700px wide
- Default width: 420px

### 5.2 Detail Header

- Same gradient as the left panel header
- Content: "Task Details" in white 18px bold + Task ID in `gold` monospace 16px bold
- Close button (✕) on the right, semi-transparent white background

### 5.3 Inline Status Row

Sits below the header. This replaces the old "Info" card and "Close Task" button.

- Background: white, bottom border
- Left: "Created: YYYY-MM-DD" in 13px
- Right: "Status:" label + clickable toggle button
  - **OPEN** state: `red` (`#c53030`) background, white text
  - **CLOSED** state: `blue` (`#1a3a7a`) background, white text
  - Click toggles between open/closed
  - 12px bold, 3px 14px padding, rounded

### 5.4 Tab Bar

Two tabs: "Details" and "Email Trail (N)"
- Active tab: `goldPale` background, 3px gold bottom border, `blue` text
- Inactive tab: transparent background, `textLight` text

### 5.5 Details Tab Content

#### Description Section
- Card with "DESCRIPTION" header (bluePale background, uppercase)
- Shows full task description text, 14px, line-height 1.6
- **Click to edit:** Clicking the description text opens a textarea for inline editing
- Shows "Click to edit" hint in italic below the text
- Save/Cancel buttons appear when editing

#### Assigned To Section
- Card with "ASSIGNED TO" header
- **Assignee chips:** Each assigned person shows as a pill/chip:
  - Initials avatar (20px circle, white background, 8px bold)
  - Name text
  - Red × button to remove
  - `bluePale` background, border, rounded-full
- **Always-visible search input** below the chips:
  - Gold border, `goldPale` background
  - Placeholder: "Type a name or email to assign..." (or "Add another person..." if assignees exist)
  - **Real-time filtering:** As user types, dropdown shows matching contacts from the roster
  - **Freeform entry:** If typed text doesn't match any contact, show "+ Assign to '[text]'" option
  - If text contains @, parse as email and extract name from prefix
  - New freeform contacts are added to the contact roster
  - Already-assigned people are filtered OUT of the dropdown
  - Enter key assigns the top match (or creates freeform)
  - Dropdown only appears when the user starts typing

#### Email Actions Section (only shows when assignees exist)
- Card with "EMAIL ACTIONS" header, `goldPale` background
- If email not yet sent: Gold "✉ SEND TASK TO [NAME]" button
  - For multiple assignees: "✉ SEND TASK TO 3 PEOPLE"
  - Note below: "Subject includes [TSK-XXX] for tracking"
- If email already sent: Green "✓ Email sent — tracking via [TSK-XXX]"
  - Shows email count and last activity

#### Delete Task
- At the bottom, separated by a border-top
- "🗑 Delete Task" button: white background, red text, red border
- Click shows confirmation: "Delete TSK-XXX?" with "Yes" (red) and "Cancel" buttons
- **Confirming permanently removes the task from the database** — it will not appear in Open, Closed, or anywhere else

### 5.6 Email Trail Tab Content

#### Email Search
- Search input at top of the Email Trail tab
- Filters emails in real time as user types
- Searches across: body, subject, from, to fields

#### Email Cards (Compact, 2-Line Format)

Emails are listed in **descending order by date** (newest first).

**Line 1 (top row):**
- Sender name (bold, `blue` for sent / `gold` for received)
- Arrow → recipient
- 📎 attachment indicator (if `hasAttachment` is true — display only, no file storage)
- Date (right-aligned, 11px, `textLight`)
- "Reply" button (right-aligned, small blue button)
- **Double-click the top row** → opens the actual email in Outlook (see Section 7)

**Line 2 (body preview):**
- Shows first ~70 characters of the email body, truncated with ellipsis
- **Click to expand:** Clicking the preview line expands the card to show the full email body
- Click again to collapse

**Email card styling:**
- White background (NO green background for received emails)
- Left border: 3px solid `blue` (sent) or `gold` (received)
- Light gray border overall
- Rounded corners, 6px margin-bottom

#### Reply Compose Area

When the user clicks "Reply" on any email:
- The bottom half of the Email Trail tab becomes a compose area
- Shows "Replying to: [name]" header
- Textarea with gold border, 13px font, placeholder "Type your response..."
- "✉ Send Reply" button (blue) and "Cancel" button
- Sending a reply adds a new "sent" email to the thread
- Updates the task's `last_activity` to "Just now" and `last_activity_from` to "You"

---

## 6. Outlook Integration

This is the most critical backend feature. TaskTracker must integrate with Microsoft Outlook on the user's Windows machine.

### 6.1 Sending Emails

When the user clicks "SEND TASK TO [NAME]":

1. Create a new Outlook email using `win32com.client` (pywin32)
2. Set the To field to the assignee's email address(es)
3. Set the Subject to: `[TSK-XXX] {task description (first ~60 chars)}`
4. Set the Body to the task description
5. Send the email via Outlook
6. Record the sent email in the TaskTracker database

```python
import win32com.client

outlook = win32com.client.Dispatch("Outlook.Application")
mail = outlook.CreateItem(0)  # olMailItem
mail.To = "john.martinez@company.com"
mail.Subject = "[TSK-001] Review Q4 mortality assumptions for Group Term Life block"
mail.Body = "John, please review the Q4 mortality assumptions..."
mail.Send()
```

For multiple assignees, send individual emails to each or use CC/BCC as appropriate.

### 6.2 Monitoring for Replies

TaskTracker needs to periodically scan the Outlook inbox for emails whose subject lines contain `[TSK-XXX]` patterns.

**Approach:** Use a polling mechanism (e.g., every 60 seconds) to scan recent inbox items:

```python
inbox = outlook.GetNamespace("MAPI").GetDefaultFolder(6)  # olFolderInbox
messages = inbox.Items
messages.Sort("[ReceivedTime]", True)  # Newest first

for msg in messages:
    # Check if subject contains a task ID pattern [TSK-XXX]
    match = re.search(r'\[TSK-\d{3}\]', msg.Subject)
    if match:
        task_id = match.group(0).strip('[]')
        # Record this email in the task's email thread
        # Update last_activity_from to the sender's name
```

### 6.3 Opening Emails in Outlook (Double-Click)

When the user double-clicks an email card's top row in the Email Trail:

```python
# If we stored the Outlook EntryID when recording the email:
namespace = outlook.GetNamespace("MAPI")
mail_item = namespace.GetItemFromID(entry_id)
mail_item.Display()  # Opens the email in Outlook's reader
```

**Implementation note:** When recording emails (both sent and received), store the Outlook `EntryID` so we can later reopen the exact email. If EntryID is not available (e.g., email was recorded before this feature), show a message that the email can't be opened.

### 6.4 Attachment Detection

When scanning emails, check `msg.Attachments.Count > 0` and set `has_attachment = True`. Do NOT download or store the attachment files — just record the boolean flag for display.

---

## 7. Behavioral Specifications

### 7.1 Task ID Generation

- Format: `TSK-XXX` where XXX is zero-padded to 3 digits
- Always increment from the highest existing task ID in the database
- If tasks TSK-001 through TSK-005 exist and TSK-003 is deleted, next task is TSK-006 (not TSK-003)

### 7.2 Card Color Logic ("Needs Attention")

A task card shows the red "needs attention" color when:
- `last_activity_from` is NOT null AND NOT "You"
- This means: someone else (an assignee) was the last person to act on this task, and the manager hasn't responded yet

The red goes away when:
- The manager sends a reply (sets `last_activity_from` to "You")
- The task is closed

### 7.3 Activity Dot Logic

| Dot Color | Condition |
|-----------|-----------|
| Green dot | Last activity was from someone other than "You" |
| Yellow dot | Email was sent but last activity was from "You" (awaiting their reply) |
| No dot | No email has been sent for this task |

### 7.4 Task Deletion

- Permanently removes the task and all associated emails from the database
- Task ID is NOT reused
- Requires confirmation before deletion

### 7.5 Status Toggle

- Tasks toggle between "open" and "closed"
- Closed tasks appear only when the "Closed" filter tab is selected
- Closed tasks render with reduced opacity (0.7) and a green left border

---

## 8. Integration with SuiteView

### 8.1 Launch Point

TaskTracker should be accessible from the SuiteView taskbar. The recommended approach is to add a "TaskTracker" button to the existing SuiteView taskbar that opens the TaskTracker window.

### 8.2 Window Behavior

- TaskTracker opens as a separate window (not embedded in the thin taskbar)
- Should be a resizable, movable window
- Should have a reasonable default size (e.g., 1100x700px)
- Should remember its position/size between sessions (store in config)

### 8.3 Module Structure

Add TaskTracker as a new module within the existing SuiteView project:

```
suiteview/
├── main.py                    # Existing entry point
├── taskbar.py                 # Existing taskbar code
├── tasktracker/               # NEW MODULE
│   ├── __init__.py
│   ├── tasktracker_window.py  # Main TaskTracker window/UI
│   ├── models.py              # Task, Email, Contact data classes
│   ├── database.py            # SQLite operations
│   ├── outlook_integration.py # Outlook COM automation
│   ├── email_scanner.py       # Background email polling
│   └── constants.py           # Colors, fonts, dimensions
└── ...
```

**IMPORTANT:** Before implementing, inspect the existing SuiteView codebase to understand:
1. What UI framework is currently in use (tkinter vs PyQt6 vs other)
2. How other features/windows are launched from the taskbar
3. Existing patterns for config storage
4. Whether there's an existing database connection module

Match the existing patterns. If SuiteView uses tkinter, build TaskTracker in tkinter. If it uses PyQt6, use PyQt6.

### 8.4 Dependencies

Add these to the project's requirements if not already present:
- `pywin32` — for Outlook COM automation via `win32com.client`
- `sqlite3` — for database (built into Python)

---

## 9. Reference Implementation

The React mockup file `tasktracker-mockup.jsx` (attached separately) contains the complete working UI prototype with all visual design, interactions, and state management. Use it as the definitive visual and behavioral reference. The mockup includes:

- Exact color values and spacing
- All interaction patterns (sorting, filtering, expanding emails, replying, etc.)
- Card color logic
- Resize handle behavior
- Search/filter behavior
- Complete mock data showing various task states

**The React mockup is the source of truth for how it should look and behave.** Translate the visual design faithfully into the Python UI framework used by SuiteView.

---

## 10. Implementation Priorities

### Phase 1 — Core UI (Do First)
1. TaskTracker window with two-panel layout
2. Task list with sorting, filtering, search
3. Quick-add bar for task creation
4. Detail panel with description editing, status toggle
5. SQLite storage for tasks and contacts
6. Delete task functionality

### Phase 2 — Assignment & Email Display
1. Contact roster management
2. Assignee assignment with search/filter/freeform
3. Multi-assignee support
4. Email trail display (using mock/manual data initially)

### Phase 3 — Outlook Integration
1. Send task emails via Outlook COM
2. Email polling/scanning for replies
3. Auto-update task activity when replies detected
4. Double-click to open email in Outlook
5. Attachment detection

### Phase 4 — Polish
1. Resize handle for detail panel
2. Window position/size persistence
3. Card color state management (needs attention logic)
4. SuiteView taskbar button integration

---

## 11. Questions for the Developer (Claude Code)

Before writing any code, please:

1. Ask Robert for the current SuiteView project path
2. Inspect the existing folder structure and main.py
3. Determine which UI framework is in use (tkinter or PyQt6)
4. Check for existing database patterns
5. Check for existing Outlook integration patterns
6. Propose a file structure that fits with the existing codebase

---

*End of specification. The attached `tasktracker-mockup.jsx` file serves as the visual design reference.*
