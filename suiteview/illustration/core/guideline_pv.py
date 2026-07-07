"""7702 guideline premium as a MONTH-BY-MONTH present value (GLP).

This is an alternative *presentation* of the same Guideline Level Premium that
``monthly_guideline.solve_guideline_premiums`` produces — not a different
answer. Where the solver runs a forward account-value endowment recursion
(``AV' = (AV·(1+T) − charges)·(1+i)`` solved for the level premium), this module
re-expresses the identical result as a survival-weighted actuarial present
value, so every policy month's contribution is visible and auditable:

    GLP = ( ΣPVDB + ΣPV Charges + load$ ) / ΣPV Annuity

It follows the layout of the ABR "ABA monthly calc." sheet / the ABR ``APVEngine``
(q'x, p'x, tp'x, vᵗ, v^(t+1), PVDB …) rather than commutation functions
(lx, dx, Nx, Dx, Cx, Mx) — handy in bulk, but opaque for a single policy.

Reconciliation
==============
For a level death benefit (DBO A) the account-value endowment premium equals the
prospective net level premium by the retrospective = prospective reserve
identity, so this PV roll-up matches ``solve_guideline_premiums(basis).glp`` to
the cent (``tools/check_guideline_pv.py`` asserts it on real policies). Both run
off the **same** :class:`~suiteview.illustration.core.monthly_guideline.GuidelineBasis`
(guaranteed COI, current expense charges, statutory interest), so the COI cap,
flat-extra truncation, PW-on-MTP basis, and load handling are shared exactly.

Conventions (matched to the solver):
  * q'x = the month's guaranteed COI per $1 of specified amount (the monthly
    mortality used by the contract); p'x = 1 − q'x; tp'x = ∏ p'x to month start.
  * Death benefit valued at month END  → discounted v^(t+1).
  * Expense charges and premiums at month START → discounted v^t (annuity-due).
  * A maturity pure endowment (survive to the deemed maturity age, receive SA)
    closes the endowment, exactly as the commutation A_{x:n} does.
  * Premium load: each premium is net of the excess load (1 − epp); the
    target/excess difference is charged as the dollar term (tpp − epp)·CTP, both
    matching ``solve_endowment_premium``.

DBO B note: the solver shrinks the COI coefficient for an increasing death
benefit; this level-DB PV view is therefore exact for DBO A and approximate for
DBO B. GLP is requested on the contract's option; the drill-down flags it.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from suiteview.illustration.core.monthly_guideline import (
    GLP_RATE_FLOOR,
    GSP_RATE_SPREAD,
    SEVEN_PAY_YEARS,
    GuidelineBasis,
    _anniversary_months,
    _net_premium_basis,
)

# Stable, ordered charge columns that always appear (benefit columns are added
# dynamically per policy from each month's ``benefit_charge_detail``).
_FIXED_CHARGE_COLUMNS = ("EPU", "MFEE")


def guideline_pv_rows(
    basis: GuidelineBasis,
    annual_rate: float,
    premium_months: set[int],
    *,
    starting_av: float = 0.0,
) -> Tuple[List[dict], dict]:
    """Month-by-month present-value decomposition of one endowment premium.

    ``annual_rate`` is the statutory basis rate (e.g. max(guaranteed, 4%) for the
    GLP). ``premium_months`` are the 0-based indices where a level premium is
    paid (anniversary months for the GLP). Returns ``(rows, rollup)``:

    * ``rows`` — one dict per policy month plus a final maturity-endowment row.
    * ``rollup`` — the numerator / denominator pieces and the resulting premium,
      mirroring ``guideline_calc.commutation_vectors``' roll-up keys.
    """
    months = basis.months
    sa = basis.total_sa
    i_m = (1.0 + annual_rate) ** (1.0 / 12.0) - 1.0
    v = 1.0 / (1.0 + i_m)

    # Benefit columns present anywhere in this basis (stable, sorted order).
    benefit_cols: List[str] = sorted({
        label for gm in months for label in gm.benefit_charge_detail
    })

    rows: List[dict] = []
    tp = 1.0                      # tp'x — survival to the START of the month
    disc = 1.0                    # v^t — discount to the START of the month
    pv_db_cum = pv_chg_cum = pv_ann_cum = pv_load_cum = pv_ann_gross_cum = 0.0

    for m, gm in enumerate(months):
        # NAR-consistent monthly mortality implied by the account-value
        # recursion: the COI per $1 (t) competes with the interest credit on the
        # fund, so q'x = t/(1+t), p'x = 1/(1+t). This is what makes the roll-up
        # reconcile to the solver to the cent (t/(1+t) ≈ t for small t).
        t = gm.coi_rate
        q = t / (1.0 + t)
        p = 1.0 - q               # = 1/(1+t)
        tp_next = tp * p          # survival to month END (COI + charges share it)
        v_end = disc * v          # v^(t+1) — death benefit paid at month end

        # ── Death benefit this month (level SA, paid on death at month end) ──
        pv_db = sa * q * tp * v_end
        pv_db_cum += pv_db

        # ── Charges this month (deducted with the COI → month-end survivors) ──
        charges = gm.epu + gm.fee + gm.benefit_charges + gm.rider_charges
        pv_chg = charges * tp_next * disc
        pv_chg_cum += pv_chg

        # ── Premium annuity + target/excess dollar load (premium months only) ──
        pv_ann = pv_load = 0.0
        is_prem = m in premium_months
        if is_prem:
            pv_ann_gross = tp * disc                 # ä gross (before the load)
            pv_ann_gross_cum += pv_ann_gross
            pv_ann = (1.0 - gm.epp) * pv_ann_gross   # net of the excess load
            pv_ann_cum += pv_ann
            pv_load = (gm.tpp - gm.epp) * basis.ctp * tp * disc
            pv_load_cum += pv_load
        target_load_diff = (gm.tpp - gm.epp) * basis.ctp if pv_ann else 0.0

        row = {
            "Policy Month": m + 1,
            "Age": gm.attained_age,
            "q'x": round(q, 8),
            "p'x": round(p, 8),
            "tp'x": round(tp, 8),
            "v^t": round(disc, 8),
            "v^(t+1)": round(v_end, 8),
            "Death Benefit": round(sa, 2),
        }
        for col in benefit_cols:
            row[col] = round(gm.benefit_charge_detail.get(col, 0.0), 2)
        row["EPU"] = round(gm.epu, 2)
        row["MFEE"] = round(gm.fee, 2)
        if gm.rider_charges:
            row["Rider"] = round(gm.rider_charges, 2)
        row["Charges"] = round(charges, 2)
        row["PVDB"] = round(pv_db, 4)
        row["PV Charges"] = round(pv_chg, 4)
        row["PV Annuity"] = round(pv_ann, 8) if is_prem else 0.0
        row["Target Load Diff"] = round(target_load_diff, 2)
        row["PV Target Load Diff"] = round(pv_load, 4)
        rows.append(row)

        # Advance survival and discount to the next month start.
        tp *= p
        disc *= v

    # ── Maturity pure endowment: survive to the deemed maturity, receive SA.
    #    This is the "endowment piece" of the guideline calc — it lives inside
    #    Σ PVDB (term death benefit + this), making PVDB the endowment insurance
    #    SA·A_{x:n}. ──
    pv_db_term = pv_db_cum
    pv_endow = sa * tp * disc
    pv_db_cum += pv_endow
    rows.append({
        "Policy Month": len(months) + 1,
        "Age": (months[-1].attained_age + 1) if months else 0,
        "q'x": 0.0,
        "p'x": 1.0,
        "tp'x": round(tp, 8),
        "v^t": round(disc, 8),
        "v^(t+1)": round(disc, 8),
        "Death Benefit": round(sa, 2),
        "Charges": 0.0,
        "PVDB": round(pv_endow, 4),
        "PV Charges": 0.0,
        "PV Annuity": 0.0,
        "Target Load Diff": 0.0,
        "PV Target Load Diff": 0.0,
        "_endowment": True,
    })

    # Express the per-premium excess load as one implied rate so the roll-up can
    # show the textbook denominator (1 − load%)·ä_gross exactly, even when the
    # load schedule varies by year: net = (1 − load%)·gross by construction.
    load_pct = (1.0 - pv_ann_cum / pv_ann_gross_cum) if pv_ann_gross_cum else 0.0

    numerator = pv_db_cum + pv_chg_cum + pv_load_cum - float(starting_av)
    denominator = pv_ann_cum
    premium = numerator / denominator if denominator else 0.0

    rollup = {
        "interest_rate": round(annual_rate, 6),
        "months": len(months),
        "specified_amount": round(sa, 2),
        "PV death benefit": round(pv_db_term, 2),
        "PV maturity endowment": round(pv_endow, 2),
        "PVDB (= SA endowment)": round(pv_db_cum, 2),
        "PV Charges": round(pv_chg_cum, 2),
        "load $ term": round(pv_load_cum, 2),
        "starting AV offset": round(float(starting_av), 2),
        "PV Annuity (gross)": round(pv_ann_gross_cum, 6),
        "load %": round(load_pct, 6),
        "PV Annuity (net of load)": round(pv_ann_cum, 6),
        "numerator": round(numerator, 2),
        "denominator": round(denominator, 6),
        "premium": round(premium, 2),
    }
    return rows, rollup


def _guideline_premium_detail(
    basis: GuidelineBasis,
    *,
    premium_label: str,
    annual_rate: float,
    premium_months: set[int],
    db_option: str | None = None,
    starting_av: float = 0.0,
) -> dict:
    rows, rollup = guideline_pv_rows(
        basis, annual_rate, premium_months, starting_av=starting_av)
    return {
        "premium_label": premium_label,
        "attained_age": basis.months[0].attained_age if basis.months else 0,
        "specified_amount": basis.total_sa,
        "db_option": db_option or basis.db_option,
        "glp_rate": annual_rate,
        "glp_rows": rows,
        "glp_rollup": rollup,
    }


def guideline_glp_detail(basis: GuidelineBasis) -> dict:
    """Monthly-PV GLP vectors + roll-up for the Values-tab drill-down.

    Mirrors the shape of ``guideline_calc.commutation_detail`` (GLP only): the
    GLP is the level premium paid at every anniversary from the calc date to the
    deemed maturity, on the contract's death-benefit option, at max(guaranteed,
    4%).
    """
    glp_rate = max(basis.guaranteed_rate, GLP_RATE_FLOOR)
    return _guideline_premium_detail(
        basis,
        premium_label="GLP",
        annual_rate=glp_rate,
        premium_months=_anniversary_months(basis),
    )


def guideline_gsp_detail(basis: GuidelineBasis) -> dict:
    """Monthly-PV GSP vectors + roll-up for the Values-tab drill-down.

    The GSP is the single premium paid at the calculation month, at max
    (guaranteed, 6%), and follows the same level-DB mechanics as the solver.
    """
    gsp_rate = max(basis.guaranteed_rate, GLP_RATE_FLOOR + GSP_RATE_SPREAD)
    return _guideline_premium_detail(
        basis,
        premium_label="GSP",
        annual_rate=gsp_rate,
        premium_months={0},
        db_option="A",
    )


def guideline_7pay_detail(basis: GuidelineBasis, *, starting_av: float = 0.0) -> dict:
    """Monthly-PV 7-pay vectors + roll-up for the TAMRA recalc drill-down.

    The 7702A 7-pay premium is a NET premium — guaranteed COI and benefit/rider
    charges only (no policy fee, per-unit charges, or premium loads) — paid at
    the 7-pay period start and the next six anniversaries, on LEVEL-DB
    mechanics at max(guaranteed, 4%), offset by the account value at the period
    start. Same premium months and basis strip as
    ``monthly_guideline.solve_guideline_premiums``' 7-pay solve, so the roll-up
    reconciles to the solved level.
    """
    net = _net_premium_basis(basis)
    seven_pay_months = {0} | _anniversary_months(net, limit_years=SEVEN_PAY_YEARS)
    if len(seven_pay_months) > SEVEN_PAY_YEARS:
        seven_pay_months = set(sorted(seven_pay_months)[:SEVEN_PAY_YEARS])
    return _guideline_premium_detail(
        net,
        premium_label="7-Pay",
        annual_rate=max(basis.guaranteed_rate, GLP_RATE_FLOOR),
        premium_months=seven_pay_months,
        db_option="A",
        starting_av=starting_av,
    )
