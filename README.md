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

**Method 1: VSCode with WSL (Best for Development)**
1. Install VSCode "WSL" extension
2. In VSCode, press `Ctrl+K Ctrl+O` and open:
   ```
   \\wsl.localhost\Ubuntu-22.04\home\obert\SuiteViewProjects\SuiteViewP
   ```
3. Open a **WSL terminal** (click dropdown next to `+` → select "Ubuntu-22.04")
4. Run:
   ```bash
   ./run_from_vscode.sh
   ```
   Or manually:
   ```bash
   source venv/bin/activate
   python -m suiteview.main
   ```

**Method 2: Standalone on Windows**
1. Make sure Python 3.13+ is installed ([download here](https://www.python.org/downloads/))
2. Copy project folder to Windows
3. Double-click `run_windows.bat`

**See [WINDOWS_SETUP.md](WINDOWS_SETUP.md) for complete Windows setup guide.**

### Linux/WSL Users

**Prerequisites:**
- Python 3.10+
- X11 server (for WSL users)

**Running:**
```bash
# Easy way
./run.sh

# Or manually
source venv/bin/activate
python -m suiteview.main
```

## Project Structure

```
SuiteViewP/
├── CLAUDE.md              # Product Requirements Document
├── README.md              # This file
├── requirements.txt       # Python dependencies
├── run.sh                 # Convenience run script
├── venv/                  # Virtual environment
├── suiteview/             # Main application package
│   ├── main.py            # Application entry point
│   ├── ui/                # UI layer (PyQt6 widgets)
│   │   ├── main_window.py
│   │   ├── connections_screen.py
│   │   ├── mydata_screen.py
│   │   ├── dbquery_screen.py
│   │   ├── xdbquery_screen.py
│   │   ├── styles.qss     # Qt Style Sheets
│   │   └── widgets/       # Reusable custom widgets
│   ├── core/              # Business logic layer
│   ├── data/              # Data access layer
│   │   └── database.py    # SQLite initialization
│   └── utils/             # Utility modules
│       ├── config.py
│       └── logger.py
├── resources/             # Application resources
│   ├── icons/
│   └── images/
└── tests/                 # Test suite
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

For questions or support, refer to CLAUDE.md for project details.
