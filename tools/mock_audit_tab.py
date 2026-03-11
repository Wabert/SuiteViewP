import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QComboBox, QCheckBox, QListWidget,
    QAbstractItemView, QStyledItemDelegate
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap

class _TightItemDelegate(QStyledItemDelegate):
    """Forces a fixed compact row height on QListWidget items."""
    ROW_H = 16

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        return QSize(sh.width(), self.ROW_H)

MY_LIST_STYLE = """
    QListWidget {
        font-size: 11px;
        border: none;
        background-color: transparent;
        outline: none;
        padding: 0px;
        margin: 0px;
    }
    QListWidget::item {
        padding: 0px 4px;
        margin: 0px;
        border: none;
        min-height: 0px;
        color: #000;
    }
    QListWidget::item:hover   { background-color: rgba(0, 0, 0, 15); }
    QListWidget::item:selected { background-color: rgba(0, 0, 0, 30); font-weight: bold; }
"""

def create_enabled_listbox(title, items, visible_rows=None):
    group = QGroupBox()
    group.setCheckable(True)
    group.setChecked(False)
    group.setTitle(title)
    
    layout = QVBoxLayout(group)
    layout.setContentsMargins(4, 4, 4, 4)
    layout.setSpacing(2)
    
    listbox = QListWidget()
    listbox.setStyleSheet(MY_LIST_STYLE)
    listbox.setItemDelegate(_TightItemDelegate(listbox))
    listbox.setUniformItemSizes(True)
    
    listbox.addItems(items)
    listbox.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    
    if visible_rows is None:
        visible_rows = len(items)
        if visible_rows < 3:
            visible_rows = 3
        if visible_rows > 12:
            visible_rows = 12
            
    # Calculate exact height needed, adding a tiny bit for borders
    listbox.setFixedHeight((visible_rows * _TightItemDelegate.ROW_H) + 2)
    layout.addWidget(listbox)
    
    return group

def create_range_input(title):
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    layout.addWidget(QLabel(title))
    low_input = QLineEdit()
    low_input.setPlaceholderText("Min")
    low_input.setFixedWidth(80)
    high_input = QLineEdit()
    high_input.setPlaceholderText("Max")
    high_input.setFixedWidth(80)
    layout.addWidget(low_input)
    layout.addWidget(QLabel("to"))
    layout.addWidget(high_input)
    layout.addStretch()
    return container

def create_field(title, widget):
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    layout.addWidget(QLabel(title))
    layout.addWidget(widget)
    layout.addStretch()
    return container

def generate_mockup():
    app = QApplication(sys.argv)
    
    app.setStyleSheet("""
        QWidget { background-color: #F5F5F5; font-family: "Segoe UI", Arial, sans-serif; }
        QGroupBox {
            background-color: #ffffff;
            border: 2px solid #1E5BA8;
            border-radius: 8px;
            margin-top: 18px;
            margin-bottom: 0px;
            padding: 0px;
            padding-top: 12px;
            font-size: 11px;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 3px 10px;
            background-color: #1E5BA8;
            color: #C0C0C0;
            border-radius: 4px;
            left: 10px;
            top: 2px;
        }
        QLineEdit, QComboBox { padding: 2px; font-size: 11px; background-color: #ffffff; }
        QLabel { background-color: transparent; }
        QCheckBox { background-color: transparent; }
    """)

    main_widget = QWidget()
    main_widget.resize(1200, 650)
    main_layout = QHBoxLayout(main_widget)
    
    # Load actual items from markdown
    items = {}
    current_key = None
    md_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs', 'audit', 'ListBoxItems.md')
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('### '):
                    current_key = line[4:].strip()
                    items[current_key] = []
                elif line.startswith('- ') and current_key:
                    items[current_key].append(line[2:])
    except Exception as e:
        print(f"Warning: Could not load ListBoxItems.md: {e}")

    def get_items(title):
        return items.get(title, ["Item 1", "Item 2", "Item 3"])

    # Column 1: General Info & Dates
    col1 = QVBoxLayout()
    
    # Identifiers
    group_ids = QGroupBox("Identifiers")
    grid_ids = QGridLayout(group_ids)
    grid_ids.setContentsMargins(4, 14, 4, 4)
    grid_ids.setHorizontalSpacing(6)
    grid_ids.setVerticalSpacing(2)
    
    def add_id_row(row, title, widget_or_layout):
        lbl = QLabel(title)
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid_ids.addWidget(lbl, row, 0)
        if isinstance(widget_or_layout, QWidget):
            grid_ids.addWidget(widget_or_layout, row, 1)
        else:
            grid_ids.addLayout(widget_or_layout, row, 1)

    pol_layout = QHBoxLayout()
    pol_layout.setContentsMargins(0, 0, 0, 0)
    pol_layout.setSpacing(4)
    pol_prefix = QLineEdit()
    pol_num = QLineEdit()
    pol_layout.addWidget(pol_prefix)
    pol_layout.addWidget(pol_num)
    add_id_row(0, "Policy:", pol_layout)

    company_combo = QComboBox()
    company_combo.addItems(["", "01 - ANICO", "04 - ANTEX"])
    add_id_row(1, "Company:", company_combo)
    
    market_combo = QComboBox()
    market_combo.addItem("")
    add_id_row(2, "Market:", market_combo)
    
    add_id_row(3, "3 div Branch #:", QLineEdit())
    add_id_row(4, "Loan Charge Rate:", QLineEdit())
    
    chkbx_billing = QCheckBox("Billing Suspended (66)")
    grid_ids.addWidget(chkbx_billing, 5, 0, 1, 2)
    
    col1.addWidget(group_ids)
    
    # Ranges
    group_ranges = QGroupBox("Ranges")
    grid_ranges = QGridLayout(group_ranges)
    grid_ranges.setContentsMargins(2, 12, 2, 2)
    grid_ranges.setHorizontalSpacing(4)
    grid_ranges.setVerticalSpacing(1)
    
    ranges = [
        "Paid To Date:", "GPE Date (51/66):", "Application Date (01):",
        "BIL Commence DT:", "Last Financial Date:", "Billing Prem Amt:"
    ]
    for i, title in enumerate(ranges):
        lbl_title = QLabel(title)
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid_ranges.addWidget(lbl_title, i, 0)
        low_input = QLineEdit()
        low_input.setPlaceholderText("Min")
        low_input.setFixedWidth(105)
        grid_ranges.addWidget(low_input, i, 1)
        lbl = QLabel("to")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid_ranges.addWidget(lbl, i, 2)
        high_input = QLineEdit()
        high_input.setPlaceholderText("Max")
        high_input.setFixedWidth(105)
        grid_ranges.addWidget(high_input, i, 3)
        
    col1.addWidget(group_ranges)
    col1.addStretch()


    # Column 2: Status & Codes (ListBoxes)
    col2 = QVBoxLayout()
    
    status_state_layout = QHBoxLayout()
    status_box = create_enabled_listbox("Status Code (01)", get_items("Status Code (01)"), visible_rows=20)
    status_box.setFixedWidth(190)
    state_box = create_enabled_listbox("State", get_items("State"), visible_rows=20)
    state_box.setFixedWidth(100)
    status_state_layout.addWidget(status_box)
    status_state_layout.addWidget(state_box)
    status_state_layout.addStretch() # keep them narrow
    
    col2.addLayout(status_state_layout)
    col2.addWidget(create_enabled_listbox("Billing Form (01)", get_items("Billing Form (01)")))
    col2.addWidget(create_enabled_listbox("Bill Mode (01)", get_items("Bill Mode (01)")))
    col2.addStretch()

    # Column 3: Product Specific & Riders
    col3 = QVBoxLayout()
    col3.addWidget(create_enabled_listbox("Def. Life Insurance (66)", get_items("Definition of Life Insurance (66)")))
    col3.addWidget(create_enabled_listbox("Grace Indicator (51/66)", get_items("Grace Indicator (51 or 66)")))
    col3.addWidget(create_enabled_listbox("Grace Period Rule (66)", get_items("Grace Period Rule Code (66)")))
    col3.addWidget(create_enabled_listbox("Last Entry Code (01)", get_items("Last Entry Code (01)")))
    col3.addWidget(create_enabled_listbox("Trad Overloan Ind (01)", get_items("Trad Overloan Ind (01)")))
    col3.addWidget(create_enabled_listbox("Death Benefit Option (66)", get_items("Death Benefit Option (66)")))
    col3.addStretch()

    # Column 4: Whole Life Options
    col4 = QVBoxLayout()
    col4.addWidget(create_enabled_listbox("Primary Div Option (01)", get_items("Primary & Secondary Dividend Option (01)")))
    col4.addWidget(create_enabled_listbox("Secondary Div Option (01)", get_items("Primary & Secondary Dividend Option (01)")))
    col4.addWidget(create_enabled_listbox("NFO Code (01)", get_items("NFO code (01)")))
    col4.addWidget(create_enabled_listbox("Loan Type (01)", get_items("Loan Type (01)")))
    col4.addWidget(create_enabled_listbox("Suspense Code (01)", get_items("Suspense Code (01)")))
    col4.addStretch()

    main_layout.addLayout(col1, 20)
    main_layout.addLayout(col2, 30)
    main_layout.addLayout(col3, 35)
    main_layout.addLayout(col4, 15)
    
    main_widget.show()
    # Give it a moment to layout
    app.processEvents()
    
    pixmap = main_widget.grab()
    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs', 'audit', 'mockup_policy_tab.png')
    pixmap.save(out_path)
    print(f"Mockup saved to {out_path}")
    
if __name__ == '__main__':
    generate_mockup()
