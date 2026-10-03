"""RERUN joint survivor (second-to-die) UL: rates, policy data and engine rules.

Offline: UL_Rates / DB2 are replaced by small fakes. Live verification of all
in-force joint policies is tools/rates/verify_rerun_joint_survivor.py and
tests/test_joint_survivor_live.py.
"""

import copy
import os
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.core import rates as rates_module
from suiteview.core.joint_survivor_coi import Insured, Rating
from suiteview.core.rates import Rates
from suiteview.core.rates_errors import RatesError
from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.corridor_rates import corridor_factor
from suiteview.illustration.core.illustration_policy_service import (
    _is_joint_phase, _joint_segment_inputs,
)
from suiteview.illustration.core.rate_loader import (
    IllustrationRates, RateLookupError, load_segment_coi, load_segment_scr,
)
from suiteview.illustration.core.scenario_builder import prepare_policy_for_issue_projection
from suiteview.illustration.core.target_premium import compute_target_premiums
from suiteview.illustration.models.case_store import (
    decode_policy_snapshot, encode_policy_snapshot,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.models.policy_data import (
    CoverageSegment, IllustrationPolicyData, JointLives,
)
from tests.corridor_fixtures import CORRIDOR_1, CORRIDOR_4

JOINT_PLANS = {
    "N91EAA00": 100, "N91EAB00": 100, "N91EAJ00": 100, "N91EAN00": 100,
    "N91EMA00": 100, "N91EMB00": 100, "N71EP100": 100, "N71EP300": 100,
    "N71EMR00": 117, "N71EMJ00": 117, "B11EP200": 121, "B11EP400": 121,
}
LIVES = JointLives(Insured("F", "H", 58), Insured("M", "H", 62),
                   [Rating("01", "1", "X", cease_year=42)])


def _segment(phase=1, *, face=500_000.0, issue=date(2013, 12, 9), lives=LIVES, target=13_750.0):
    return CoverageSegment(
        coverage_phase=phase, issue_date=issue, issue_age=lives.primary.issue_age if lives else 58,
        rate_sex="F", rate_class="H", face_amount=face, original_face_amount=face,
        units=face / 1000.0, joint_lives=copy.deepcopy(lives), surrender_target=target)


# ── plan configuration ─────────────────────────────────────────────────────

@pytest.mark.parametrize("plancode,maturity", JOINT_PLANS.items())
def test_joint_plan_rows(plancode, maturity):
    config = load_plancode(plancode)
    assert config.is_ffl and config.maturity_age == maturity == config.premium_cease_age
    # Schema PLAN CORR: the FFL joint corridor (1.00 from age 95).
    assert config.corridor_by_age is not None
    assert corridor_factor(config, 94) == 1.01 and corridor_factor(config, 95) == 1.0
    assert config.safety_net_years(58) == 0
    pct = config.scr_pct_of_surrender_target
    if plancode.startswith("N91"):
        assert pct is None  # per-unit SCR loaded from the IAF
    else:
        assert pct[:3] == (1.0, 1.0, 0.93) and pct[14:] == (0.09, 0.0)


def test_joint_corridor_is_one_from_age_95_while_standard_set_keeps_101():
    joint = PlancodeConfig(plancode="N91EAB00", corridor_by_age=CORRIDOR_4)
    assert corridor_factor(joint, 40) == 2.5
    assert corridor_factor(joint, 94) == 1.01
    assert corridor_factor(joint, 95) == 1.0
    assert corridor_factor(joint, 121) == 1.0
    assert corridor_factor(PlancodeConfig(plancode="X", corridor_by_age=CORRIDOR_1), 95) == 1.01


def test_schema_corridor_uses_end_values_past_the_table():
    config = PlancodeConfig(plancode="X", corridor_by_age={18: 2.5, 95: 1.0})
    assert corridor_factor(config, 10) == 2.5
    assert corridor_factor(config, 95) == 1.0
    assert corridor_factor(config, 120) == 1.0


def test_plan_without_corridor_has_factor_one():
    assert corridor_factor(PlancodeConfig(plancode="N91EAB00"), 40) == 1.0


def test_invalid_joint_config_values_raise():
    with pytest.raises(ValueError, match="SCR_PctOfSurrenderTarget"):
        PlancodeConfig(plancode="X", scr_pct_of_surrender_target=(1.5,))


# ── schema-rates source in suiteview.core.rates ─────────────────────────────

@pytest.fixture
def joint_rates(monkeypatch):
    """A Rates whose dbo views are empty and whose schema ``rates`` holds one joint plan."""
    from suiteview.core.rates_schema import (
        CellAssignment, PlanAssignment, PlanAttr, PlanDef, ScheduleWindow,
    )

    monkeypatch.setattr(rates_module, "local_data_enabled", lambda: False)
    monkeypatch.setattr(Rates, "_cache", {})
    monkeypatch.setattr(Rates, "_joint_companies", {})
    # (rate type, benefit, sex, class) -> {scale: {duration: rate}} at issue age 58.
    cells = {
        ("MFEE", "", "F", "H"): {"C": {1: 40.0, 2: 40.0, 3: 10.0}, "G": {1: 45.0, 2: 45.0, 3: 45.0}},
        ("PREMLOAD_PCT", "", "F", "H"): {"C": {1: 0.1, 2: 0.1}},
        ("SCR", "", "F", "H"): {"G": {1: 10.0, 2: 9.0}},
        ("COI", "3F", "M", "K"): {"C": {1: 0.5, 2: 0.6}},     # benefit 3F: one generic cell
    }
    assignments, windows, values = [], [], {}
    for schedule_id, ((rate_type, benefit, sex, rate_class), scales) in enumerate(cells.items(), 1):
        assignments.append(CellAssignment(benefit, sex, rate_class, "0", "**", "", rate_type, schedule_id))
        for scale, schedule in scales.items():
            rate_set_id = schedule_id * 10 + "CG".index(scale)
            windows.append(ScheduleWindow(schedule_id, scale, date(1900, 1, 1), None, rate_set_id))
            values[rate_set_id] = {(58, d): r for d, r in schedule.items()}
    values[999] = {(0, 1): 0.03, (0, 2): 0.03}
    calls = []

    class FakeSchema:
        def plan_defs(self, plancode):
            calls.append(("plan_defs", plancode))
            return [PlanDef("26", plancode, "00", "UL", "BASE", plancode, ())]

        def plan_attrs(self, company, plancode):
            return [PlanAttr("LIVES", "3")] if plancode == "B11EP200" else []

        def cell_assignments(self, company, plancode):
            calls.append(("cell_assignments", plancode))
            return assignments

        def schedule_windows(self, schedule_ids):
            return [w for w in windows if w.schedule_id in schedule_ids]

        def rate_values(self, rate_set_ids, issue_age):
            return {i: values.get(i, {}) for i in rate_set_ids}

        def plan_assignments(self, company, plancode):
            return [PlanAssignment("**", "GINT", "G", 999)]

    rates = Rates()
    rates._schema_repo = FakeSchema()
    monkeypatch.setattr(rates, "_fetch_rates", lambda sql, params=None: None)  # dbo: no rows
    return rates, calls

def test_joint_plan_rates_come_from_schema_rates_with_dbo_shapes(joint_rates):
    rates, _ = joint_rates
    assert rates.joint_survivor_company("B11EP200") == "26"
    assert rates.get_rates("MFEE", "B11EP200", 58, "F", "H", scale=1) == [None, 40.0, 40.0, 10.0]
    assert rates.get_rates("MFEE", "B11EP200", 58, "F", "H", scale=0) == [None, 45.0, 45.0, 45.0]
    assert rates.get_rates("TPP", "B11EP200", 58, "F", "H", scale=1) == [None, 0.1, 0.1]
    assert rates.get_rates("SCR", "B11EP200", 58, "F", "H", scale=1) == [None, 10.0, 9.0]
    assert rates.get_rates("GINT", "B11EP200") == [None, 0.03, 0.03]
    assert rates.get_rates("BENCOI", "B11EP200", 58, "F", "H", benefit_type="3F") == [None, 0.5, 0.6]
    # VP/MS targets and unbanded plans: not available, never a dbo guess.
    assert rates.get_mtp("B11EP200", 58, "F", "H", 1) is None
    assert rates.get_band("B11EP200", 500_000.0) is None


def test_joint_plan_base_coi_request_is_loud(joint_rates):
    rates, _ = joint_rates
    with pytest.raises(RatesError, match="blended two-life JointCOI"):
        rates.get_rates("COI", "B11EP200", 58, "F", "H", scale=1, band=1)


def test_single_life_plans_never_see_schema_rates_cells(joint_rates):
    rates, calls = joint_rates
    assert rates.get_rates("MFEE", "1U1F4M00", 45, "F", "H", scale=1, band=1) is None
    assert ("cell_assignments", "1U1F4M00") not in calls


def test_base_cells_must_match_sex_and_class_exactly(joint_rates):
    rates, _ = joint_rates
    with pytest.raises(RatesError, match="No rate for sex 'M'"):
        rates.get_rates("MFEE", "B11EP200", 58, "M", "H", scale=1)


# ── rate loading ───────────────────────────────────────────────────────────

class _FakeRatesDb:
    """Rates stand-in: one joint plan, flat JS_Q so the schedule is easy to check."""

    def joint_survivor_company(self, plancode):
        return "26" if plancode == "B11EP200" else None

    def get_plan_attributes(self, company, plancode):
        return {"LIVES": "3", "JS_TABLE_PCT": "0=1;X=9.99", "JS_FLAT_FACTOR": "0.012",
                "JS_CAP_CURR_AT_GUAR": "Y", "JS_ZERO_GUAR_AT_Q1": "Y", "JS_ZERO_CURR_AT_Q0": "Y"}

    def get_plan_definition(self, company, plancode):
        return {"MATURITY_AGE": 121, "DESCRIPTION": "B11EP200"}

    def get_joint_survivor_q(self, company, plancode, scale, sex, rate_class, issue_age):
        base = 0.01 if scale == "C" else 0.02
        return {t: base for t in range(1, 101)}

    def get_rates(self, *args, **kwargs):
        raise AssertionError("single-life COI must not be requested for a joint segment")


def test_joint_segment_coi_is_the_blended_schedule_by_scale():
    current = load_segment_coi(_FakeRatesDb(), "B11EP200", _segment(), scale=1, band=1)
    guaranteed = load_segment_coi(_FakeRatesDb(), "B11EP200", _segment(), scale=0, band=1)
    assert current[0] is None and guaranteed[0] is None
    assert len(current) == 1 + (121 - 58)  # younger issue age 58 to maturity 121
    # The table-X joint life raises the joint rate; current is capped at guaranteed (B11).
    assert 0 < current[1] <= guaranteed[1]
    unrated = _segment(lives=JointLives(LIVES.primary, LIVES.joint, []))
    assert load_segment_coi(_FakeRatesDb(), "B11EP200", unrated, scale=1, band=1)[1] < current[1]


def test_joint_lives_on_a_non_joint_plan_are_rejected():
    with pytest.raises(RateLookupError, match="not a joint survivor plan"):
        load_segment_coi(_FakeRatesDb(), "N91EAB99", _segment(), scale=1, band=1)


def test_percent_of_surrender_target_scr_is_per_unit():
    config = load_plancode("B11EP200")
    schedule = load_segment_scr(None, "B11EP200", _segment(), config)
    # 000335148: year 13 is 23% of the 13,750 ST target -> $3,162.50 on 500 units.
    assert schedule[13] * 500 == pytest.approx(3162.50)
    assert schedule[16] == schedule[-1] == 0.0
    with pytest.raises(RateLookupError, match="stored surrender target"):
        load_segment_scr(None, "B11EP200", _segment(target=None), config)


# ── policy loading ─────────────────────────────────────────────────────────

def test_lives_code_and_plan_definition_must_agree():
    cov = SimpleNamespace(cov_pha_nbr=4, number_of_lives_code="3")
    assert _is_joint_phase(cov, "26", "B11EP200")
    with pytest.raises(ValueError, match="cannot illustrate it as a single life"):
        _is_joint_phase(cov, None, "ZZ000000")
    with pytest.raises(ValueError, match="not 3"):
        _is_joint_phase(SimpleNamespace(cov_pha_nbr=1, number_of_lives_code="1"), "26", "B11EP200")
    assert not _is_joint_phase(SimpleNamespace(cov_pha_nbr=1, number_of_lives_code=""), None, "X")


def test_joint_segment_inputs_come_from_policy_information():
    pi = SimpleNamespace(
        coverages=SimpleNamespace(cov_index_for_phase=lambda phase: 2),
        rates=SimpleNamespace(
            cov_joint_insureds=lambda index: (LIVES.primary, LIVES.joint),
            cov_joint_ratings=lambda index: LIVES.ratings),
        targets=SimpleNamespace(cov_surrender_target=lambda phase: 13750),
    )
    lives, target = _joint_segment_inputs(pi, SimpleNamespace(cov_pha_nbr=7))
    assert lives == LIVES and target == 13750.0


def _policy(**overrides) -> IllustrationPolicyData:
    fields = dict(
        plancode="B11EP200", company_code="26", issue_date=date(2013, 12, 9),
        valuation_date=date(2026, 9, 9), issue_age=58, attained_age=70, maturity_age=121,
        policy_year=13, policy_month=10, duration=154, face_amount=500_000.0, units=500.0,
        db_option="A", account_value=159_948.07, mtp=100.0, ctp=13_750.0,
        segments=[_segment()],
    )
    fields.update(overrides)
    return IllustrationPolicyData(**fields)


def test_snapshot_round_trip_keeps_joint_lives():
    policy = _policy()
    decoded = decode_policy_snapshot(encode_policy_snapshot(policy))
    assert decoded.segments[0].joint_lives == LIVES
    assert decoded.segments[0].surrender_target == 13_750.0
    assert decoded.is_joint_survivor


def test_vpms_targets_are_held_at_record_value():
    targets = compute_target_premiums(_policy(), load_plancode("B11EP200"))
    assert targets.held_at_record
    assert (targets.mtp_annual, targets.ctp_annual) == (1200.0, 13_750.0)


def test_issue_scenario_keeps_record_targets_for_joint_plans():
    issue = prepare_policy_for_issue_projection(_policy())
    assert issue.run_from_issue and issue.account_value == 0.0
    assert (issue.mtp, issue.ctp) == (100.0, 13_750.0)


def test_face_increase_lives_age_together_and_keep_active_ratings():
    base = _segment(lives=JointLives(LIVES.primary, LIVES.joint, [
        Rating("01", "1", "X", cease_year=42), Rating("00", "2", flat_per_1000=5.0, cease_year=10)]))
    lives = calc_engine._increase_joint_lives(base, 71, date(2026, 12, 9))
    assert (lives.primary.issue_age, lives.joint.issue_age) == (71, 75)
    # Increase in base year 14: the table-X rating runs 29 more years; the flat has ceased.
    assert lives.ratings == [Rating("01", "1", "X", cease_year=29)]
    assert calc_engine._increase_joint_lives(_segment(lives=None), 71, date(2026, 12, 9)) is None


# ── engine: corridor NAR at the newest active phase's rate (upstream rule) ─

@pytest.fixture
def corridor_policy(monkeypatch):
    """AV above face at age 89: all NAR is corridor NAR (000231979's pattern)."""
    base = _segment(1, face=100_000.0, issue=date(1993, 10, 6), target=None,
                    lives=JointLives(Insured("F", "H", 57), Insured("M", "H", 62), []))
    cola = _segment(6, face=20_000.0, issue=date(2002, 10, 6), target=None,
                    lives=JointLives(Insured("F", "H", 66), Insured("M", "H", 71), []))
    policy = _policy(
        plancode="N91EAB00", issue_date=date(1993, 10, 6), valuation_date=date(2026, 9, 6),
        issue_age=57, attained_age=89, maturity_age=100, policy_year=33, policy_month=12,
        duration=396, face_amount=120_000.0, units=120.0, account_value=176_988.28,
        system_monthly_deduction=86.25, current_interest_rate=0.05,
        guaranteed_interest_rate=0.05, segments=[base, cola])
    rates = IllustrationRates(
        segment_coi={1: [None] + [10.59295] * 60, 6: [None] + [10.03256] * 60},
        mfee=[None] + [5.0] * 60)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_: BonusConfig())
    monkeypatch.setattr(calc_engine.IllustrationEngine, "_load_rates", lambda *_: rates)
    monkeypatch.setattr(Rates, "get_band", lambda *_a, **_k: None)  # unbanded joint plan
    return calc_engine.IllustrationEngine().project(copy.deepcopy(policy), months=0)[0]


def test_corridor_nar_is_charged_at_the_latest_phase_rate(corridor_policy):
    # CyberLife charged 81.25 on 000231979: corridor NAR 8,099.05 at the newest
    # COLA phase's 10.03256, not the base phase's 10.59295.
    assert corridor_policy.coi_rate_corr == 10.03256
    assert corridor_policy.total_coi_charge == pytest.approx(
        corridor_policy.nar_corr * 10.03256 / 1000, abs=0.01)


# ── Policy tab ─────────────────────────────────────────────────────────────

_QT_APP = None


def test_policy_tab_shows_joint_insured_from_saved_case():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from suiteview.illustration.ui.policy_tab import IllustrationPolicyTab

    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    tab = IllustrationPolicyTab()
    tab.load_data_from_snapshot(_policy())
    info = tab.policy_info
    assert info._fields["joint_label"].text() == "Joint Second to Die"
    assert info._fields["joint_insured_label"].text() == "Male / H / age 62"
    assert info._fields["table_rating"].text() == "01: Table X (yrs 1-42)"
    assert info._fields["flat_extra"].text() == "None"
    assert not info._fields["joint_insured_label"].isHidden()
    tab.load_data_from_snapshot(_policy(segments=[_segment(lives=None)]))
    assert info._fields["joint_insured_label"].isHidden()
    tab.deleteLater()
