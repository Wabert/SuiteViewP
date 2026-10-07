"""Per-plancode illustration gating.

Developers: the Illustration plancode table carries a ``CanIllustrate`` flag,
enforced ONLY in packaged distribution builds (``sys.frozen``) — in dev it must
have zero effect. The flag is False for every IUL plancode (identified by the
app's own ``is_iul_plan`` criterion — an index-strategy row) and True elsewhere.

Business users (soft launch M5): only the 156 phase-1 UL plancodes in
``plancodes/phase1_allowlist.json`` may illustrate, in any build. ISWL, IUL,
the UL plancodes outside phase 1, par whole life and term are refused.
"""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

import suiteview.illustration.models.plancode_config as pc
import suiteview.illustration.ui.main_window as mw
from suiteview.illustration.core.business_mode import BUSINESS_MODE_ENV
from suiteview.illustration.core.run_gates import phase1_plancodes
from suiteview.illustration.models.index_strategies import is_iul_plan
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.ui.main_window import IllustrationWindow
from tests.plan_facts_fixtures import plan_facts

_QT_APP = None

# The exact operator-facing text the window must post for a blocked plancode.
_BLOCK_MSG = ("This plancode ({pc}) is not currently enabled for illustration "
             "in this application.")


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


# ── PlancodeConfig model ─────────────────────────────────────────────


def _minimal_table_row(plancode: str, **overrides):
    row = {
        "Plancode": plancode,
        "SA_Basis": "CurrentSA",
    }
    row.update(overrides)
    return row


def _use_table_row(monkeypatch, row):
    plancode = row["Plancode"]
    monkeypatch.setattr(pc, "load_plan_facts", lambda code: plan_facts(code))
    monkeypatch.setattr(pc, "_TABLE_CACHE", {plancode: row})
    monkeypatch.setattr(pc, "_CONFIG_CACHE", {})


def test_can_illustrate_defaults_true_when_key_absent(monkeypatch):
    # Dataclass default is True.
    assert PlancodeConfig().can_illustrate is True

    # A table row with no CanIllustrate key still loads as True — existing
    # plancodes keep illustrating.
    _use_table_row(monkeypatch, _minimal_table_row("ZZNOKEY00"))
    assert load_plancode("ZZNOKEY00").can_illustrate is True


def test_can_illustrate_reads_false_from_table(monkeypatch):
    _use_table_row(monkeypatch, _minimal_table_row("ZZBLOCK00", CanIllustrate=False))
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


# ── Business users: phase-1 allow-list (soft launch M5) ─────────────

_ALLOWLIST = (Path(pc.__file__).resolve().parent.parent / "plancodes"
              / "phase1_allowlist.json")
_ISWL_PLANCODE = "80110429"        # ISWL — CanIllustrate True, outside phase 1
_EXTRA_UL_PLANCODE = "1U145000"    # UL CanIllustrate True, not in the phase-1 list


def test_shipped_allowlist_is_the_156_phase1_ul_plancodes():
    data = json.loads(_ALLOWLIST.read_text(encoding="utf-8"))
    plancodes = data["plancodes"]
    assert len(plancodes) == len(set(plancodes)) == 156
    assert phase1_plancodes() == frozenset(plancodes)
    table = pc._load_plancode_table()
    for plancode in plancodes:
        assert plancode in table, plancode
        cfg = load_plancode(plancode)
        assert not cfg.is_iswl and not is_iul_plan(plancode), plancode
        assert cfg.can_illustrate is True, plancode
    for outside in (_IUL_PLANCODE, _ISWL_PLANCODE, _EXTRA_UL_PLANCODE):
        assert outside not in phase1_plancodes()
    assert load_plancode(_ISWL_PLANCODE).is_iswl


def _phase1_policy(plancode: str, status: str = "22"):
    return SimpleNamespace(plancode=plancode, premium_pay_status_code=status,
                           suspense_code="0")


@pytest.fixture
def business_window(monkeypatch):
    monkeypatch.setenv(BUSINESS_MODE_ENV, "1")
    return _window()


@pytest.mark.parametrize("plancode", [_IUL_PLANCODE, _ISWL_PLANCODE, _EXTRA_UL_PLANCODE])
def test_business_gate_blocks_plancodes_outside_phase1(business_window, plancode):
    win = business_window
    win.run_values_btn.setEnabled(True)
    win._illustration_data = _phase1_policy(plancode)
    assert win._apply_illustration_gate() is True
    assert win.run_values_btn.isEnabled() is False
    message = (f"Plancode {plancode} is not supported for in-force illustration "
               "in this release.")
    assert win._status_label.text() == message
    assert not win.run_notice.isHidden()
    assert message in win.run_notice.text()


def test_business_gate_allows_phase1_plancode_in_source_and_exe(business_window, monkeypatch):
    win = business_window
    for frozen in (False, True):
        monkeypatch.setattr(mw, "is_distribution_build", lambda frozen=frozen: frozen)
        win.run_values_btn.setEnabled(True)
        win._illustration_data = _phase1_policy(_ALLOWED_PLANCODE)
        assert win._apply_illustration_gate() is False
        assert win.run_values_btn.isEnabled() is True
        assert win.run_notice.isHidden()


class _DummyDb:
    def __init__(self, region):
        self.region = region

    def connect(self):
        pass

    def close(self):
        pass


@pytest.mark.parametrize("family, message", [
    ("parwl", "Participating whole life policies are not supported"),
    ("term", "Indeterminate premium term policies are not supported"),
])
def test_business_refuses_par_wl_and_term_workspaces(business_window, monkeypatch, family, message):
    win = business_window
    monkeypatch.setattr(mw, "DB2Connection", _DummyDb)
    monkeypatch.setattr(win, "_is_par_whole_life", lambda policy: family == "parwl")
    monkeypatch.setattr(win, "_is_indeterminate_term", lambda policy: family == "term")
    loaded = []
    monkeypatch.setattr(win, "_load_parwl_into_ui", lambda *a, **k: loaded.append("parwl"))
    monkeypatch.setattr(win, "_load_term_into_ui", lambda *a, **k: loaded.append("term"))
    win._policy = SimpleNamespace(exists=True, company_code="01", policy_number="W0000001",
                                  system_code="I")
    win._policy_info = {"CompanyCode": "01", "PolicyNumber": "W0000001"}
    win.run_values_btn.setEnabled(True)
    win._load_policy_into_ui("CKPR")
    assert loaded == []
    assert win._workspace_stack.currentWidget() is win.tabs
    assert win.run_values_btn.isEnabled() is False
    assert win.save_case_btn.isEnabled() is False
    assert message in win.run_notice.text()


def test_developer_par_wl_still_opens_its_workspace(monkeypatch):
    monkeypatch.delenv(BUSINESS_MODE_ENV, raising=False)
    win = _window()
    monkeypatch.setattr(mw, "DB2Connection", _DummyDb)
    monkeypatch.setattr(win, "_is_par_whole_life", lambda policy: True)
    loaded = []
    monkeypatch.setattr(win, "_load_parwl_into_ui", lambda *a, **k: loaded.append("parwl"))
    win._policy = SimpleNamespace(exists=True, company_code="01", policy_number="W0000001",
                                  system_code="I")
    win._policy_info = {"CompanyCode": "01", "PolicyNumber": "W0000001"}
    win._load_policy_into_ui("CKPR")
    assert loaded == ["parwl"]


# ── Policy status (soft launch M3) ───────────────────────────────────


@pytest.mark.parametrize("status", ["44", "45", "99", "54", "42", "21", ""])
def test_business_gate_blocks_status_outside_phase1(business_window, status):
    win = business_window
    win.run_values_btn.setEnabled(True)
    win._illustration_data = _phase1_policy(_ALLOWED_PLANCODE, status)
    assert win._apply_illustration_gate() is True
    assert win.run_values_btn.isEnabled() is False
    assert win._status_label.text().startswith(f"Policy status {status or '(blank)'} (")
    assert "not supported for in-force illustration in this release" in win.run_notice.text()


def test_business_gate_extended_term_message(business_window):
    win = business_window
    win._illustration_data = _phase1_policy(_ALLOWED_PLANCODE, "44")
    win._apply_illustration_gate()
    assert win._status_label.text() == (
        "Policy status 44 (Extended Term) is not supported for in-force "
        "illustration in this release.")


def test_business_gate_allows_premium_paying_including_suspended(business_window):
    win = business_window
    win.run_values_btn.setEnabled(True)
    policy = _phase1_policy(_ALLOWED_PLANCODE, "22")
    policy.suspense_code = "2"          # suspended stays allowed (banner on Inputs)
    win._illustration_data = policy
    assert win._apply_illustration_gate() is False
    assert win.run_values_btn.isEnabled() is True


@pytest.mark.parametrize("status, label", [
    ("32", "Waiver of Premium"), ("33", "Waiver of Charges"), ("34", "Waiver of COI"),
])
def test_business_gate_blocks_disability_waiver(business_window, status, label):
    win = business_window
    win.run_values_btn.setEnabled(True)
    win._illustration_data = _phase1_policy(_ALLOWED_PLANCODE, status)
    assert win._apply_illustration_gate() is True
    assert win.run_values_btn.isEnabled() is False
    assert win._status_label.text() == (
        f"Policy status {status} ({label}) is not supported for in-force illustration: "
        "policies on disability waiver are not illustrated in this release.")


def test_business_gate_blocks_death_claim_pending_suspense(business_window):
    win = business_window
    policy = _phase1_policy(_ALLOWED_PLANCODE)
    policy.suspense_code = "3"
    win._illustration_data = policy
    assert win._apply_illustration_gate() is True
    assert "Death Claim Pending" in win._status_label.text()


def test_developer_gets_status_warning_not_block(monkeypatch):
    monkeypatch.delenv(BUSINESS_MODE_ENV, raising=False)
    win = _window()
    win.run_values_btn.setEnabled(True)
    win._illustration_data = _phase1_policy(_ALLOWED_PLANCODE, "44")
    assert win._apply_illustration_gate() is False
    assert win.run_values_btn.isEnabled() is True
    assert "Policy status 44 (Extended Term)" in win.run_notice.text()
    assert "developer run allowed" in win.run_notice.text()
