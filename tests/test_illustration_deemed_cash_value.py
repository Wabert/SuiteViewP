"""E02 — CVAT deemed cash value (DCV) roll and the Necessary Premium Test.

RERUN CalcEngine columns YW..AAK (DCV roll), LG..LI (vValue_for_NPT, vNPT_NSP,
vNPT_Premium) and ND (NPT Allowance0). The NSP-sheet numbers below come from
the RERUN v20 workbook ``NSP`` sheet (rows 19/20, plancode 1U145500, 4.5%).
"""
from __future__ import annotations

import copy
import os
from datetime import date
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine, ProjectionTiming
from suiteview.illustration.core.deemed_cash_value import (
    DCV_DEFAULTED_KEY,
    DcvCharges,
    DcvCoverage,
    DcvMonthInput,
    NptTracker,
    NspMonth,
    NspSchedule,
    dcv_defaulted,
    npt_nsp_values,
    npt_premium,
    roll_deemed_cash_value,
)
from suiteview.illustration.core.premium_allowance import (
    INF,
    DeemedCashValueRequiredError,
    PremiumAllowanceInput,
    compute_premium_allowances,
)
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.run_service import (
    EngineServices,
    PolicyBasis,
    RunControls,
    RunRequest,
    SolveRequestSet,
    execute_run,
)
from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.illustration.core.target_premium import TargetPremiumResult
from suiteview.illustration.core.ul_rates import ULRates
from suiteview.illustration.models import case_store
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    InforceOverrideSet,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData

# NSP sheet, row 19: W19 (q per 1000 from Q = 0.10339) and X19 (v at 4.5%).
SHEET_W = 0.10337931161297233
SHEET_V = 0.9963386453799393
GLP_DISCOUNT = 1.04 ** (1 / 12)


# ── LH — NSP schedule recursion (mNSPs) ─────────────────────────────────


def test_nsp_recursion_matches_the_rerun_nsp_sheet():
    # The workbook's own pair: Y19 = v·W + v·(1 − W/1000)·Y20.
    assert SHEET_V * SHEET_W + SHEET_V * (1 - SHEET_W / 1000) * 138.63375606860686 == (
        pytest.approx(138.21489014038292, abs=1e-12))

    values = npt_nsp_values(
        [NspMonth(0.10339)] * 3, annual_rate=0.045, death_benefit=25_000.0)
    per_thousand = [value / 25.0 for value in values]
    # Last month before age 100 endows: v·W + v·(1 − W/1000)·1000 = v·1000.
    assert per_thousand[2] == pytest.approx(SHEET_V * 1000, abs=1e-9)
    # Each earlier month uses the sheet's q and v exactly.
    for index in (0, 1):
        expected = SHEET_V * SHEET_W + SHEET_V * (1 - SHEET_W / 1000) * per_thousand[index + 1]
        assert per_thousand[index] == pytest.approx(expected, abs=1e-9)


def test_rider_nsp_adds_the_discounted_qab_charge_stream():
    # Q = 0: AH = AF·1 + v·AH_next; base NSP = DB·v^n.
    values = npt_nsp_values(
        [NspMonth(0.0, 10.0), NspMonth(0.0, 10.0)], annual_rate=0.045, death_benefit=1_000.0)
    assert values[1] == pytest.approx(SHEET_V * 1000 + 10.0, abs=1e-9)
    assert values[0] == pytest.approx(SHEET_V ** 2 * 1000 + 10.0 + SHEET_V * 10.0, abs=1e-9)


def test_nsp_schedule_indexes_by_policy_month_from_its_anchor():
    schedule = NspSchedule(anchor_duration=145, death_benefit=100_000.0,
                           annual_rate=0.04, values=(30_000.0, 30_100.0))
    assert schedule.nsp_at(145) == 30_000.0
    assert schedule.nsp_at(146) == 30_100.0
    assert schedule.nsp_at(147) == 100_000.0          # age 100: Y = 1000
    with pytest.raises(ValueError, match="before the schedule"):
        schedule.nsp_at(144)


# ── LI — vNPT_Premium ───────────────────────────────────────────────────


def test_npt_premium_grosses_up_by_target_and_excess_loads():
    common = dict(is_gpt=False, ctp=1_500.0, tpp=0.08, epp=0.04)
    # Under the CTP: 1,000 / (1 − 0.08).
    assert npt_premium(nsp=10_000.0, value_for_npt=9_000.0, **common) == (
        pytest.approx(1086.9565217391305))
    # Over the CTP: (3,000 + (0.08 − 0.04)·1,500) / (1 − 0.04) = 3,187.50.
    assert npt_premium(nsp=10_000.0, value_for_npt=7_000.0, **common) == pytest.approx(3187.5)
    # Value at/above the NSP needs no premium.
    assert npt_premium(nsp=10_000.0, value_for_npt=10_500.0, **common) == 0.0
    # GPT policies have no NPT.
    assert npt_premium(nsp=10_000.0, value_for_npt=0.0, **{**common, "is_gpt": True}) == 0.0


# ── YW..AAK — the DCV roll ───────────────────────────────────────────────


def _dcv_input(**overrides) -> DcvMonthInput:
    data = dict(
        begin_dcv=10_000.0,
        gross_withdrawal=500.0,
        net_premium=1_000.0,
        coverages=(DcvCoverage(100_000.0, 0.5),),
        charges=DcvCharges(epu=10.0, monthly_fee=5.0, poav_rate=0.001,
                           rider_benefit=3.0, pw_rate=0.05, monthly_mtp=50.0),
        glp_rate=0.04,
    )
    data.update(overrides)
    return DcvMonthInput(**data)


def test_dcv_roll_hand_checked_level_option():
    month = roll_deemed_cash_value(_dcv_input())
    assert month.after_changes == pytest.approx(9_500.0)       # BDCV − gross WD
    assert month.after_premium == pytest.approx(10_500.0)      # + net premium
    # NAAR = 100,000 / 1.04^(1/12) − 10,500; COI at 0.5 per 1,000.
    assert month.coi_charge == pytest.approx(44.58684713092811, abs=1e-9)
    # MD = (PoAV 10.50 + fee 5 + EPU 10 + riders 3 + COI) × (1 + PW 5%) — the
    # MD exceeds MTP/12 = 50, so PW waives the MD.
    assert month.monthly_deduction == pytest.approx(76.74118948747451, abs=1e-9)
    # Interest at the 4% GLP rate over 365/12 days.
    assert month.interest == pytest.approx(34.12303702813019, abs=1e-9)
    assert month.end_dcv == pytest.approx(10457.381847540655, abs=1e-9)


def test_dcv_roll_increasing_option_nets_full_dcv_against_each_coverage():
    month = roll_deemed_cash_value(_dcv_input(
        begin_dcv=8_000.0, gross_withdrawal=0.0, net_premium=0.0, db_option="B",
        coverages=(DcvCoverage(50_000.0, 0.4), DcvCoverage(30_000.0, 0.6)),
        charges=DcvCharges()))
    # Cov 1 DBD = (50,000 + 8,000)/d − 8,000; the workbook's cov 2 formula
    # nets the whole DCV again: 30,000/d − 8,000.
    assert month.coi_charge == pytest.approx(33.06556203588477, abs=1e-9)
    assert month.death_benefit == pytest.approx(88_000.0)


def test_valuation_row_uses_the_entered_dcv_and_cyberlife_timing_credits_first():
    month = roll_deemed_cash_value(_dcv_input(valuation_dcv=-67.96, charges=DcvCharges()))
    assert month.after_premium == -67.96                       # ZA = sInput_DeemedCashValue
    assert month.interest == 0.0                               # AAJ floors at zero

    start = roll_deemed_cash_value(_dcv_input(
        gross_withdrawal=0.0, net_premium=0.0, coverages=(), charges=DcvCharges(),
        interest_at_start=True))
    assert start.begin_interest == pytest.approx(10_000.0 * (GLP_DISCOUNT - 1.0))
    assert start.interest == 0.0
    assert start.end_dcv == pytest.approx(10_000.0 * GLP_DISCOUNT)


# ── ND — NPT Allowance0 plumbing ─────────────────────────────────────────


def _allowance(**overrides):
    data = dict(
        is_cvat=True, is_gpt=False, tefra_force=False, tamra_force=True,
        mec_bypass=False, guideline_limit=0.0, prem_less_wd=0.0, force_out=0.0,
        loan_repay_from_forceout=0.0, seven_pay_level=3_000.0, tamra_year=8,
        tamra_month_of_year=1, policy_month=1, amount_in_7pay=0.0, npt_premium=None,
        tamra_reset=False, requested_scheduled=100.0, requested_lumpsum=0.0,
        payment_count_policy_year=12, payment_count_tamra_year=0,
        loan_repay_from_lumpsum=0.0, loan_repay_from_scheduled=0.0,
        ln_repay_left_over=0.0, has_loan_balance=False, levelizing_premium=False,
        beginning_of_year=True, policy_anniversary=True, prior_scheduled_prem_cap=0.0,
    )
    data.update(overrides)
    return compute_premium_allowances(PremiumAllowanceInput(**data))


def test_cvat_tamra_year_8_unknown_npt_fails_loud():
    # Only callers that price a single receipt outside the projection pass no NPT
    # premium; illustration runs always have one (DCV entered or defaulted to 0).
    with pytest.raises(DeemedCashValueRequiredError, match="93 segment"):
        _allowance()


def test_cvat_tamra_year_8_premium_below_the_npt_premium_is_accepted():
    accepted = _allowance(npt_premium=500.0)
    assert accepted.npt_allowance_0 == 500.0
    assert accepted.applied_scheduled_premium == pytest.approx(100.0)
    assert not accepted.capped_by_tamra

    limited = _allowance(npt_premium=40.0)
    assert limited.applied_scheduled_premium == pytest.approx(40.0)
    assert limited.capped_by_tamra


def test_unknown_npt_is_harmless_where_the_npt_cannot_limit_a_premium():
    assert _allowance(tamra_year=7).npt_allowance_0 == INF        # unlimited yrs 1-7
    assert _allowance(requested_scheduled=0.0).npt_allowance_0 == INF
    assert _allowance(tamra_force=False).applied_scheduled_premium == pytest.approx(100.0)
    assert _allowance(mec_bypass=True).applied_scheduled_premium == pytest.approx(100.0)
    assert _allowance(is_cvat=False, is_gpt=True).npt_allowance_0 == INF


# ── Engine regression: CVAT past TAMRA year 7 ───────────────────────────


def _rates() -> IllustrationRates:
    coi = [0.0] + [2.4] * 180
    return IllustrationRates(
        coi=coi, segment_coi={1: coi}, epu=[0.0] * 181, segment_epu={1: [0.0] * 181},
        scr=[0.0] + [4.0] * 180, segment_scr={1: [0.0] + [4.0] * 180},
        mfee=[0.0] + [5.0] * 180, tpp=[0.0] + [0.06] * 180, epp=[0.0] + [0.03] * 180,
    )


def _config() -> PlancodeConfig:
    return PlancodeConfig(
        plancode="E02CVAT", gint=0.03, dbd=0.0, lapse_value="SV",
        interest_method="MonthlyCompounding",
    )


def _cvat_policy(dcv, **overrides) -> IllustrationPolicyData:
    data = dict(
        policy_number="E02-CVAT", plancode="E02CVAT", def_of_life_ins="CVAT",
        issue_date=date(2014, 3, 15), valuation_date=date(2026, 3, 15),
        issue_age=45, attained_age=57, maturity_age=121, policy_year=13, policy_month=1,
        duration=145, face_amount=100_000.0, units=100.0, db_option="A",
        account_value=15_000.0, premiums_paid_to_date=20_000.0, modal_premium=150.0,
        billing_frequency=1, mtp=40.0, ctp=900.0, current_interest_rate=0.04,
        guaranteed_interest_rate=0.03, tamra_7pay_start_date=date(2014, 3, 15),
        tamra_7pay_level=3_000.0, tamra_7year_lowest_db=100_000.0,
        deemed_cash_value=dcv,
        segments=[CoverageSegment(
            coverage_phase=1, issue_date=date(2014, 3, 15), issue_age=45, rate_sex="M",
            rate_class="N", face_amount=100_000.0, original_face_amount=100_000.0,
            units=100.0)],
    )
    data.update(overrides)
    return IllustrationPolicyData(**data)


@pytest.fixture
def offline_engine(monkeypatch):
    rates, config = _rates(), _config()
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _plancode: copy.deepcopy(config))
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_args: BonusConfig())
    monkeypatch.setattr(calc_engine.IllustrationEngine, "_load_rates", lambda *_args: rates)
    monkeypatch.setattr(calc_engine.IllustrationEngine, "_guaranteed_rates", lambda *_args: rates)
    monkeypatch.setattr(calc_engine, "compute_target_premiums", lambda *_a, **_k: TargetPremiumResult())
    monkeypatch.setattr(calc_engine, "build_target_detail_snapshots", lambda *_a, **_k: ({}, {}))
    monkeypatch.setattr(calc_engine, "_reload_policy_band_rates", lambda *_a, **_k: None)
    monkeypatch.setattr(ULRates, "get_band", lambda *_a, **_k: None)

    def project(policy, months=3, options=None, inputs=None,
                timing=ProjectionTiming.ILLUSTRATION):
        return IllustrationEngine().project(
            policy, months=months, future_inputs=inputs, options=options,
            stop_on_lapse=False, rates_override=rates, bonus_override=BonusConfig(),
            timing=timing)

    return project


def test_cvat_tamra_year_8_without_dcv_uses_dcv_zero(offline_engine):
    """Robert 2026-10-06: no DCV entered -> illustrated as if DCV = 0, flagged, no stop."""
    defaulted = offline_engine(_cvat_policy(None))
    entered_zero = offline_engine(_cvat_policy(0.0))
    inforce = defaulted[0].premium_allowance_detail
    assert inforce["vDCV_AfterPremium"] == 0.0
    assert inforce[DCV_DEFAULTED_KEY] == 1.0
    assert dcv_defaulted(defaulted) and not dcv_defaulted(entered_zero)
    for default_row, zero_row in zip(defaulted[1:], entered_zero[1:]):
        assert default_row.tamra_year == 13
        assert default_row.premium_allowance_detail["vNPT_Premium"] == pytest.approx(
            zero_row.premium_allowance_detail["vNPT_Premium"])
        assert default_row.gross_premium == pytest.approx(zero_row.gross_premium)
        assert default_row.gross_premium == pytest.approx(150.0)


def test_entered_dcv_takes_precedence_over_the_default(offline_engine):
    defaulted = offline_engine(_cvat_policy(None))
    entered = offline_engine(_cvat_policy(14_000.0))
    assert not dcv_defaulted(entered)
    assert entered[0].premium_allowance_detail["vDCV_AfterPremium"] == 14_000.0
    assert DCV_DEFAULTED_KEY not in entered[0].premium_allowance_detail
    # A higher DCV leaves less NSP shortfall, so a smaller necessary premium.
    assert (entered[1].premium_allowance_detail["vNPT_Premium"]
            < defaulted[1].premium_allowance_detail["vNPT_Premium"])


def test_cvat_tamra_year_8_with_dcv_accepts_premium_below_npt(offline_engine):
    states = offline_engine(_cvat_policy(14_000.0))
    inforce, first = states[0], states[1]
    # The valuation row seeds vEDCV from the entered DCV; month 1 carries it.
    assert inforce.premium_allowance_detail["vDCV_AfterPremium"] == 14_000.0
    assert first.premium_allowance_detail["BDCV"] == pytest.approx(
        inforce.premium_allowance_detail["vEDCV"])
    for state in states[1:]:
        detail = state.premium_allowance_detail
        assert state.tamra_year == 13
        assert detail["vValue_for_NPT"] == pytest.approx(detail["vDCV_AfterChanges"])
        assert detail["NPT Allowance0"] == pytest.approx(detail["vNPT_Premium"])
        assert detail["vNPT_Premium"] > 150.0
        assert state.gross_premium == pytest.approx(150.0)        # accepted (was 0)
        assert not state.premium_capped_by_tamra


def test_cvat_npt_limits_a_premium_above_the_npt_premium(offline_engine):
    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(TransactionKind.PREMIUM, date(2026, 4, 15), 5_000_000.0)])
    states = offline_engine(_cvat_policy(14_000.0), months=1, inputs=inputs)
    month = states[1]
    npt = month.premium_allowance_detail["vNPT_Premium"]
    assert month.premium_capped_by_tamra
    assert month.gross_premium == pytest.approx(npt, abs=0.01)


def test_cyberlife_timing_rolls_the_dcv_with_interest_first(offline_engine):
    states = offline_engine(
        _cvat_policy(14_000.0), months=2, timing=ProjectionTiming.CYBERLIFE_MONTHLIVERSARY)
    inforce, first = states[0].premium_allowance_detail, states[1].premium_allowance_detail
    assert inforce["DCV Interest"] == 0.0               # credited next month instead
    assert first["DCV Interest"] > 0.0
    assert first["vDCV_AfterChanges"] == pytest.approx(inforce["vEDCV"] + first["DCV Interest"])
    assert states[1].gross_premium == pytest.approx(150.0)


def test_npt_needs_no_dcv_when_it_cannot_bind(offline_engine):
    # GPT, Conform to TAMRA off, and a run that stays inside the 7-pay window.
    offline_engine(_cvat_policy(None, def_of_life_ins="GPT"))
    off = offline_engine(_cvat_policy(None), options=IllustrationOptions(conform_to_tamra=False))
    assert off[1].gross_premium == pytest.approx(150.0)
    inside = offline_engine(_cvat_policy(None, tamra_7pay_start_date=date(2024, 3, 15)))
    assert "vNPT_Premium" not in inside[1].premium_allowance_detail


def test_npt_tracker_rebuilds_the_nsp_schedule_on_a_7702_change():
    policy, config, rates = _cvat_policy(14_000.0), _config(), _rates()
    tracker = NptTracker(load_guaranteed=lambda _policy: rates, glp_rate=0.04)
    row = SimpleNamespace(
        epu_charge=0.0, mfee_charge=5.0, rider_charges=0.0, benefit_charges=0.0,
        pw_charge=0.0, benefit_rates={}, days_in_month=365 / 12)
    detail = tracker.start(policy, config, rates, row, lowest_death_benefit=100_000.0)
    assert detail["vDCV_AfterPremium"] == 14_000.0
    assert tracker.schedule.anchor_duration == 145
    first_nsp = tracker.schedule.nsp_at(146)

    policy.segments[0].face_amount = 150_000.0
    tracker.policy_changed(policy, config, duration=150, attained_age=57,
                           months_into_year=5, as_of=date(2026, 8, 15),
                           lowest_death_benefit=150_000.0)
    assert tracker.nsp_schedules_built == 2
    assert tracker.schedule.anchor_duration == 150
    assert tracker.schedule.nsp_at(150) > first_nsp


# ── Run Values plumbing ──────────────────────────────────────────────────


def _run_request(dcv) -> RunRequest:
    return RunRequest(
        basis=PolicyBasis("E02-CVAT", policy_data=_cvat_policy(None)),
        inputs=IllustrationInputSet(),
        controls=RunControls(options=IllustrationOptions(), projection_months=12,
                             duration_label="for 1 years", stop_on_lapse=True),
        solves=SolveRequestSet(),
        inforce_overrides=InforceOverrideSet(deemed_cash_value=dcv),
    )


def test_run_status_says_when_the_dcv_default_was_used():
    from suiteview.illustration.core.run_service import _final_status

    scenario = SimpleNamespace(scenario=SimpleNamespace(run_from_issue=False))
    flagged = [SimpleNamespace(premium_allowance_detail={DCV_DEFAULTED_KEY: 1.0}), SimpleNamespace()]
    entered = [SimpleNamespace(premium_allowance_detail={"vDCV_AfterPremium": 14_000.0}),
               SimpleNamespace()]
    status = _final_status(_run_request(None), scenario, flagged, None, None)
    assert "Deemed cash value not available; illustrated with DCV = 0" in status
    assert "DCV = 0" not in _final_status(_run_request(14_000.0), scenario, entered, None, None)


def test_entered_dcv_reaches_the_projected_policy():
    seen = {}

    class _Stop(Exception):
        pass

    def project(policy, **_kwargs):
        seen["dcv"] = policy.deemed_cash_value
        raise _Stop()

    with pytest.raises(_Stop):
        execute_run(_run_request(-67.96), EngineServices(project=project))
    assert seen["dcv"] == -67.96


def test_scenario_dcv_comes_only_from_the_entry():
    stale = _cvat_policy(5_000.0)
    assert build_illustration_scenario(stale).projectable_policy.deemed_cash_value is None
    entered = build_illustration_scenario(
        stale, inforce_overrides=InforceOverrideSet(deemed_cash_value=1_234.5))
    assert entered.projectable_policy.deemed_cash_value == 1_234.5
    assert entered.base_policy.deemed_cash_value == 5_000.0
    issue = build_illustration_scenario(
        stale, inforce_overrides=InforceOverrideSet(deemed_cash_value=1_234.5),
        run_from_issue=True)
    assert issue.projectable_policy.deemed_cash_value == 0.0     # no cash value at issue


# ── Input tab: DCV entry ─────────────────────────────────────────────────


_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


class _FakePolicy:
    """Just enough policy surface for the Input tab."""

    issue_date = date(2014, 3, 15)
    base_issue_age = 45
    attained_age = 57
    valuation_date = date(2026, 3, 15)
    policy_year = 13
    duration = 145
    maturity_age = 121
    billing_frequency = 1
    modal_premium = 150.0
    def_of_life_ins = "GPT"
    glp = 1200.0
    accumulated_glp = 5000.0
    premiums_paid_to_date = 20000.0
    withdrawals_to_date = 0.0
    base_rate_class = "N"
    base_table_rating = 0
    base_plancode = "1U145700"
    status_code = "0"

    def __init__(self):
        self.coverages = SimpleNamespace(get_coverages=lambda: [])
        self.benefits = SimpleNamespace(get_benefits=lambda: [])


class _CvatPolicy(_FakePolicy):
    def_of_life_ins = "CVAT"


def _inputs_tab(policy):
    from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab

    _app()
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(policy)
    return tab


def test_dcv_entry_greyed_with_italic_note_for_gpt_never_hidden():
    panel = _inputs_tab(_FakePolicy()).dynamic_panel
    assert not panel.dcv_edit.isEnabled()
    assert not panel.dcv_edit.isHidden() and not panel.dcv_note.isHidden()
    assert panel.dcv_note.text() == "Not applicable — not a CVAT policy"
    assert "italic" in panel.dcv_note.styleSheet()
    panel.dcv_edit.setText("1,000.00")
    assert panel.deemed_cash_value() is None


def test_dcv_entry_follows_cvat_and_conform_to_tamra():
    tab = _inputs_tab(_CvatPolicy())
    panel = tab.dynamic_panel
    assert panel.tamra_check.isChecked()
    assert panel.dcv_edit.isEnabled()
    assert panel.dcv_note.text().endswith("blank uses DCV = 0")
    assert tab.export_inforce_overrides().deemed_cash_value is None   # blank -> default
    panel.dcv_edit.setText("-67.96")                      # a DCV can be negative
    assert tab.export_inforce_overrides().deemed_cash_value == -67.96

    panel.tamra_check.setChecked(False)
    assert not panel.dcv_edit.isEnabled()
    assert panel.dcv_note.text() == "Not applicable — Conform to TAMRA is off"
    assert tab.export_inforce_overrides().deemed_cash_value is None

    panel.tamra_check.setChecked(True)
    assert panel.deemed_cash_value() == -67.96


def test_dcv_round_trips_through_a_saved_case_and_clears_on_policy_load(tmp_path):
    source = _inputs_tab(_CvatPolicy())
    source.dynamic_panel.dcv_edit.setText("12,345.67")
    state = source.capture_case_inputs()
    case_store.save_case("DCV Case", policy_number="E02-CVAT", region="CKPR",
                         inputs=state, directory=tmp_path)
    loaded = case_store.load_case("DCV Case", directory=tmp_path)

    target = _inputs_tab(_CvatPolicy())
    assert target.dynamic_panel.dcv_edit.text() == ""     # fresh policy: no DCV
    assert target.apply_case_inputs(loaded.inputs) == []
    assert target.export_inforce_overrides() == source.export_inforce_overrides()
    assert target.export_inforce_overrides().deemed_cash_value == 12_345.67
