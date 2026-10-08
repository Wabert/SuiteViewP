"""Shadow-account rules found by running the engine from issue against CyberLife XP (2026-10-07).

* SGUL N+1 target relief on the TPP/EPP load (all modes).
* SGUL shadow interest (1+i)^(1/12)-1 in history replays (rollback / from issue).
* A premium received before the anniversary it is bucketed to is posted to the prior
  policy year's total, and is loaded against the new year's total without being added
  to it (history replays; non-forgiveness plans such as LTGUL).
"""
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core.calc_engine import _shadow_premium_totals, _shadow_prior_year_premium
from suiteview.illustration.core.input_compiler import compile_month_inputs
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.shadow_calc import ShadowInput, calculate_shadow
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData

SGUL_PLANCODES = ("1U145700", "1U146000", "1U146100", "1U146200", "1U146300", "1U146600",
                  "1U146700", "1U147200", "1U147300", "1U147600", "1U147700")


def _rates(**overrides) -> IllustrationRates:
    values = dict(
        shadow_coi=[None, 0.0],
        shadow_tpr=[None, 10.0],
        shadow_tpr_tbl1=[None, 0.0],
        shadow_tpp=[None, 0.06],
        shadow_epp=[None, 0.35],
        shadow_int=[None, 0.045],
        shadow_dbd=[None, 0.045],
        shadow_epu=[None, 0.0],
    )
    values.update(overrides)
    return IllustrationRates(**values)


def _policy(**fields) -> IllustrationPolicyData:
    policy = IllustrationPolicyData(
        face_amount=100_000.0,
        db_option="A",
        ccv_active=True,
        premiums_paid_to_date=0.0,
        segments=[CoverageSegment(
            face_amount=100_000.0, original_face_amount=100_000.0, issue_age=45,
            rate_sex="M", rate_class="N", band=1, original_band=1,
        )],
    )
    for name, value in fields.items():
        setattr(policy, name, value)
    return policy


def _shadow(config, *, gross, ytd, ptd, year=3, month=1, policy=None, rates=None, **kw):
    return calculate_shadow(ShadowInput(
        prev_shadow_eav=kw.pop("prev", 0.0), gross_premium=gross, premiums_ytd=ytd, premiums_to_date=ptd,
        policy=policy or _policy(), config=config, rates=rates or _rates(), rate_year=year,
        policy_month=month, attained_age=45, days_in_month=31, policy_debt=0.0, **kw,
    ))


# --- SGUL N+1 relief ---------------------------------------------------------------------------

def test_sgul_nplus1_relief_loads_early_next_year_premium_at_tpp():
    # Target 1,000. Year 3, month 9 (8 full months done): YTD after 1,500 is above one
    # target but within 2, and premium to date 3,500 is within (3+1) targets.
    config = PlancodeConfig(shadow_nplus1_relief=True)
    result = _shadow(config, gross=500.0, ytd=1_500.0, ptd=3_500.0, month=9)
    assert result.shadow_prem_over_target == 0.0
    assert result.shadow_prem_load == pytest.approx(500.0 * 0.06)
    without = _shadow(PlancodeConfig(), gross=500.0, ytd=1_500.0, ptd=3_500.0, month=9)
    assert without.shadow_prem_load == pytest.approx(500.0 * 0.35)


def test_sgul_nplus1_relief_waits_for_seven_full_policy_months():
    config = PlancodeConfig(shadow_nplus1_relief=True)
    result = _shadow(config, gross=500.0, ytd=1_500.0, ptd=3_500.0, month=7)
    assert result.shadow_prem_over_target == 500.0


def test_sgul_nplus1_relief_is_capped_by_premium_to_date_and_two_targets():
    config = PlancodeConfig(shadow_nplus1_relief=True)
    # Premium to date 4,300 is 300 above (3+1) targets: 300 of the premium is excess.
    capped = _shadow(config, gross=500.0, ytd=1_500.0, ptd=4_300.0, month=9)
    assert capped.shadow_prem_over_target == pytest.approx(300.0)
    # YTD 2,400 is 400 above 2 targets: that 400 is excess even within (N+1) targets.
    within = _shadow(config, gross=500.0, ytd=2_400.0, ptd=3_500.0, month=9)
    assert within.shadow_prem_over_target == pytest.approx(400.0)
    # Both allowances exceeded: the larger excess is loaded (relief needs both).
    both = _shadow(config, gross=500.0, ytd=2_400.0, ptd=4_450.0, month=9)
    assert both.shadow_prem_over_target == pytest.approx(450.0)


@pytest.mark.parametrize("plancode", SGUL_PLANCODES)
def test_sgul_plancodes_carry_the_history_and_relief_flags(plancode):
    config = load_plancode(plancode)
    assert config.shadow_nplus1_relief and config.shadow_monthly_interest


@pytest.mark.parametrize("plancode", ["1U143800", "1U144500", "1U135200", "1U135400", "1U135L00"])
def test_ltgul_and_passport_keep_their_own_rules(plancode):
    config = load_plancode(plancode)
    assert not config.shadow_nplus1_relief and not config.shadow_monthly_interest


# --- monthly-effective shadow interest in history replays --------------------------------------

def _interest(*, history, flag):
    policy = _policy(run_from_issue=history)
    return _shadow(PlancodeConfig(shadow_monthly_interest=flag), gross=0.0, ytd=0.0, ptd=0.0,
                   policy=policy, prev=10_000.0, display_days_in_month=31)


def test_history_replay_credits_sgul_shadow_a_monthly_effective_rate():
    result = _interest(history=True, flag=True)
    assert result.shadow_eff_rate == pytest.approx(1.045 ** (1 / 12) - 1)
    assert result.shadow_days == pytest.approx(365 / 12)


@pytest.mark.parametrize("history,flag", [(False, True), (True, False)])
def test_exact_days_shadow_interest_is_kept_otherwise(history, flag):
    result = _interest(history=history, flag=flag)
    assert result.shadow_eff_rate == pytest.approx(1.045 ** (31 / 365) - 1)


# --- prior-year receipt bucketed to the anniversary ---------------------------------------------

def test_prior_year_receipt_is_loaded_against_the_new_year_without_counting_in_it():
    config = PlancodeConfig(shadow_aps205_load_relief=True)
    rates = _rates(shadow_tpp=[None, 0.0], shadow_epp=[None, 0.45])
    # U0609851 shape: anniversary month, 950 received in the old year (whose total is
    # far above target). The new year's total excludes it, so nothing is loaded.
    result = _shadow(config, gross=950.0, ytd=0.0, ptd=20_000.0, rates=rates,
                     prior_year_gross_premium=950.0)
    assert result.shadow_prem_load == 0.0
    assert result.shadow_net_prem == 950.0
    # A prior-year receipt above one target alone is not loaded either: U0574638 (annual
    # 3,344 paid before the anniversary, target 2,150) from issue -6,274 -> +60 vs XP only
    # without that load; loading the part above target leaves it at -6,274.
    big = _shadow(config, gross=1_400.0, ytd=0.0, ptd=20_000.0, rates=rates,
                  prior_year_gross_premium=1_400.0)
    assert big.shadow_prem_load == 0.0


def test_prior_year_receipt_part_does_not_change_ordinary_premiums():
    config = PlancodeConfig(shadow_aps205_load_relief=True)
    rates = _rates(shadow_tpp=[None, 0.0], shadow_epp=[None, 0.45])
    plain = _shadow(config, gross=600.0, ytd=1_200.0, ptd=20_000.0, month=5, rates=rates)
    explicit = _shadow(config, gross=600.0, ytd=1_200.0, ptd=20_000.0, month=5, rates=rates,
                       prior_year_gross_premium=0.0)
    assert plain == explicit
    assert plain.shadow_prem_load == pytest.approx(200.0 * 0.45)


def _replay_policy():
    return _policy(issue_date=date(2009, 5, 23), valuation_date=date(2026, 3, 23), duration=203,
                   rollback_date=date(2026, 3, 23))


def test_compiler_flags_a_receipt_from_the_prior_policy_year():
    policy = _replay_policy()
    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(kind=TransactionKind.PREMIUM, effective_date=date(2026, 5, 23), amount=23_917.0,
                         metadata={"actual_date": "2026-04-28"}),
        DatedTransaction(kind=TransactionKind.PREMIUM, effective_date=date(2026, 6, 23), amount=23_939.0,
                         metadata={"actual_date": "2026-05-28"}),
    ])
    compiled = compile_month_inputs(policy, inputs, 4)
    assert compiled[205].shadow_prior_year_premium == 23_917.0  # 5/23 anniversary (duration 205)
    assert compiled[206].shadow_prior_year_premium == 0.0


def test_compiler_ignores_prior_year_receipts_outside_history_replays():
    policy = _replay_policy()
    policy.rollback_date = None
    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(kind=TransactionKind.PREMIUM, effective_date=date(2026, 5, 23), amount=100.0,
                         metadata={"actual_date": "2026-04-28"}),
    ])
    compiled = compile_month_inputs(policy, inputs, 4)
    assert compiled[205].shadow_prior_year_premium == 0.0


def _ctx(*, forgiveness=False, history=True, prior=0.0, ytd=None, td=None):
    return SimpleNamespace(
        config=SimpleNamespace(shadow_late_payment_forgiveness=forgiveness),
        state=SimpleNamespace(shadow_premiums_ytd=ytd, shadow_premiums_to_date=td),
        policy=SimpleNamespace(run_from_issue=history, rollback_date=None),
        month_inputs=SimpleNamespace(shadow_prior_year_premium=prior),
    )


def _work(*, month, av_ytd, av_td, av_gross):
    return SimpleNamespace(
        next_month=month,
        prem=SimpleNamespace(premiums_ytd=av_ytd, premiums_to_date=av_td, gross_premium=av_gross),
    )


def test_history_shadow_totals_leave_the_prior_year_receipt_out_of_the_new_year():
    ctx = _ctx(prior=100.0, ytd=1_200.0, td=5_000.0)
    work = _work(month=1, av_ytd=100.0, av_td=5_100.0, av_gross=100.0)
    assert _shadow_prior_year_premium(ctx, 100.0) == 100.0
    assert _shadow_premium_totals(ctx, work, 100.0, 100.0) == (0.0, 5_100.0)
    # The next month's YTD carries on from the shadow's own total, not the AV's.
    ctx = _ctx(ytd=0.0, td=5_100.0)
    work = _work(month=2, av_ytd=200.0, av_td=5_200.0, av_gross=100.0)
    assert _shadow_premium_totals(ctx, work, 100.0) == (100.0, 5_200.0)


def test_forgiveness_plans_do_not_use_the_prior_year_split():
    assert _shadow_prior_year_premium(_ctx(forgiveness=True, prior=100.0), 100.0) == 0.0


# --- premium received after the opening monthliversary of a replay ------------------------------

def test_compiler_brings_a_late_premium_after_the_seed_into_month_one():
    policy = _replay_policy()  # rollback seed 3/23/2026 is the opening (inforce) row
    policy.duration = 203
    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(kind=TransactionKind.PREMIUM, effective_date=date(2026, 4, 23), amount=300.0,
                         metadata={"actual_date": "2026-04-02"}),
    ])
    compiled = compile_month_inputs(policy, inputs, 3)
    assert compiled[204].shadow_opening_late_premium == 300.0
    assert compiled[204].shadow_bucketed_prior_period_premium == 300.0


def test_opening_late_premium_is_brought_forward_with_a_month_of_interest():
    config = PlancodeConfig(shadow_late_payment_forgiveness=True, shadow_monthly_interest=True)
    policy = _policy(rollback_date=date(2026, 3, 23))
    base = _shadow(config, gross=0.0, ytd=0.0, ptd=0.0, month=5, policy=policy, prev=1_000.0)
    late = _shadow(config, gross=0.0, ytd=200.0, ptd=200.0, month=5, policy=policy, prev=1_000.0,
                   opening_late_gross_premium=200.0)
    net = round(200.0 * (1 - 0.06), 2)
    assert late.shadow_bav - base.shadow_bav == pytest.approx(round(net * 1.045 ** (1 / 12), 2))


# --- SGUL shadow deducts the gross withdrawal ---------------------------------------------------

@pytest.mark.parametrize("plancode,gross", [("1U145700", True), ("1U146600", True), ("1U143800", False),
                                            ("1U144500", False), ("1U135200", True), ("1U135L00", True)])
def test_withdrawal_basis_flag(plancode, gross):
    assert load_plancode(plancode).shadow_withdrawal_gross is gross


def test_shadow_step_uses_the_gross_withdrawal_when_flagged(monkeypatch):
    from suiteview.illustration.core import calc_engine

    seen = {}

    def fake(inputs):
        seen["wd"] = inputs.gross_withdrawal
        return None

    monkeypatch.setattr(calc_engine, "calculate_shadow", fake)
    monkeypatch.setattr(calc_engine, "_shadow_rider_charges_from_deduction", lambda *a: 0.0)
    for flag, expected in ((True, 990.99), (False, 961.08)):
        ctx = SimpleNamespace(
            config=SimpleNamespace(shadow_late_payment_forgiveness=False, shadow_withdrawal_gross=flag),
            state=SimpleNamespace(shadow_eav=0.0, shadow_premiums_ytd=None, shadow_premiums_to_date=None),
            policy=SimpleNamespace(run_from_issue=False, rollback_date=None),
            month_inputs=None, rates=None,
        )
        work = SimpleNamespace(
            prem=SimpleNamespace(gross_premium=0.0, premiums_ytd=0.0, premiums_to_date=0.0),
            wd=SimpleNamespace(applied_net_withdrawal=961.08, gross_withdrawal=990.99),
            ded=SimpleNamespace(standard_db=0.0), intr=SimpleNamespace(actual_days_in_month=30, days_in_month=30),
            accrual_loan=SimpleNamespace(policy_debt=0.0), rate_year=1, next_month=2, attained_age=50,
            month_date=None,
        )
        calc_engine.calculate_shadow_step(ctx, SimpleNamespace(shadow_enabled=True), work)
        assert seen["wd"] == expected


# --- the shadow band ignores withdrawal-driven face reductions (SGUL) ----------------------------

class _BandDb:
    def get_band(self, plancode, amount, issue_date=None):
        return 2 if amount >= 100_000 else 1


def _band_policy(*, withdrawn, dbo="A"):
    policy = _policy(db_option=dbo, withdrawals_to_date=withdrawn)
    seg = policy.base_segment
    seg.face_amount = seg.original_face_amount = 98_304.0
    seg.band = seg.original_band = 1
    policy.face_amount = 98_304.0
    return policy, seg


@pytest.mark.parametrize("withdrawn,dbo,flag,expected", [
    (1_698.28, "A", True, 2),   # UE057740: 98,304 + 1,698.28 is band 2 before the withdrawals
    (1_000.00, "A", True, 1),   # still band 1 before the withdrawals
    (1_698.28, "B", True, 1),   # increasing DB: withdrawals do not lower the face
    (1_698.28, "A", False, 1),  # plans without the flag keep the current band
    (0.0, "A", True, 1),
])
def test_shadow_band_ignores_withdrawals(withdrawn, dbo, flag, expected):
    from suiteview.illustration.core.rate_loader import _shadow_band

    policy, seg = _band_policy(withdrawn=withdrawn, dbo=dbo)
    config = PlancodeConfig(shadow_band_ignores_withdrawals=flag)
    assert _shadow_band(policy, config, _BandDb(), seg) == expected
