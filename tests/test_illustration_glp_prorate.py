"""Mid-year guideline recalc — pro-rata AccumGLP true-up.

When a policy change recalculates the guideline premiums mid-policy-year, the
anniversary has already banked a FULL year of the prior GLP, so AccumGLP must
be adjusted by (months-remaining/12) x (new GLP - prior GLP): a change at the
beginning of month 4 keeps 3 months of the old GLP and accrues 9 months at the
new one (Robert's rule, 2026-07-17 — RERUN's annual vectors cannot express a
mid-year change, so there is no workbook reference for this).

Uses the fully-injected metadata path (new_glp/new_gsp/new_7pay) so no rates
database or guideline solver is needed.
"""
import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from suiteview.illustration.core.calc_engine import _recalc_guideline_on_change
from suiteview.illustration.models.input_set import PolicyChangeEvent, PolicyChangeKind
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def _policy(glp: float) -> IllustrationPolicyData:
    return IllustrationPolicyData(
        plancode="TEST", issue_date=date(2000, 1, 12), duration=120,
        glp=glp, gsp=50000.0,
    )


def _change(change_date: date, new_glp: float) -> PolicyChangeEvent:
    return PolicyChangeEvent(
        kind=PolicyChangeKind.FACE_AMOUNT, effective_date=change_date,
        value=40000.0,
        metadata={"new_glp": new_glp, "new_gsp": 50000.0, "new_7pay": 3000.0},
    )


def _recalc(policy, change, change_date):
    return _recalc_guideline_on_change(
        policy, None, change, 40,
        change_date=change_date, before=None, av=0.0, material_change=True)


def test_midyear_recalc_prorates_accum_glp():
    # Robert's example: change at BOM 4, old GLP 4000, new GLP 1000 ->
    # adjustment = 9/12 * (new - old). Monthly-cent floors: 3999.96 / 999.96.
    policy = _policy(glp=4000.0)
    change_date = date(2010, 4, 12)  # policy month 4 (issue day Jan 12)
    detail = _recalc(policy, _change(change_date, 1000.0), change_date)
    assert detail["accum_glp_adjustment"] == round(0.75 * (999.96 - 3999.96), 2)
    assert detail["accum_glp_adjustment"] == -2250.0
    assert detail["accum_glp_months_remaining"] == 9
    assert policy.glp == 999.96


def test_recalc_summary_shows_accum_glp_adjustment():
    # Values tab TEFRA/TAMRA Summary: one column explains the true-up (or why
    # there was none).
    from suiteview.illustration.ui.values_tab import _accum_glp_adjust_text

    assert _accum_glp_adjust_text(
        {"accum_glp_adjustment": -2250.0, "accum_glp_months_remaining": 9}
    ) == "-2,250.00  (9/12 × GLP Δ)"
    assert _accum_glp_adjust_text(
        {"glp_prior": 3999.96, "glp_new": 999.96}
    ) == "none — anniversary (full year at new GLP)"
    assert _accum_glp_adjust_text(
        {"glp_prior": 999.96, "glp_new": 999.96}
    ) == "none — GLP unchanged"


def test_anniversary_recalc_needs_no_adjustment():
    # m=1: the anniversary accumulation this month already reads the new GLP.
    policy = _policy(glp=4000.0)
    change_date = date(2010, 1, 12)
    detail = _recalc(policy, _change(change_date, 1000.0), change_date)
    assert "accum_glp_adjustment" not in detail


def test_unchanged_glp_needs_no_adjustment():
    policy = _policy(glp=1000.0)
    change_date = date(2010, 4, 12)
    detail = _recalc(policy, _change(change_date, 1000.0), change_date)
    assert "accum_glp_adjustment" not in detail
