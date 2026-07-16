"""Tests for the Display-tab sort-priority reindex helpers.

These exercise the pure priority-management logic (no Qt widgets) that keeps
sort-order integers contiguous and cascades edits, mirroring the behavior the
user asked for: setting a column to priority N bumps the current N, N+1, ...
down by one.
"""
import unittest

from suiteview.audit.tabs._sort_controls import (
    handle_direction_changed, handle_order_edited, renumber, order_by_specs,
)


class FakeCtrl:
    def __init__(self):
        self._dir = ""
        self._order = 0

    @property
    def direction(self):
        return self._dir

    @property
    def order(self):
        return self._order

    def set_order(self, value):
        self._order = max(0, int(value or 0))

    def set_direction(self, value):
        self._dir = (value or "").upper()
        if not self._dir:
            self._order = 0


class FakeRow:
    def __init__(self, name):
        self.name = name
        self.sort_ctrl = FakeCtrl()


def _orders(rows):
    return {r.name: r.sort_ctrl.order for r in rows}


class SortReindexTests(unittest.TestCase):
    def _rows(self, n):
        return [FakeRow(chr(ord("A") + i)) for i in range(n)]

    def _activate(self, rows, direction="ASC"):
        for row in rows:
            row.sort_ctrl.set_direction(direction)
            handle_direction_changed(rows, row)

    def test_activation_appends_at_end(self):
        rows = self._rows(3)
        self._activate(rows)
        self.assertEqual(_orders(rows), {"A": 1, "B": 2, "C": 3})

    def test_deactivation_renumbers_contiguously(self):
        rows = self._rows(3)
        self._activate(rows)
        rows[1].sort_ctrl.set_direction("")  # turn B off
        handle_direction_changed(rows, rows[1])
        self.assertEqual(_orders(rows), {"A": 1, "B": 0, "C": 2})

    def test_edit_inserts_and_cascades(self):
        # Four sorted columns 1,2,3,4 plus a fifth activated -> 5.
        rows = self._rows(5)
        self._activate(rows)
        self.assertEqual(_orders(rows), {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5})
        # Set the fifth (E) to priority 2 -> existing 2,3,4 become 3,4,5.
        handle_order_edited(rows, rows[4], 2)
        self.assertEqual(
            _orders(rows), {"A": 1, "E": 2, "B": 3, "C": 4, "D": 5})

    def test_edit_clamps_above_max(self):
        rows = self._rows(3)
        self._activate(rows)
        handle_order_edited(rows, rows[0], 99)  # A -> last
        self.assertEqual(_orders(rows), {"B": 1, "C": 2, "A": 3})

    def test_edit_clamps_below_one(self):
        rows = self._rows(3)
        self._activate(rows)
        handle_order_edited(rows, rows[2], 0)  # C -> first
        self.assertEqual(_orders(rows), {"C": 1, "A": 2, "B": 3})

    def test_renumber_ignores_unsorted_rows(self):
        rows = self._rows(3)
        rows[0].sort_ctrl.set_direction("ASC")
        rows[0].sort_ctrl.set_order(5)
        rows[2].sort_ctrl.set_direction("DESC")
        rows[2].sort_ctrl.set_order(9)
        renumber(rows)
        self.assertEqual(_orders(rows), {"A": 1, "B": 0, "C": 2})

    def test_order_by_specs_filters_and_sorts(self):
        specs = [
            {"column": "A", "sort": "ASC", "sort_order": 2},
            {"column": "B", "sort": "", "sort_order": 0},
            {"column": "C", "sort": "DESC", "sort_order": 1},
        ]
        result = order_by_specs(specs)
        self.assertEqual([s["column"] for s in result], ["C", "A"])


if __name__ == "__main__":
    unittest.main()
