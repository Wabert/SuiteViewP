"""
mock_audit_common_tab.py
============================
Generates a PyQt6 mockup screenshot for the "Common" audit criteria panel,
which contains commonly used fields like Product Line Code (02).

Run:
    python tools/mock_audit_common_tab.py

Output:
    docs/audit/mockup_common_tab.png
"""

import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QListWidget, QAbstractItemView, QStyledItemDelegate
)
from PyQt6.QtCore import Qt, QSize


class _TightItemDelegate(QStyledItemDelegate):
    ROW_H = 16
    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        return QSize(sh.width(), self.ROW_H)

MY_LIST_STYLE = """
    QListWidget {
        font-size: 11px; border: none; background-color: transparent;
        outline: none; padding: 0px; margin: 0px;
    }
    QListWidget::item {
        padding: 0px 4px; margin: 0px; border: none;
        min-height: 0px; color: #000;
    }
    QListWidget::item:hover   { background-color: rgba(0,0,0,15); }
    QListWidget::item:selected { background-color: rgba(0,0,0,30); font-weight: bold; }
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

    listbox.setFixedHeight((visible_rows * _TightItemDelegate.ROW_H) + 2)
    layout.addWidget(listbox)
    layout.addStretch()
    return group


def load_items():
    items = {}
    current_key = None
    md_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "docs", "audit", "ListBoxItems.md",
    )
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("### "):
                    current_key = line[4:].strip()
                    items[current_key] = []
                elif line.startswith("- ") and current_key:
                    items[current_key].append(line[2:])
    except Exception as e:
        print(f"Warning: Could not load ListBoxItems.md: {e}")
    return items


def get_items(items, title):
    return items.get(title, ["Item 1", "Item 2", "Item 3"])


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
    """)

    items = load_items()
    main_widget = QWidget()
    main_widget.resize(300, 300)
    main_layout = QHBoxLayout(main_widget)
    main_layout.setSpacing(6)

    # ================================================================
    # COMMON FIELDS
    # ================================================================
    col1 = QVBoxLayout()
    
    grp_prd_line = create_enabled_listbox(
        "Product Line Code (02)", 
        get_items(items, "Product Line Code (02)")
    )
    grp_prd_line.setFixedWidth(240)
    col1.addWidget(grp_prd_line)
    col1.addStretch()

    # ── Assemble ─────────────────────────────────────────────────────
    main_layout.addLayout(col1)
    main_layout.addStretch()

    main_widget.show()
    app.processEvents()

    pixmap = main_widget.grab()
    out_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "docs", "audit", "mockup_common_tab.png",
    )
    pixmap.save(out_path)
    print(f"Mockup saved to {out_path}")


if __name__ == "__main__":
    generate_mockup()
