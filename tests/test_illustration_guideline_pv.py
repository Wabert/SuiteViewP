"""The month-by-month guideline PV must reconcile to the account-value solver.

``guideline_pv`` is only an alternative *presentation* of the GLP that
``solve_endowment_premium`` produces — an exact algebraic unrolling of the same
monthly recursion — so the PV roll-up premium must equal the solver to the cent
for BOTH death-benefit options. These tests assert that on hand-built bases
(no DB), plus the structural shape of the rows.
"""
from suiteview.illustration.core.guideline_pv import (
    guideline_7pay_detail,
    guideline_glp_detail,
    guideline_gsp_detail,
    guideline_pv_rows,
)
from suiteview.illustration.core.monthly_guideline import (
    GuidelineBasis,
    GuidelineMonth,
    solve_endowment_premium,
    solve_guideline_premiums,
)


def _basis(months, *, total_sa=100_000.0, ctp=0.0, db_option="A"):
    return GuidelineBasis(
        months=months, total_sa=total_sa, db_option=db_option,
        ctp=ctp, guaranteed_rate=0.0,
    )


def _level_months(n, *, coi=0.0009, fee=10.0, epu=5.0, benefit=0.0):
    """n monthly rows, anniversary every 12th, with constant charges/COI."""
    out = []
    for m in range(n):
        out.append(GuidelineMonth(
            attained_age=45 + m // 12,
            coi_rate=coi,
            fee=fee,
            epu=epu,
            benefit_charges=benefit,
            tpp=0.06,
            epp=0.06,
            is_anniversary=(m % 12 == 0),
        ))
    return out


def _anniversaries(months):
    return {m for m, gm in enumerate(months) if gm.is_anniversary}


def test_pv_glp_reconciles_to_solver_level_db():
    months = _level_months(240)              # 20 years
    basis = _basis(months)
    prem = _anniversaries(months)
    rate = 0.04

    _, rollup = guideline_pv_rows(basis, rate, prem)
    solver = solve_endowment_premium(basis, rate, prem)

    assert abs(rollup["premium"] - solver) < 0.01


def test_pv_glp_reconciles_to_solver_dbo_b():
    """DBO B (NAR = full SA) uses the solver's t_eff mechanics — exact, not an
    approximation. Non-level COI keeps the check strict."""
    months = _level_months(240)
    for m, gm in enumerate(months):
        gm.coi_rate = (1.0 + 0.35 * (m // 12)) / 1000.0
    basis = _basis(months, db_option="B")
    prem = _anniversaries(months)

    _, rollup = guideline_pv_rows(basis, 0.04, prem)
    solver = solve_endowment_premium(basis, 0.04, prem)

    assert abs(rollup["premium"] - solver) < 0.01
    # The DBO B GLP is materially larger than the level-DB one — the old
    # level-DB-only view would have missed this by a wide margin.
    level_solver = solve_endowment_premium(basis, 0.04, prem, db_option="A")
    assert rollup["premium"] > level_solver * 1.1


def test_pv_rows_db_option_override_forces_level_mechanics():
    """The GSP/7-pay path: an explicit db_option="A" on a DBO B basis must value
    on level-DB mechanics, matching the solver's own override."""
    months = _level_months(120)
    basis = _basis(months, db_option="B")

    _, rollup = guideline_pv_rows(basis, 0.06, {0}, db_option="A")
    solver = solve_endowment_premium(basis, 0.06, {0}, db_option="A")

    assert abs(rollup["premium"] - solver) < 0.01


def test_pv_glp_reconciles_with_load_dollar_term():
    # tpp != epp triggers the (tpp - epp)*CTP dollar load in both paths.
    months = _level_months(180)
    for gm in months:
        gm.tpp, gm.epp = 0.10, 0.04
    basis = _basis(months, ctp=1_500.0)
    prem = _anniversaries(months)

    _, rollup = guideline_pv_rows(basis, 0.04, prem)
    solver = solve_endowment_premium(basis, 0.04, prem)

    assert abs(rollup["premium"] - solver) < 0.01
    assert rollup["load $ term"] > 0.0


def test_pv_glp_reconciles_with_benefit_charges():
    months = _level_months(120, benefit=12.34)
    basis = _basis(months)
    prem = _anniversaries(months)

    _, rollup = guideline_pv_rows(basis, 0.04, prem)
    solver = solve_endowment_premium(basis, 0.04, prem)

    assert abs(rollup["premium"] - solver) < 0.01


def test_rows_carry_pv_columns_and_maturity_endowment():
    months = _level_months(36)
    basis = _basis(months)
    rows, _ = guideline_pv_rows(basis, 0.04, _anniversaries(months))

    # One row per month plus the closing maturity-endowment row.
    assert len(rows) == len(months) + 1
    assert rows[-1].get("_endowment") is True
    assert rows[-1]["q'x"] == 0.0

    first = rows[0]
    for col in ("q'x", "p'x", "tp'x", "v^t", "v^(t+1)", "Death Benefit",
                "EPU", "MFEE", "Charges", "PVDB", "PV Charges", "PV Annuity",
                "Target Load Diff", "PV Target Load Diff"):
        assert col in first, f"missing column {col}"
    assert list(first).index("Target Load Diff") == list(first).index("PV Annuity") + 1
    assert list(first).index("PV Target Load Diff") == list(first).index("Target Load Diff") + 1
    # tp'x starts at full survival; p'x = 1 - q'x.
    assert first["tp'x"] == 1.0
    assert abs((first["p'x"] + first["q'x"]) - 1.0) < 1e-9


def test_rows_show_target_excess_load_per_premium_month():
    months = _level_months(24)
    for gm in months:
        gm.tpp, gm.epp = 0.10, 0.04
    basis = _basis(months, ctp=2_000.0)

    rows, rollup = guideline_pv_rows(basis, 0.04, _anniversaries(months))

    assert rows[0]["Target Load Diff"] == 120.0
    assert rows[0]["PV Target Load Diff"] == 120.0
    assert rows[1]["Target Load Diff"] == 0.0
    assert rows[1]["PV Target Load Diff"] == 0.0
    assert round(sum(row["PV Target Load Diff"] for row in rows), 2) == rollup["load $ term"]


def test_benefit_detail_becomes_its_own_column():
    months = _level_months(24)
    for gm in months:
        gm.benefit_charge_detail = {"PW (Waiver)": 3.21}
        gm.benefit_charges = 3.21
    basis = _basis(months)
    rows, _ = guideline_pv_rows(basis, 0.04, _anniversaries(months))

    assert "PW (Waiver)" in rows[0]
    assert rows[0]["PW (Waiver)"] == 3.21


def test_glp_detail_shape():
    months = _level_months(60)
    detail = guideline_glp_detail(_basis(months))

    assert set(detail) >= {"attained_age", "specified_amount", "db_option",
                           "glp_rate", "glp_rows", "glp_rollup"}
    assert detail["glp_rate"] == 0.04
    assert detail["glp_rollup"]["premium"] > 0.0


def test_gsp_detail_reconciles_to_solver_single_premium():
    months = _level_months(60)
    basis = _basis(months)

    detail = guideline_gsp_detail(basis)
    solver = solve_endowment_premium(basis, 0.06, {0}, db_option="A")

    assert detail["premium_label"] == "GSP"
    assert detail["glp_rate"] == 0.06
    assert abs(detail["glp_rollup"]["premium"] - solver) < 0.01


def test_7pay_detail_reconciles_to_solver():
    """The 7-pay PV roll-up equals the account-value solver's seven_pay —
    same NET basis (no fee/EPU/loads), same premium months, same AV offset."""
    months = _level_months(240, benefit=4.56)
    basis = _basis(months)

    detail = guideline_7pay_detail(basis, starting_av=5_000.0)
    solver = solve_guideline_premiums(basis, starting_av=5_000.0).seven_pay

    assert detail["premium_label"] == "7-Pay"
    assert detail["db_option"] == "A"
    assert detail["glp_rate"] == 0.04
    assert abs(detail["glp_rollup"]["premium"] - solver) < 0.01
    assert detail["glp_rollup"]["starting AV offset"] == 5_000.0
    # NET basis: the fee/EPU columns from the source basis are stripped.
    assert detail["glp_rows"][0]["EPU"] == 0.0
    assert detail["glp_rows"][0]["MFEE"] == 0.0
    # Exactly seven premium months.
    assert sum(1 for r in detail["glp_rows"] if r["PV Annuity"]) == 7


def test_equation_text_shows_starting_av_offset():
    from suiteview.illustration.ui.guideline_pv_view import GuidelinePvDetailView

    detail = guideline_7pay_detail(_basis(_level_months(120)), starting_av=2_500.0)
    text = GuidelinePvDetailView._equation_text(detail["glp_rollup"], "7-Pay")
    assert "Starting AV" in text
    assert "2,500.00" in text

    no_av = guideline_glp_detail(_basis(_level_months(120)))
    assert "Starting AV" not in GuidelinePvDetailView._equation_text(no_av["glp_rollup"])


def test_pv_detail_view_renders_detail():
    """The inline Guideline PV Detail group renders a captured detail."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])  # noqa: F841
    from suiteview.illustration.ui.guideline_pv_view import GuidelinePvDetailView

    detail = guideline_glp_detail(_basis(_level_months(60)))
    view = GuidelinePvDetailView()
    view.show_detail(detail)
    assert view.body.isVisible() or view._detail is detail
    assert view._grid_df is not None and not view._grid_df.empty
    # The worked-out equation ends with the GLP.
    glp = detail["glp_rollup"]["premium"]
    assert f"{glp:,.2f}" in view.equation.text()

    view.show_detail(None)  # graceful empty state
    assert view._detail is None
