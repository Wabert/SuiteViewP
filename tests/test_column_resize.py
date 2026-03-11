"""Test script to verify column resizing functionality in FilterTableView"""

import sys
import pandas as pd
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel
from suiteview.ui.widgets.filter_table_view import FilterTableView


def main():
    """Test the FilterTableView with column resize functionality"""
    app = QApplication(sys.argv)
    
    # Create main window
    window = QMainWindow()
    window.setWindowTitle("Column Resize Test")
    window.setGeometry(100, 100, 800, 600)
    
    # Create central widget
    central = QWidget()
    layout = QVBoxLayout(central)
    
    # Add instructions label
    instructions = QLabel(
        "<b>Test Instructions:</b><br>"
        "1. <b>Sort Icon</b>: Click the small icon on the far right of each header to toggle sort (▲/▼)<br>"
        "2. <b>Resize Column</b>: Hover near the edge of a column header until you see the resize cursor (↔), then drag to resize<br>"
        "3. <b>Auto-fit Column</b>: Double-click the edge of a column header to auto-fit the column width<br>"
        "4. <b>Filter Popup</b>: Click anywhere else in the header (not the sort icon or edge) to open the filter dialog<br>"
        "5. <b>Filter Search</b>: When filter opens, search box is auto-focused - just start typing! Press Enter to apply filter<br>"
        "6. <b>Tab Spacing</b>: Notice the space between tabs at the top is now transparent, blending with the background"
    )
    instructions.setWordWrap(True)
    layout.addWidget(instructions)
    
    # Create sample data
    data = {
        'Name': ['Alice Johnson', 'Bob Smith', 'Charlie Brown', 'David Wilson', 'Eve Davis',
                 'Frank Miller', 'Grace Lee', 'Henry Taylor', 'Ivy Anderson', 'Jack White'],
        'Age': [25, 30, 35, 40, 45, 28, 33, 38, 42, 29],
        'City': ['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix',
                 'New York', 'Chicago', 'Los Angeles', 'Houston', 'Phoenix'],
        'Salary': [50000, 60000, 70000, 80000, 90000, 55000, 65000, 75000, 85000, 58000],
        'Department': ['Sales', 'Marketing', 'IT', 'Finance', 'HR',
                       'Sales', 'IT', 'Marketing', 'Finance', 'Sales']
    }
    df = pd.DataFrame(data)
    
    # Create and add FilterTableView
    filter_table = FilterTableView()
    filter_table.set_dataframe(df)
    layout.addWidget(filter_table)
    
    window.setCentralWidget(central)
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
