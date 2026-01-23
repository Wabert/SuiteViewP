# SuiteView Data Manager - Windows Setup Guide

## Quick Start (Run from Source)

### Prerequisites
- Windows 10 or 11
- Python 3.13 or later (recommended)
- 500 MB free disk space

### Installation Steps

#### 1. Install Python
1. Go to https://www.python.org/downloads/
2. Download Python 3.13 or later
3. Run the installer
4. **IMPORTANT**: Check ✅ "Add Python to PATH"
5. Click "Install Now"

#### 2. Verify Python Installation
Open Command Prompt (Win+R, type `cmd`, press Enter) and run:
```cmd
python --version
```
You should see: `Python 3.13.x` or higher

#### 3. Set Up the Project
1. Copy the entire `SuiteViewP` folder to your Windows machine
2. Navigate to the project folder in Command Prompt:
```cmd
cd C:\path\to\SuiteViewP
```

#### 4. Create Virtual Environment
```cmd
python -m venv venv
```

#### 5. Activate Virtual Environment

**For Command Prompt:**
```cmd
venv\Scripts\activate.bat
```

**For PowerShell:**
```powershell
venv\Scripts\Activate.ps1
```

**Note:** If PowerShell gives an error about execution policy, run this first:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

You should now see `(venv)` at the beginning of your command prompt.

#### 6. Install Dependencies
```cmd
pip install -r requirements.txt
```

This will install:
- PyQt6 (UI framework)
- SQLAlchemy (database toolkit)
- Pandas (data manipulation)
- Cryptography (credential encryption)
- OpenPyXL (Excel file support)
- PyODBC (ODBC database connections)

#### 7. Run the Application
```cmd
python -m suiteview.main
```

The application window should open!

---

## Building a Standalone Executable (Optional)

If you want to create a `.exe` file that can run without Python installed:

### Step 1: Activate Virtual Environment
```cmd
venv\Scripts\activate.bat
```

### Step 2: Run Build Script
```cmd
python build_windows.py
```

### Step 3: Find Your Executable
The standalone `.exe` will be created in:
```
dist\SuiteView Data Manager.exe
```

You can:
- Copy this `.exe` to any Windows computer
- No Python installation required
- No dependencies needed
- File size: ~50-70 MB

---

## Setting Up ODBC Drivers (For Database Connections)

To connect to SQL Server, DB2, or other ODBC databases:

### SQL Server
1. Download **Microsoft ODBC Driver for SQL Server**:
   - https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
2. Install the appropriate version (x64 for most systems)
3. Create ODBC Data Sources:
   - Press Win+R, type `odbcad32.exe`, press Enter
   - Go to "User DSN" tab
   - Click "Add"
   - Select "ODBC Driver 17 for SQL Server" or "SQL Server"
   - Configure your connection details

### DB2
1. Download **IBM Data Server Driver**:
   - https://www.ibm.com/support/pages/download-db2-fix-packs-version-db2-linux-unix-and-windows
2. Install the driver
3. Configure DSN in ODBC Administrator (same as above)

### Access
- Access drivers are built into Windows
- No additional installation needed for `.mdb` and `.accdb` files

---

## Troubleshooting

### "Python is not recognized as an internal or external command"
**Solution:** Python is not in your PATH. Reinstall Python and check "Add Python to PATH" during installation.

### "pip is not recognized..."
**Solution:** Run:
```cmd
python -m pip install --upgrade pip
```

### PyQt6 Installation Fails
**Solution:** Make sure you have the latest pip:
```cmd
python -m pip install --upgrade pip
pip install PyQt6
```

### "Cannot activate virtual environment" (PowerShell)
**Solution:** Run PowerShell as Administrator and execute:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Application Won't Start - "Failed to execute script"
**Solution:**
1. Make sure all dependencies are installed: `pip install -r requirements.txt`
2. Check Python version: `python --version` (must be 3.10+)
3. Try running from source instead of .exe

### ODBC Connection Fails
**Solution:**
1. Verify ODBC driver is installed
2. Test the DSN in ODBC Administrator:
   - Win+R → `odbcad32.exe`
   - Select your DSN → Click "Configure" → Click "Test Data Source"
3. Make sure the database server is accessible from your network

### Excel Files Won't Load
**Solution:**
1. Make sure file isn't open in Excel
2. Verify file format (.xlsx or .xls)
3. Check file permissions (not read-only)

---

## Running on Startup (Optional)

To have SuiteView start automatically with Windows:

### Option 1: Create Shortcut in Startup Folder
1. Create a batch file `start_suiteview.bat`:
```batch
@echo off
cd C:\path\to\SuiteViewP
call venv\Scripts\activate.bat
python -m suiteview.main
```

2. Press Win+R, type `shell:startup`, press Enter
3. Create a shortcut to your batch file in this folder

### Option 2: Use the .exe
1. Build the executable (see above)
2. Create a shortcut to the `.exe`
3. Press Win+R, type `shell:startup`, press Enter
4. Copy the shortcut to this folder

---

## Updating the Application

To update to a new version:

1. Activate virtual environment:
```cmd
venv\Scripts\activate.bat
```

2. Update dependencies:
```cmd
pip install -r requirements.txt --upgrade
```

3. Run the application:
```cmd
python -m suiteview.main
```

---

## Uninstalling

### If Running from Source:
1. Delete the project folder
2. (Optional) Uninstall Python if not needed for other projects

### If Using .exe:
1. Delete the executable file
2. Delete application data folder:
   - Press Win+R, type `%APPDATA%\SuiteView`, press Enter
   - Delete this folder

---

## Performance Tips

1. **Use ODBC over Linked Files**: ODBC connections are faster than Excel/CSV for large datasets
2. **Limit Result Sets**: Use filters to reduce the number of rows returned
3. **Close Unused Connections**: Right-click connections and delete ones you don't use
4. **Regular Maintenance**: Clear cached metadata periodically (refresh button)

---

## Support & Development

- **Documentation**: See `CLAUDE.md` for complete product specifications
- **Logs**: Application logs are stored in `%APPDATA%\SuiteView\logs\`
- **Database**: User data is stored in `%APPDATA%\SuiteView\suiteview.db`

---

## System Requirements

### Minimum:
- Windows 10 (64-bit)
- 4 GB RAM
- 1 GB free disk space
- 1280x720 display resolution

### Recommended:
- Windows 11 (64-bit)
- 8 GB RAM
- 2 GB free disk space (for data caching)
- 1920x1080 display resolution

---

## Next Steps

After installation:

1. **Add Your First Connection**:
   - Click the "+ New" button in the CONNECTIONS panel
   - Choose your connection type (ODBC, Excel, Access, CSV, or Fixed Width)
   - Fill in the details and test the connection

2. **Explore Your Data**:
   - Browse tables and columns
   - Check boxes to add tables to "My Data"
   - View unique values in columns

3. **Build Your First Query**:
   - Go to the "DB Query" tab
   - Select your data source
   - Drag fields to create filters and select display columns
   - Run your query!

Enjoy using SuiteView Data Manager!
