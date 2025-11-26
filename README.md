# SuiteView Data Manager

A native Python desktop application for visual, low-code access to diverse data sources across an enterprise. Built with PyQt6.

## Features

### Data Connections
- **SQL Server, DB2, Oracle** - Enterprise database connectivity via ODBC
- **MS Access** - Direct .mdb/.accdb file access
- **Excel & CSV** - File-based data sources with encoding options
- **Fixed Width Files** - Support for legacy file formats
- **Mainframe FTP** - Browse and download mainframe datasets

### Visual Query Building
- **DB Query** - Single-database visual query builder (no SQL required)
- **XDB Query** - Cross-database queries with application-level joins
- **Drag-and-drop** criteria and display field selection
- **Smart filters** - Type-aware filter controls for strings, numbers, dates

### My Data Workspace
- Curated list of saved tables and queries
- Query metadata tracking (last run, duration, record count)
- Find unique values for columns
- Organize queries in folders

### File Explorer
- Windows-style file browser with OneDrive integration
- Multi-tab support for multiple folder views
- Bookmarks system for quick access to files, folders, and URLs
- Cut/Copy/Paste, Rename, Delete operations
- File preview pane

### Mainframe Navigation
- Browse mainframe datasets via FTP/TLS
- Preview dataset members
- Export to local files

## Quick Start

### Windows (Recommended)

**Option 1: Run from source**
```cmd
cd C:\path\to\SuiteViewP
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
python -m suiteview.main
```

**Option 2: Use batch file**
```cmd
run_windows.bat
```

### Linux/WSL
```bash
./run.sh
```

See [WINDOWS_SETUP.md](WINDOWS_SETUP.md) for detailed installation instructions.

## Project Structure

```
SuiteViewP/
├── CLAUDE.md              # Product Requirements Document
├── README.md              # This file
├── requirements.txt       # Python dependencies
├── suiteview/             # Main application package
│   ├── main.py            # Application entry point
│   ├── ui/                # UI layer (PyQt6 widgets)
│   │   ├── main_window.py
│   │   ├── connections_screen.py
│   │   ├── mydata_screen.py
│   │   ├── dbquery_screen.py
│   │   ├── xdbquery_screen.py
│   │   ├── mainframe_nav_screen.py
│   │   ├── file_explorer_core.py
│   │   ├── file_explorer_multitab.py
│   │   ├── dialogs/       # Dialog windows
│   │   └── widgets/       # Reusable custom widgets
│   ├── core/              # Business logic layer
│   │   ├── connection_manager.py
│   │   ├── query_builder.py
│   │   ├── query_executor.py
│   │   ├── schema_discovery.py
│   │   └── ftp_manager.py
│   ├── data/              # Data access layer
│   │   ├── database.py
│   │   └── repositories.py
│   └── utils/             # Utility modules
├── resources/             # Application resources (icons, images)
└── tests/                 # Test suite
```

## Application Data

The application stores its data in your home directory:
- **Database**: `~/.suiteview/suiteview.db`
- **Logs**: `~/.suiteview/logs/suiteview.log`
- **Bookmarks**: `~/.suiteview/bookmarks.json`
- **Quick Links**: `~/.suiteview/quick_links.json`

## Technology Stack

- **UI Framework**: PyQt6
- **Database**: SQLite 3 (local), SQLAlchemy (external connections)
- **Data Processing**: Pandas, DuckDB
- **Security**: cryptography (credential encryption)
- **Packaging**: PyInstaller

## Documentation

- [CLAUDE.md](CLAUDE.md) - Complete Product Requirements Document
- [WINDOWS_SETUP.md](WINDOWS_SETUP.md) - Windows installation guide
- [MAINFRAME_NAV_GUIDE.md](MAINFRAME_NAV_GUIDE.md) - Mainframe navigation help
- [BOOKMARKS_FEATURE.md](BOOKMARKS_FEATURE.md) - Bookmarks system documentation
- [TECH_DEBT.md](TECH_DEBT.md) - Technical debt and refactoring opportunities

## Development

### Running Tests
```bash
source venv/bin/activate  # or venv\Scripts\activate on Windows
pytest
```

### Code Formatting
```bash
black suiteview/
flake8 suiteview/
```

### Building Executable
```bash
python build_windows.py
```
Output: `dist/SuiteView Data Manager.exe`

## System Requirements

### Minimum
- Windows 10 (64-bit) or Linux
- Python 3.10+
- 4 GB RAM
- 1 GB free disk space

### Recommended
- Windows 11 (64-bit)
- Python 3.13+
- 8 GB RAM
- 1920x1080 display

## License

Proprietary - Internal use only
