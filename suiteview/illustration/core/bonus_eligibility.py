"""Conditional interest-bonus eligibility — CyberLife mod AN0230 (reward type C).

The ANICO1996 PULU plans (1U135900 / 1U135H00 / 1U135Q00) carry a two-tier duration
bonus: 0.50% in policy years 11-20 and 0.75% from year 21 (SR113413 business
requirements; Robert Haessly's note of 8/24/2021). Each tier is earned only by passing
the AN0230 test at the start of its first year (the 11th and 21st):

* premiums paid are at least the accumulated minimum premium (MAP, ``LH_POL_TARGET`` 'MA');
* the face amount has not been decreased;
* there have been no partial withdrawals.

A policy that fails at year 11 never gets a bonus; one that passes at 11 but fails at 21
keeps the 0.50% for good. CyberLife records the stage reached in
``LH_NON_TRD_POL.PRO_BNS_RS_CD``: ``0`` none, ``5`` tier 1, ``6`` tier 2 (DB2 CKPR
2026-10-04: code 5 set at the 10th/11th anniversary on 15,853 policies, code 6 at the
20th/21st on 306; the 33 code-0 policies have no date).

Resolution, one tier at a time:

* The stage code already reaches the tier -> earned (it never moves down).
* The tier's test year has passed (the run starts in or after it) -> the code is final:
  a stage-5 policy past year 21 stays at 0.50%, a stage-0 policy past year 11 stays at 0.
  A blank or unknown code falls back to the projected test on in-force values.
* The test year is still ahead -> the projected test below.

**Projected test (approximation).** Run on the in-force values plus the illustrated
scenario up to the test anniversary:

* withdrawals: none to date (``withdrawals_to_date``) and none requested in the scenario;
* face: no base coverage below its original face, and no requested face change below the
  face before it, after the engine's plan-minimum limit (``core.face_minimum``): a decrease
  the minimum fully blocks is no decrease, and the applied face carries forward;
* premiums: premiums to date plus the scenario premiums (a month without a scenario
  premium bills the modal premium, as the engine does) at least the MAP accumulated by
  the test date - the in-force 'MA' accumulation plus the monthly MTP for the rest of the
  MAP period (the first 120 months; IAF "MAP PERIOD 120").

It ignores guideline/TAMRA premium limits and the engine's own lapse/force-outs; a
scenario that the engine later caps can therefore be projected to pass. CyberLife's
VP/MS model is not readable, so this is the documented rule, not a replica.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.face_minimum import limited_decrease
from suiteview.illustration.core.input_compiler import compile_month_inputs
from suiteview.illustration.models.input_set import IllustrationInputSet, PolicyChangeKind
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData

# LH_NON_TRD_POL.PRO_BNS_RS_CD -> duration tiers earned.
STAGE_TIERS = {"0": 0, "5": 1, "6": 2}
# The MAP target accumulates over the first 120 policy months (IAF "MAP PERIOD 120").
MAP_PERIOD_MONTHS = 120
_EPS = 0.005


def apply_bonus_eligibility(
    bonus: BonusConfig,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    future_inputs: Optional[IllustrationInputSet] = None,
) -> BonusConfig:
    """``bonus`` capped at the tier the policy earns; unconditional plans unchanged."""
    if not bonus.bonus_conditional:
        return bonus
    return replace(bonus, bonus_max_tier=earned_bonus_tier(bonus, policy, config, future_inputs))


def stage_tier(stage_code) -> Optional[int]:
    """Tier recorded by ``PRO_BNS_RS_CD``; None for a blank or unknown code."""
    return STAGE_TIERS.get(str(stage_code or "").strip())


def with_recorded_stage(bonus: BonusConfig, stage_code) -> BonusConfig:
    """A conditional bonus capped at the recorded stage alone (no projected test).

    Right for the policy's current year: a tier still ahead cannot apply yet. A blank or
    unknown code leaves the bonus uncapped.
    """
    tier = stage_tier(stage_code)
    if not bonus.bonus_conditional or tier is None:
        return bonus
    return replace(bonus, bonus_max_tier=tier)


def earned_bonus_tier(
    bonus: BonusConfig,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    future_inputs: Optional[IllustrationInputSet] = None,
) -> int:
    """Highest duration tier the policy earns over the run (see the module docstring)."""
    recorded = stage_tier(policy.prospective_bonus_stage)
    earned = 0
    for tier, (threshold, _rate) in enumerate(bonus.duration_tiers(), start=1):
        test_year = threshold + 1
        if recorded is not None and recorded >= tier:
            passed = True
        elif recorded is not None and policy.policy_year >= test_year:
            passed = False
        else:
            passed = projected_test_passes(policy, config, future_inputs, test_year)
        if not passed:
            break
        earned = tier
    return earned


def projected_test_passes(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    future_inputs: Optional[IllustrationInputSet],
    test_year: int,
) -> bool:
    """The AN0230 test at the start of ``test_year`` on in-force values plus the scenario."""
    if policy.withdrawals_to_date > _EPS:
        return False
    if any(seg.is_base and seg.face_amount < seg.original_face_amount - _EPS
           for seg in policy.segments):
        return False
    test_duration = (test_year - 1) * 12  # last month before the test anniversary
    months = max(0, test_duration - policy.duration)
    compiled = compile_month_inputs(policy, future_inputs, months)
    premiums = float(policy.premiums_paid_to_date or 0.0)
    for duration in range(policy.duration + 1, policy.duration + months + 1):
        month = compiled.get(duration)
        if month is not None and (month.withdrawal > _EPS or month.withdrawal_gross > _EPS):
            return False
        total = month.total_premium if month is not None else None
        premiums += float(policy.modal_premium or 0.0) if total is None else float(total)
    if _scenario_decreases_face(policy, config, future_inputs, test_year):
        return False
    remaining_map_months = max(0, min(MAP_PERIOD_MONTHS, test_duration) - policy.duration)
    required = float(policy.accumulated_mtp or 0.0) + float(policy.mtp or 0.0) * remaining_map_months
    return premiums + _EPS >= required


def _scenario_decreases_face(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    future_inputs: Optional[IllustrationInputSet],
    test_year: int,
) -> bool:
    """Whether a requested face change before the test date lowers the face the engine applies.

    Each request is limited at the plan minimum face as the engine limits it
    (``core.face_minimum``): a fully blocked decrease is no decrease, and the applied
    face (not the request) carries forward to the next change.
    """
    if future_inputs is None or policy.issue_date is None:
        return False
    test_date: date = policy.issue_date + relativedelta(years=test_year - 1)
    face = float(policy.total_face)
    changes = sorted(
        (c for c in future_inputs.policy_changes
         if c.kind == PolicyChangeKind.FACE_AMOUNT and c.effective_date < test_date),
        key=lambda c: c.effective_date)
    for change in changes:
        requested = float(change.value)
        if requested >= face:
            face = requested
            continue
        applied = face - limited_decrease(config, face, face - requested, change.metadata)
        if applied < face - _EPS:
            return True
        face = applied
    return False
