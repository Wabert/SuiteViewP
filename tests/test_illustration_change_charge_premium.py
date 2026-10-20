"""Apply premium needed to cover policy change surrender charge.

With the option on, a specified face decrease or DB option A to B change whose
partial surrender charge the surrender value cannot cover gets a solved
premium, applied after the withdrawal and before the change, with premium load,
tested against the guideline / 7-pay room, and added to PremTD / cost basis.
UE204564 (live): 250,000 -> 100,000, PSC 4,657.50, SV -7,597.88 -> net
12,255.38, gross 16,340.51 at a 25% load.
"""
import os
from datetime import date
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.change_charge_premium import (
    DETAIL_COLUMNS,
    REJECTED_TITLE,
    ChangeChargePremiumRejectedError,
)
from suiteview.illustration.core.decrease_charge_check import PSC_EXCEEDS_SV_KEY, SV_BEFORE_CHANGE_KEY
from suiteview.illustration.core.guaranteed_projection import guaranteed_options, lock_values
from suiteview.illustration.core.input_compiler import CHANGE_CHARGE_SUBTYPE, compile_month_inputs
from suiteview.illustration.core.loan_handler import LoanState
from suiteview.illustration.core.monthly_guideline import GuidelineSolveResult
from suiteview.illustration.core.premium_handler import PremiumResult
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.withdrawal_handler import WithdrawalResult
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    PolicyChangeEvent,
    PolicyChangeKind,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData

WHEN = date(2026, 6, 9)
_LOAD = [None] + [0.10] * 20     # 10% target and excess load every year


@pytest.fixture(autouse=True)
def _no_rate_reloads(monkeypatch):
    monkeypatch.setattr(calc_engine, "_reload_policy_band_rates", lambda *_args: None)
    monkeypatch.setattr(
        calc_engine, "compute_target_premiums",
        lambda *_a, **_kw: SimpleNamespace(mtp_annual=120.0, ctp_annual=0.0))
    monkeypatch.setattr(
        calc_engine, "_solve_guideline_state",
        lambda *_a, **_kw: GuidelineSolveResult(glp=60.0, gsp=120.0, seven_pay=36.0))


def _policy(*, db_option="A", seven_pay=1_000.0) -> IllustrationPolicyData:
    return IllustrationPolicyData(
        def_of_life_ins="GPT", face_amount=100_000.0, db_option=db_option,
        glp=1_200.0, gsp=2_400.0, ctp=0.0,
        tamra_7pay_level=seven_pay, tamra_7pay_start_date=date(2020, 6, 9),
        segments=[CoverageSegment(coverage_phase=1, face_amount=100_000.0, units=100.0)],
    )


def _ctx(change, *, cover=True, locked=0.0, policy=None, accumulated_7pay=0.0):
    return SimpleNamespace(
        policy=policy or _policy(),
        config=PlancodeConfig(sa_basis="CurrentSA"),
        rates=IllustrationRates(scr=[None] + [10.0] * 20,
                                segment_scr={1: [None] + [10.0] * 20},
                                tpp=_LOAD, epp=_LOAD),
        options=IllustrationOptions(cover_change_surrender_charge=cover),
        policy_changes=[change],
        month_inputs=SimpleNamespace(change_charge_premium=locked) if locked else None,
        state=MonthlyState(accumulated_glp=5_000.0, accumulated_7pay=accumulated_7pay),
        npt=None,
    )


def _work(*, av, premiums_to_date=3_000.0, debt=0.0):
    work = calc_engine.MonthWork(
        attained_age=56, month_date=WHEN, rate_year=7, duration=80, av=av,
        premiums_ytd=0.0, premiums_to_date=premiums_to_date, cost_basis=premiums_to_date,
        withdrawals_to_date=0.0)
    work.wd = WithdrawalResult()
    work.cap_loan = LoanState(rg_loan_princ=debt)
    work.policy_change_av_reduction = 0.0
    work.tamra_reset = False
    work.dbo_change_detail = {}
    work.face_change_detail = {}
    return work


def _decrease(value=60_000.0):
    return PolicyChangeEvent(PolicyChangeKind.FACE_AMOUNT, WHEN, value)


def _premium_then_change(ctx, work):
    calc_engine._apply_change_charge_premium(ctx, work)
    calc_engine._apply_policy_change_loop(ctx, work)
    return work


# ── engine: solve, load, trackers, then the change clears its check ──


def test_face_decrease_premium_covers_the_charge_with_load_and_trackers():
    ctx = _ctx(_decrease())
    work = _premium_then_change(ctx, _work(av=500.0))

    # SC 1,000 (100 units x 10), PSC 400 (40 units x 10), SV -500: net 900.
    premium = work.change_premium
    assert premium.surrender_value_before == pytest.approx(-500.0)
    assert premium.largest_psc == pytest.approx(400.0)
    assert premium.net_needed == pytest.approx(900.0)
    assert premium.gross == pytest.approx(1_000.0)        # 900 / (1 - 10% load)
    assert premium.premium_load == pytest.approx(100.0)
    assert premium.av_after == pytest.approx(1_400.0)
    assert premium.room.guideline == pytest.approx(2_000.0)  # AccumGLP 5,000 - PremTD 3,000
    assert work.premiums_ytd == pytest.approx(1_000.0)
    assert work.premiums_to_date == pytest.approx(4_000.0)
    assert work.cost_basis == pytest.approx(4_000.0)
    detail = work.face_change_detail
    assert detail[SV_BEFORE_CHANGE_KEY] == pytest.approx(400.0)
    assert detail[PSC_EXCEEDS_SV_KEY] is False
    assert work.av == pytest.approx(1_000.0)             # 1,400 less the 400 PSC


def test_option_off_leaves_the_uncovered_decrease_flagged():
    work = _premium_then_change(_ctx(_decrease(), cover=False), _work(av=500.0))
    assert work.change_premium is None
    assert work.face_change_detail[PSC_EXCEEDS_SV_KEY] is True


def test_covered_decrease_pays_no_premium():
    work = _premium_then_change(_ctx(_decrease()), _work(av=2_000.0))
    assert work.change_premium is None
    assert work.premiums_to_date == pytest.approx(3_000.0)


def test_option_a_to_b_solve_retests_the_growing_decrease():
    ctx = _ctx(PolicyChangeEvent(PolicyChangeKind.DB_OPTION, WHEN, "B"))
    work = _premium_then_change(ctx, _work(av=500.0))

    # The A to B decrease equals the AV, so its PSC grows as premium is added:
    # AV - SC 1,000 must cover 1% of the AV -> AV about 1,010.11.
    premium = work.change_premium
    assert premium.av_after - 1_000.0 >= premium.largest_psc
    assert premium.av_after == pytest.approx(1_010.11, abs=0.02)
    assert premium.largest_psc == pytest.approx(10.10, abs=0.01)
    assert work.dbo_change_detail[PSC_EXCEEDS_SV_KEY] is False


def test_premium_above_guideline_room_stops_the_run():
    with pytest.raises(ChangeChargePremiumRejectedError) as error:
        calc_engine._apply_change_charge_premium(
            _ctx(_decrease()), _work(av=500.0, premiums_to_date=4_500.0))
    assert str(error.value).startswith(
        "The premium of $1,000.00 needed to cover the partial surrender charge of the "
        "policy change effective 06/09/2026 cannot be accepted: it exceeds the remaining "
        "guideline premium limit of $500.00.")


def test_premium_above_seven_pay_room_stops_the_run():
    ctx = _ctx(_decrease(), policy=_policy(seven_pay=100.0))   # 7 x 100 = 700 room
    with pytest.raises(ChangeChargePremiumRejectedError, match="7-pay"):
        calc_engine._apply_change_charge_premium(ctx, _work(av=500.0))


def test_locked_premium_replays_without_solving_or_limits():
    ctx = _ctx(_decrease(), cover=False, locked=1_000.0)
    work = _premium_then_change(ctx, _work(av=500.0, premiums_to_date=4_900.0))
    assert work.change_premium.locked
    assert work.change_premium.net_needed == 0.0
    assert work.change_premium.gross == pytest.approx(1_000.0)
    assert work.av == pytest.approx(1_000.0)
    assert work.face_change_detail[PSC_EXCEEDS_SV_KEY] is False


@pytest.mark.parametrize(("before_premium", "expected_to_date"), [(True, 5_000.0), (False, 6_000.0)])
def test_fold_adds_the_premium_to_the_month_without_double_counting(before_premium, expected_to_date):
    work = _work(av=500.0)
    work.change_premium = SimpleNamespace()
    work.change_premium_split = calc_engine.split_premium_load(
        1_000.0, premiums_ytd=0.0, ctp=0.0, tpp=0.1, epp=0.1, flat=0.0)
    work.change_premium_before_premium = before_premium
    work.prem = PremiumResult(gross_premium=200.0, net_premium=180.0, excess_load=20.0,
                              total_premium_load=20.0, premiums_to_date=5_000.0)
    calc_engine._fold_change_charge_premium(work)
    assert work.prem.gross_premium == pytest.approx(1_200.0)
    assert work.prem.net_premium == pytest.approx(1_080.0)
    assert work.prem.total_premium_load == pytest.approx(120.0)
    assert work.prem.premiums_to_date == pytest.approx(expected_to_date)


# ── guaranteed replay ─────────────────────────────────────────────────


def test_lock_values_replays_the_change_premium_apart_from_the_month_premium():
    policy = IllustrationPolicyData(issue_date=date(2020, 6, 9), duration=72)
    states = [MonthlyState(duration=72),
              MonthlyState(duration=73, gross_premium=1_200.0, change_charge_premium=1_000.0)]
    locked = lock_values(policy, states).dated_transactions
    assert [(tx.amount, tx.subtype) for tx in locked] == [
        (1_000.0, CHANGE_CHARGE_SUBTYPE), (200.0, "locked")]

    compiled = compile_month_inputs(policy, IllustrationInputSet(dated_transactions=locked), 1)[73]
    assert compiled.change_charge_premium == 1_000.0
    assert compiled.unscheduled_premium == 200.0
    assert not guaranteed_options(
        IllustrationOptions(cover_change_surrender_charge=True)).cover_change_surrender_charge


# ── Run Values, report, Values tab ────────────────────────────────────


def test_refused_premium_is_a_user_facing_run_stop():
    from suiteview.illustration.core.run_service import (
        EngineServices, PolicyBasis, RunControls, RunFlowError, RunRequest, SolveRequestSet,
        execute_run,
    )

    def refuse(*_args, **_kwargs):
        raise ChangeChargePremiumRejectedError("The premium of $1.00 ... cannot be accepted")

    services = EngineServices(
        scenario_builder=lambda data, **kw: SimpleNamespace(
            projectable_policy=data, future_inputs=kw["future_inputs"]),
        engine_factory=lambda: object(), project=refuse,
        business_mode=lambda: False, missing_rates=lambda _p: ())
    request = RunRequest(
        basis=PolicyBasis("UE204564", policy_data=IllustrationPolicyData(
            policy_number="UE204564", plancode="1U147600", premium_pay_status_code="22")),
        inputs=IllustrationInputSet(),
        controls=RunControls(options=IllustrationOptions(), projection_months=2,
                             duration_label="2 months", stop_on_lapse=True),
        solves=SolveRequestSet())
    with pytest.raises(RunFlowError) as error:
        execute_run(request, services)
    assert error.value.title == REJECTED_TITLE
    assert "cannot be accepted" in error.value.message


def test_report_lists_the_change_premium_and_the_setting():
    from suiteview.illustration.core.report_builder import (
        _request_lines_from_specs, non_default_settings_lines,
    )

    policy = IllustrationPolicyData(issue_date=date(2020, 6, 9), issue_age=50, billing_frequency=1)
    states = [MonthlyState(duration=72),
              MonthlyState(date=WHEN, duration=73, policy_year=7, requested_premium=100.0,
                           change_charge_premium=16_340.51)]
    assert ("PREMIUM OF $16,340.51 ON 06/09/2026 TO COVER THE PARTIAL SURRENDER CHARGE "
            "OF THE POLICY CHANGE") in _request_lines_from_specs(policy, states, None)
    assert "PREMIUM APPLIED TO COVER POLICY CHANGE PARTIAL SURRENDER CHARGES" in (
        non_default_settings_lines(IllustrationOptions(cover_change_surrender_charge=True)))


def test_values_tab_shows_the_change_premium_columns():
    from suiteview.illustration.ui.values_tab import IllustrationValuesTab

    empty = IllustrationValuesTab._change_premium_values(MonthlyState())
    assert list(empty) == list(DETAIL_COLUMNS)
    assert empty["Chg Prem GP Room"] == "" and empty["Chg Prem Gross"] == 0.0
    filled = IllustrationValuesTab._change_premium_values(
        MonthlyState(change_premium_detail={"Chg Prem Gross": 16_340.51}))
    assert filled["Chg Prem Gross"] == 16_340.51
    assert IllustrationValuesTab.TAB_ORDER.index("Policy Change Premium") == (
        IllustrationValuesTab.TAB_ORDER.index("Increase/Decrease") + 1)


def test_input_checkbox_is_off_by_default_exports_and_round_trips():
    from PyQt6.QtWidgets import QApplication

    from suiteview.illustration.ui.main_window import IllustrationWindow

    app = QApplication.instance() or QApplication([])
    window = IllustrationWindow()
    try:
        panel = window.inputs_tab.dynamic_panel
        check = panel.cover_change_charge_check
        assert check.text() == "Apply premium needed to cover policy change surrender charge"
        assert not check.isChecked()
        assert not window.inputs_tab.export_options().cover_change_surrender_charge

        check.setChecked(True)
        assert window.inputs_tab.export_options().cover_change_surrender_charge
        state = panel.capture_state()
        assert state["cover_change_surrender_charge"] is True

        check.setChecked(False)
        panel.apply_state({"cover_change_surrender_charge": True})
        assert check.isChecked()
        panel.apply_state({})
        assert not check.isChecked()
    finally:
        window.close()
    assert app is not None
