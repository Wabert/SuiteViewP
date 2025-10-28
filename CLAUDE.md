# SuiteView Data Manager - Product Requirements Document

## Executive Summary

SuiteView Data Manager is a native Python desktop application that provides business users with visual, low-code access to diverse data sources across an enterprise. Built with PyQt6, the application enables non-technical users to connect to databases (SQL Server, DB2, Oracle, MS Access, Excel, CSV, etc.), explore schemas, build queries through drag-and-drop interactions, and execute both single-database and cross-database queries without writing SQL.

**Target Users:** 15 business analysts and data workers within a single company, all using Windows OS
**Core Value Proposition:** Democratize data access by replacing SQL knowledge requirements with intuitive visual query building
**Key Differentiator:** Native support for cross-database queries with transparent application-level join processing
**Architecture:** All-Python stack with PyQt6 for a native, high-performance desktop experience

---

## Technology Stack

### UI Framework
- **Framework:** PyQt6 (or PySide6) - Professional Qt bindings for Python
- **Why PyQt6:**
  - Native desktop widgets with excellent performance
  - Built-in components for everything we need (trees, grids, splitters, tabs, drag-and-drop)
  - Qt Style Sheets for modern, polished UI (CSS-like styling)
  - Cross-platform with native OS integration
  - Excellent LLM training data and documentation
- **Key Qt Widgets Used:**
  - `QTreeWidget` - Connection/table/field trees
  - `QTableView` with custom models - High-performance data grids
  - `QSplitter` - Resizable panel dividers
  - `QTabWidget` - Tab controls (ribbon navigation)
  - Drag-and-drop built into Qt framework
  - `QMenu` - Context menus

### Business Logic & Data Layer
- **Database Connectivity:**
  - `sqlalchemy` 2.0+ - Universal database ORM/toolkit
  - `pyodbc` - ODBC connections (SQL Server, Access, etc.)
  - `ibm_db` - IBM DB2 connections
  - `cx_oracle` - Oracle connections
  - `pandas` - Data manipulation and application-level joins
  - `openpyxl` - Excel file handling
- **Security:** `cryptography` - Credential encryption (DPAPI equivalent)
- **Architecture:** Integrated application (no separate API server needed)

### Local Storage
- **Database:** SQLite 3 (built into Python)
- **Location:** `%APPDATA%\SuiteView\suiteview.db`
- **Purpose:** User preferences, saved queries, cached metadata, encrypted connection credentials

### Deployment
- **Package Tool:** PyInstaller (or cx_Freeze as alternative)
- **Output:** Single Windows .exe (~50MB)
- **Dependencies:** All bundled into executable
- **No Installation Required:** Can run portable or install to Program Files

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                   PyQt6 Desktop Application                     │
│                                                                 │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │
│  ┃                    UI Layer (Qt Widgets)                  ┃  │
│  ┃  ┌────────────────────────────────────────────────────┐   ┃  │
│  ┃  │  QMainWindow with QTabWidget (Ribbon)              │   ┃  │
│  ┃  │  ├─ ConnectionsScreen (QWidget)                    │   ┃  │
│  ┃  │  │   └─ QSplitter → QTreeWidget, QTableView, etc.  │   ┃  │
│  ┃  │  ├─ MyDataScreen (QWidget)                         │   ┃  │
│  ┃  │  ├─ DBQueryScreen (QWidget)                        │   ┃  │
│  ┃  │  └─ XDBQueryScreen (QWidget)                       │   ┃  │
│  ┃  └────────────────────────────────────────────────────┘   ┃  │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  │
│                              ↕                                  │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │
│  ┃                  Business Logic Layer                    ┃  │
│  ┃  • ConnectionManager - Database connection management    ┃  │
│  ┃  • QueryBuilder - Query construction logic              ┃  │
│  ┃  • QueryExecutor - Query execution & result handling    ┃  │
│  ┃  • SchemaDiscovery - Metadata introspection             ┃  │
│  ┃  • CredentialManager - Encryption/decryption            ┃  │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  │
│                              ↕                                  │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │
│  ┃                     Data Layer                           ┃  │
│  ┃  • SQLAlchemy ORM - Database connections & queries      ┃  │
│  ┃  • Pandas DataFrames - Data manipulation & XDB joins    ┃  │
│  ┃  • SQLite Repository - Local data persistence           ┃  │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  │
│                              ↕                                  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              Local & External Databases                  │  │
│  │  ┌───────────────────────────────────────────────────┐  │  │
│  │  │  SQLite (Local)                                   │  │  │
│  │  │  • User preferences   • Cached metadata           │  │  │
│  │  │  • Saved queries      • Encrypted credentials     │  │  │
│  │  └───────────────────────────────────────────────────┘  │  │
│  │  ┌───────────────────────────────────────────────────┐  │  │
│  │  │  External Data Sources (via SQLAlchemy)          │  │  │
│  │  │  • SQL Server    • DB2         • Oracle           │  │  │
│  │  │  • MS Access     • Excel       • CSV/Flat Files   │  │  │
│  │  └───────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Architecture Benefits

**Single Process Design:**
- All code runs in one Python process
- Direct method calls (no HTTP/JSON serialization overhead)
- Simpler debugging with standard Python debugger
- Lower memory footprint (~100MB vs ~300MB with Electron)

**Clear Separation of Concerns:**
- **UI Layer:** PyQt6 widgets handle user interaction and display
- **Business Logic:** Pure Python classes handle query building, connection management
- **Data Layer:** SQLAlchemy and Pandas handle all data operations

**Communication Flow:**
1. User interacts with PyQt6 widgets (click, drag, type)
2. Widget emits Qt signals to business logic layer
3. Business logic processes request using SQLAlchemy/Pandas
4. Data layer queries SQLite or external databases
5. Results flow back through layers to UI for display

**No API Contracts Needed:**
- Direct Python method calls between layers
- Type hints provide interface contracts
- No REST endpoints to maintain
- Simpler error handling (Python exceptions throughout)

---

## Functional Requirements

### 1. Connections Screen

**Purpose:** Gateway to all organizational data sources. Users add, test, and manage database connections.

**Core Features:**
- **Add New Connection**
  - Support connection types: SQL Server, DB2, Oracle, MS Access, Excel, CSV, ODBC generic
  - Capture: server name, database name, authentication method (Windows/SQL Auth)
  - Test connection immediately upon entry
  - Encrypt credentials using Windows DPAPI equivalent before storage
  
- **Browse Databases & Tables**
  - Left panel: Tree view of all configured connections (expandable nodes)
  - Middle panel: Searchable list of tables when database selected
  - Right panel: Detailed schema (columns, data types, keys, constraints, row counts)
  - Real-time schema discovery via SQLAlchemy reflection
  
- **Curate My Data Workspace**
  - Checkbox next to each table for selection
  - Checked tables automatically appear in My Data screen
  - Multi-select capability for batch operations
  
- **Connection Management**
  - Edit existing connections (update credentials, server names)
  - Delete connections (with confirmation)
  - Refresh metadata to capture schema changes
  - Connection status indicator (green dot = connected, red = error)

**UI Layout:**
- **Left Panel (200px):** QTreeWidget showing connection tree with folder icons
- **Middle Panel (300px):** QTreeWidget with table list, checkboxes, and QLineEdit search box
- **Right Panel (flex):** Custom QWidget with QTableView showing schema details
- **Toolbar:** QToolBar with QPushButtons: "Add New Connection", "Manage Connections", "Test Connection", "Refresh Metadata"

---

### 2. My Data Screen

**Purpose:** Personalized workspace showing user's curated tables and saved queries.

**Core Features:**
- **Organized Data Access**
  - Three collapsible tree sections:
    1. **My Connections:** Tables/views saved from Connections screen (grouped by database)
    2. **DB Queries:** Single-database saved queries (grouped by database)
    3. **XDB Queries:** Cross-database saved queries (grouped by user-defined categories)
  
- **Deep Schema Exploration**
  - Select saved table → right panel shows column schema in data grid
  - "Find Unique Values" feature:
    - Check columns to analyze
    - Click "Find Unique Values" button
    - System queries each column and displays distinct values
    - Shows count + scrollable list (first 50 if many values)
    - Timestamp of last update
  
- **Query Management**
  - Select saved query → right panel shows:
    - Metadata: Last saved, last run, execution duration, record count
    - Database information
    - Display fields (SELECT list)
    - Selection fields (fields in WHERE clause)
    - Filter criteria with values
  - **Run Button:** Execute query immediately, open results in new window
  - **Edit Button:** Open query in DB Query or XDB Query builder
  - **Right-click context menu:** Delete/remove from My Data
  
- **Cross-Database Query Visibility**
  - For XDB queries, clearly show:
    - All databases involved (colored badges)
    - All tables/queries accessed (database-qualified names)
    - Complete field listings from each source
    - Full filter criteria

**UI Layout:**
- **Left Panel (200px):** QTreeWidget with three-section tree (My Connections, DB Queries, XDB Queries)
- **Right Panel (flex):** Adaptive QWidget content
  - For tables: Custom QTableView with schema + QPushButton for "Find Unique"
  - For queries: QWidget with form layout showing metadata and query definition + QPushButtons for "Run" and "Edit"

---

### 3. DB Query Screen

**Purpose:** Visual query builder for single-database operations. No SQL required.

**Core Features:**
- **Query Context Setup**
  - Left panels show: Data sources tree → Tables for selected DB → Fields for selected table
  - Double-click field → expand to show unique values inline
  - Data type displayed for each field (int, varchar, datetime, etc.)
  
- **Intelligent Filter Building (Criteria Tab)**
  - Drag field from Fields panel → drop in criteria zone
  - System creates type-aware filter control:
    - **String fields:** Match type dropdown (exact, starts with, ends with, contains) + text input
    - **Numeric fields:** Exact value checkbox + range inputs (low/high)
    - **Date fields:** Date pickers for exact date or range
    - **Limited unique values:** Checkbox list with [none] and [all] options
  - Multiple criteria stack vertically (implicit AND)
  - Remove criteria via X button
  
- **Visual Column Selection (Display Tab)**
  - Drag fields to define SELECT list
  - Fields show fully qualified names (table.field)
  - Order matters (top to bottom = left to right in results)
  - Remove fields via X button
  
- **JOIN Management (Tables Tab)**
  - System auto-tracks all tables referenced in criteria/display
  - "Tables Involved" section shows colored badges
  - **FROM clause:** Dropdown to select primary table
  - **Add Join button:** Creates new join block
    - Join type dropdown (INNER, LEFT OUTER, RIGHT OUTER, FULL OUTER)
    - Table dropdown
    - ON conditions: Field dropdowns with = operator
    - Add multiple AND conditions within join
  - Multiple join blocks supported
  - Remove join via X button
  
- **Execution & Persistence**
  - **Run Query:** Execute and open results in separate window (ag-grid)
  - **Save Query:** Store complete definition in SQLite
    - Prompt for query name
    - Save under DB Queries in My Data
    - Track metadata (last run time, duration, record count)

**UI Layout:**
- **Left Panel 1 (200px):** QTreeWidget showing My Data sources tree
- **Left Panel 2 (200px):** QTreeWidget with tables list for selected database
- **Left Panel 3 (200px):** QTreeWidget with fields list showing data types
- **Right Panel (flex):**
  - QToolBar: QPushButtons for "Run Query", "Save Query"
  - QTabWidget: Criteria | Display | Tables tabs
  - Large drop zones (custom QWidget) that populate with filter/display controls

---

### 4. XDB Query Screen

**Purpose:** Cross-database query builder. Extends DB Query with multi-source support.

**Core Features:**
- **All DB Query Features** (criteria, display, joins) with database awareness
  
- **Cross-Database Query Construction**
  - Can select tables/queries from ANY database in My Data
  - System handles backend coordination automatically
  
- **Enhanced Data Source Management**
  - Every table/field/query shows source database via:
    - Visual badges (color-coded by database type)
    - Database qualification (database.table.field notation in monospace)
  
- **Application-Level Join Management**
  - When joining tables from different databases:
    - Yellow warning banner appears
    - Explains joins execute at application level (not in database)
    - May have performance implications for large datasets
  - System retrieves from each database independently
  - Pandas performs joins in application memory
  
- **Saved Query Integration**
  - Previously saved DB Queries appear as queryable sources
  - Drag saved query → fields expand to show available columns
  - Query composition: Build complex queries from simpler ones
  - **Limitation:** Cannot use other XDB queries as sources (only My Connections and DB Queries)
  
- **Databases Tab** (replaces Tables tab)
  - **Databases Involved:** Colored badges for each source
  - **Queries Involved:** List of saved queries being used
  - **Tables Involved:** Regular tables
  - **FROM & JOIN configuration:** Same as DB Query but with database awareness

**UI Layout:**
- Identical to DB Query screen layout
- Key difference: Third tab is "Databases" instead of "Tables"
- Visual indicators throughout:
  - Teal badges for SQL Server
  - Yellow badges for saved queries
  - Database-qualified names everywhere in monospace font
  - Warning banners for cross-database operations

---

## Data Models

### SQLite Database Schema

```sql
-- Connections table
CREATE TABLE connections (
    connection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_name TEXT NOT NULL UNIQUE,
    connection_type TEXT NOT NULL, -- 'SQL_SERVER', 'DB2', 'ORACLE', 'ACCESS', 'EXCEL', 'CSV', 'ODBC'
    server_name TEXT,
    database_name TEXT,
    auth_type TEXT, -- 'WINDOWS', 'SQL_AUTH'
    encrypted_username BLOB,
    encrypted_password BLOB,
    connection_string TEXT, -- for ODBC
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_tested TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

-- Saved tables (My Data selections)
CREATE TABLE saved_tables (
    saved_table_id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id INTEGER NOT NULL,
    schema_name TEXT,
    table_name TEXT NOT NULL,
    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (connection_id) REFERENCES connections(connection_id) ON DELETE CASCADE
);

-- Cached metadata
CREATE TABLE table_metadata (
    metadata_id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id INTEGER NOT NULL,
    schema_name TEXT,
    table_name TEXT NOT NULL,
    row_count INTEGER,
    last_modified TIMESTAMP,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (connection_id) REFERENCES connections(connection_id) ON DELETE CASCADE
);

CREATE TABLE column_metadata (
    column_id INTEGER PRIMARY KEY AUTOINCREMENT,
    metadata_id INTEGER NOT NULL,
    column_name TEXT NOT NULL,
    data_type TEXT NOT NULL,
    is_nullable BOOLEAN,
    is_primary_key BOOLEAN,
    max_length INTEGER,
    FOREIGN KEY (metadata_id) REFERENCES table_metadata(metadata_id) ON DELETE CASCADE
);

CREATE TABLE unique_values_cache (
    cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
    metadata_id INTEGER NOT NULL,
    column_name TEXT NOT NULL,
    unique_values TEXT, -- JSON array
    value_count INTEGER,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (metadata_id) REFERENCES table_metadata(metadata_id) ON DELETE CASCADE
);

-- Saved queries
CREATE TABLE saved_queries (
    query_id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_name TEXT NOT NULL,
    query_type TEXT NOT NULL, -- 'DB' or 'XDB'
    category TEXT, -- for XDB queries (e.g., 'Reinsurance', 'Default')
    query_definition TEXT NOT NULL, -- JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_executed TIMESTAMP,
    execution_duration_ms INTEGER,
    record_count INTEGER
);

-- Query definition JSON structure:
/*
{
  "databases": ["database1", "database2"], // XDB only
  "from_table": "Customers",
  "from_database": "ProductionDB", // XDB only
  "joins": [
    {
      "join_type": "INNER",
      "table": "Orders",
      "database": "ProductionDB", // XDB only
      "on_conditions": [
        {"left_field": "Customers.CustomerID", "operator": "=", "right_field": "Orders.CustomerID"}
      ]
    }
  ],
  "display_fields": [
    {"table": "Customers", "field": "Name", "database": "ProductionDB"},
    {"table": "Orders", "field": "OrderDate", "database": "ProductionDB"}
  ],
  "criteria": [
    {
      "table": "Customers",
      "field": "State",
      "database": "ProductionDB",
      "type": "string",
      "match_type": "exact",
      "value": "CA"
    },
    {
      "table": "Orders",
      "field": "OrderDate",
      "database": "ProductionDB",
      "type": "date",
      "range_start": "2025-01-01",
      "range_end": "2025-12-31"
    }
  ]
}
*/

-- User preferences
CREATE TABLE user_preferences (
    preference_key TEXT PRIMARY KEY,
    preference_value TEXT
);
```

### Python Class Interfaces

Since this is an integrated Python application (no REST API), components communicate via direct method calls with type hints.

#### Core Business Logic Classes

```python
class ConnectionManager:
    """Manages database connections and credentials"""
    
    def add_connection(self, name: str, conn_type: str, server: str, 
                      database: str, auth_type: str, 
                      username: str = None, password: str = None) -> int:
        """Add new connection, returns connection_id"""
        pass
    
    def test_connection(self, connection_id: int) -> tuple[bool, str]:
        """Test connection, returns (success, message)"""
        pass
    
    def get_connections(self) -> list[dict]:
        """Get all connections"""
        pass
    
    def delete_connection(self, connection_id: int) -> bool:
        """Delete connection"""
        pass


class SchemaDiscovery:
    """Discovers and caches database metadata"""
    
    def get_tables(self, connection_id: int) -> list[dict]:
        """Get all tables for a connection"""
        pass
    
    def get_columns(self, connection_id: int, table_name: str) -> list[dict]:
        """Get columns for a table"""
        pass
    
    def get_unique_values(self, connection_id: int, table_name: str, 
                         column_name: str) -> list[Any]:
        """Get unique values for a column"""
        pass
    
    def refresh_metadata(self, connection_id: int) -> None:
        """Refresh cached metadata"""
        pass


class QueryBuilder:
    """Builds query definitions from UI state"""
    
    def create_query(self, query_type: str) -> Query:
        """Create new query object"""
        pass
    
    def add_criteria(self, query: Query, field: str, filter_config: dict) -> None:
        """Add filter criteria"""
        pass
    
    def add_display_field(self, query: Query, field: str) -> None:
        """Add field to SELECT list"""
        pass
    
    def add_join(self, query: Query, join_config: dict) -> None:
        """Add JOIN configuration"""
        pass
    
    def validate_query(self, query: Query) -> tuple[bool, str]:
        """Validate query definition, returns (is_valid, message)"""
        pass


class QueryExecutor:
    """Executes queries and returns results"""
    
    def execute_db_query(self, query: Query) -> pd.DataFrame:
        """Execute single-database query"""
        pass
    
    def execute_xdb_query(self, query: Query) -> pd.DataFrame:
        """Execute cross-database query with application-level joins"""
        pass
    
    def get_execution_metadata(self) -> dict:
        """Get last execution stats (duration, row count)"""
        pass


class QueryRepository:
    """Manages saved queries in SQLite"""
    
    def save_query(self, name: str, query_type: str, 
                   definition: dict, category: str = None) -> int:
        """Save query, returns query_id"""
        pass
    
    def get_queries(self, query_type: str = None) -> list[dict]:
        """Get all saved queries, optionally filtered by type"""
        pass
    
    def get_query_by_id(self, query_id: int) -> dict:
        """Get query definition by ID"""
        pass
    
    def update_query(self, query_id: int, definition: dict) -> bool:
        """Update query definition"""
        pass
    
    def delete_query(self, query_id: int) -> bool:
        """Delete query"""
        pass
    
    def update_execution_stats(self, query_id: int, duration_ms: int, 
                              record_count: int) -> None:
        """Update last execution statistics"""
        pass
```

#### Qt Signal/Slot Patterns

PyQt6 uses signals and slots for event-driven communication:

```python
from PyQt6.QtCore import QObject, pyqtSignal

class ConnectionsScreen(QWidget):
    # Signals emitted by UI
    connection_added = pyqtSignal(dict)  # Emit connection config
    connection_tested = pyqtSignal(int)  # Emit connection_id
    table_selected = pyqtSignal(int, str)  # Emit (connection_id, table_name)
    
    def __init__(self):
        super().__init__()
        # Connect signals to business logic
        self.connection_manager = ConnectionManager()
        self.connection_added.connect(self.on_connection_added)
    
    def on_connection_added(self, config: dict):
        """Handle connection addition"""
        connection_id = self.connection_manager.add_connection(**config)
        self.refresh_connection_tree()
```

This pattern allows loose coupling between UI and business logic.

---

## UI/UX Specifications

### Design System

**Styling Approach:**
- PyQt6 uses Qt Style Sheets (QSS) - similar syntax to CSS but for Qt widgets
- Defined in `.qss` files loaded at application startup
- Can style individual widgets or entire application
- Example: `QTabBar::tab:selected { background: white; border-bottom: 3px solid #667eea; }`

**Color Palette:**
- Primary: `#667eea` (blue-purple gradient)
- Secondary: `#764ba2` (purple)
- Success: `#28a745` (green)
- Warning: `#ffc107` (yellow)
- Danger: `#dc3545` (red)
- Background: `#f8f9fa` (light gray)
- Panel Background: `#ffffff` (white)
- Border: `#dee2e6` (medium gray)

**Typography:**
- Primary Font: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif
- Monospace Font: 'Consolas', 'Courier New', monospace (for database.table.field notation)
- Title Bar: 16px, bold, white text
- Tab Headers: 13px, semi-bold
- Body Text: 11-12px
- Small Text: 10px

**Spacing:**
- Panel padding: 10-15px
- Control spacing: 8-12px
- Section margins: 15-20px

### Application Window

- **Window Type:** QMainWindow (PyQt6)
- **Window Size:** 1600px × 900px (default), resizable
- **Minimum Size:** 1200px × 700px
- **Title Bar:** Custom styled or native Windows title bar with "SuiteView - Data Manager"
- **Ribbon Navigation:** QTabWidget with four tabs (Connections | My Data | DB Query | XDB Query)
  - Active tab: white background, blue bottom border (via QSS)
  - Hover: light gray background (via QSS)
  - Tab icons using QIcon, text using QTabWidget.addTab()
  - Badge counts displayed using custom painted labels

### Layout Structure

**All screens follow this pattern:**

```
┌─────────────────────────────────────────────────────────────┐
│ Title Bar: SuiteView - Data Manager                        │
├─────────────────────────────────────────────────────────────┤
│ Connections | My Data | DB Query | XDB Query               │
├────────┬────────┬────────┬─────────────────────────────────┤
│        │        │        │                                  │
│ Panel1 │ Panel2 │ Panel3 │      Right Panel                │
│ (Tree) │ (List) │(Fields)│      (Adaptive Content)          │
│        │        │        │                                  │
│        │        │        │                                  │
│        │        │        │                                  │
└────────┴────────┴────────┴─────────────────────────────────┘
```

- Left panels: 200px each, resizable via QSplitter widgets
- Right panel: Takes remaining space (QSplitter with stretch factor)
- All panels use QWidget with light gray backgrounds
- Panel headers: QLabel with dark gray background, uppercase 10px text
- Implemented using nested QSplitter(Qt.Orientation.Horizontal)

### Drag-and-Drop Visual Feedback

**Qt Drag-and-Drop Implementation:**
- Use QTreeWidget/QListWidget with `setDragEnabled(True)` and `setAcceptDrops(True)`
- Implement `dragEnterEvent()`, `dragMoveEvent()`, `dropEvent()` in drop zone widgets
- Use `QMimeData` to transfer field/table information
- Custom drag pixmap using `QDrag.setPixmap()` for visual feedback

**Draggable Items:**
- Fields in Fields panel (QTreeWidgetItem with drag enabled)
- Tables in Tables panel (for XDB Query)
- Cursor changes to "move" icon via `QCursor.setShape(Qt.CursorShape.DragMoveCursor)`
- Item semi-transparent while dragging (set opacity in QDrag pixmap)

**Drop Zones:**
- Default: Custom QWidget with dashed border (painted via QPainter), light background
- On hover (dragEnterEvent): Blue dashed border, blue-tinted background
- Text: QLabel with "Drag fields here to add..."

**Drop Success:**
- Drop zone widget hidden or removed (if first item)
- New filter/display control widget appears with QPropertyAnimation for smooth entry
- Control has light background, border, QPushButton for remove button

### Reference Screenshots

The application follows the visual design shown in the 10 embedded screenshots in the Word document, specifically:

1. **Screenshot 1 (My Data - XDB Queries):** Shows three-panel layout with tree navigation, table listing, and query details
2. **Screenshot 2 (XDB Query - Display):** Shows empty Display tab with drag zone
3. **Screenshot 3 (My Data - DB Queries):** Shows saved query metadata view
4. **Screenshot 4 (XDB Query - Criteria):** Shows empty Criteria tab with drag zone
5. **Screenshot 5 (My Data - Tables):** Shows table schema grid with Find Unique button
6. **Screenshot 6 (DB Query - Tables tab):** Shows FROM clause and JOIN configuration
7. **Screenshot 7 (Connections):** Shows connection tree, table checkboxes, and schema details
8. **Screenshot 8 (DB Query - Display tab):** Shows populated Display tab with fields
9. **Screenshot 9 (DB Query - Criteria tab):** Shows populated Criteria tab with filters
10. **Screenshot 10 (XDB Query - Database):** Shows Databases tab with database badges and FROM/JOIN config

---

## User Stories & Use Cases

### Epic 1: Initial Setup & Connection Management

**User Story 1.1:** As a business analyst, I want to add a SQL Server connection so I can access production data.
- User clicks "Connections" tab
- Clicks "Add New Connection" button
- Fills in: Connection name, server, database, auth type
- Clicks "Test Connection"
- System validates connection and saves encrypted credentials
- Connection appears in tree with green status dot

**User Story 1.2:** As a user, I want to browse available tables so I can understand what data exists.
- User expands connection in tree
- Clicks database node
- Middle panel populates with table list
- User selects table
- Right panel shows columns, data types, row counts

**User Story 1.3:** As a user, I want to save frequently-used tables to My Data so I don't have to search for them repeatedly.
- User checks boxes next to relevant tables
- System immediately saves to My Data
- User switches to "My Data" tab
- Sees selected tables in "My Connections" tree section

### Epic 2: Basic Query Building

**User Story 2.1:** As a business user, I want to see all customers in California without writing SQL.
- User clicks "DB Query" tab
- Selects "ProductionDB" → "Customers" table
- System populates Fields panel
- User drags "State" field to Criteria tab
- System creates string filter with dropdown
- User selects "exact match" and types "CA"
- User drags "Name", "Email", "City" fields to Display tab
- User clicks "Run Query"
- Results open in new window

**User Story 2.2:** As a user, I want to filter orders by date range so I can analyze Q4 sales.
- User drags "OrderDate" field to Criteria tab
- System creates date filter with range pickers
- User selects 10/01/2025 to 12/31/2025
- Adds display fields
- Runs query and sees filtered results

**User Story 2.3:** As a user, I want to save my query so I can run it again later.
- User builds query with criteria and display fields
- Clicks "Save Query"
- System prompts for query name
- User enters "Q4 2025 Orders"
- Query appears in My Data → DB Queries → ProductionDB

### Epic 3: Advanced Query Features

**User Story 3.1:** As an analyst, I want to join Customers and Orders tables so I can see customer purchase history.
- User adds criteria/display fields from both Customers and Orders
- Switches to Tables tab
- System shows "Tables Involved: Customers, Orders"
- User selects "Customers" in FROM dropdown
- Clicks "Add Join"
- Selects "INNER JOIN" and "Orders"
- Configures ON: Customers.CustomerID = Orders.CustomerID
- Runs query and sees joined results

**User Story 3.2:** As a user, I want to use checkbox lists for filtering so I can select multiple values easily.
- User double-clicks "State" field in Fields panel
- System expands to show unique values inline
- User drags "State" to Criteria tab
- System creates filter with checkbox list of all states
- User checks "CA", "NY", "TX"
- Query filters to only those states

**User Story 3.3:** As a user, I want to see unique values for a saved table so I can understand data distributions.
- User navigates to My Data → My Connections → ProductionDB → Customers
- Right panel shows schema grid
- User checks "City", "State", "CustomerTypeID" columns
- Clicks "Find Unique Values"
- System queries each column and displays unique values with counts
- User reviews data before building queries

### Epic 4: Cross-Database Queries

**User Story 4.1:** As an analyst, I want to combine data from SQL Server and DB2 so I can correlate production and legacy data.
- User clicks "XDB Query" tab
- Selects ProductionDB (SQL Server) → Customers table
- Adds display fields from Customers
- Selects LegacyDB (DB2) → Orders table
- Adds display fields from Orders
- Switches to Databases tab
- System shows "Databases Involved: ProductionDB (teal badge), LegacyDB (teal badge)"
- User configures FROM ProductionDB.Customers
- Adds join to LegacyDB.Orders
- Yellow warning appears: "Cross-database joins execute at application level"
- User runs query and sees combined results

**User Story 4.2:** As a user, I want to use a saved DB Query as a data source in an XDB Query so I can build on previous work.
- User previously saved "CA_Customers" query in ProductionDB
- Opens XDB Query
- Selects ProductionDB in left panel
- Sees "Query: CA_Customers" in list (distinct styling)
- Drags fields from CA_Customers query
- Combines with table from another database
- System treats saved query as a virtual table

**User Story 4.3:** As a user, I want to clearly see which databases are involved in my XDB query so I understand performance implications.
- User builds complex XDB query with 3 databases
- Databases tab shows:
  - "Databases Involved: ProductionDB, LegacyDB, FinanceDB" (colored badges)
  - "Tables Involved" with database.table notation
  - Warning banners for cross-database operations
- User understands this query will take longer than single-database queries

### Epic 5: Query Management & Iteration

**User Story 5.1:** As a user, I want to run a saved query with updated data so I can see current results.
- User navigates to My Data → DB Queries → ProductionDB → "Monthly Sales Report"
- Right panel shows query metadata (last run: 3 days ago)
- User reviews criteria, display fields, filters
- Clicks "Run Query"
- System executes and updates "last run" timestamp
- Results open in new window

**User Story 5.2:** As a user, I want to edit a saved query so I can refine the criteria.
- User finds saved query in My Data
- Clicks "Edit" button
- System opens DB Query screen with query loaded
- User modifies criteria (adds new date range)
- Clicks "Save Query"
- System updates existing query definition
- Metadata shows "last modified" timestamp

**User Story 5.3:** As a user, I want to delete old queries so My Data stays organized.
- User right-clicks saved query in My Data tree
- Context menu shows "Delete"
- User clicks, system prompts for confirmation
- User confirms, query removed from tree and database

---

## Non-Functional Requirements

### Performance

**Query Execution:**
- Single-database queries: Execute within 2 seconds for < 100K rows
- Cross-database queries: Execute within 10 seconds for < 100K rows combined
- Large result sets (> 100K rows): Stream results with progress indicator
- Schema discovery: Cache metadata, refresh only on demand
- Unique values: Cache results, show "last updated" timestamp

**UI Responsiveness:**
- Drag-and-drop: < 50ms response time
- Tab switching: Instant (< 100ms)
- Panel resizing: Smooth (60 fps)
- Tree expansion: < 100ms
- Search/filter: Update results as user types (< 200ms)

**Application Startup:**
- Cold start: < 3 seconds to display main window
- Backend ready: < 2 seconds for Python service to start
- Total to usable: < 5 seconds

### Security

**Credential Storage:**
- Encrypt all passwords using Windows DPAPI equivalent (Python `cryptography` library)
- Store encrypted credentials in SQLite database with user-specific encryption key
- Never log or display passwords in plaintext
- Connection strings sanitized in logs

**Database Connections:**
- Use connection pooling with maximum lifetime limits
- Close connections after inactivity timeout (5 minutes)
- Validate all SQL inputs to prevent injection (parameterized queries only)
- Respect database permissions (users only see what they're authorized to access)

**Application Security:**
- No remote access (localhost only for backend API)
- SQLite database file permissions: User only (Windows file ACLs)
- Electron: Disable Node integration in renderer, use context isolation
- No eval() or dynamic code execution

### Scalability

**Data Handling:**
- Support result sets up to 1 million rows (with pagination/virtualization)
- Handle databases with 1000+ tables
- Support 50+ concurrent connections to different databases
- Cached metadata can grow to 100MB without performance degradation

**User Limits:**
- Designed for 15 concurrent users (no multi-user conflicts as data is local)
- Each user maintains independent SQLite database
- No shared state between user installations

### Reliability

**Error Handling:**
- Graceful database connection failures with user-friendly messages
- Query execution errors: Display SQL error with context
- Application crashes: Auto-restart with unsaved work recovery
- Backend service crashes: Electron auto-restarts Python process

**Data Integrity:**
- SQLite transactions for all write operations
- Automatic backups of SQLite database (daily, keep last 7)
- Query definitions validated before save
- Corrupt query definitions logged and skipped (don't crash app)

**Logging:**
- Application logs: `%APPDATA%\SuiteView\logs\app.log`
- Backend logs: `%APPDATA%\SuiteView\logs\backend.log`
- Rotate logs daily, keep last 30 days
- Include timestamps, log levels, stack traces for errors

### Usability

**Learning Curve:**
- New users can build basic query within 10 minutes (with provided tutorial)
- No SQL knowledge required for core functionality
- Tooltips on all UI elements
- Help button links to online documentation

**Accessibility:**
- Keyboard navigation support throughout
- Focus indicators visible
- Color contrast ratio ≥ 4.5:1 for text
- Resizable fonts (follow Windows system settings)

**Localization:**
- Initially English only
- String externalization for future localization
- Date/time formats respect Windows regional settings
- Number formats respect Windows regional settings

### Maintainability

**Code Quality:**
- TypeScript strict mode enabled
- Python type hints throughout
- Unit test coverage ≥ 70% for business logic
- ESLint + Prettier for JavaScript/TypeScript
- Black + Flake8 for Python
- Automated tests run on every commit

**Documentation:**
- Inline code comments for complex logic
- API documentation (FastAPI auto-generates Swagger docs)
- Component documentation (Storybook for React components)
- Architecture decision records (ADRs) for major design choices

**Version Control:**
- Git repository with feature branch workflow
- Semantic versioning (MAJOR.MINOR.PATCH)
- Changelog maintained for every release
- Git tags for every release version

### Deployment & Updates

**Installation:**
- Single .exe installer (electron-builder output)
- Silent install option for IT deployment
- Installs to: `C:\Program Files\SuiteView Data Manager`
- User data in: `%APPDATA%\SuiteView`
- Uninstaller removes all application files, prompts to keep user data

**Updates:**
- Check for updates on application startup
- User prompt to install updates
- Download and install in background
- Restart application to apply update
- Rollback capability if update fails

**Versioning:**
- Display version number in About dialog
- Backend API version compatibility check
- Warn user if backend/frontend versions mismatch

---

## Development Phases

### Phase 1: Foundation (Weeks 1-2)
- Set up Python project structure with proper package organization
- Create requirements.txt and virtual environment
- Set up PyQt6 with QMainWindow and basic window
- Create SQLite database schema and initialize database
- Implement basic ConnectionManager and database access layer
- Build main application shell:
  - QMainWindow with custom title bar styling
  - QTabWidget for ribbon navigation (4 tabs)
  - QSplitter-based multi-panel layout
  - Load and apply Qt Style Sheets (.qss files)

### Phase 2: Connections Screen (Weeks 3-4)
- Implement QTreeWidget for connection hierarchy
- Build Add/Edit Connection QDialog forms
- Implement SchemaDiscovery class with SQLAlchemy reflection
- Create QTreeWidget for table list with QCheckBox integration
- Build QTableView with custom model for schema details
- Implement save-to-My-Data functionality in SQLite
- Add connection testing with QMessageBox feedback
- Implement error handling with proper Qt exception dialogs

### Phase 3: My Data Screen (Weeks 5-6)
- Build QTreeWidget with three collapsible sections
- Implement table schema view using QTableView with custom model
- Create Find Unique Values button and query execution
- Implement unique values caching in SQLite
- Build saved query detail widget with QFormLayout
- Create results window using QTableView with Pandas data model
- Implement Run Query with QProgressDialog
- Add Edit Query button that switches tabs and loads query
- Implement QMenu context menu for delete operations

### Phase 4: DB Query Screen (Weeks 7-9)
- Build three QTreeWidget panels with QSplitter layout
- Implement Qt drag-and-drop (dragEnterEvent, dropEvent, QMimeData)
- Create Criteria tab with custom QWidget controls for each data type
- Build Display tab with QListWidget for field stacking
- Create Tables tab with QComboBox and custom JOIN widgets
- Implement QueryBuilder and QueryExecutor classes
- Generate SQL using SQLAlchemy query builders
- Add Save Query with QInputDialog for name entry
- Connect to My Data screen via Qt signals

### Phase 5: XDB Query Screen (Weeks 10-12)
- Extend DB Query widgets to support multi-database selection
- Add database qualification labels throughout (using QLabel with monospace font)
- Create Databases tab widget with badge display (custom painted QWidget)
- Implement cross-database QueryExecutor using Pandas merge/join
- Add warning QFrame widgets with yellow background for cross-DB operations
- Implement saved query as data source in tree structure
- Test complex multi-database scenarios with mock data
- Add performance monitoring and timing display

### Phase 6: Polish & Testing (Weeks 13-14)
- Comprehensive testing (pytest for business logic, Qt Test for UI)
- Performance optimization (query result caching, QTableView optimization)
- Error handling improvements with proper QMessageBox dialogs
- Visual polish (QPropertyAnimation for transitions, QProgressBar for loading)
- Documentation (docstrings, user manual, tooltip text)
- Create PyInstaller spec file and test packaging
- Beta testing with 2-3 target users, collect feedback

### Phase 7: Deployment (Week 15)
- Create production build with PyInstaller:
  - `pyinstaller --onefile --windowed --icon=app.ico main.py`
  - Bundle all dependencies into single executable
- Create Windows installer (optional: using Inno Setup or NSIS)
- Deploy executable to test machines
- User training sessions with hands-on exercises
- Production rollout to 15 users (distribute .exe via network share or installer)
- Monitor for issues and collect feedback

---

## Success Criteria

### Functional Completeness
- ✅ Users can connect to SQL Server, DB2, Oracle, Access, Excel, CSV
- ✅ Users can browse schemas and save tables to My Data
- ✅ Users can build queries with visual drag-and-drop (no SQL required)
- ✅ Users can execute single-database and cross-database queries
- ✅ Users can save, edit, run, and delete queries
- ✅ Results display in high-performance data grid

### Performance Targets
- ✅ Application starts in < 5 seconds
- ✅ Single-database queries execute in < 2 seconds (< 100K rows)
- ✅ Cross-database queries execute in < 10 seconds (< 100K rows)
- ✅ UI interactions respond in < 100ms

### Usability Goals
- ✅ New users can build basic query within 10 minutes
- ✅ No SQL knowledge required
- ✅ Intuitive drag-and-drop interactions
- ✅ Clear visual feedback throughout

### Adoption Metrics
- ✅ All 15 target users actively using within 1 month
- ✅ Average 5+ queries per user per day
- ✅ 80% of users report satisfaction in survey
- ✅ 50% reduction in time to access data vs. previous methods

---

## Technical Constraints & Considerations

### Windows-Specific Considerations
- Use native Windows file paths (`%APPDATA%`, `C:\Program Files`)
- Respect Windows theme (light/dark mode if feasible)
- Proper Windows installer with add/remove programs entry
- Windows Defender exclusions may be needed for PyInstaller executable

### Database-Specific Considerations
- **SQL Server:** Use Windows authentication by default, fallback to SQL auth
- **DB2:** Requires IBM Data Server Driver installation on user machines
- **Oracle:** Requires Oracle Client installation
- **Access:** Use 32-bit ODBC driver (may require 32-bit Python build)
- **Excel:** Limited to .xlsx format, read-only recommended
- **CSV:** Support various encodings (UTF-8, Windows-1252)

### Cross-Database Query Limitations
- Performance degrades with large datasets (millions of rows)
- No optimization hints (application-level joins are brute-force)
- Memory limits: Pandas loads full result sets into RAM
- Consider pagination or warning thresholds (e.g., warn if > 500K rows)

### Electron/Python Integration Challenges
- Python backend must be packaged as standalone executable
- Port conflicts: Detect if port 8000 in use, choose alternative
- Process lifecycle: Electron must start/stop Python backend
- Error communication: Backend errors must surface in frontend UI

---

## Future Enhancements (Out of Scope for V1)

### Phase 2 Features
- SQL view/edit mode (for advanced users who want to see generated SQL)
- Scheduled query execution (run queries on schedule, email results)
- Result set export (Excel, CSV, PDF reports)
- Parameterized queries (prompt user for values at runtime)
- Query templates (pre-built queries users can customize)

### Phase 3 Features
- Collaboration (share queries between users)
- Version control for queries (track changes over time)
- Query performance analytics (identify slow queries)
- Data visualization (charts/graphs from query results)
- Python/R integration (export results to notebooks)

### Enterprise Features
- Central administration console
- Role-based access control
- Audit logging (track who ran what queries)
- Cloud deployment option
- Mobile app (view-only)

---

## Glossary

- **My Data:** User's personalized workspace showing curated tables and saved queries
- **DB Query:** Single-database query builder
- **XDB Query:** Cross-database query builder (XDB = Cross-Database)
- **Criteria:** Filter conditions applied to query (WHERE clause)
- **Display Fields:** Columns shown in query results (SELECT list)
- **FROM Clause:** Primary table in query
- **JOIN:** Combining tables based on related columns
- **Application-Level Join:** Join performed in Python/Pandas rather than database
- **Schema Discovery:** Automatic detection of database structure (tables, columns)
- **Unique Values:** Distinct values in a column (useful for filtering)
- **Metadata:** Information about data structure (table names, column types, etc.)
- **DPAPI:** Windows Data Protection API (for encrypting credentials)

---

## Appendix: Key Dependencies

### requirements.txt (All Python Dependencies)
```txt
# UI Framework
PyQt6==6.6.1
PyQt6-Qt6==6.6.1

# Database Connectivity
sqlalchemy==2.0.23
pandas==2.1.4
pyodbc==5.0.1
ibm-db==3.2.0
cx-oracle==8.3.0
openpyxl==3.1.2

# Security
cryptography==41.0.7

# Utilities
python-dateutil==2.8.2

# Development & Testing
pytest==7.4.3
pytest-qt==4.2.0
black==23.12.1
flake8==6.1.0

# Packaging
pyinstaller==6.3.0
```

### Project Structure

```text
suiteview-data-manager/
|
+-- CLAUDE.md                      (This PRD)
+-- requirements.txt               (Python dependencies)
+-- setup.py                       (Package configuration)
+-- build.spec                     (PyInstaller spec file)
|
+-- suiteview/                     (Main application package)
|   |
|   +-- __init__.py
|   +-- main.py                    (Application entry point)
|   |
|   +-- ui/                        (UI layer - PyQt6 widgets)
|   |   +-- __init__.py
|   |   +-- main_window.py         (QMainWindow)
|   |   +-- connections_screen.py  (Connections tab widget)
|   |   +-- mydata_screen.py       (My Data tab widget)
|   |   +-- dbquery_screen.py      (DB Query tab widget)
|   |   +-- xdbquery_screen.py     (XDB Query tab widget)
|   |   +-- widgets/               (Reusable custom widgets)
|   |   |   +-- __init__.py
|   |   |   +-- tree_widget.py     (Enhanced QTreeWidget)
|   |   |   +-- criteria_widget.py (Filter control widgets)
|   |   |   +-- results_grid.py    (Results QTableView)
|   |   |   +-- drop_zone.py       (Drag-and-drop zones)
|   |   +-- styles.qss             (Qt Style Sheets)
|   |
|   +-- core/                      (Business logic layer)
|   |   +-- __init__.py
|   |   +-- connection_manager.py  (Connection management)
|   |   +-- query_builder.py       (Query construction)
|   |   +-- query_executor.py      (Query execution)
|   |   +-- schema_discovery.py    (Metadata introspection)
|   |   +-- credential_manager.py  (Encryption/decryption)
|   |
|   +-- data/                      (Data access layer)
|   |   +-- __init__.py
|   |   +-- database.py            (SQLite connection)
|   |   +-- models.py              (SQLAlchemy models)
|   |   +-- repositories.py        (Data access methods)
|   |
|   +-- utils/                     (Utility modules)
|       +-- __init__.py
|       +-- config.py              (Configuration)
|       +-- logger.py              (Logging)
|
+-- resources/                     (Application resources)
|   +-- icons/                     (Application icons)
|   |   +-- app.ico
|   +-- images/                    (UI images)
|
+-- tests/                         (Test suite)
    +-- __init__.py
    +-- test_connection_manager.py
    +-- test_query_builder.py
    +-- test_query_executor.py
    +-- test_ui_components.py
```

### PyInstaller Build Command
```bash
# Development build (with console for debugging)
pyinstaller --name="SuiteView Data Manager" \
            --icon=resources/icons/app.ico \
            --add-data="suiteview/ui/styles.qss:suiteview/ui" \
            --add-data="resources:resources" \
            --hidden-import=PyQt6 \
            --hidden-import=sqlalchemy.dialects.mssql \
            --hidden-import=sqlalchemy.dialects.oracle \
            suiteview/main.py

# Production build (no console window)
pyinstaller --name="SuiteView Data Manager" \
            --icon=resources/icons/app.ico \
            --add-data="suiteview/ui/styles.qss:suiteview/ui" \
            --add-data="resources:resources" \
            --hidden-import=PyQt6 \
            --hidden-import=sqlalchemy.dialects.mssql \
            --hidden-import=sqlalchemy.dialects.oracle \
            --windowed \
            --onefile \
            suiteview/main.py
```

### Sample Entry Point (main.py)
```python
#!/usr/bin/env python3
"""SuiteView Data Manager - Main entry point"""

import sys
from PyQt6.QtWidgets import QApplication
from suiteview.ui.main_window import MainWindow
from suiteview.utils.config import load_config
from suiteview.utils.logger import setup_logging

def main():
    """Application entry point"""
    # Set up logging
    setup_logging()
    
    # Load configuration
    config = load_config()
    
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("SuiteView Data Manager")
    app.setOrganizationName("YourCompany")
    
    # Create and show main window
    window = MainWindow(config)
    window.show()
    
    # Start event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
```

---

## Contact & Support

**Development Team Lead:** [Your Name]
**Project Sponsor:** [Manager Name]
**Technical Questions:** Claude Code (AI pair programmer)
**Issue Tracking:** [GitHub/Jira URL]
**Documentation:** [Wiki/Confluence URL]

---

*This document is a living specification and will be updated as requirements evolve during development.*
