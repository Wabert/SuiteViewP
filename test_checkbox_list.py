# Quick test to verify checkbox functionality
from PyQt6.QtWidgets import QApplication, QListView
from PyQt6.QtCore import QAbstractListModel, Qt, QModelIndex
from PyQt6.QtGui import QStandardItemModel, QStandardItem
import sys

app = QApplication(sys.argv)

# Test with QStandardItemModel (has built-in checkbox support)
model = QStandardItemModel()
for i in range(10):
    item = QStandardItem(f"Item {i}")
    item.setCheckable(True)
    item.setCheckState(Qt.CheckState.Checked)
    model.appendRow(item)

view = QListView()
view.setModel(model)
view.show()

sys.exit(app.exec())
