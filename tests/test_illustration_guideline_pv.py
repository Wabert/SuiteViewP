"""The month-by-month guideline PV must reconcile to the account-value solver.

``guideline_pv`` is only an alternative *presentation* of the GLP that
``solve_endowment_premium`` produces, so for a level death benefit (DBO A) the
PV roll-up premium must equal the solver to the cent. These tests assert that on
hand-built bases (no DB), plus the structural shape of the rows.
"""
from suiteview.illustration.core.guideline_pv import (
    guideline_glp_detail,
    guideline_gsp_detail,
    guideline_pv_rows,
)
from suiteview.illustration.core.monthly_guideline import (
    GuidelineBasis,
    GuidelineMonth,
    solve_endowment_premium,
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
