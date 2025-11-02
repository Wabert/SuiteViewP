# Mainframe Navigator Quick Start Guide

## How to Access Your Mainframe Datasets

### Step 1: Go to the Connections Tab
Click on the **"Connections"** tab at the top of the application (it's the last tab on the right).

### Step 2: Find the MAINFRAME_FTP Folder
In the left panel of the Connections screen, you'll see a tree view with different connection types:
- DB2
- SQL_SERVER
- ACCESS
- EXCEL
- CSV
- FIXED_WIDTH
- **MAINFRAME_FTP** ← Look for this folder!

### Step 3: Expand the MAINFRAME_FTP Folder
Click the arrow next to **MAINFRAME_FTP** to expand it and see your mainframe connections inside.

### Step 4: Click on a Connection
Click on any mainframe connection name (e.g., "PRODESA Mainframe", "Production", etc.)

**What happens next:**
- The application automatically switches to the **Mainframe Nav** tab
- Your selected connection is loaded and connected
- You can now browse datasets!

---

## Using the Mainframe Navigator

Once you're on the Mainframe Nav screen with a connection loaded:

### Browse by Path
1. Type a dataset path in the **Dataset Path** box at the top
   - Example: `D03.AA0139` or `D03.AA0139.CKAS`
2. Click the **Go** button or press Enter

### Navigate Like Windows Explorer
- **Left Panel (Dataset Tree)**: Shows folder hierarchy
  - Click folders to navigate
  - Expand folders to see subdirectories
  
- **Middle Panel (Contents)**: Shows files and folders with details
  - **Double-click folders** to navigate into them
  - **Single-click members/files** to preview them
  
- **Right Panel (Preview)**: Shows file contents
  - Preview shows first 2000 lines
  - Click **View All** to see complete file
  - Click **Export to File** to save locally
  - Click **Load to My Data** to import (coming soon)

### Tips
- Use **Refresh** button to reload current view
- Right-click items for context menus with additional options
- The tree view remembers expanded folders as you navigate

---

## Common Dataset Paths

Here are some examples of dataset path formats:

```
D03.AA0139                    # High-level qualifier
D03.AA0139.CKAS              # Dataset group
D03.AA0139.CKAS.CIRF         # Subdataset
D03.AA0139.CKAS.CIRF.DATA    # Specific dataset
```

To view a member within a dataset:
1. Navigate to the dataset (e.g., `D03.AA0139.CKAS`)
2. The members will appear in the Contents panel
3. Click a member to preview it

---

## Troubleshooting

**"No Connection" error when clicking Go?**
- Make sure you've selected a MAINFRAME_FTP connection from the Connections tab first

**Can't see any datasets?**
- Check that the path is correct (no typos)
- Verify you have permissions to access that dataset on the mainframe
- Try starting with just the high-level qualifier (e.g., `D03`)

**Preview not loading?**
- Some datasets may be too large or binary
- Try exporting to a file instead
- Check the connection is still active (click Refresh)

---

## Need Help?

If you're not sure what datasets to browse, ask your team members for common dataset paths they use. The paths typically follow your organization's mainframe naming conventions.

Happy browsing! 🚀
