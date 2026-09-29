"""RERUN joint survivor: rate class / table changes, the Joint COI Values group
and the Joint COI sheet on a TEFRA/TAMRA recalc.

Offline: UL_Rates is a small fake with flat JS_Q so schedules are easy to check.
"""

import copy
import math
import os
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.core import rates as rates_module
from suiteview.core.joint_survivor_coi import (
    Insured, Rating, active_table_code, ratings_with_table,
)
from suiteview.illustration.core import calc_engine, input_context
from suiteview.illustration.core.input_context import build_policy_context
from suiteview.illustration.core.rate_loader import IllustrationRates, load_segment_coi
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    IllustrationInputSet, PolicyChangeEvent, PolicyChangeKind,
)
from suiteview.illustration.models.policy_data import (
    CoverageSegment, IllustrationPolicyData, JointLives,
)

ISSUE = date(2013, 12, 9)
LIVES = JointLives(Insured("F", "H", 58), Insured("M", "H", 62),
                   [Rating("01", "1", "X", cease_year=42)])


class _FakeRatesDb:
    """One joint plan (B11EP200), flat JS_Q that depends on the class."""

    def joint_survivor_company(self, plancode):
        return "26" if plancode == "B11EP200" else None

    def get_plan_attributes(self, company, plancode):
        return {"LIVES": "3", "JS_TABLE_PCT": "0=1;B=1.5;X=9.99", "JS_FLAT_FACTOR": "0.012",
                "JS_CAP_CURR_AT_GUAR": "Y", "JS_ZERO_GUAR_AT_Q1": "Y", "JS_ZERO_CURR_AT_Q0": "Y"}

    def get_plan_definition(self, company, plancode):
        return {"MATURITY_AGE": 121, "DESCRIPTION": "B11EP200"}

    def get_joint_survivor_q(self, company, plancode, scale, sex, rate_class, issue_age):
        base = (0.01 if scale == "C" else 0.02) * (2 if rate_class == "S" else 1)
        return {t: base for t in range(1, 101)}

    def joint_survivor_rate_classes(self, company, plancode):
        return ["H", "S"]


def _segment(phase=1, lives=LIVES, issue=ISSUE):
    return CoverageSegment(
        coverage_phase=phase, issue_date=issue, issue_age=lives.primary.issue_age,
        rate_sex="F", rate_class="H", face_amount=500_000.0, original_face_amount=500_000.0,
        units=500.0, joint_lives=copy.deepcopy(lives), surrender_target=13_750.0)


def _policy(*segments):
    return IllustrationPolicyData(
        plancode="B11EP200", company_code="26", issue_date=ISSUE,
        valuation_date=date(2026, 9, 9), issue_age=58, attained_age=70, maturity_age=121,
        policy_year=13, policy_month=10, duration=154, face_amount=500_000.0, units=500.0,
        db_option="A", rate_class="H", segments=list(segments) or [_segment()])


def _change(kind, value, person="01"):
    metadata = {"person": person} if person else {}
    return PolicyChangeEvent(kind=kind, effective_date=date(2026, 12, 9), value=value,
                             metadata=metadata)


@pytest.fixture
def reloads(monkeypatch):
    """Record segment rate reloads instead of reading UL_Rates."""
    calls = []
    monkeypatch.setattr(calc_engine, "_load_segment_rates",
                        lambda rates, seg, plancode, config=None: calls.append(seg.coverage_phase))
    monkeypatch.setattr(calc_engine, "_reband_benefits", lambda rates, policy: None)
    return calls


# ── core rating helpers ────────────────────────────────────────────────────

def test_table_change_ceases_the_old_rating_and_keeps_flats():
    ratings = [Rating("01", "1", "X", cease_year=42),
               Rating("00", "2", flat_per_1000=5.0, cease_year=10)]
    changed = ratings_with_table(ratings, "01", "B", 13)
    assert changed == [Rating("01", "1", "X", cease_year=13),
                       Rating("00", "2", flat_per_1000=5.0, cease_year=10),
                       Rating("01", "1", "B", effective_year=13, cease_year=999)]
    assert active_table_code(changed, "01", 13) == "X"
    assert active_table_code(changed, "01", 14) == "B"
    assert active_table_code(ratings_with_table(ratings, "01", "0", 13), "01", 14) == "0"
    assert active_table_code([Rating("00", "0", percent=150)], "00", 1) == ""


# ── engine: rate class and table changes re-rate the named insured ─────────

def test_joint_rate_class_change_rates_only_the_named_insured(reloads):
    policy = _policy()
    outcome = calc_engine._PolicyChangeOutcome()
    calc_engine._apply_rate_class_change(
        policy, None, _change(PolicyChangeKind.RATE_CLASS, "S"), IllustrationRates(), outcome)
    lives = policy.segments[0].joint_lives
    assert (lives.primary.rate_class, lives.joint.rate_class) == ("H", "S")
    assert policy.segments[0].rate_class == "H" and policy.rate_class == "H"
    assert outcome.coverage_changed and reloads == [1]


def test_joint_primary_rate_class_change_keeps_the_segment_class_in_step(reloads):
    policy = _policy()
    outcome = calc_engine._PolicyChangeOutcome()
    calc_engine._apply_rate_class_change(
        policy, None, _change(PolicyChangeKind.RATE_CLASS, "S", "00"), IllustrationRates(), outcome)
    assert policy.segments[0].joint_lives.primary.rate_class == "S"
    assert policy.segments[0].rate_class == policy.rate_class == "S"


def test_joint_change_must_name_the_insured(reloads):
    with pytest.raises(ValueError, match="must name the insured"):
        calc_engine._apply_rate_class_change(
            _policy(), None, _change(PolicyChangeKind.RATE_CLASS, "S", person=None),
            IllustrationRates(), calc_engine._PolicyChangeOutcome())


def test_joint_table_change_rerates_from_the_next_coverage_year(reloads):
    policy = _policy()
    outcome = calc_engine._PolicyChangeOutcome()
    calc_engine._apply_substandard_change(
        policy, None, _change(PolicyChangeKind.SUBSTANDARD, "B", "00"), date(2026, 12, 9),
        IllustrationRates(), outcome)
    seg = policy.segments[0]
    # 12/9/2026 is the 13th anniversary: the primary's table B starts in year 14.
    assert Rating("00", "1", "B", effective_year=13, cease_year=999) in seg.joint_lives.ratings
    assert seg.table_rating == 0 and outcome.coverage_changed and reloads == [1]


def test_unchanged_joint_table_is_not_a_change(reloads):
    policy = _policy()
    change = _change(PolicyChangeKind.SUBSTANDARD, "X", "01")
    assert not calc_engine._joint_table_segments(policy, change, date(2026, 12, 9))
    outcome = calc_engine._PolicyChangeOutcome()
    calc_engine._apply_substandard_change(
        policy, None, change, date(2026, 12, 9), IllustrationRates(), outcome)
    assert not outcome.coverage_changed and reloads == []


def test_joint_changes_trigger_a_guideline_before_capture():
    policy = _policy()
    policy.def_of_life_ins = "GPT"
    assert calc_engine._will_alter_guideline_charge_basis(
        policy, _change(PolicyChangeKind.RATE_CLASS, "S"), date(2026, 12, 9))
    assert not calc_engine._will_alter_guideline_charge_basis(
        policy, _change(PolicyChangeKind.RATE_CLASS, "H"), date(2026, 12, 9))


# ── monthly Joint COI detail ───────────────────────────────────────────────

def test_segment_basis_is_kept_for_joint_phases_only():
    bases = {}
    load_segment_coi(_FakeRatesDb(), "B11EP200", _segment(), scale=1, band=1, joint_bases=bases)
    assert bases[1].horizon == 121 - 58


def test_month_detail_is_the_run_scale_year_behind_the_coi():
    policy = _policy()
    for scale in (1, 0):
        rates = IllustrationRates(coi_scale=scale)
        rates.segment_coi[1] = load_segment_coi(
            _FakeRatesDb(), "B11EP200", policy.segments[0], scale=scale, band=1,
            joint_bases=rates.segment_joint)
        detail = calc_engine.joint_coi_month_detail(policy, rates, date(2026, 10, 9), 13)["cov1"]
        assert detail["year"] == 13
        assert detail["joint_coi"] == rates.segment_coi[1][13]
        assert detail["js_q_primary"] == (0.01 if scale == 1 else 0.02)
        # The joint insured's table X rates its q up (9.99x) and the survival steps follow.
        assert detail["q_joint"] == pytest.approx(detail["js_q_joint"] * 9.99)
        assert 0 < detail["tqxy"] < 1 and 0 < detail["monthly_p"] < 1
    assert calc_engine.joint_coi_month_detail(
        _policy(), IllustrationRates(), date(2026, 10, 9), 13) == {}


# ── TEFRA/TAMRA recalc: the Joint COI sheet data ───────────────────────────

@pytest.fixture
def fake_rates(monkeypatch):
    monkeypatch.setattr(rates_module, "Rates", _FakeRatesDb)


def test_recalc_detail_compares_before_and_after_for_a_re_rated_phase(fake_rates):
    policy = _policy()
    before = calc_engine._joint_lives_by_phase(policy)
    seg = policy.segments[0]
    seg.joint_lives = calc_engine._with_joint_life(
        seg.joint_lives, "01", Insured("M", "S", 62))
    detail = calc_engine.joint_coi_recalc_detail(
        policy, before, date(2026, 12, 9), ["Rate Class Change"])
    assert detail["recalculated"] and not detail["reason"]
    assert detail["changes"] == ["Cov 1: Joint insured rate class H → S"]
    first = detail["rows"][0]
    assert (first["Coverage"], first["Year"], first["Primary Age"]) == ("Cov 1", 14, 71)
    assert first["Joint q After"] == pytest.approx(2 * first["Joint q Before"])
    # Last-survivor COI is conditional on earlier deaths, so it can move either way.
    assert first["Guar COI After"] != first["Guar COI Before"]
    assert detail["rows"][-1]["Year"] == 121 - 58


def test_recalc_detail_names_the_first_re_rated_year_of_a_table_change(fake_rates, reloads):
    policy = _policy()
    before = calc_engine._joint_lives_by_phase(policy)
    calc_engine._apply_substandard_change(
        policy, None, _change(PolicyChangeKind.SUBSTANDARD, "B", "00"), date(2026, 12, 9),
        IllustrationRates(), calc_engine._PolicyChangeOutcome())
    detail = calc_engine.joint_coi_recalc_detail(
        policy, before, date(2026, 12, 9), ["Substandard Rating Change"])
    assert detail["changes"] == ["Cov 1: Primary insured table Standard → B from coverage year 14"]
    first = detail["rows"][0]
    assert first["Year"] == 14
    assert first["Primary q After"] == pytest.approx(1.5 * first["Primary q Before"])


def test_recalc_detail_lists_a_new_face_increase_phase(fake_rates):
    policy = _policy()
    before = calc_engine._joint_lives_by_phase(policy)
    policy.segments.append(_segment(2, JointLives(
        Insured("F", "H", 71), Insured("M", "H", 75), []), issue=date(2026, 12, 9)))
    detail = calc_engine.joint_coi_recalc_detail(
        policy, before, date(2026, 12, 9), ["Specified Amount Change"])
    assert detail["changes"] == [
        "Cov 2: new joint phase (face increase), insureds issued at ages 71 / 75"]
    assert detail["rows"][0]["Year"] == 1 and detail["rows"][0]["Guar COI Before"] is None


def test_recalc_detail_explains_when_the_joint_coi_is_unchanged(fake_rates):
    policy = _policy()
    detail = calc_engine.joint_coi_recalc_detail(
        policy, calc_engine._joint_lives_by_phase(policy), date(2026, 12, 9),
        ["Death Benefit Option Change"])
    assert not detail["recalculated"] and detail["rows"] == []
    assert "Death Benefit Option Change leaves both insureds' rate classes" in detail["reason"]
    assert "unbanded" in detail["reason"]


# ── inputs: joint policies name the insured ────────────────────────────────

_QT_APP = None


def _app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


@pytest.fixture
def joint_context(monkeypatch):
    monkeypatch.setattr(input_context, "Rates", _FakeRatesDb)


def test_policy_context_offers_the_plans_joint_classes_and_tables(joint_context):
    ctx = build_policy_context(_policy())
    assert ctx.is_joint
    assert [(person, role) for person, role, _ in ctx.joint_insureds] == [
        ("00", "Primary"), ("01", "Joint")]
    assert ctx.joint_rate_classes == ("H", "S")
    assert ctx.joint_table_codes == (("0", 1.0), ("B", 1.5), ("X", 9.99))
    single = _policy(CoverageSegment(coverage_phase=1, issue_date=ISSUE, issue_age=58))
    assert not build_policy_context(single).is_joint


def test_joint_change_rows_export_the_insured(joint_context):
    _app()
    from suiteview.illustration.ui.inputs_dynamic import DynamicInputsPanel

    panel = DynamicInputsPanel()
    panel.load_from_policy(_policy())
    rc = panel.rateclass_section.rows()[0]
    assert [rc.value_combo.itemText(i) for i in range(rc.value_combo.count())] == [
        "Primary: H", "Primary: S", "Joint: H", "Joint: S"]
    rc.year_edit.setText("14")
    rc._year_edited()
    rc.value_combo.setCurrentIndex(3)
    table = panel.table_section.rows()[0]
    assert table.value_combo.itemText(1) == "Primary: B (150%)"
    table.year_edit.setText("14")
    table._year_edited()
    table.value_combo.setCurrentIndex(1)
    input_set = IllustrationInputSet()
    panel.collect_into(input_set)
    changes = {c.kind: c for c in input_set.policy_changes}
    assert (changes[PolicyChangeKind.RATE_CLASS].value,
            changes[PolicyChangeKind.RATE_CLASS].metadata) == ("S", {"person": "01"})
    assert (changes[PolicyChangeKind.SUBSTANDARD].value,
            changes[PolicyChangeKind.SUBSTANDARD].metadata) == ("B", {"person": "00"})
    # A single-life policy gets the standard choices back.
    panel.load_from_policy(_policy(CoverageSegment(coverage_phase=1, issue_date=ISSUE, issue_age=58)))
    assert panel.rateclass_section.rows()[0].value_combo.itemData(0) == "R"
    panel.deleteLater()


# ── Values tab: Joint COI group and recalc sheet ───────────────────────────

def _joint_state(month: int) -> MonthlyState:
    return MonthlyState(
        policy_year=14, policy_month=month, attained_age=71, date=date(2027, month, 9),
        coi_rates_by_coverage={"cov1": 0.61},
        joint_coi_detail={"cov1": {
            "year": 14, "js_q_primary": 0.01, "js_q_joint": 0.02, "q_primary": 0.01,
            "q_joint": 0.1998, "tpx": 0.9, "tpy": 0.1, "tpxy": 0.91, "tqxy": 0.003,
            "monthly_p": 0.9997, "joint_coi": 0.61}})


def test_values_tab_shows_joint_coi_group_for_joint_policies_only():
    _app()
    from suiteview.illustration.ui.values_tab import IllustrationValuesTab

    tab = IllustrationValuesTab()
    tab.display_projection(_policy(), [_joint_state(1), _joint_state(2)])
    stages = [tab.nav_tree.topLevelItem(i).text(0) for i in range(tab.nav_tree.topLevelItemCount())]
    assert stages.index("Joint COI") == stages.index("Testing") - 1
    frame = tab._tab_grids["Joint COI"].model.get_original_data()
    assert ["JS Year Cov1", "Primary JS_Q Cov1", "Joint COI Cov1", "COI Rate Cov1"] == [
        c for c in frame.columns
        if c in ("JS Year Cov1", "Primary JS_Q Cov1", "Joint COI Cov1", "COI Rate Cov1")]
    assert frame["Joint COI Cov1"].tolist() == [0.61, 0.61]
    assert frame["COI Rate Cov1"].tolist() == [0.61, 0.61]

    tab.display_projection(IllustrationPolicyData(), [MonthlyState(policy_year=1, policy_month=1)])
    stages = [tab.nav_tree.topLevelItem(i).text(0) for i in range(tab.nav_tree.topLevelItemCount())]
    assert "Joint COI" not in stages
    tab.deleteLater()


def test_joint_coi_values_blank_past_the_horizon():
    from suiteview.illustration.ui.values_tab import IllustrationValuesTab

    values = IllustrationValuesTab._joint_coi_values(MonthlyState(), ["cov1"])
    assert math.isnan(values["Joint COI Cov1"])


def _recalc_view():
    _app()
    from suiteview.illustration.ui.values_tab import GuidelineRecalcDetailView

    return GuidelineRecalcDetailView()


def _recalc(**extra):
    detail = {"change_kind": "Rate Class Change", "change_date": date(2026, 12, 9),
              "glp_before": 96.0, "glp_after": 120.0, "glp_prior": 96.0, "glp_new": 120.0,
              "gsp_before": 192.0, "gsp_after": 240.0, "gsp_prior": 192.0, "gsp_new": 240.0}
    detail.update(extra)
    return detail


def test_recalc_sheet_shows_the_re_rated_joint_coi():
    view = _recalc_view()
    index = view.tabs.indexOf(view.joint_page)
    assert view.tabs.tabText(index) == "Joint COI" and not view.tabs.isTabVisible(index)
    view.show_recalc(_recalc(joint_coi={
        "recalculated": True, "reason": "",
        "changes": ["Cov 1: Joint insured rate class H → S"],
        "rows": [{"Coverage": "Cov 1", "Year": 14, "Primary Age": 71,
                  "Primary q Before": 0.02, "Primary q After": 0.02,
                  "Joint q Before": 0.1998, "Joint q After": 0.3996,
                  "Guar COI Before": 1.1, "Guar COI After": 2.2,
                  "Curr COI Before": 0.6, "Curr COI After": 1.2}]}))
    assert view.tabs.isTabVisible(index)
    assert "Joint insured rate class H → S" in view.joint_info.text()
    assert view.joint_note.isHidden() and view.joint_grid.isEnabled()
    frame = view.joint_grid.model.get_original_data()
    assert frame.loc[0, "Guar COI After"] == 2.2


def test_recalc_sheet_greys_with_a_note_when_the_joint_coi_is_unchanged():
    view = _recalc_view()
    view.show_recalc(_recalc(joint_coi={
        "recalculated": False, "changes": [], "rows": [],
        "reason": "No joint COI recalculation: Death Benefit Option Change ..."}))
    assert view.tabs.isTabVisible(view.tabs.indexOf(view.joint_page))
    assert view.joint_note.text().startswith("No joint COI recalculation")
    assert view.joint_info.isHidden() and not view.joint_grid.isEnabled()
    view.show_recalc(_recalc())
    assert not view.tabs.isTabVisible(view.tabs.indexOf(view.joint_page))


def test_policy_change_month_attaches_the_joint_sheet(fake_rates):
    policy = _policy()
    ctx = SimpleNamespace(policy=policy, policy_changes=[
        _change(PolicyChangeKind.DB_OPTION, "B", person=None)])
    work = SimpleNamespace(guideline_recalc={"glp_new": 1.0}, month_date=date(2026, 12, 9),
                           wd=SimpleNamespace(face_decrease=0.0))
    calc_engine._attach_joint_coi_recalc(ctx, work, calc_engine._joint_lives_by_phase(policy))
    assert work.guideline_recalc["joint_coi"]["recalculated"] is False
    work.guideline_recalc = {}
    calc_engine._attach_joint_coi_recalc(ctx, work, {})
    assert "joint_coi" not in work.guideline_recalc
