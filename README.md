# SuiteView Data Manager

A native Python desktop application for visual, low-code access to diverse data sources across an enterprise. Built with PyQt6.

## Project Status: Phase 2 Complete

### Completed Features
- ✅ Complete Python project structure
- ✅ SQLite database schema initialization
- ✅ PyQt6 application with professional royal blue & gold theme
- ✅ Four-tab navigation (Connections | My Data | DB Query | XDB Query)
- ✅ **Connections Screen** with full functionality:
  - Connection browser tree
  - Table schema viewer
  - Right-click context menu (Edit/Delete)
  - Comprehensive Add Connection dialog supporting:
    - Local ODBC (SQL Server, DB2)
    - Excel Files (.xlsx, .xls)
    - MS Access (.accdb, .mdb)
    - CSV Files (with delimiter & encoding options)
    - Fixed Width Files (with field definitions)

## Quick Start

### Windows Users (Recommended Platform)

1. Make sure Python 3.13+ is installed ([download here](https://www.python.org/downloads/))
2. Double-click `run_windows.bat`

Or manually:
```powershell
.\venv_window\Scripts\Activate.ps1
python -m suiteview.main
```

**See [docs/WINDOWS_SETUP.md](docs/WINDOWS_SETUP.md) for complete Windows setup guide.**

## Project Structure

```
SuiteViewP/
├── README.md              # This file
├── requirements.txt       # Python dependencies
├── setup.py               # Package setup
├── suiteview.spec         # PyInstaller build spec
├── build_windows.py       # Build script for Windows executable
├── run_windows.bat        # Windows launcher script
├── venv_window/           # Virtual environment (Windows)
│
├── suiteview/             # Main application package
│   ├── main.py            # Application entry point
│   ├── ui/                # UI layer (PyQt6 widgets)
│   │   ├── main_window.py
│   │   ├── launcher.py
│   │   ├── connections_screen.py
│   │   ├── mydata_screen.py
│   │   ├── dbquery_screen.py
│   │   ├── xdbquery_screen.py
│   │   ├── styles.qss     # Qt Style Sheets
│   │   ├── dialogs/       # Dialog windows
│   │   ├── widgets/       # Reusable custom widgets
│   │   └── helpers/       # UI helper utilities
│   ├── core/              # Business logic layer
│   ├── data/              # Data access layer
│   │   └── database.py    # SQLite initialization
│   ├── models/            # Data models
│   └── utils/             # Utility modules
│       ├── config.py
│       └── logger.py
│
├── scripts/               # Utility scripts & standalone launchers
│   ├── run_launcher.py
│   ├── run_file_explorer.py
│   ├── run_screenshot_manager.py
│   ├── icon_picker.py
│   └── verify_setup.py
│
├── tests/                 # Test suite
│
└── docs/                  # Documentation
    ├── QUICK_START.md
    ├── WINDOWS_SETUP.md
    ├── guides/            # Feature guides
    └── planning/          # Planning documents
```

## Application Data

The application stores its data in your home directory:
- Database: `~/.suiteview/suiteview.db`
- Logs: `~/.suiteview/logs/suiteview.log`

## Features (Current)

### UI Shell
- Main window with tabbed navigation (4 tabs)
- Responsive multi-panel layouts with resizable splitters
- Modern, professional styling using Qt Style Sheets
- Color-coded panels for easy identification

### UI Conventions
- **Context Menus:** 
  - Item context menus: Blue border (`#0078d4`)
  - Category context menus: Dynamic color matching the category's color (darkened)
  - Compact styling with minimal padding for space efficiency
  - Items include: Edit, Open folder location, Copy link, Remove (as applicable)

- **UI Style Preference:**
  - **Fast & responsive UI** is the top priority - minimize latency on all interactions
  - Use async loading, database caching, and deferred operations to keep UI snappy
  - Compact, space-efficient layouts preferred throughout the application
  - Tight padding on menu items and buttons
  - Minimal whitespace while maintaining readability

- **Visual Design Preference:**
  - **Rounded corners** on buttons, panels, and popups for a modern, friendly look
  - **3D/dimensional effects** (gradients, subtle shadows, beveled borders) to draw attention to key controls
  - Panel headers should have depth/dimension to stand out from content areas
  - Styled message boxes and dialogs matching the app theme (not default OS style)

- **Category Colors:**
  - Categories can have custom colors from a 36-color palette
  - Colors are persisted and transfer when moving categories between bar/sidebar
  - Right-click category → "🎨 Change Color" to set color

### Bookmark Architecture
Both the **top bar** and **sidebar** now use the unified `BookmarkContainer` class:

- **BookmarkContainer** (`suiteview/ui/widgets/bookmark_widgets.py`): 
  Unified container class for bookmarks and categories supporting both horizontal (top bar) 
  and vertical (sidebar) orientations with standardized data interface
  - `location='bar'` + `orientation='horizontal'` → Top bookmark bar
  - `location='sidebar'` + `orientation='vertical'` → Quick Links sidebar
  
- **CategoryButton**: Draggable button with dropdown popup for category contents
- **StandaloneBookmarkButton**: Draggable button for individual bookmarks outside categories
- **CategoryPopup**: Dropdown popup showing category items with drag/drop support

Data storage:
- Top bar: `~/.suiteview/bookmarks.json` (keys: `bar_items`, `categories`, `category_colors`)
- Sidebar: `~/.suiteview/quick_links.json` (keys: `items`, `categories`, `category_colors`)

### Database
- SQLite database with complete schema:
  - Connections table
  - Saved tables
  - Cached metadata (tables & columns)
  - Unique values cache
  - Saved queries
  - User preferences

### Infrastructure
- Logging system with file rotation
- Configuration management
- Database initialization and connection pooling
- Clean separation of concerns (UI/Core/Data layers)

## Next Steps - Phase 2: Connections Screen

Phase 2 will implement the Connections Screen functionality:
- QTreeWidget for connection hierarchy
- Add/Edit Connection dialogs
- Schema discovery with SQLAlchemy
- Table list with checkboxes
- Schema details table view
- Connection testing
- Save to My Data functionality

## Development

### Installing Additional Dependencies

```bash
source venv/bin/activate
pip install <package-name>
```

### Running Tests

```bash
source venv/bin/activate
pytest
```

### Code Formatting

```bash
source venv/bin/activate
black suiteview/
flake8 suiteview/
```

## Technology Stack

- **UI Framework:** PyQt6
- **Database:** SQLite 3 (local), SQLAlchemy (connections)
- **Data Processing:** Pandas
- **Security:** cryptography
- **Packaging:** PyInstaller (for future deployment)

## Architecture

All-Python stack with direct method calls between layers:
- **UI Layer:** PyQt6 widgets handle user interaction
- **Business Logic:** Pure Python classes for query building, connection management
- **Data Layer:** SQLAlchemy and Pandas for data operations

## License

Proprietary - Internal use only

## Contact

For questions or support, please contact the development team.
