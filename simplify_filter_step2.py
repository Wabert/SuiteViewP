# Script to replace FilterPopup with simplified multi-select list

with open(r'c:\Dev\SuiteViewP\suiteview\ui\widgets\filter_table_view.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the init_ui method in FilterPopup
old_init_ui_start = '''    def init_ui(self):
        """Initialize the filter popup UI"""
        from PyQt6.QtWidgets import QListView
        from PyQt6.QtCore import QTimer, QAbstractListModel'''

# Find where init_ui ends (at the next method definition)
init_ui_start = content.find(old_init_ui_start)
if init_ui_start == -1:
    print("ERROR: Could not find init_ui method")
    exit(1)

# Find the next method after init_ui
next_method_pattern = '\n    def filter_list(self, search_text: str):'
next_method_pos = content.find(next_method_pattern, init_ui_start)

if next_method_pos == -1:
    print("ERROR: Could not find end of init_ui method")
    exit(1)

# Extract parts
before_init_ui = content[:init_ui_start]
after_init_ui = content[next_method_pos:]

# New simplified init_ui implementation
new_init_ui = '''    def init_ui(self):
        """Initialize the filter popup UI"""
        # Create a widget to hold everything
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)

        # Top bar with close button
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #666;
                font-size: 14px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                color: #000;
                background-color: #f0f0f0;
                border-radius: 3px;
            }
        """)
        close_btn.clicked.connect(self.close)
        top_bar.addWidget(close_btn)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Search values...")
        self.search_box.setFixedHeight(24)
        self.search_box.setStyleSheet("""
            QLineEdit {
                padding: 2px 6px;
                font-size: 10px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QLineEdit:focus {
                border: 1px solid #3498db;
            }
        """)
        self.search_box.textChanged.connect(self.filter_list)
        self.search_box.returnPressed.connect(self.apply_filter)
        layout.addWidget(self.search_box)

        # Control buttons row
        button_row = QHBoxLayout()
        button_row.setSpacing(4)
        
        # (Clear Filter) button
        clear_btn = QPushButton("Clear Filter")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 9px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        clear_btn.clicked.connect(self.clear_filter)
        button_row.addWidget(clear_btn)
        
        # Select All button
        select_all_btn = QPushButton("All")
        select_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 9px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        select_all_btn.clicked.connect(self.select_all)
        button_row.addWidget(select_all_btn)
        
        # Deselect All button
        deselect_all_btn = QPushButton("None")
        deselect_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 9px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        deselect_all_btn.clicked.connect(self.deselect_all)
        button_row.addWidget(deselect_all_btn)
        
        button_row.addStretch()
        layout.addLayout(button_row)

        # Create multi-select list widget
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list_widget.setMinimumWidth(200)
        self.list_widget.setMaximumWidth(400)
        self.list_widget.setMinimumHeight(250)
        self.list_widget.setMaximumHeight(400)
        self.list_widget.setStyleSheet("""
            QListWidget {
                font-size: 10px;
                border: 1px solid #ccc;
            }
            QListWidget::item {
                padding: 2px;
            }
            QListWidget::item:hover {
                background-color: #e8f0fa;
            }
            QListWidget::item:selected {
                background-color: #3498db;
                color: white;
            }
        """)
        
        # Add all values to the list
        self.list_widget.addItems(self.all_unique_values)
        
        # Select items that are in current_selection
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.text() in self.current_selection:
                item.setSelected(True)
        
        layout.addWidget(self.list_widget)

        # Info label
        self.info_label = QLabel(f"Showing all {len(self.all_unique_values):,} values")
        self.info_label.setStyleSheet("font-size: 9px; color: #666; padding: 2px;")
        layout.addWidget(self.info_label)

        # OK button
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 15px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        ok_btn.clicked.connect(self.apply_filter)
        layout.addWidget(ok_btn)

        # Add widget action
        action = QWidgetAction(self)
        action.setDefaultWidget(container)
        self.addAction(action)

        self.setStyleSheet("""
            QMenu {
                background-color: white;
                border: 2px solid #3498db;
                border-radius: 5px;
            }
        """)
        
        # Auto-focus the search box when the popup opens
        QTimer.singleShot(0, self.search_box.setFocus)
'''

# Assemble new content
new_content = before_init_ui + new_init_ui + after_init_ui

# Write updated file
with open(r'c:\Dev\SuiteViewP\suiteview\ui\widgets\filter_table_view.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("✓ Replaced init_ui with simplified multi-select list")
