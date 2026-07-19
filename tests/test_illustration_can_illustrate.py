"""Per-plancode CanIllustrate gating (distribution-only).

The Illustration plancode table carries a ``CanIllustrate`` flag. It is
enforced ONLY in packaged distribution builds (``sys.frozen``) — in dev it must
have zero effect. The flag is False for every IUL plancode (identified by the
app's own ``is_iul_plan`` criterion — an index-strategy row) and True elsewhere.
"""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

import suiteview.illustration.models.plancode_config as pc
import suiteview.illustration.ui.main_window as mw
from suiteview.illustration.models.index_strategies import is_iul_plan
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.ui.main_window import IllustrationWindow

_QT_APP = None

# The exact operator-facing text the window must post for a blocked plancode.
_BLOCK_MSG = ("This plancode ({pc}) is not currently enabled for illustration "
             "in this application.")


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


# ── PlancodeConfig model ─────────────────────────────────────────────


def test_can_illustrate_defaults_true_when_key_absent(monkeypatch):
    # Dataclass default is True.
    assert PlancodeConfig().can_illustrate is True

    # A table row with no CanIllustrate key still loads as True — existing
    # plancodes keep illustrating.
    monkeypatch.setattr(pc, "_TABLE_CACHE", {"ZZNOKEY00": {"Plancode": "ZZNOKEY00"}})
    monkeypatch.setattr(pc, "_CONFIG_CACHE", {})
    assert load_plancode("ZZNOKEY00").can_illustrate is True


def test_can_illustrate_reads_false_from_table(monkeypatch):
    monkeypatch.setattr(
        pc, "_TABLE_CACHE",
        {"ZZBLOCK00": {"Plancode": "ZZBLOCK00", "CanIllustrate": False}})
    monkeypatch.setattr(pc, "_CONFIG_CACHE", {})
    assert load_plancode("ZZBLOCK00").can_illustrate is False


def test_shipped_table_flags_every_iul_false_and_others_true():
    """Guards against drift: the shipped table must carry False for exactly
    the IUL plancodes (the app's is_iul_plan criterion) and True elsewhere."""
    table = pc._load_plancode_table()
    assert table, "plancode table did not load"
    iul_false = []
    for plancode in table:
        cfg = load_plancode(plancode)
        if is_iul_plan(plancode):
            assert cfg.can_illustrate is False, f"{plancode} is IUL but not blocked"
            iul_false.append(plancode)
        else:
            assert cfg.can_illustrate is True, f"{plancode} is non-IUL but blocked"
    # There ARE IULs in the shipped table (sanity — the assertion above is not
    # vacuously satisfied).
    assert len(iul_false) >= 1


# ── Distribution-only enforcement in the window ──────────────────────

# A blocked plancode (IUL) and an allowed one (declared-rate UL) taken straight
# from the shipped table, so the tests exercise real config data.
_IUL_PLANCODE = "1U144600"      # IUL08 — CanIllustrate False
_ALLOWED_PLANCODE = "1U143900"  # EXECUL — CanIllustrate True


def _window():
    _app()
    return IllustrationWindow()


def test_gate_has_no_effect_in_dev(monkeypatch):
    win = _window()
    monkeypatch.setattr(mw, "is_distribution_build", lambda: False)

    win.run_values_btn.setEnabled(True)
    win._show_status("Loaded policy X")
    win._illustration_data = SimpleNamespace(plancode=_IUL_PLANCODE)

    assert win._apply_illustration_gate() is False
    # Dev: even a blocked plancode leaves Run Values enabled and posts no notice.
    assert win.run_values_btn.isEnabled() is True
    assert "not currently enabled" not in win._status_label.text()


def test_gate_blocks_iul_in_distribution(monkeypatch):
    win = _window()
    monkeypatch.setattr(mw, "is_distribution_build", lambda: True)

    win.run_values_btn.setEnabled(True)
    win._illustration_data = SimpleNamespace(plancode=_IUL_PLANCODE)

    assert win._apply_illustration_gate() is True
    assert win.run_values_btn.isEnabled() is False
    assert win._status_label.text() == _BLOCK_MSG.format(pc=_IUL_PLANCODE)


def test_gate_reenables_when_allowed_plancode_loads(monkeypatch):
    win = _window()
    monkeypatch.setattr(mw, "is_distribution_build", lambda: True)

    # Block first...
    win.run_values_btn.setEnabled(True)
    win._illustration_data = SimpleNamespace(plancode=_IUL_PLANCODE)
    assert win._apply_illustration_gate() is True
    assert win.run_values_btn.isEnabled() is False

    # ...then a different, allowed policy loads (the load path re-enables the
    # button before the gate runs). The gate leaves it enabled, no notice.
    win.run_values_btn.setEnabled(True)
    win._show_status("Loaded policy Y")
    win._illustration_data = SimpleNamespace(plancode=_ALLOWED_PLANCODE)
    assert win._apply_illustration_gate() is False
    assert win.run_values_btn.isEnabled() is True
    assert "not currently enabled" not in win._status_label.text()
