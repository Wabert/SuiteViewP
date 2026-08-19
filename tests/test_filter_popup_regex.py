"""FilterPopup RegEx toggle behavior in the column filter box."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.ui.widgets.filter_table_view import FilterPopup

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


VALUES = ["#1", "#4", "39", "39, 76", "#1, #2, #3, 39", "A1", "4C", "#1, #4"]


def _popup():
    _app()
    return FilterPopup("Col", VALUES)


def _visible(popup):
    """Return the values currently visible in the filtered list."""
    pm = popup.proxy_model
    return {pm.data(pm.index(r, 0)) for r in range(pm.rowCount())}


def test_regex_off_by_default():
    p = _popup()
    assert p.regex_enabled is False
    assert p.regex_btn.isChecked() is False


def test_plain_substring_still_works():
    p = _popup()
    p.search_box.setText("39")
    vis = _visible(p)
    assert all("39" in v for v in vis)
    assert "39" in vis and "39, 76" in vis
    assert "#1" not in vis


def test_toggle_enables_regex():
    p = _popup()
    p.regex_btn.setChecked(True)
    assert p.regex_enabled is True


def test_regex_or_matches_either():
    # "39" OR "#4"  ->  regex  39|#4
    p = _popup()
    p.regex_btn.setChecked(True)
    p.search_box.setText("39|#4")
    vis = _visible(p)
    for v in vis:
        assert ("39" in v) or ("#4" in v)
    assert "39" in vis          # has 39
    assert "#4" in vis          # has #4
    assert "#1, #4" in vis      # has #4
    assert "A1" not in vis      # has neither


def test_regex_and_matches_both_in_any_order():
    # "39" AND "#4" (both present, any order)  ->  regex  (?=.*39)(?=.*#4)
    p = _popup()
    p.regex_btn.setChecked(True)
    p.search_box.setText(r"(?=.*39)(?=.*#4)")
    vis = _visible(p)
    for v in vis:
        assert ("39" in v) and ("#4" in v)
    # none of the sample values contain BOTH 39 and #4
    assert vis == set()


def test_invalid_regex_flags_and_shows_nothing():
    p = _popup()
    p.regex_btn.setChecked(True)
    p.search_box.setText("[")  # unterminated class -> invalid
    assert _visible(p) == set()
    assert "Invalid" in p.info_label.text()


def test_toggle_off_returns_to_substring():
    p = _popup()
    p.regex_btn.setChecked(True)
    p.search_box.setText("39|#4")
    assert len(_visible(p)) > 0
    # Turn regex off: "39|#4" is now a literal substring, matches nothing
    p.regex_btn.setChecked(False)
    assert _visible(p) == set()
