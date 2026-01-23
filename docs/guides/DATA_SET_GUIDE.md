# Data Set Feature - Quick Start Guide

## Overview
The **Data Set** screen allows you to build dynamic SQL queries using Python scripting. This is perfect for creating reusable queries where the SQL changes based on runtime parameters.

## Key Features
- ✅ Write Python code to generate SQL dynamically
- ✅ Auto-detect parameters from function signature
- ✅ Python syntax highlighting in code editor
- ✅ Runtime parameter prompts with validation
- ✅ SQL preview before execution
- ✅ Auto-detect output fields from SQL
- ✅ Save/Load Data Sets for reuse
- ✅ Future: Use in XDB queries

## How to Use

### 1. Create a New Data Set
- Click **➕ New Data Set**
- Enter a name and optional description
- Go to **Script Builder** tab

### 2. Write Your Python Function
Write a function named `build_query` that:
- Takes parameters (will be prompted at runtime)
- Returns a SQL string

**Example:**
```python
def build_query(policy_nums=None, state=None, as_of_date=None):
    """
    Build dynamic SQL based on parameters
    
    Args:
        policy_nums: Policy number(s) - single value or list
        state: State code (optional)
        as_of_date: As-of date for filtering (optional)
    
    Returns:
        SQL string
    """
    sql = "SELECT PolicyNumber, State, EffectiveDate, Premium FROM Policies WHERE 1=1"
    
    # Handle policy numbers
    if policy_nums is not None:
        if isinstance(policy_nums, list):
            # Multiple policy numbers
            nums = ",".join(f"'{n}'" for n in policy_nums)
            sql += f" AND PolicyNumber IN ({nums})"
        else:
            # Single policy number
            sql += f" AND PolicyNumber = '{policy_nums}'"
    
    # Optional state filter
    if state is not None:
        sql += f" AND State = '{state}'"
    
    # Optional date filter
    if as_of_date is not None:
        sql += f" AND EffectiveDate <= '{as_of_date}'"
    
    return sql
```

### 3. Validate Your Script
- Click **✓ Validate Script**
- System automatically detects parameters from function signature
- Switch to **Parameters** tab to see detected parameters

### 4. Define Display Fields
Two options:
- **Auto-detect**: Click **🔍 Auto-Detect from SQL** (runs with sample params)
- **Manual**: Click **➕ Add Field** to add fields one by one

### 5. Save Your Data Set
- Click **💾 Save**
- Data Set is saved to `~/.suiteview/datasets/`

### 6. Run Your Data Set
- Click **▶️ Run Data Set**
- Dialog appears prompting for parameter values
- Fill in required parameters (marked with *)
- Optional: Click **🔍 Preview SQL** to see generated SQL
- Click **OK** to execute

## Parameter Types
The system auto-detects parameter types from:
1. **Type annotations** (if provided)
2. **Default values** (if provided)

**Supported types:**
- `text` - String values
- `number` - Integer or float
- `date` - Date strings
- `list` - Multiple values (one per line in dialog)
- `boolean` - Checkbox

**Parameter behavior:**
- Parameters with `=None` default → **Optional**
- Parameters without defaults → **Required**

## Tips & Tricks

### Load Template
Click **📄 Load Template** to get a starter template

### Parameter Inference
```python
def build_query(
    policy_num,              # Required text (no default)
    amount=100,              # Optional number (has default)
    active=True,             # Optional boolean
    states=None,             # Optional (type inferred from usage)
    date: str = None         # Optional text (type annotation)
):
```

### Handling Lists
At runtime, list parameters show a text area where users enter one value per line:
```
12345
67890
11111
```

Your code receives: `['12345', '67890', '11111']`

### SQL Best Practices
- Always start with `WHERE 1=1` for easy appending
- Use f-strings for readability
- Quote strings: `f"'{value}'"`
- Don't quote numbers: `f"{value}"`
- Handle None checks for optional parameters
- Use `isinstance()` to check for lists vs single values

### Error Handling
```python
def build_query(table_name, limit=100):
    if not table_name:
        raise ValueError("table_name is required")
    
    # Validate limit
    if limit < 1:
        limit = 100
    
    return f"SELECT * FROM {table_name} LIMIT {limit}"
```

## File Storage
Data Sets are stored as JSON files in:
```
~/.suiteview/datasets/
  ├── Policy Analysis.json
  ├── Monthly Report.json
  └── Custom Query.json
```

Each file contains:
- Name & description
- Python script code
- Parameters (auto-detected)
- Display fields
- Created/modified timestamps
- Connection info (for future XDB integration)

## Future Integration with XDB
The Data Set feature is designed to integrate with XDB Query functionality:
- Define parameterized queries once
- Reference them in XDB queries to join data across sources
- Parameters will flow through to XDB execution

## Keyboard Shortcuts in Script Editor
- **Ctrl+S** - Save Data Set
- **Tab** - Indent (in script)
- **Shift+Tab** - Unindent
- Standard text editing shortcuts work

## Example Use Cases

### 1. Date Range Query
```python
def build_query(start_date, end_date):
    return f"""
    SELECT * FROM Transactions 
    WHERE TransactionDate BETWEEN '{start_date}' AND '{end_date}'
    ORDER BY TransactionDate
    """
```

### 2. Multi-Table with Optional Filters
```python
def build_query(join_table=None, filter_status=None):
    sql = "SELECT p.*, c.CustomerName FROM Policies p"
    
    if join_table == "Customers":
        sql += " INNER JOIN Customers c ON p.CustomerID = c.CustomerID"
    
    sql += " WHERE 1=1"
    
    if filter_status:
        sql += f" AND p.Status = '{filter_status}'"
    
    return sql
```

### 3. Dynamic Column Selection
```python
def build_query(columns=None):
    if columns is None or len(columns) == 0:
        cols = "*"
    else:
        cols = ", ".join(columns)
    
    return f"SELECT {cols} FROM MyTable"
```

## Troubleshooting

### "Script must contain a 'build_query' function"
Make sure your function is named exactly `build_query` (case-sensitive)

### "Syntax error in script"
Check your Python syntax - use Validate Script to see the error

### "build_query must return a string (SQL)"
Ensure your function returns a SQL string, not None or other type

### Parameters not detected
- Click **✓ Validate Script** after editing
- Check function signature has parameter names

### Fields not auto-detected
- Make sure SQL is valid SELECT statement
- Try adding fields manually if SQL is complex

## Navigation
The Data Set screen is located in the main navigation between **Data Package** and **XDB Query** tabs.

---

**Version:** 1.0  
**Created:** December 19, 2025  
**Location:** SuiteView Data Manager → Data Set Tab
