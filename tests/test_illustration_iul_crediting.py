"""Engine-side IUL crediting — AG49 asset charge, variable-loan spread, WAIR.

Hand-computed values follow the RERUN formulas in
docs/Illustration_UL/IUL_AG49_WAIR.md (CalcEngine SS..SX, VV, US..VL).
"""
from datetime import date

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.iul_crediting import (
    build_iul_context,
    cap_wair,
    IULCreditingContext,
    monthly_asset_charge,
    project_tav,
    variable_loan_accrual_rate,
    wair_interest,
    weighted_average_rate,
)
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.input_set import IllustrationOptions
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)

# A plancode present in plancodes/index_strategies.json (IUL14U product).
IUL_PLANCODE = "1U145500"


def _ctx(
    ag49_index=2,
    spread=0.01,
    asset_charge_rate=0.0,
    declared_rate=0.045,
    wair_enabled=True,
    guaranteed_basis=False,
):
    return IULCreditingContext(
        ag49_index=ag49_index,
        loan_credit_spread=spread,
        asset_charge_rate=asset_charge_rate,
        declared_rate=declared_rate,
        wair_enabled=wair_enabled,
        guaranteed_basis=guaranteed_basis,
    )


def _iul_policy(**overrides):
    kwargs = dict(
        plancode=IUL_PLANCODE,
        issue_date=date(2016, 6, 1),
        valuation_date=date(2026, 6, 1),
        issue_age=45,
        attained_age=55,
        maturity_age=121,
        policy_year=11,
        policy_month=1,
        duration=121,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        account_value=20_000.0,
        current_interest_rate=0.0625,   # UO — the effective blend
        guaranteed_interest_rate=0.02,
        iul_declared_rate=0.045,        # UJ
        modal_premium=0.0,
        segments=[CoverageSegment(
            coverage_phase=1, issue_date=date(2016, 6, 1),
            face_amount=100_000.0, units=100.0)],
    )
    kwargs.update(overrides)
    return IllustrationPolicyData(**kwargs)


def _test_config(**overrides):
    kwargs = dict(
        plancode="TEST",
        gint=0.02,
        dbd=0.0,
        premium_load="0",
        prem_flat_load=0.0,
        epu_code="0",
        mfee="10",
        poav_code="0",
        bonus="0",
        corridor_code=None,
        snet_period=0,
        lapse_value="SV",
        interest_method="MonthlyCompounding",
    )
    kwargs.update(overrides)
    return PlancodeConfig(**kwargs)


def _patch_config(monkeypatch, config):
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _plancode: config)
    monkeypatch.setattr(
        calc_engine, "load_bonus_config", lambda _plancode, _date: BonusConfig())
    # The MTP/CTP display detail queries the live UL_Rates DB for the real
    # IUL plancode — irrelevant to crediting, so stub it out.
    monkeypatch.setattr(calc_engine, "compute_target_premiums", lambda *a, **k: None)
    monkeypatch.setattr(
        calc_engine, "build_target_detail_snapshots", lambda _policy, _targets: ({}, {}))
    # The coverage-after-change snapshot bands the current face via the live
    # UL_Rates DB (no DSN on this machine) — stub the Rates class.
    import suiteview.core.rates as core_rates

    class _FakeRatesDB:
        def get_band(self, _plancode, _face, issue_date=None):
            return None

    monkeypatch.setattr(core_rates, "Rates", _FakeRatesDB)


# ── AG49 regime resolution ────────────────────────────────────


def test_context_none_for_declared_rate_plan():
    policy = _iul_policy(plancode="TEST")
    assert build_iul_context(policy, IllustrationOptions()) is None


def test_regime_current_when_policy_regime_unchecked():
    ctx = build_iul_context(
        _iul_policy(), IllustrationOptions(use_policy_ag49_regime=False))
    assert ctx.ag49_index == 4                 # AG49B — the current regime
    assert ctx.loan_credit_spread == pytest.approx(0.005)
    assert ctx.asset_charge_rate == 0.0        # SU zero above index 2


def test_regime_by_issue_date_when_checked():
    opts = IllustrationOptions(use_policy_ag49_regime=True)
    # 2016 issue → original AG49 (index 2, spread 0.01)
    ctx = build_iul_context(_iul_policy(), opts)
    assert ctx.ag49_index == 2
    assert ctx.loan_credit_spread == pytest.approx(0.01)
    # Pre-2015 issue floors at AG49 (RERUN CP79 = MAX(2, tier))
    ctx = build_iul_context(_iul_policy(issue_date=date(1990, 1, 1)), opts)
    assert ctx.ag49_index == 2
    # AG49A window
    ctx = build_iul_context(_iul_policy(issue_date=date(2021, 1, 1)), opts)
    assert ctx.ag49_index == 3
    assert ctx.loan_credit_spread == pytest.approx(0.005)
    # AG49B
    ctx = build_iul_context(_iul_policy(issue_date=date(2024, 1, 1)), opts)
    assert ctx.ag49_index == 4


def test_context_asset_charge_from_allocations_fallback():
    # 50% IP (0.0215) + 25% IR (0.0415), percent-form allocations — SU under
    # regime 2 = 0.5×0.0215 + 0.25×0.0415 = 0.021125.
    policy = _iul_policy(
        iul_asset_charge_rate=None,
        premium_allocations={"IP": 50.0, "IR": 25.0, "U1": 25.0},
    )
    ctx = build_iul_context(policy, IllustrationOptions(use_policy_ag49_regime=True))
    assert ctx.asset_charge_rate == pytest.approx(0.021125)


def test_context_declared_rate_falls_back_to_gint():
    policy = _iul_policy(iul_declared_rate=None, guaranteed_interest_rate=0.03)
    ctx = build_iul_context(policy, IllustrationOptions())
    assert ctx.declared_rate == pytest.approx(0.03)


# ── Asset charge (SS..SX) ─────────────────────────────────────


def test_asset_charge_formula():
    # SV = MAX(0, SU/12 × (OO − MS − MT)) = 0.0265/12 × (10000 − 2000 − 50)
    ctx = _ctx(ag49_index=2, asset_charge_rate=0.0265)
    assert monthly_asset_charge(ctx, 10_000.0, 2_000.0, 50.0) == pytest.approx(
        0.0265 / 12.0 * 7_950.0)


def test_asset_charge_floors_at_zero():
    ctx = _ctx(ag49_index=2, asset_charge_rate=0.0265)
    assert monthly_asset_charge(ctx, 1_000.0, 2_000.0, 0.0) == 0.0


def test_asset_charge_gated_by_regime():
    # The SX CHOOSE deducts the charge only under regimes 1-2.
    ctx3 = _ctx(ag49_index=3, asset_charge_rate=0.0265)
    ctx4 = _ctx(ag49_index=4, asset_charge_rate=0.0265)
    assert monthly_asset_charge(ctx3, 10_000.0, 0.0, 0.0) == 0.0
    assert monthly_asset_charge(ctx4, 10_000.0, 0.0, 0.0) == 0.0
    assert monthly_asset_charge(None, 10_000.0, 0.0, 0.0) == 0.0


# ── Variable-loan accrual rate (VV) ───────────────────────────


def test_variable_loan_rate_spread_choose():
    # VV: MAX(input, UO − spread) once AG49 applies (index > 1).
    ctx2 = _ctx(ag49_index=2, spread=0.01)
    assert variable_loan_accrual_rate(ctx2, 0.04, 0.0625) == pytest.approx(0.0525)
    assert variable_loan_accrual_rate(ctx2, 0.06, 0.0625) == pytest.approx(0.06)
    ctx3 = _ctx(ag49_index=3, spread=0.005)
    assert variable_loan_accrual_rate(ctx3, 0.04, 0.0625) == pytest.approx(0.0575)
    # Pre-AG49 (index 1): the input rate as-is.
    ctx1 = _ctx(ag49_index=1, spread=0.0)
    assert variable_loan_accrual_rate(ctx1, 0.04, 0.0625) == pytest.approx(0.04)
    # Non-IUL plan: input rate untouched.
    assert variable_loan_accrual_rate(None, 0.04, 0.0625) == pytest.approx(0.04)
    # No input rate → the index-linked floor.
    assert variable_loan_accrual_rate(ctx2, None, 0.0625) == pytest.approx(0.0525)


# ── TAV projection (US..VG) ───────────────────────────────────


def test_tav_projection_premium_capped_by_annual_room():
    # UU = 1000×12; UV = 12500; no repay; VE = MIN(12500, NK=8000);
    # VF = 50000 + 8000×(1−0.06) = 57520.
    tav = project_tav(
        begin_av=50_000.0, planned_premium=1_000.0, payments_per_year=12,
        lumpsum=500.0, policy_month=1,
        fixed_ln_principal=0.0, fixed_ln_accrued=0.0,
        vbl_ln_principal=0.0, vbl_ln_accrued=0.0,
        reg_loan_charge_rate=0.05, vbl_loan_rate=0.06,
        apply_prem_to_loan=False, is_cvat=False,
        annual_cap=8_000.0, premium_load=0.06,
    )
    assert tav.forecast_premium == pytest.approx(12_500.0)
    assert tav.loan_repayment == 0.0
    assert tav.capped_premium == pytest.approx(8_000.0)
    assert tav.tav == pytest.approx(57_520.0)
    assert tav.tav_display == pytest.approx(57_520.0)


def test_tav_projection_cvat_skips_the_cap():
    tav = project_tav(
        begin_av=50_000.0, planned_premium=1_000.0, payments_per_year=12,
        lumpsum=500.0, policy_month=1,
        fixed_ln_principal=0.0, fixed_ln_accrued=0.0,
        vbl_ln_principal=0.0, vbl_ln_accrued=0.0,
        reg_loan_charge_rate=0.05, vbl_loan_rate=0.06,
        apply_prem_to_loan=False, is_cvat=True,
        annual_cap=8_000.0, premium_load=0.0,
    )
    assert tav.capped_premium == pytest.approx(12_500.0)
    assert tav.tav == pytest.approx(62_500.0)


def test_tav_projection_apply_prem_to_loan_diverts_premium():
    # VA = 10000×(1+0.05×1) + 100 = 10600; VB = 5000×(1+0.06×1) + 50 = 5350;
    # VC = MIN(12500, 15950) = 12500 → VD = 0 → VF = begin AV.
    tav = project_tav(
        begin_av=50_000.0, planned_premium=1_000.0, payments_per_year=12,
        lumpsum=500.0, policy_month=1,
        fixed_ln_principal=10_000.0, fixed_ln_accrued=100.0,
        vbl_ln_principal=5_000.0, vbl_ln_accrued=50.0,
        reg_loan_charge_rate=0.05, vbl_loan_rate=0.06,
        apply_prem_to_loan=True, is_cvat=False,
        annual_cap=999_999_999.0, premium_load=0.06,
    )
    assert tav.loan_repayment == pytest.approx(12_500.0)
    assert tav.capped_premium == 0.0
    assert tav.tav == pytest.approx(50_000.0)


def test_tav_projection_mid_year_loan_interest_fraction():
    # (13 − month)/12 at month 7 → half a year of loan interest.
    tav = project_tav(
        begin_av=0.0, planned_premium=0.0, payments_per_year=0,
        lumpsum=20_000.0, policy_month=7,
        fixed_ln_principal=10_000.0, fixed_ln_accrued=0.0,
        vbl_ln_principal=0.0, vbl_ln_accrued=0.0,
        reg_loan_charge_rate=0.05, vbl_loan_rate=0.06,
        apply_prem_to_loan=True, is_cvat=False,
        annual_cap=999_999_999.0, premium_load=0.0,
    )
    # VA = 10000×(1 + 0.05×0.5) = 10250 → VC = MIN(20000, 10250) = 10250.
    assert tav.loan_repayment == pytest.approx(10_250.0)
    assert tav.capped_premium == pytest.approx(9_750.0)


def test_tav_display_floors_at_zero():
    tav = project_tav(
        begin_av=-500.0, planned_premium=0.0, payments_per_year=0,
        lumpsum=0.0, policy_month=1,
        fixed_ln_principal=0.0, fixed_ln_accrued=0.0,
        vbl_ln_principal=0.0, vbl_ln_accrued=0.0,
        reg_loan_charge_rate=0.05, vbl_loan_rate=0.06,
        apply_prem_to_loan=False, is_cvat=False,
        annual_cap=0.0, premium_load=0.0,
    )
    assert tav.tav == pytest.approx(-500.0)
    assert tav.tav_display == 0.0


# ── WAIR weighting (VI/VJ) ────────────────────────────────────


def test_wair_three_slice_weighting():
    # sweep 6000@5% + loaned 20000@4.5% + indexed 73500@6.25%, over 100000:
    # (300 + 900 + 4593.75)/100000 = 0.0579375
    wair = weighted_average_rate(
        av=100_000.0, swam=6_000.0,
        reg_ln_principal=20_000.0, reg_ln_accrued=500.0,
        reg_loan_credit_rate=0.045,
        declared_plus_bonus=0.05, blend_plus_bonus=0.0625,
    )
    assert wair == pytest.approx((6_000 * 0.05 + 20_000 * 0.045
                                  + 73_500 * 0.0625) / 100_000)


def test_wair_zero_when_av_not_positive():
    assert weighted_average_rate(
        av=0.0, swam=1_000.0, reg_ln_principal=0.0, reg_ln_accrued=0.0,
        reg_loan_credit_rate=0.045, declared_plus_bonus=0.05,
        blend_plus_bonus=0.0625) == 0.0


def test_wair_sweep_slice_clamped_to_av():
    # SWAM above AV: the whole AV earns the declared rate.
    wair = weighted_average_rate(
        av=5_000.0, swam=10_000.0, reg_ln_principal=0.0, reg_ln_accrued=0.0,
        reg_loan_credit_rate=0.045, declared_plus_bonus=0.05,
        blend_plus_bonus=0.0625)
    assert wair == pytest.approx(0.05)


def test_wair_guaranteed_cap_and_interest():
    ctx_cur = _ctx(guaranteed_basis=False)
    ctx_gtd = _ctx(guaranteed_basis=True)
    assert cap_wair(ctx_cur, 0.058, 0.045) == pytest.approx(0.058)
    assert cap_wair(ctx_gtd, 0.058, 0.045) == pytest.approx(0.045)   # VK MIN
    assert cap_wair(ctx_gtd, 0.030, 0.045) == pytest.approx(0.030)
    # VL = MAX(0, AV×((1+WAIR)^(days/365) − 1))
    days = 365.0 / 12.0
    assert wair_interest(20_000.0, 0.0579375, days) == pytest.approx(
        20_000.0 * ((1.0579375) ** (1.0 / 12.0) - 1.0))
    assert wair_interest(20_000.0, -0.02, days) == 0.0


# ── Engine wiring ─────────────────────────────────────────────


def _project(policy, options, monkeypatch, months=13, config=None):
    _patch_config(monkeypatch, config or _test_config())
    return IllustrationEngine().project(
        policy, months=months, stop_on_lapse=False,
        rates_override=IllustrationRates(), bonus_override=BonusConfig(),
        options=options)


def test_engine_wair_valuation_row_uses_vi(monkeypatch):
    policy = _iul_policy(sweep_account_min=5_000.0)
    options = IllustrationOptions(
        iul_wair_crediting=True, use_policy_ag49_regime=True)
    results = _project(policy, options, monkeypatch, months=1)
    m0 = results[0]
    # VI = (5000×0.045 + 15000×0.0625)/20000 (no loans, bonus 0)
    expected_vi = (5_000 * 0.045 + 15_000 * 0.0625) / 20_000
    assert m0.wair_swam == pytest.approx(5_000.0)
    assert m0.wair_held == pytest.approx(expected_vi)
    assert m0.wair_rate == pytest.approx(expected_vi)
    assert m0.interest_credited == pytest.approx(
        20_000.0 * ((1.0 + expected_vi) ** (1.0 / 12.0) - 1.0))
    assert m0.av_end_of_month == pytest.approx(20_000.0 + m0.interest_credited)


def test_engine_wair_recomputed_at_boy_and_held(monkeypatch):
    policy = _iul_policy(sweep_account_min=5_000.0)
    options = IllustrationOptions(
        iul_wair_crediting=True, use_policy_ag49_regime=True)
    results = _project(policy, options, monkeypatch, months=13)

    m1 = results[1]
    # First projected month is a beginning-of-year row: the TAV is the AV post
    # withdrawal (= prior EOM AV here — no premium accepted, guideline room 0),
    # and VH proxies the SWAM as this month's deduction × 12.
    assert m1.wair_tav == pytest.approx(results[0].av_end_of_month)
    assert m1.wair_swam == pytest.approx(m1.total_deduction * 12.0)
    expected_vj = (
        min(m1.wair_swam, m1.wair_tav) * 0.045
        + (m1.wair_tav - min(m1.wair_swam, m1.wair_tav)) * 0.0625
    ) / m1.wair_tav
    assert m1.wair_held == pytest.approx(expected_vj)
    # VL replaces the blend credit: no impaired split under WAIR.
    assert m1.reg_impaired_int == 0.0
    assert m1.effective_annual_rate == pytest.approx(m1.wair_rate)
    assert m1.interest_credited == pytest.approx(
        m1.av_after_exception * ((1.0 + m1.wair_rate) ** (1.0 / 12.0) - 1.0))

    # Held through the policy year (VJ carry-forward)…
    for state in results[2:12]:
        assert state.wair_held == pytest.approx(m1.wair_held)
        assert state.wair_tav == pytest.approx(m1.wair_tav)
    # …and recomputed at the next anniversary from the grown AV.
    m12 = results[12]
    assert m12.is_anniversary
    assert m12.wair_tav == pytest.approx(results[11].av_end_of_month)
    assert m12.wair_tav > m1.wair_tav


def test_engine_wair_guaranteed_run_caps_at_declared(monkeypatch):
    policy = _iul_policy(sweep_account_min=0.0)
    options = IllustrationOptions(
        iul_wair_crediting=True, use_policy_ag49_regime=True,
        guaranteed_assumption=True)
    results = _project(policy, options, monkeypatch, months=2)
    for state in results:
        # The uncapped WAIR sits near the blend (0.0625) — the guaranteed run
        # caps the credited rate at the declared rate (VK).
        assert state.wair_held > 0.045
        assert state.wair_rate == pytest.approx(0.045)


def test_engine_wair_off_keeps_blended_crediting(monkeypatch):
    policy = _iul_policy(sweep_account_min=5_000.0)
    options = IllustrationOptions(
        iul_wair_crediting=False, use_policy_ag49_regime=True)
    results = _project(policy, options, monkeypatch, months=2)
    for state in results:
        assert state.wair_rate == 0.0
        assert state.wair_held == 0.0
    assert results[1].effective_annual_rate == pytest.approx(0.0625)


def test_engine_asset_charge_deducted_under_regimes_1_2(monkeypatch):
    policy = _iul_policy(iul_asset_charge_rate=0.024)
    options = IllustrationOptions(use_policy_ag49_regime=True)   # index 2
    results = _project(policy, options, monkeypatch, months=2)
    m1 = results[1]
    assert m1.asset_charge_rate == pytest.approx(0.024)
    # SV = SU/12 × (OO − MS − MT); no loans → charge base is the pre-deduction AV.
    assert m1.asset_charge == pytest.approx(0.024 / 12.0 * m1.av_after_premium)
    # SX: the charge comes out of AV alongside the monthly deduction.
    assert m1.av_after_deduction == pytest.approx(
        m1.av_after_premium - m1.total_deduction - m1.asset_charge)
    # Valuation row takes the system AV verbatim — no charge.
    assert results[0].asset_charge == 0.0


def test_engine_asset_charge_zero_under_current_regime(monkeypatch):
    policy = _iul_policy(iul_asset_charge_rate=0.024)
    options = IllustrationOptions(use_policy_ag49_regime=False)  # index 4
    results = _project(policy, options, monkeypatch, months=2)
    m1 = results[1]
    assert m1.asset_charge_rate == 0.0
    assert m1.asset_charge == 0.0
    assert m1.av_after_deduction == pytest.approx(
        m1.av_after_premium - m1.total_deduction)


def test_engine_variable_loan_accrues_at_spread_rate(monkeypatch):
    policy = _iul_policy(
        variable_loan_principal=10_000.0,
        variable_loan_charge_rate=0.04,
    )
    options = IllustrationOptions(use_policy_ag49_regime=True)   # index 2, spread 1%
    results = _project(policy, options, monkeypatch, months=1)
    # Accrual at MAX(0.04, 0.0625 − 0.01) = 5.25%: 10000 × 0.0525 × (365/12)/365.
    assert results[0].vbl_loan_charge == pytest.approx(10_000.0 * 0.0525 / 12.0)


def test_engine_non_iul_variable_loan_uses_input_rate(monkeypatch):
    policy = _iul_policy(
        plancode="TEST",
        variable_loan_principal=10_000.0,
        variable_loan_charge_rate=0.04,
    )
    results = _project(policy, IllustrationOptions(), monkeypatch, months=1)
    assert results[0].vbl_loan_charge == pytest.approx(10_000.0 * 0.04 / 12.0)
