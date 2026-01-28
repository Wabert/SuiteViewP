# SuiteView Data Manager

A native Python desktop application for visual, low-code access to diverse data sources across an enterprise. Built with PyQt6 and featuring an integrated AI assistant powered by VS Code Bridge.

## Project Status: AI Integration Complete

### Latest Features ✨
- ✅ **AI Assistant Integration** - Built-in chatbot powered by GitHub Copilot via VS Code Bridge
- ✅ **Smart Thread Naming** - AI automatically generates descriptive conversation titles
- ✅ **Dedicated VS Code Session** - Automatic VS Code workspace management for AI Bridge
- ✅ **Floating Launcher Bar** - Always-on-top toolbar with AI status indicator
- ✅ **Complete Python project structure**
- ✅ **SQLite database schema initialization**
- ✅ **PyQt6 application with professional royal blue & gold theme**
- ✅ **Four-tab navigation (Connections | My Data | DB Query | XDB Query)**
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

## AI Assistant Features 🤖

### Overview
SuiteView includes a powerful AI chatbot interface that connects to GitHub Copilot through VS Code, giving you access to multiple AI models including GPT-4, Claude, Gemini, and more.

### Key Features
- **VS Code Bridge Connection**: Seamless integration with GitHub Copilot through VS Code
- **Multi-Model Support**: Access to various AI agents (GPT-4o, Claude, Gemini, etc.)
- **Smart Thread Naming**: After your second message, the AI automatically generates a descriptive title for each conversation (max 40 characters)
- **Thread Management**: Conversations are automatically named "New Thread 1", "New Thread 2", etc., then renamed intelligently
- **Persistent Conversations**: All chats are saved and can be resumed anytime
- **Dedicated Workspace**: Automatic VS Code workspace creation in `~/.suiteview/llm_chat/ai_bridge_workspace/`
- **Window Visibility Toggle**: Hide/show the AI Bridge VS Code window with a gold/blue slider toggle
- **Live Status Indicator**: Green "AI Active" indicator shows real-time connection status

### Getting Started with AI Assistant

1. **Prerequisites**:
   - VS Code installed on your system
   - GitHub Copilot extension installed and active in VS Code
   - GitHub Copilot subscription (Individual, Business, or Enterprise)
   - For premium models (Claude, Gemini): Copilot Pro+ ($39/month)

2. **First-Time Setup**:
   - Click the 🤖 AI Assistant button in the SuiteView launcher
   - Click "Start Dedicated VS Code Session" button
   - SuiteView will automatically:
     - Find your VS Code installation
     - Create a dedicated workspace
     - Launch VS Code in the background
     - Connect to the AI Bridge

3. **Using the AI**:
   - Select your preferred AI agent from the dropdown (GPT-4o, Claude, etc.)
   - Type your question and press Ctrl+Enter or click Send
   - The AI will respond with streaming output
   - Your first two prompts will auto-name the thread

4. **Window Management**:
   - Toggle button (top-right of launcher): Click to show/hide the AI Bridge VS Code window
   - Gold slider on left = Window hidden (default)
   - Blue slider on right = Window visible

### AI Assistant Launcher Bar

The floating launcher bar shows:
- **"AI Active" indicator**: Green when connected, gray when disconnected
- **Toggle slider**: Gold/blue switch to control VS Code window visibility
- **App buttons**: Quick access to all SuiteView tools
- **Always on top**: Stays accessible while you work

### Troubleshooting AI Assistant

**Issue: AI Bridge won't connect**
- Ensure VS Code is installed (checked in common locations: `%LOCALAPPDATA%`, `%ProgramFiles%`)
- Verify GitHub Copilot extension is installed in VS Code
- Check that you're signed into GitHub in VS Code
- Try clicking "Start Dedicated VS Code Session" again

**Issue: Models not loading**
- Open VS Code manually and verify Copilot is working
- Check VS Code settings for Copilot enabled models
- Try restarting the dedicated VS Code session

**Issue: Thread not auto-renaming**
- Auto-naming happens after the second AI response
- Requires connection to VS Code Bridge
- Uses gpt-4o-mini model (must be available in your Copilot subscription)

**Issue: Can't find VS Code window**
- Click the toggle slider (top-right of launcher)
- When blue (slider on right), VS Code window is visible
- When gold (slider on left), VS Code window is hidden
- Check Windows taskbar for VS Code icon

For more details, see `docs/guides/AI_ASSISTANT_GUIDE.md` (coming soon)

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
│   │   ├── launcher.py            # Floating always-on-top toolbar with AI indicator
│   │   ├── llm_chat_window.py     # AI Assistant chatbot interface
│   │   ├── connections_screen.py
│   │   ├── mydata_screen.py
│   │   ├── dbquery_screen.py
│   │   ├── xdbquery_screen.py
│   │   ├── styles.qss     # Qt Style Sheets
│   │   ├── dialogs/       # Dialog windows
│   │   ├── widgets/       # Reusable custom widgets
│   │   └── helpers/       # UI helper utilities
│   ├── core/              # Business logic layer
│   │   ├── llm_client.py          # VS Code Bridge client & conversation management
│   │   ├── connection_manager.py
│   │   └── ...
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
- **Database**: `~/.suiteview/suiteview.db` - Main application database
- **Logs**: `~/.suiteview/logs/suiteview.log` - Application logs
- **AI Conversations**: `~/.suiteview/llm_chat/conversations.json` - Saved chat history
- **AI Workspace**: `~/.suiteview/llm_chat/ai_bridge_workspace/` - Dedicated VS Code workspace
- **VS Code Session**: `~/.suiteview/llm_chat/vscode_session.json` - Active session tracking
- **Bookmarks**: `~/.suiteview/bookmarks.json` - Unified bookmark storage

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
  - **Lighthearted, friendly tone** in user-facing messages (see docs/DEV_GUIDE.md)

- **Application Personality:**
  - Brief, friendly explanations for technical concepts
  - Casual, conversational tone in UI messages
  - Light humor where appropriate (coffee machine analogies, etc.)
  - Professional when dealing with errors or critical operations
  - See `docs/DEV_GUIDE.md` "Application Personality & Messaging Style" section

- **Category Colors:**
  - Categories can have custom colors from a 36-color palette
  - Colors are persisted and transfer when moving categories between bar/sidebar
  - Right-click category → "🎨 Change Color" to set color

### Bookmark Architecture
All bookmark bars use the unified `BookmarkContainer` class with centralized data storage:

- **BookmarkDataManager** (`suiteview/ui/widgets/bookmark_data_manager.py`):
  Singleton manager providing unified data storage for all bookmark bars.
  - Single JSON file: `~/.suiteview/bookmarks.json`
  - Scalable design supports unlimited bookmark bars
  - Each bar identified by unique string ID (e.g., `'top_bar'`, `'sidebar'`, `'toolbar_2'`)

- **BookmarkContainer** (`suiteview/ui/widgets/bookmark_widgets.py`): 
  Unified container class for bookmarks and categories supporting both horizontal (top bar) 
  and vertical (sidebar) orientations with standardized data interface
  - `location='top_bar'` + `orientation='horizontal'` → Top bookmark bar
  - `location='sidebar'` + `orientation='vertical'` → Quick Links sidebar
  - `use_data_manager=True` → Auto-load/save via BookmarkDataManager
  
- **BookmarkContainerRegistry**: Enables cross-bar drag/drop between any bookmark bars

- **CategoryButton**: Draggable button with dropdown popup for category contents
- **StandaloneBookmarkButton**: Draggable button for individual bookmarks outside categories
- **CategoryPopup**: Dropdown popup showing category items with drag/drop support

Data storage (unified):
```json
~/.suiteview/bookmarks.json
{
  "bars": {
    "top_bar": {"items": [...], "categories": {...}, "category_colors": {...}},
    "sidebar": {"items": [...], "categories": {...}, "category_colors": {...}}
  },
  "version": 2
}
```

### Database
- SQLite database with complete schema:
  - Connections table
  - Saved tables
  - Cached metadata (tables & columns)
  - Unique values cache
  - Saved queries
  - User preferences
  - Bookmark icons cache

### Infrastructure
- Logging system with file rotation
- Configuration management
- Database initialization and connection pooling
- Clean separation of concerns (UI/Core/Data layers)
- **AI Integration**:
  - VS Code Bridge client with HTTP API (localhost:5678)
  - Dedicated VS Code session management with automatic workspace creation
  - Background thread workers for async AI responses
  - Smart thread naming using GPT-4o-mini
  - Conversation persistence and restoration
  - Window visibility management via Windows API (ctypes)

## Next Steps

### Planned Features
- **AI Assistant Enhancements**:
  - API connection configuration UI
  - Code execution from AI responses
  - File attachment support (if supported by bridge)
  - Conversation export/import
  
- **Data Management**:
  - Saved queries interface
  - Data set management
  - Query result caching
  - Export to multiple formats

- **UI Improvements**:
  - Additional tool integrations
  - Email navigator enhancements
  - Screenshot manager improvements
  - Mainframe navigator upgrades

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
- **AI Integration:** VS Code Bridge with GitHub Copilot
- **Database:** SQLite 3 (local), SQLAlchemy (connections)
- **Data Processing:** Pandas
- **Security:** cryptography
- **HTTP Client:** aiohttp (async), requests (sync)
- **Process Management:** psutil
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
