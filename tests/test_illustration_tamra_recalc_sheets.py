"""TAMRA sheets on the TEFRA/TAMRA recalc detail pages.

Three cases, keyed by the change's position in the 7-pay window:
  * outside the window, no new period  -> "no recalc needed" statement;
  * inside the window, no new period   -> 7-pay calc detail + MEC back-test;
  * material change (new period)       -> 7-pay calc detail + "new period
    begins on MM/DD/YYYY" statement.

Covers the engine classification (``_recalc_guideline_on_change``), the
back-test builder (``_seven_pay_backtest``), and the sheet rendering
(``GuidelineRecalcDetailView``).
"""
import os
from datetime import date
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.monthly_guideline import GuidelineSolveResult
from suiteview.illustration.models.input_set import PolicyChangeEvent, PolicyChangeKind
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData

CHANGE_DATE = date(2026, 6, 9)


# ── Engine classification ─────────────────────────────────────────────────


def _recalc(monkeypatch, policy, *, material=False, av=5_000.0):
    monkeypatch.setattr(
        calc_engine, "_solve_guideline_state",
        lambda *_a, **_k: GuidelineSolveResult(glp=120.0, gsp=240.0, seven_pay=48.0))
    monkeypatch.setattr(
        calc_engine, "_safe_guideline_pv_recalc_detail", lambda *_a, **_k: {})
    monkeypatch.setattr(
        calc_engine, "_safe_seven_pay_pv_detail",
        lambda *_a, **_k: {"premium_label": "7-Pay"})
    return calc_engine._recalc_guideline_on_change(
        policy, PlancodeConfig(),
        PolicyChangeEvent(
            kind=PolicyChangeKind.FACE_AMOUNT,
            effective_date=CHANGE_DATE, value=80_000.0),
        attained_age=45,
        change_date=CHANGE_DATE,
        before=GuidelineSolveResult(glp=96.0, gsp=192.0, seven_pay=36.0),
        av=av,
        material_change=material,
    )


def _policy(seven_pay_start):
    return IllustrationPolicyData(
        glp=96.0, gsp=240.0,
        tamra_7pay_level=60.0,
        tamra_7pay_start_date=seven_pay_start,
        tamra_7pay_start_av=1_000.0,
    )


def test_recalc_within_period_classifies_and_carries_pv_detail(monkeypatch):
    policy = _policy(date(2024, 6, 9))
    detail = _recalc(monkeypatch, policy)

    assert detail["tamra_case"] == "within_period"
    assert detail["tamra_year_at_change"] == 3
    assert detail["seven_pay_window_start"] == date(2024, 6, 9)
    assert detail["seven_pay_prior"] == 60.0
    assert detail["seven_pay_new"] == 48.0
    assert detail["seven_pay_pv"] == {"premium_label": "7-Pay"}
    # No new period: the window start is untouched.
    assert policy.tamra_7pay_start_date == date(2024, 6, 9)


def test_recalc_outside_period_states_no_recalc_needed(monkeypatch):
    policy = _policy(date(2015, 6, 9))
    detail = _recalc(monkeypatch, policy)

    assert detail["tamra_case"] == "no_recalc"
    assert detail["tamra_year_at_change"] == 12
    assert "seven_pay_pv" not in detail


def test_material_change_starts_new_period_at_change_date(monkeypatch):
    policy = _policy(date(2015, 6, 9))
    detail = _recalc(monkeypatch, policy, material=True, av=5_000.0)

    assert detail["tamra_case"] == "new_period"
    assert detail["seven_pay_prior_start"] == date(2015, 6, 9)
    assert detail["seven_pay_window_start"] == CHANGE_DATE
    assert detail["seven_pay_start_av"] == 5_000.0
    assert detail["seven_pay_pv"] == {"premium_label": "7-Pay"}
    assert policy.tamra_7pay_start_date == CHANGE_DATE


# ── MEC back-test builder ─────────────────────────────────────────────────


WINDOW_START = date(2024, 1, 15)


def _state(tamra_year, accumulated, amount_in, when):
    return SimpleNamespace(
        tamra_7pay_start_date=WINDOW_START,
        tamra_year=tamra_year,
        accumulated_7pay=accumulated,
        amount_in_7pay=amount_in,
        date=when,
    )


def _backtest(new_level):
    from suiteview.illustration.ui.values_tab import _seven_pay_backtest

    # Window years 1-2 are historical (per-year contributions); the valuation
    # sits in TAMRA year 3 and the recalc fires two projected months later.
    policy = SimpleNamespace(tamra_7year_contributions=[1_000.0, 1_200.0, 0, 0, 0, 0, 0])
    states = [
        _state(3, 2_200.0, 2_200.0, date(2026, 3, 15)),   # seed
        _state(3, 2_500.0, 2_200.0, date(2026, 4, 15)),
        _state(3, 2_900.0, 2_500.0, date(2026, 5, 15)),   # recalc month
    ]
    detail = {
        "seven_pay_new": new_level,
        "seven_pay_window_start": WINDOW_START,
        "tamra_year_at_change": 3,
    }
    return _seven_pay_backtest(policy, states, 2, detail)


def test_backtest_flags_mec_when_new_limit_is_exceeded():
    result = _backtest(800.0)

    assert result["is_mec"] is True
    assert result["mec_year"] == 1          # year 1: 1,000 paid vs 800 limit
    rows = result["rows"]
    assert [r["Result"] for r in rows] == [
        "MEC", "MEC", "MEC", "not reached", "not reached", "not reached", "not reached"]
    assert rows[0]["Net Prems (Cum)"] == 1_000.0        # historical year 1
    assert rows[1]["Net Prems (Cum)"] == 2_200.0        # historical years 1+2
    assert rows[2]["Net Prems (Cum)"] == 2_500.0        # through the month before the change
    assert rows[2]["7-Pay Limit (Cum)"] == 2_400.0
    assert rows[0]["Year Begins"] == "01/15/2024"
    assert rows[6]["Year Begins"] == "01/15/2030"


def test_backtest_passes_when_premiums_stay_inside_new_limit():
    result = _backtest(1_500.0)

    assert result["is_mec"] is False
    assert result["mec_year"] is None
    assert [r["Result"] for r in result["rows"][:3]] == ["OK", "OK", "OK"]
    assert result["through_date"] == date(2026, 5, 15)


# ── Sheet rendering ───────────────────────────────────────────────────────


_QT_APP = None


def _view():
    from PyQt6.QtWidgets import QApplication

    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    from suiteview.illustration.ui.values_tab import GuidelineRecalcDetailView

    return GuidelineRecalcDetailView()


def _base_detail(**extra):
    detail = {
        "change_kind": "Specified Amount Change",
        "change_date": CHANGE_DATE,
        "glp_before": 96.0, "glp_after": 120.0, "glp_prior": 96.0, "glp_new": 120.0,
        "gsp_before": 192.0, "gsp_after": 240.0, "gsp_prior": 192.0, "gsp_new": 240.0,
    }
    detail.update(extra)
    return detail


def test_view_carries_the_three_tamra_sheets():
    view = _view()
    labels = [view.tabs.tabText(i) for i in range(view.tabs.count())]
    assert labels[-3:] == ["TAMRA Calc", "MEC Back-Test", "New 7-Pay Period"]


def test_no_recalc_sheet_states_no_recalc_needed():
    view = _view()
    view.show_recalc(_base_detail(
        tamra_case="no_recalc",
        tamra_year_at_change=12,
        seven_pay_prior=60.0, seven_pay_new=48.0,
        seven_pay_prior_start=date(2015, 6, 9),
        seven_pay_window_start=date(2015, 6, 9),
    ))

    assert "does not need to be recalculated" in view.tamra_note.text()
    assert "06/09/2022" in view.tamra_note.text()       # period ended start + 7y
    assert not view.tamra_note.isHidden()
    assert view.tamra_pv.isHidden()
    assert "outside its 7-pay period" in view.backtest_note.text()
    assert view.new_period_label.isHidden()
    assert "does not start a new 7-pay period" in view.new_period_detail.text()


def test_within_period_sheet_shows_calc_and_backtest():
    view = _view()
    backtest = _backtest(800.0)
    view.show_recalc(_base_detail(
        tamra_case="within_period",
        tamra_year_at_change=3,
        seven_pay_prior=60.0, seven_pay_new=48.0,
        seven_pay_window_start=WINDOW_START,
        seven_pay_start_av=1_000.0,
        seven_pay_pv={"premium_label": "7-Pay"},
        seven_pay_backtest=backtest,
    ))

    assert view.tamra_note.isHidden()
    assert not view.tamra_pv.isHidden()
    assert "60.00 → 48.00" in view.tamra_info.text()
    assert not view.backtest_verdict.isHidden()
    assert "becomes a MEC" in view.backtest_verdict.text()
    assert view.new_period_label.isHidden()


def test_new_period_sheet_states_the_start_date():
    view = _view()
    view.show_recalc(_base_detail(
        tamra_case="new_period",
        tamra_year_at_change=12,
        seven_pay_prior=60.0, seven_pay_new=48.0,
        seven_pay_window_start=CHANGE_DATE,
        seven_pay_start_av=5_000.0,
        seven_pay_pv={"premium_label": "7-Pay"},
    ))

    assert not view.new_period_label.isHidden()
    assert "A new TAMRA 7-pay period begins on 06/09/2026." in view.new_period_label.text()
    assert "period ends 06/09/2033" in view.new_period_detail.text()
    assert "not re-tested" in view.backtest_note.text()
    assert not view.tamra_pv.isHidden()
