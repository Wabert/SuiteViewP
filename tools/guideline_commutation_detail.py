"""Closed-form 7702 guideline solve with every commutation vector exposed.

Reuses the policy -> GuidelinePremiumInputs bridge from tools/validate_guideline.py
(guaranteed COI per $1000/month -> implied annual qx; current loads/fees/EPU as
expenses), then rebuilds the commutation columns the closed-form calculate_glp /
calculate_gsp consume and shows the present-value roll-up year by year:

    GLP = [ SA·A_{x:n} + PV(expenses) + load$ ] / [ (1 − load)·ä_{x:n} ]
    GSP = [ SA·A_{x:n} + PV(expenses) ] / (1 − single_load)   (GSP interest floor)

Per attained age it prints qx, lx, dx, v^t, Dx, Cx, Mx, Nx and the running PV of
the death benefit, the premium-paying annuity, and the expense charges — so the
totals (term + pure endowment = A_{x:n}; ΣDx/Dx = ä_{x:n}) can be read straight
off the cumulative columns.

Usage (single JSON arg):
    venv\\Scripts\\python.exe tools/guideline_commutation_detail.py '<json>'

    {"policy":"U0688012","company":"01","region":"CKPR","endowment_age":100,
     "basis":"glp","csv":"/tmp/glp_vectors.csv","png":"/tmp/glp_vectors.png"}

"basis" selects which interest floor the vector grid is tabulated at:
  "glp" -> max(guar, 4%)   "gsp" -> max(guar, 6%).  The roll-up block always
reports both GLP and GSP.
"""
from __future__ import annotations

import csv as csvmod
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _lvl(arr, i=1, default=0.0):
    return arr[i] if arr and len(arr) > i and arr[i] is not None else default


def build_inputs(policy: str, region: str, company, endow: int):
    """Policy -> (GuidelinePremiumInputs, context). Mirrors validate_guideline."""
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.core.rate_loader import load_rates
    from suiteview.illustration.models.plancode_config import load_plancode
    from suiteview.illustration.core.commutation import MortalityTable
    from suiteview.illustration.core.guideline_calc import (
        ExpenseAssumptions, GuidelinePremiumInputs,
    )

    clear_cache()
    pd = build_illustration_data(policy, region=region, company_code=company)
    config = load_plancode(pd.plancode)
    guar = load_rates(pd, config, coi_scale=0)
    cur = load_rates(pd, config, coi_scale=1)

    coi_sched = guar.segment_coi.get(pd.base_segment.coverage_phase, [])
    qx, coi_monthly = [], []
    for d in range(1, len(coi_sched)):
        rate = coi_sched[d]
        if rate is None:
            break
        mq = float(rate) / 1000.0
        coi_monthly.append(float(rate))
        qx.append(min(1.0, 1.0 - (1.0 - mq) ** 12))
    mort = MortalityTable.from_rates(qx, start_age=pd.issue_age, name="guar-coi")

    exp = ExpenseAssumptions(
        premium_load_target=_lvl(cur.tpp),
        premium_load_excess=_lvl(cur.epp),
        target_premium=float(pd.ctp or 0.0),
        per_policy_fee_annual=12.0 * _lvl(cur.mfee),
        per_unit_charge_annual=12.0 * _lvl(cur.epu),
        units=pd.face_amount / 1000.0,
    )
    gi = GuidelinePremiumInputs(
        attained_age=pd.issue_age, mortality=mort, specified_amount=pd.face_amount,
        db_option="A", endowment_age=endow,
        guaranteed_rate=float(pd.guaranteed_interest_rate or 0.0),
        glp_rate=0.04, gsp_rate=0.06, expenses=exp,
    )
    ctx = {
        "policy": policy, "plancode": pd.plancode, "issue_age": pd.issue_age,
        "face": pd.face_amount, "endowment_age": endow, "admin_glp": pd.glp,
        "admin_gsp": pd.gsp, "guaranteed_rate": gi.guaranteed_rate,
        "coi_monthly_per1000": coi_monthly, "qx": qx,
    }
    return gi, exp, ctx


def vectors_and_rollup(gi, exp, rate: float, single: bool):
    """Commutation columns x..x+n and the PV roll-up at one interest basis."""
    from suiteview.illustration.core.commutation import CommutationFunctions

    x = gi.attained_age
    n = gi.years_to_maturity()
    i = max(rate, gi.guaranteed_rate)
    comm = CommutationFunctions.build(
        gi.mortality, i, substandard=gi.substandard,
        issue_age=gi.issue_age if gi.issue_age is not None else x, start_age=x,
    )
    v = 1.0 / (1.0 + i)
    Dx0 = comm._D(x)
    units = exp.units
    fee_per_year = exp.per_policy_fee_annual + exp.per_unit_charge_annual * units
    sa = gi.specified_amount

    # Recover lx/dx from qx for display (radix 1.0 from issue age).
    rows = []
    pv_db_cum = pv_ann_cum = pv_exp_cum = 0.0
    lx = 1.0
    # advance lx from issue_age to x (x == issue_age here, loop is a no-op then)
    for age in range(gi.mortality.min_age, x):
        lx *= (1.0 - gi.mortality.q(age))
    for k in range(n + 1):
        age = x + k
        q = gi.mortality.q(age)
        dx = lx * q
        Dx, Cx, Mx, Nx = comm._D(age), comm._C(age), comm._M(age), comm._N(age)
        # Per-year PV contributions (relative to Dx at the solve age). Death
        # benefit is the term piece for ages x..x+n-1; the maturity age x+n
        # contributes the PURE ENDOWMENT instead, so the cumulative reconciles
        # exactly to SA·A_{x:n}. The annuity-due pays ages x..x+n-1.
        if k < n:
            pv_db_year = sa * Cx / Dx0 if Dx0 else 0.0
            pv_ann_year = Dx / Dx0 if Dx0 else 0.0
        else:
            pv_db_year = sa * Dx / Dx0 if Dx0 else 0.0   # pure endowment at maturity
            pv_ann_year = 0.0
        pv_exp_year = fee_per_year * pv_ann_year
        pv_db_cum += pv_db_year
        pv_ann_cum += pv_ann_year
        pv_exp_cum += pv_exp_year
        rows.append({
            "PolYr": age - gi.mortality.min_age + 1,
            "Age": age,
            "COI/1000/mo": round(_coi_at(gi, age), 5),
            "qx": round(q, 8),
            "lx": round(lx, 6),
            "dx": round(dx, 6),
            "v^t": round(v ** k, 6),
            "Dx": round(Dx, 6),
            "Cx": round(Cx, 8),
            "Mx": round(Mx, 6),
            "Nx": round(Nx, 6),
            "PV DB (yr)": round(pv_db_year, 4),
            "PV DB (cum)": round(pv_db_cum, 4),
            "PV Annuity (cum)": round(pv_ann_cum, 6),
            "PV Expense (cum)": round(pv_exp_cum, 4),
        })
        lx -= dx

    A = comm.endowment_insurance(x, n)
    term = comm.term_insurance(x, n)
    pure = comm.pure_endowment(x, n)
    ann = comm.annuity_due(x, n)
    pv_benefit = sa * A
    pv_fee = fee_per_year * ann
    pv_addl = sum(
        c.annual_charge * comm.annuity_due(x, n if c.years is None else min(c.years, n))
        for c in gi.additional_charges
    )
    numerator = pv_benefit + pv_fee + pv_addl

    load_t = exp.premium_load_target
    load_e = exp.premium_load_excess if exp.premium_load_excess is not None else load_t
    load_term = 0.0
    if not single and exp.target_premium > 0.0 and abs(load_t - load_e) > 1e-12:
        net_load = load_e
        load_term = exp.target_premium * (load_t - load_e) * ann
        numerator += load_term
    elif single:
        net_load = exp.single_premium_load if exp.single_premium_load is not None else load_t
    else:
        net_load = load_t

    denominator = (1.0 - net_load) if single else (1.0 - net_load) * ann
    premium = numerator / denominator if denominator else 0.0

    rollup = {
        "interest_rate": round(i, 4),
        "x": x, "n": n,
        "A_x:n (endowment ins)": round(A, 6),
        "  term A^1_x:n": round(term, 6),
        "  pure endowment nEx": round(pure, 6),
        "annuity_due a_x:n": round(ann, 6),
        "PV benefit (SA·A)": round(pv_benefit, 2),
        "PV expense (fee·a)": round(pv_fee, 2),
        "PV additional charges": round(pv_addl, 2),
        "load $ term": round(load_term, 2),
        "numerator": round(numerator, 2),
        "net_load": round(net_load, 6),
        "denominator": round(denominator, 6),
        "premium": round(premium, 2),
    }
    return rows, rollup


def _coi_at(gi, age: int) -> float:
    """The guaranteed COI/1000/month implied for display (inverse of the qx map)."""
    q = gi.mortality.q(age)
    if q >= 1.0:
        return 1000.0
    return (1.0 - (1.0 - q) ** (1.0 / 12.0)) * 1000.0


def run(cmd: dict) -> dict:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    policy = cmd["policy"]
    gi, exp, ctx = build_inputs(
        policy, cmd.get("region", "CKPR"), cmd.get("company"),
        int(cmd.get("endowment_age", 100)),
    )

    glp_rows, glp_roll = vectors_and_rollup(gi, exp, gi.glp_rate, single=False)
    gsp_rows, gsp_roll = vectors_and_rollup(gi, exp, gi.gsp_rate, single=True)

    basis = cmd.get("basis", "glp").lower()
    rows = gsp_rows if basis == "gsp" else glp_rows

    csv_path = cmd.get("csv")
    if csv_path:
        _write_csv(rows, csv_path)
    png_path = cmd.get("png")
    if png_path:
        png_path = _render(rows, png_path, f"{policy} — {basis.upper()} commutation vectors")

    return {
        "context": {k: ctx[k] for k in ("policy", "plancode", "issue_age", "face",
                                        "endowment_age", "guaranteed_rate",
                                        "admin_glp", "admin_gsp")},
        "expenses": {
            "premium_load_target": exp.premium_load_target,
            "premium_load_excess": exp.premium_load_excess,
            "target_premium(ctp)": exp.target_premium,
            "fee_annual": exp.per_policy_fee_annual,
            "per_unit_annual": exp.per_unit_charge_annual,
            "units": exp.units,
        },
        "glp_rollup": glp_roll,
        "gsp_rollup": gsp_roll,
        "vector_rows": len(rows),
        "vectors_head": rows[:6],
        "vectors_tail": rows[-3:],
        "csv": csv_path,
        "png": png_path,
    }


def _write_csv(rows, path):
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csvmod.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _render(rows, path, title):
    import pandas as pd
    from PyQt6.QtWidgets import QApplication, QVBoxLayout, QLabel, QWidget
    from suiteview.ui.widgets.filter_table_view import FilterTableView

    app = QApplication.instance() or QApplication([])
    holder = QWidget()
    holder.setStyleSheet("background:#F3ECFC;")
    lay = QVBoxLayout(holder)
    lay.setContentsMargins(6, 6, 6, 6)
    head = QLabel(title)
    head.setStyleSheet("background:#2A1458;color:#FFD54F;font-weight:bold;"
                       "font-size:11px;padding:4px 8px;border-radius:4px;")
    lay.addWidget(head)
    grid = FilterTableView()
    grid.set_search_visible(False)
    grid.apply_ledger_style()
    grid.set_sort_enabled(False)
    lay.addWidget(grid, 1)
    grid.set_dataframe(pd.DataFrame(rows), limit_rows=False)
    grid.set_numeric_formatting(default_decimals=4)
    grid.autofit_columns_to_data()
    holder.resize(1180, min(40 + 22 * (len(rows) + 2), 1400))
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    holder.grab().save(str(out))
    app.processEvents()
    return str(out)


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "missing JSON arg"}))
        sys.exit(1)
    print(json.dumps(run(json.loads(sys.argv[1])), indent=1, default=str))


if __name__ == "__main__":
    main()
