"""Index-strategy loader and blended-rate math vs the RERUN INPUT formulas."""
import pytest

from suiteview.illustration.models.index_strategies import (
    allocation_problems,
    compute_blended_rates,
    is_iul_plan,
    load_index_strategies,
)


def test_non_iul_plancode_returns_none():
    assert load_index_strategies("1S135M0X") is None
    assert not is_iul_plan("1S135M0X")
    assert load_index_strategies("") is None


def test_iul08_strategies_load():
    plan = load_index_strategies("1U144600")
    assert plan is not None
    assert plan.product == "IUL08"
    assert is_iul_plan("1U144600")
    u1 = plan.strategy("U1")
    ix = plan.strategy("IX")
    assert u1.max_rate == pytest.approx(0.035)
    assert ix.max_rate == pytest.approx(0.0623)
    # IUL08 offers only the fixed strategy and the 1-yr PtP cap
    offered = {s.fund_id for s in plan.strategies if s.is_offered}
    assert offered == {"U1", "IX"}


def test_m1_low_volatility_rate_from_mb_column():
    # IUL21/23 carry their low-volatility rate in RERUN's MB column; MB was
    # never implemented — the extraction folds it into M1.
    plan = load_index_strategies("1U147500")   # IUL21
    assert plan.strategy("M1").max_rate == pytest.approx(0.0625)
    plan23 = load_index_strategies("1U147800")  # IUL23
    assert plan23.strategy("M1").max_rate == pytest.approx(0.0625)


def test_multiplier_parameters_load():
    plan = load_index_strategies("1U146800")   # IUL19 offers IP/IR
    ip = plan.strategy("IP")
    ir = plan.strategy("IR")
    assert ip.multiplier == pytest.approx(0.24)
    assert ip.asset_charge == pytest.approx(0.0215)
    assert ir.multiplier == pytest.approx(0.60)
    assert ir.asset_charge == pytest.approx(0.0415)


def test_blend_all_fixed_matches_rerun_defaults():
    # RERUN INPUT default: 100% fixed at 4.5% -> nominal = effective = 0.045,
    # guaranteed blend = 100% x GINT.
    plan = load_index_strategies("1U145500")   # IUL14
    blended = compute_blended_rates(
        plan, {"U1": 1.0}, {"U1": 0.045}, gint=0.035)
    assert blended.nominal == pytest.approx(0.045)
    assert blended.effective == pytest.approx(0.045)
    assert blended.guaranteed == pytest.approx(0.035)
    assert blended.asset_charge_rate == 0.0


def test_blend_truncates_to_four_decimals():
    # INPUT!B52 wraps the weighted sum in TRUNC(...,4).
    plan = load_index_strategies("1U145500")
    blended = compute_blended_rates(
        plan, {"U1": 0.5, "IX": 0.5}, {"U1": 0.035, "IX": 0.0623}, gint=0.035)
    # 0.5*0.035 + 0.5*0.0623 = 0.04865 -> TRUNC 0.0486
    assert blended.nominal == 0.0486
    assert blended.effective == 0.0486
    assert blended.guaranteed == pytest.approx(0.5 * 0.035)


def test_blend_multiplier_strategy_effective_rate():
    # INPUT!E49/E52: IP credits rate x (1 + multiplier) under AG49 index <= 2,
    # and carries its asset charge into the engine's charge rate.
    plan = load_index_strategies("1U146800")   # IUL19
    rate = 0.0727
    blended = compute_blended_rates(plan, {"IP": 1.0}, {"IP": rate}, gint=0.035)
    assert blended.nominal == pytest.approx(0.0727)
    assert blended.effective == pytest.approx(
        int(rate * 1.24 * 10000) / 10000)   # TRUNC(0.090148, 4) = 0.0901
    assert blended.guaranteed == 0.0        # no fixed allocation
    assert blended.asset_charge_rate == pytest.approx(0.0215)


def test_validation_flags_total_unoffered_and_over_max():
    plan = load_index_strategies("1U144600")   # IUL08: U1 + IX only
    # 90% total, allocation to unoffered IF, IX rate above its 6.23% max
    problems = allocation_problems(
        plan,
        {"U1": 0.5, "IX": 0.2, "IF": 0.2},
        {"U1": 0.035, "IX": 0.07},
    )
    text = " ".join(problems)
    assert "must equal 100%" in text
    assert "IF" in text and "not available" in text
    assert "exceeds the current illustrated rate" in text


def test_validation_passes_clean_inputs():
    plan = load_index_strategies("1U144600")
    problems = allocation_problems(
        plan, {"U1": 0.4, "IX": 0.6}, {"U1": 0.035, "IX": 0.0623})
    assert problems == []


def test_default_rates_placeholder_capped_at_ag49_and_gint_for_fixed():
    # Index strategies default to the 6.25% placeholder capped at the AG49
    # max; the fixed strategy defaults to the plan guaranteed rate.
    plan = load_index_strategies("1U146800")   # IUL19 — offers IP/IR too
    defaults = plan.default_rates(gint=0.02)
    assert defaults["U1"] == pytest.approx(0.02)
    for strat in plan.strategies:
        if strat.is_offered and strat.fund_id != "U1":
            assert defaults[strat.fund_id] == pytest.approx(
                min(0.0625, float(strat.max_rate)))


def test_default_rates_without_gint_falls_back_to_table_rate():
    plan = load_index_strategies("1U144600")
    defaults = plan.default_rates()
    assert defaults["U1"] == pytest.approx(0.035)   # JSON table rate
    assert defaults["IX"] == pytest.approx(0.0623)  # min(6.25%, 6.23%)


# ── AG49 regimes (Rates_Control CR78:CS83 / CP79 / CP80) ─────────


def test_ag49_regime_table_loads():
    from suiteview.illustration.models.index_strategies import ag49_regimes
    regimes = ag49_regimes()
    assert [r["name"] for r in regimes] == [
        "Prior to AG49", "AG49", "AG49A", "AG49B"]
    assert regimes[1]["start"].isoformat() == "2015-09-01"
    assert regimes[3]["start"].isoformat() == "2023-05-01"


def test_ag49_index_for_issue_date_floors_at_2():
    # RERUN CP79 = MAX(2, date tier): pre-AG49 issues still illustrate at 2.
    from datetime import date
    from suiteview.illustration.models.index_strategies import (
        ag49_index_for_issue_date,
    )
    assert ag49_index_for_issue_date(date(1985, 7, 23)) == 2
    assert ag49_index_for_issue_date(date(2015, 8, 31)) == 2
    assert ag49_index_for_issue_date(date(2015, 9, 1)) == 2
    assert ag49_index_for_issue_date(date(2020, 11, 25)) == 3
    assert ag49_index_for_issue_date(date(2023, 5, 1)) == 4
    assert ag49_index_for_issue_date(None) == 2


def test_current_ag49_index_is_latest_regime():
    from suiteview.illustration.models.index_strategies import current_ag49_index
    assert current_ag49_index() == 4


def test_loan_credit_spread_by_index():
    # Rates_Control CP80: CHOOSE(index, 0, 0.01, 0.005, 0.005)
    from suiteview.illustration.models.index_strategies import (
        loan_credit_spread_for_index,
    )
    assert loan_credit_spread_for_index(1) == pytest.approx(0.0)
    assert loan_credit_spread_for_index(2) == pytest.approx(0.01)
    assert loan_credit_spread_for_index(3) == pytest.approx(0.005)
    assert loan_credit_spread_for_index(4) == pytest.approx(0.005)


def test_plan_with_ag49_index_gates_multiplier_crediting():
    from suiteview.illustration.models.index_strategies import (
        plan_with_ag49_index,
    )
    plan = load_index_strategies("1U146800")   # IUL19 offers IP/IR
    at2 = plan_with_ag49_index(plan, 2)
    at4 = plan_with_ag49_index(plan, 4)
    assert at2.multiplier_active and not at4.multiplier_active
    assert at2.loan_credit_spread == pytest.approx(0.01)
    assert at4.loan_credit_spread == pytest.approx(0.005)

    allocs = {"IP": 1.0}
    rates = {"IP": 0.06}
    blended2 = compute_blended_rates(at2, allocs, rates, gint=0.035)
    blended4 = compute_blended_rates(at4, allocs, rates, gint=0.035)
    # Index 2: IP credits rate x (1 + 0.24) and charges the 2.15% asset fee.
    assert blended2.effective == pytest.approx(0.0744)
    assert blended2.asset_charge_rate == pytest.approx(0.0215)
    # Index 4 (AG49B): no multiplier crediting, no asset charge.
    assert blended4.effective == pytest.approx(0.06)
    assert blended4.asset_charge_rate == 0.0
