"""
mock_audit_coverages_tab.py
============================
Generates a PyQt6 mockup screenshot for the CL_POLREC_02_03_09_67
(Coverages & Riders) audit criteria panel.

Run:
    python tools/mock_audit_coverages_tab.py

Output:
    docs/audit/mockup_coverages_tab.png
"""

import sys
import json

import os
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QComboBox, QCheckBox, QListWidget,
    QAbstractItemView, QStyledItemDelegate, QFrame,
)
from PyQt6.QtCore import Qt, QSize


# ── Shared helpers (match mock_audit_tab.py styling) ─────────────────────

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
    return group


# ── Load items from ListBoxItems.md ──────────────────────────────────────

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


# ── Main mockup generator ───────────────────────────────────────────────

def create_coverage_group(title, items, is_base=False):
    grp_rider = QGroupBox(title)
    grp_rider.setFixedWidth(225)
    grid_rider = QGridLayout(grp_rider)
    grid_rider.setContentsMargins(4, 14, 4, 4)
    grid_rider.setHorizontalSpacing(6)
    grid_rider.setVerticalSpacing(2)

    def add_row(grid, row, label, widget, col_start=1, col_span=1):
        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(lbl, row, 0)
        grid.addWidget(widget, row, col_start, 1, col_span)

    def add_combo_row(grid, row, label, values):
        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(lbl, row, 0)
        cb = QComboBox()
        cb.addItems([""] + values)
        grid.addWidget(cb, row, 1)

    r = 0
    add_row(grid_rider, r, "Plancode:", QLineEdit()); r += 1
    add_combo_row(grid_rider, r, "Prod Line (02):", get_items(items, "Product Line Code (02)")); r += 1
    add_combo_row(grid_rider, r, "Prod Ind (02):", get_items(items, "Product Indicator (02) - All covs")); r += 1
    add_row(grid_rider, r, "Form Number:", QLineEdit()); r += 1

    add_combo_row(grid_rider, r, "Rateclass (67):", get_items(items, "Rateclass Code (67)")); r += 1
    add_combo_row(grid_rider, r, "Sex Code (67):", get_items(items, "Sex Code (67)")); r += 1
    add_combo_row(grid_rider, r, "Sex Code (02):", get_items(items, "Sex Code (02)")); r += 1
    add_combo_row(grid_rider, r, "Person:", get_items(items, "Covered Person")); r += 1
    add_combo_row(grid_rider, r, "Lives Cov (02):", get_items(items, "Lives Covered Code (02)")); r += 1
    add_combo_row(grid_rider, r, "Change Type (02):", get_items(items, "Change Type (02)")); r += 1
    add_combo_row(grid_rider, r, "COLA Ind:", get_items(items, "COLA Ind")); r += 1
    add_combo_row(grid_rider, r, "GIO/FIO:", get_items(items, "GIO/FIO")); r += 1
    add_combo_row(grid_rider, r, "Addl Plancode:", get_items(items, "Additional Plancode Criteria")); r += 1

    chk_row = QWidget()
    chk_lay = QHBoxLayout(chk_row)
    chk_lay.setContentsMargins(0, 0, 0, 0)
    chk_lay.addWidget(QCheckBox("Table (03)"))
    chk_lay.addWidget(QCheckBox("Flat (03)"))
    grid_rider.addWidget(chk_row, r, 0, 1, 2); r += 1

    if not is_base:
        chk_post = QCheckBox("Post Issue")
        grid_rider.addWidget(chk_post, r, 0, 1, 2); r += 1

    def add_range(row_idx, label_text):
        lbl = QLabel(label_text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid_rider.addWidget(lbl, row_idx, 0, 1, 2)
        rng_row = QWidget()
        rng_lay = QHBoxLayout(rng_row)
        rng_lay.setContentsMargins(6, 0, 0, 0)
        rng_lay.setSpacing(4)
        lo = QLineEdit(); lo.setPlaceholderText("Min")
        hi = QLineEdit(); hi.setPlaceholderText("Max")
        rng_lay.addWidget(lo)
        rng_lay.addWidget(QLabel("to"))
        rng_lay.addWidget(hi)
        grid_rider.addWidget(rng_row, row_idx + 1, 0, 1, 2)

    add_range(r, "Issue Date:"); r += 2
    add_range(r, "Change Date:"); r += 2

    return grp_rider


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

    items = load_items()
    main_widget = QWidget()
    main_widget.resize(1100, 680)
    main_layout = QHBoxLayout(main_widget)
    main_layout.setSpacing(6)

    # ================================================================
    # COLUMN 1 – Valuation + Policy Toggles
    # ================================================================
    col1 = QVBoxLayout()

    grp_val = QGroupBox("Valuation (02)")
    grp_val.setFixedWidth(200)
    grid_val = QGridLayout(grp_val)
    grid_val.setContentsMargins(4, 14, 4, 4)
    grid_val.setHorizontalSpacing(6)
    grid_val.setVerticalSpacing(2)

    val_fields = ["Class:", "Base:", "Sub:", "Val Mort Table:", "RPU Mort Table:", "ETI Mort Table:", "NFO Int Rate:"]

    for i, lbl_text in enumerate(val_fields):
        lbl = QLabel(lbl_text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid_val.addWidget(lbl, i, 0)
        le = QLineEdit()
        le.setFixedWidth(50)
        grid_val.addWidget(le, i, 1)

    chk_val_class = QCheckBox("Val Class ≠ PlanDesc Class")
    grid_val.addWidget(chk_val_class, len(val_fields), 0, 1, 2)

    col1.addWidget(grp_val)

    # -- Policy-Level Toggles --
    grp_toggles = QGroupBox("Policy-Level (02/09)")
    grp_toggles.setFixedWidth(200)
    toggle_layout = QVBoxLayout(grp_toggles)
    toggle_layout.setContentsMargins(4, 14, 4, 4)
    toggle_layout.setSpacing(2)

    toggles = [
        "Multiple Base Covs (02)",
        "Cov has GIO ind (02)",
        "Cov has COLA ind (02)",
        "Skipped Cov Rein (09)",
        "CV rate > 0 base cov (02)",
        "GCV > Current CV (ISWL)",
        "GCV < Current CV (ISWL)",
    ]
    for t in toggles:
        toggle_layout.addWidget(QCheckBox(t))

    col1.addWidget(grp_toggles)

    # -- Non Trad Indicator (moved here from col2) --
    col1.addWidget(create_enabled_listbox("Non Trad Indicator (02)", get_items(items, "Non Trad Indicator (02)"), visible_rows=2))

    # -- Curr Specified Amt (moved here from col2) --
    grp_sa = QGroupBox("Curr Specified Amt (02)")
    grp_sa.setFixedWidth(200)
    sa_lay = QHBoxLayout(grp_sa)
    sa_lay.setContentsMargins(4, 14, 4, 4)
    sa_min = QLineEdit(); sa_min.setPlaceholderText("Min"); sa_min.setFixedWidth(70)
    sa_max = QLineEdit(); sa_max.setPlaceholderText("Max"); sa_max.setFixedWidth(70)
    sa_lay.addWidget(sa_min)
    sa_lay.addWidget(QLabel("to"))
    sa_lay.addWidget(sa_max)
    sa_lay.addStretch()
    col1.addWidget(grp_sa)

    col1.addStretch()

    # ================================================================
    # COLUMN 2 – Listbox Selectors Group 2
    # ================================================================
    col2 = QVBoxLayout()
    grp_init_term = create_enabled_listbox("Init Term Period (02)", get_items(items, "Init Term Period (02)"), visible_rows=16)
    grp_init_term.setMinimumWidth(160)
    col2.addWidget(grp_init_term)

    # -- Mortality Table Codes --
    mort_json_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "suiteview", "polview", "data", "ckaptb32_mortality_tables.json",
    )
    mort_items = []
    try:
        with open(mort_json_path, "r", encoding="utf-8") as f:
            mort_data = json.load(f)
        seen = set()
        for entry in mort_data:
            code = entry.get("mortality_code", "").strip()
            desc = entry.get("description", "").strip()
            if code and code not in seen:
                seen.add(code)
                mort_items.append(f"{code} - {desc}")
        mort_items.sort(key=lambda s: s.split(" - ")[0])
    except Exception as e:
        print(f"Warning: Could not load mortality table JSON: {e}")
        mort_items = ["(could not load)"]

    grp_mort = QGroupBox("Mortality Table Codes")
    grp_mort.setMinimumWidth(160)
    # Distinct style: teal/slate border + label to indicate display-only reference
    grp_mort.setStyleSheet("""
        QGroupBox {
            border: 2px solid #5B8C85;
        }
        QGroupBox::title {
            background-color: #5B8C85;
            color: #E0E0E0;
        }
    """)
    mort_layout = QVBoxLayout(grp_mort)
    mort_layout.setContentsMargins(4, 14, 4, 4)
    mort_layout.setSpacing(2)
    mort_list = QListWidget()
    mort_list.setStyleSheet(MY_LIST_STYLE)
    mort_list.setItemDelegate(_TightItemDelegate(mort_list))
    mort_list.setUniformItemSizes(True)
    mort_list.addItems(mort_items)
    mort_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    mort_list.setFixedHeight(min(len(mort_items), 12) * _TightItemDelegate.ROW_H + 2)
    mort_layout.addWidget(mort_list)
    col2.addWidget(grp_mort)

    col2.addStretch()



    # ================================================================
    # COLUMN 3 – Base Coverage (Rider-style)
    # ================================================================
    col3 = QVBoxLayout()
    col3.addWidget(create_coverage_group("Base Coverage (02)", items, is_base=True))
    col3.addStretch()

    # ================================================================
    # COLUMN 4 – Rider 1
    # ================================================================
    col4 = QVBoxLayout()
    col4.addWidget(create_coverage_group("Rider 1 Criteria", items, is_base=False))
    col4.addStretch()

    # ================================================================
    # COLUMN 5 – Rider 2
    # ================================================================
    col5 = QVBoxLayout()
    col5.addWidget(create_coverage_group("Rider 2 Criteria", items, is_base=False))
    col5.addStretch()


    # ── Assemble ─────────────────────────────────────────────────────
    main_layout.addLayout(col1)
    main_layout.addLayout(col2)
    main_layout.addLayout(col3)
    main_layout.addLayout(col4)
    main_layout.addLayout(col5)
    main_layout.addStretch()

    main_widget.show()
    app.processEvents()

    pixmap = main_widget.grab()
    out_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "docs", "audit", "mockup_coverages_tab.png",
    )
    pixmap.save(out_path)
    print(f"Mockup saved to {out_path}")


if __name__ == "__main__":
    generate_mockup()
