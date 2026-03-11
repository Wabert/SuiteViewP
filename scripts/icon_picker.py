"""
Icon Picker - Preview icons for category buttons
A standalone utility for selecting and previewing Unicode icons.
"""
import sys
from pathlib import Path

# Add parent directory to path (in case suiteview imports are needed later)
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, 
                              QPushButton, QLabel, QGridLayout, QScrollArea, QWidget)
from PyQt6.QtCore import Qt

class IconPickerDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pick a Category Icon")
        self.resize(600, 500)
        
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("<h2>Click an icon to see how it looks as a category button</h2>")
        layout.addWidget(header)
        
        # Preview area
        preview_layout = QHBoxLayout()
        preview_layout.addWidget(QLabel("Preview:"))
        self.preview_btn = QPushButton("◆ General ▾")
        self.preview_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 3px 10px;
                text-align: left;
                font-size: 9pt;
                font-weight: 500;
                color: #202124;
            }
            QPushButton:hover {
                background-color: #E8EAED;
                border-color: #DADCE0;
            }
        """)
        preview_layout.addWidget(self.preview_btn)
        preview_layout.addStretch()
        layout.addLayout(preview_layout)
        
        # Selected icon display
        self.selected_label = QLabel("Selected: ◆ (U+25C6)")
        self.selected_label.setStyleSheet("font-size: 12pt; padding: 10px;")
        layout.addWidget(self.selected_label)
        
        # Scroll area for icons
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(5)
        
        # Icons organized by category
        icons = [
            # Geometric shapes
            ("◆", "Black Diamond", "U+25C6"),
            ("◇", "White Diamond", "U+25C7"),
            ("●", "Black Circle", "U+25CF"),
            ("○", "White Circle", "U+25CB"),
            ("■", "Black Square", "U+25A0"),
            ("□", "White Square", "U+25A1"),
            ("▲", "Black Triangle", "U+25B2"),
            ("△", "White Triangle", "U+25B3"),
            ("▶", "Black Right Triangle", "U+25B6"),
            ("▷", "White Right Triangle", "U+25B7"),
            ("★", "Black Star", "U+2605"),
            ("☆", "White Star", "U+2606"),
            ("✦", "Black Four Star", "U+2726"),
            ("✧", "White Four Star", "U+2727"),
            
            # Arrows and pointers
            ("➤", "Black Right Pointer", "U+27A4"),
            ("►", "Black Right Pointer 2", "U+25BA"),
            ("▸", "Small Black Right Triangle", "U+25B8"),
            ("➜", "Heavy Right Arrow", "U+279C"),
            ("⯈", "Right Triangle Arrow", "U+2BC8"),
            
            # Bullets and markers
            ("•", "Bullet", "U+2022"),
            ("‣", "Triangular Bullet", "U+2023"),
            ("⁃", "Hyphen Bullet", "U+2043"),
            ("◉", "Fisheye", "U+25C9"),
            ("◎", "Bullseye", "U+25CE"),
            ("⦿", "Circled Bullet", "U+29BF"),
            
            # Misc symbols
            ("§", "Section Sign", "U+00A7"),
            ("¶", "Pilcrow", "U+00B6"),
            ("†", "Dagger", "U+2020"),
            ("‡", "Double Dagger", "U+2021"),
            ("※", "Reference Mark", "U+203B"),
            ("⌘", "Command Key", "U+2318"),
            ("⚙", "Gear", "U+2699"),
            ("⚡", "Lightning", "U+26A1"),
            ("☰", "Hamburger Menu", "U+2630"),
            ("≡", "Identical To", "U+2261"),
            ("⋮", "Vertical Ellipsis", "U+22EE"),
            ("⋯", "Midline Ellipsis", "U+22EF"),
            
            # Brackets and containers
            ("⟨", "Left Angle Bracket", "U+27E8"),
            ("⟩", "Right Angle Bracket", "U+27E9"),
            ("⌂", "House", "U+2302"),
            ("⌐", "Reversed Not", "U+2310"),
            
            # Box drawing / folders
            ("╬", "Box Cross", "U+256C"),
            ("╋", "Heavy Cross", "U+254B"),
            ("┿", "Light Cross", "U+253F"),
            
            # Common emojis (may not render on all systems)
            ("📂", "Open Folder", "U+1F4C2"),
            ("📁", "Folder", "U+1F4C1"),
            ("📑", "Bookmark Tabs", "U+1F4D1"),
            ("🏷", "Label", "U+1F3F7"),
            ("📌", "Pushpin", "U+1F4CC"),
            ("📎", "Paperclip", "U+1F4CE"),
            ("🔖", "Bookmark", "U+1F516"),
            ("🗀", "Folder Outline", "U+1F5C0"),
            ("🗁", "Open Folder Outline", "U+1F5C1"),
            ("🗂", "Card Index Dividers", "U+1F5C2"),
            ("🗃", "Card File Box", "U+1F5C3"),
            ("🗄", "File Cabinet", "U+1F5C4"),
            ("📋", "Clipboard", "U+1F4CB"),
            ("📚", "Books", "U+1F4DA"),
            ("📖", "Open Book", "U+1F4D6"),
            ("🔷", "Blue Diamond", "U+1F537"),
            ("🔶", "Orange Diamond", "U+1F536"),
            ("🔹", "Small Blue Diamond", "U+1F539"),
            ("🔸", "Small Orange Diamond", "U+1F538"),
        ]
        
        row = 0
        col = 0
        max_cols = 6
        
        for icon, name, code in icons:
            btn = QPushButton(f"{icon}")
            btn.setFixedSize(60, 40)
            btn.setToolTip(f"{name}\n{code}")
            btn.setStyleSheet("font-size: 16pt;")
            btn.clicked.connect(lambda checked, i=icon, n=name, c=code: self.select_icon(i, n, c))
            grid.addWidget(btn, row, col)
            
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
        
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        # Copy button
        copy_btn = QPushButton("Copy Selected Icon to Clipboard")
        copy_btn.clicked.connect(self.copy_to_clipboard)
        layout.addWidget(copy_btn)
        
        self.selected_icon = "◆"
    
    def select_icon(self, icon, name, code):
        self.selected_icon = icon
        self.preview_btn.setText(f"{icon} General ▾")
        self.selected_label.setText(f"Selected: {icon} - {name} ({code})")
    
    def copy_to_clipboard(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.selected_icon)
        self.selected_label.setText(f"Copied: {self.selected_icon}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    dialog = IconPickerDialog()
    dialog.exec()
