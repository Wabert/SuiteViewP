"""7702 Guideline premium calculations (GLP / GSP).

Two independent methods, both parameterized to be called flexibly:

1. Commutation / present-value method (``calculate_glp`` / ``calculate_gsp``):
       GLP = (PV endowment-insurance benefit + PV charges) / (net-of-load annuity)
   This is the closed-form actuarial formula GLP ≈ (A_{x:n} + expenses) / ä_{x:n}.
   Fully self-contained — give it a mortality table and it runs anywhere.

2. Iterative / account-value method (``calculate_glp_iterative``): mirrors the
   admin system — binary-search the level annual premium that endows the contract
   (account value = face at the 7702 maturity age), running the real CalcEngine
   with GUARANTEED COI and CURRENT premium loads / expenses / fees, at the 7702
   interest rate.

On a policy change the new GLP is the attained-age delta:

       new GLP = current GLP + (GLP_after_change − GLP_before_change)

both computed at the current attained age — see ``glp_on_change``.

7702 interest basis: GLP uses max(4%, guaranteed); GSP uses max(6%, guaranteed)
(pre-2021 statutory floors; the floors are parameters so post-2021 contracts can
override them). Mortality must not exceed the prevailing CSO table; here you pass
the table (or the contract's guaranteed COI implied qx) explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from suiteview.illustration.core.commutation import (
    CommutationFunctions,
    MortalityTable,
    SubstandardRating,
)


# ── Commutation / present-value method ───────────────────────────────────


@dataclass
class ExpenseAssumptions:
    """Current expense charges that load the guideline premium.

    Premium load can be a single rate (``premium_load_target`` with no target
    split) or a target/excess split. When ``target_premium`` > 0 and the loads
    differ, the excess load is used in the denominator and the extra cost of the
    higher target load on the target portion is added to the numerator (the lmi
    treatment; assumes GLP ≥ target premium).
    """

    premium_load_target: float = 0.0    # load on premium up to target (and the single-load default)
    premium_load_excess: Optional[float] = None  # load above target; None -> same as target (single load)
    target_premium: float = 0.0         # annual target premium for the load split
    single_premium_load: Optional[float] = None  # load for GSP single premium; None -> premium_load_target

    per_policy_fee_annual: float = 0.0  # annual per-contract fee (e.g., 12 * monthly fee)
    per_unit_charge_annual: float = 0.0 # annual charge per unit of specified amount
    units: float = 0.0                  # specified amount / 1000 (or contract unit basis)


@dataclass
class AdditionalBenefitCharge:
    """A rider / QAB whose current charge stream loads the guideline premium.

    Its present value (annual_charge over the charge period) is added to the
    numerator, producing a level positive increment to the guideline premium.
    """

    annual_charge: float
    years: Optional[int] = None   # charge period from current age; None = to maturity


@dataclass
class GuidelinePremiumInputs:
    """Everything needed to compute a GLP/GSP by the commutation method."""

    attained_age: int
    mortality: MortalityTable
    specified_amount: float            # death benefit base (face)
    sex: str = ""                      # informational; the table encodes mortality
    db_option: str = "A"               # "A" level supported here; B/C -> use the iterative method
    endowment_age: int = 100           # 7702 deemed maturity (95-100)
    guaranteed_rate: float = 0.03
    glp_rate: float = 0.04             # statutory GLP interest floor
    gsp_rate: float = 0.06             # statutory GSP interest floor
    substandard: SubstandardRating = field(default_factory=SubstandardRating)
    issue_age: Optional[int] = None    # for flat-extra timing; defaults to attained_age
    expenses: ExpenseAssumptions = field(default_factory=ExpenseAssumptions)
    additional_charges: List[AdditionalBenefitCharge] = field(default_factory=list)

    def years_to_maturity(self) -> int:
        return max(0, self.endowment_age - self.attained_age)


def _check_level_db(inputs: GuidelinePremiumInputs) -> None:
    if str(inputs.db_option).upper() not in ("A", "1", "LEVEL"):
        raise NotImplementedError(
            "The commutation method supports level (DBO A) benefits only. For "
            "increasing/ROP death benefits (DBO B/C) use calculate_glp_iterative()."
        )


def _expense_numerator(comm: CommutationFunctions, inputs: GuidelinePremiumInputs, x: int, n: int) -> float:
    """PV of per-policy + per-unit charges and additional-benefit charges."""
    exp = inputs.expenses
    annuity = comm.annuity_due(x, n)
    fee_pv = (exp.per_policy_fee_annual + exp.per_unit_charge_annual * exp.units) * annuity
    addl_pv = 0.0
    for charge in inputs.additional_charges:
        years = n if charge.years is None else min(charge.years, n)
        addl_pv += charge.annual_charge * comm.annuity_due(x, years)
    return fee_pv + addl_pv


def calculate_glp(inputs: GuidelinePremiumInputs) -> float:
    """Guideline Level Premium via commutation functions.

    GLP = [ SA·A_{x:n} + PV(expenses) ] / [ (1 − load)·ä_{x:n} ]
    """
    _check_level_db(inputs)
    x = inputs.attained_age
    n = inputs.years_to_maturity()
    if n <= 0:
        return 0.0

    i = max(inputs.glp_rate, inputs.guaranteed_rate)
    comm = CommutationFunctions.build(
        inputs.mortality, i, substandard=inputs.substandard,
        issue_age=inputs.issue_age if inputs.issue_age is not None else x,
        start_age=x,
    )
    annuity = comm.annuity_due(x, n)
    if annuity <= 0:
        return 0.0

    pv_benefit = inputs.specified_amount * comm.endowment_insurance(x, n)
    numerator = pv_benefit + _expense_numerator(comm, inputs, x, n)

    exp = inputs.expenses
    load_target = exp.premium_load_target
    load_excess = exp.premium_load_excess if exp.premium_load_excess is not None else load_target
    if exp.target_premium > 0.0 and abs(load_target - load_excess) > 1e-12:
        net_load = load_excess
        numerator += exp.target_premium * (load_target - load_excess) * annuity
    else:
        net_load = load_target

    denominator = (1.0 - net_load) * annuity
    return numerator / denominator if denominator else 0.0


def calculate_gsp(inputs: GuidelinePremiumInputs) -> float:
    """Guideline Single Premium via commutation functions.

    GSP = [ SA·A_{x:n} + PV(expenses) ] / (1 − single_load), at the GSP interest floor.
    """
    _check_level_db(inputs)
    x = inputs.attained_age
    n = inputs.years_to_maturity()
    if n <= 0:
        return 0.0

    i = max(inputs.gsp_rate, inputs.guaranteed_rate)
    comm = CommutationFunctions.build(
        inputs.mortality, i, substandard=inputs.substandard,
        issue_age=inputs.issue_age if inputs.issue_age is not None else x,
        start_age=x,
    )
    pv_benefit = inputs.specified_amount * comm.endowment_insurance(x, n)
    numerator = pv_benefit + _expense_numerator(comm, inputs, x, n)

    exp = inputs.expenses
    single_load = exp.single_premium_load if exp.single_premium_load is not None else exp.premium_load_target
    denominator = 1.0 - single_load
    return numerator / denominator if denominator else 0.0


def calculate_7pay_premium(inputs: GuidelinePremiumInputs, pay_years: int = 7) -> float:
    """7702A 7-pay premium via commutation functions.

    The 7-pay premium is the level annual premium payable over ``pay_years``
    (default 7) that funds the contract's future benefits — the same NSP-style
    numerator as the guideline premium, but the premium-paying annuity is capped
    at the 7-pay period:

        7-pay = [ SA·A_{x:n} + PV(expenses) ] / [ (1 − load)·ä_{x:k} ],  k = min(pay_years, n)

    7702A uses the §7702 interest floor (4%) and the contract's guaranteed
    mortality. Because the premium-paying period (k≤7) is shorter than the
    benefit period (n), the 7-pay premium is materially larger than the GLP.

    NOTE: like ``calculate_glp``, penny-validation against admin / RERUN's
    Guideline_Premiums sheet needs the guaranteed-COI mortality table (live
    UL_Rates) — verify on the work laptop. RERUN computes its own 7-pay
    (CalcEngine ``KY`` ← Guideline_Premiums col 6) by a slightly different method;
    they should agree closely. See QUESTION_LOG.md for the expense/interest basis
    questions.
    """
    _check_level_db(inputs)
    x = inputs.attained_age
    n = inputs.years_to_maturity()
    if n <= 0:
        return 0.0

    # 7702A interest basis: greater of 4% (the §7702 floor) and the contract rate.
    i = max(inputs.glp_rate, inputs.guaranteed_rate)
    comm = CommutationFunctions.build(
        inputs.mortality, i, substandard=inputs.substandard,
        issue_age=inputs.issue_age if inputs.issue_age is not None else x,
        start_age=x,
    )
    pay_n = min(pay_years, n)
    annuity_pay = comm.annuity_due(x, pay_n)
    if annuity_pay <= 0:
        return 0.0

    pv_benefit = inputs.specified_amount * comm.endowment_insurance(x, n)
    numerator = pv_benefit + _expense_numerator(comm, inputs, x, n)

    exp = inputs.expenses
    load_target = exp.premium_load_target
    load_excess = exp.premium_load_excess if exp.premium_load_excess is not None else load_target
    if exp.target_premium > 0.0 and abs(load_target - load_excess) > 1e-12:
        net_load = load_excess
        numerator += exp.target_premium * (load_target - load_excess) * annuity_pay
    else:
        net_load = load_target

    denominator = (1.0 - net_load) * annuity_pay
    return numerator / denominator if denominator else 0.0


# ── Policy-change recalculation: new GLP = current + (GLPa − GLPb) ────────


def glp_on_change(
    current_glp: float,
    inputs_before: GuidelinePremiumInputs,
    inputs_after: GuidelinePremiumInputs,
    method: Callable[[GuidelinePremiumInputs], float] = calculate_glp,
) -> float:
    """New GLP after a policy change, attained-age delta method.

        new GLP = current GLP + (GLP_after − GLP_before)

    Both GLP_before and GLP_after are computed at the current attained age.
    ``method`` is the GLP function to use — ``calculate_glp`` (commutation) by
    default, or pass a closure around ``calculate_glp_iterative`` for the
    account-value method.
    """
    glp_before = method(inputs_before)
    glp_after = method(inputs_after)
    return current_glp + (glp_after - glp_before)


# ── Commutation detail: every vector + the present-value roll-up ──────────


def policy_to_guideline_inputs(
    policy, config, attained_age: int, *, endowment_age: int = 100,
) -> GuidelinePremiumInputs:
    """Build closed-form ``GuidelinePremiumInputs`` from a live policy state.

    Guaranteed COI (scale 0, per $1000/month) becomes the implied annual qx;
    current loads / fees / per-unit charges (scale 1) become the expense load.
    The specified amount and per-unit basis are the policy's TOTAL face, so a
    before/after policy state yields the before/after guideline basis. Rates are
    loaded lazily so this module stays import-light for callers that only need
    the pure commutation math.
    """
    from suiteview.illustration.core.rate_loader import load_rates

    guar = load_rates(policy, config, coi_scale=0)
    cur = load_rates(policy, config, coi_scale=1)

    def _lvl(arr, i=1, default=0.0):
        return arr[i] if arr and len(arr) > i and arr[i] is not None else default

    base = policy.base_segment
    coi_sched = guar.segment_coi.get(base.coverage_phase, []) if base is not None else []
    qx: List[float] = []
    for duration in range(1, len(coi_sched)):
        rate = coi_sched[duration]
        if rate is None:
            break
        monthly_q = float(rate) / 1000.0
        qx.append(min(1.0, 1.0 - (1.0 - monthly_q) ** 12))
    mort = MortalityTable.from_rates(qx, start_age=policy.issue_age, name="guar-coi")

    total_face = float(policy.total_face or 0.0)
    expenses = ExpenseAssumptions(
        premium_load_target=_lvl(cur.tpp),
        premium_load_excess=_lvl(cur.epp),
        target_premium=float(policy.ctp or 0.0),
        per_policy_fee_annual=12.0 * _lvl(cur.mfee),
        per_unit_charge_annual=12.0 * _lvl(cur.epu),
        units=total_face / 1000.0,
    )
    return GuidelinePremiumInputs(
        attained_age=attained_age,
        mortality=mort,
        specified_amount=total_face,
        db_option="A",                 # commutation detail is the level-DB view
        endowment_age=endowment_age,
        guaranteed_rate=float(policy.guaranteed_interest_rate or 0.0),
        glp_rate=0.04,
        gsp_rate=0.06,
        expenses=expenses,
        issue_age=policy.issue_age,
    )


def _coi_per_1000_month(gi: GuidelinePremiumInputs, age: int) -> float:
    """Guaranteed COI/1000/month implied by the annual qx (inverse of the map)."""
    q = gi.mortality.q(age)
    if q >= 1.0:
        return 1000.0
    return (1.0 - (1.0 - q) ** (1.0 / 12.0)) * 1000.0


def commutation_vectors(gi: GuidelinePremiumInputs, rate: float, single: bool):
    """One interest basis: per-age commutation vectors + the PV roll-up.

    Returns ``(rows, rollup)``. ``rows`` is one dict per attained age from the
    solve age to the endowment age with qx / lx / dx / vᵗ / Dx / Cx / Mx / Nx and
    the running present value of the death benefit, the premium-paying annuity,
    and the expense charges. ``rollup`` is the closed-form numerator/denominator
    and the resulting premium. Deaths are the term piece for ages x..x+n−1; the
    maturity age contributes the pure endowment, so the cumulative PV death
    benefit reconciles exactly to SA·A_{x:n}.
    """
    x = gi.attained_age
    n = gi.years_to_maturity()
    i = max(rate, gi.guaranteed_rate)
    comm = CommutationFunctions.build(
        gi.mortality, i, substandard=gi.substandard,
        issue_age=gi.issue_age if gi.issue_age is not None else x, start_age=x,
    )
    v = 1.0 / (1.0 + i)
    dx0 = comm._D(x)
    units = gi.expenses.units
    fee_per_year = gi.expenses.per_policy_fee_annual + gi.expenses.per_unit_charge_annual * units
    sa = gi.specified_amount

    rows = []
    pv_db_cum = pv_ann_cum = pv_exp_cum = 0.0
    lx = 1.0
    for age in range(gi.mortality.min_age, x):
        lx *= (1.0 - gi.mortality.q(age))
    for k in range(n + 1):
        age = x + k
        q = gi.mortality.q(age)
        dx = lx * q
        d_age, c_age, m_age, nn_age = comm._D(age), comm._C(age), comm._M(age), comm._N(age)
        if k < n:
            pv_db_year = sa * c_age / dx0 if dx0 else 0.0
            pv_ann_year = d_age / dx0 if dx0 else 0.0
        else:
            pv_db_year = sa * d_age / dx0 if dx0 else 0.0   # pure endowment at maturity
            pv_ann_year = 0.0
        pv_exp_year = fee_per_year * pv_ann_year
        pv_db_cum += pv_db_year
        pv_ann_cum += pv_ann_year
        pv_exp_cum += pv_exp_year
        rows.append({
            "PolYr": age - gi.mortality.min_age + 1,
            "Age": age,
            "COI/1000/mo": round(_coi_per_1000_month(gi, age), 5),
            "qx": round(q, 8),
            "lx": round(lx, 6),
            "dx": round(dx, 6),
            "v^t": round(v ** k, 6),
            "Dx": round(d_age, 6),
            "Cx": round(c_age, 8),
            "Mx": round(m_age, 6),
            "Nx": round(nn_age, 6),
            "PV DB (yr)": round(pv_db_year, 4),
            "PV DB (cum)": round(pv_db_cum, 4),
            "PV Annuity (cum)": round(pv_ann_cum, 6),
            "PV Expense (cum)": round(pv_exp_cum, 4),
        })
        lx -= dx

    a_xn = comm.endowment_insurance(x, n)
    term = comm.term_insurance(x, n)
    pure = comm.pure_endowment(x, n)
    ann = comm.annuity_due(x, n)
    pv_benefit = sa * a_xn
    pv_fee = fee_per_year * ann
    pv_addl = sum(
        c.annual_charge * comm.annuity_due(x, n if c.years is None else min(c.years, n))
        for c in gi.additional_charges
    )
    numerator = pv_benefit + pv_fee + pv_addl

    exp = gi.expenses
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
        "x": x,
        "n": n,
        "A_x:n": round(a_xn, 6),
        "term A^1_x:n": round(term, 6),
        "pure endowment nEx": round(pure, 6),
        "annuity_due a_x:n": round(ann, 6),
        "PV benefit (SA*A)": round(pv_benefit, 2),
        "PV expense (fee*a)": round(pv_fee, 2),
        "PV additional charges": round(pv_addl, 2),
        "load $ term": round(load_term, 2),
        "numerator": round(numerator, 2),
        "net_load": round(net_load, 6),
        "denominator": round(denominator, 6),
        "premium": round(premium, 2),
    }
    return rows, rollup


def commutation_detail(gi: GuidelinePremiumInputs) -> dict:
    """Closed-form GLP and GSP vectors + roll-up for one guideline basis."""
    glp_rows, glp_rollup = commutation_vectors(gi, gi.glp_rate, single=False)
    gsp_rows, gsp_rollup = commutation_vectors(gi, gi.gsp_rate, single=True)
    return {
        "attained_age": gi.attained_age,
        "endowment_age": gi.endowment_age,
        "specified_amount": gi.specified_amount,
        "glp_rows": glp_rows,
        "glp_rollup": glp_rollup,
        "gsp_rows": gsp_rows,
        "gsp_rollup": gsp_rollup,
    }


# ── Iterative / account-value method (admin replication) ─────────────────


@dataclass
class IterativeGuidelineResult:
    glp: float
    solved_annual_premium: float
    ending_account_value: float
    target_face: float
    iterations: int
    converged: bool


def calculate_glp_iterative(
    policy,
    guaranteed_rates,
    *,
    glp_rate: float = 0.04,
    endowment_age: int = 100,
    target_face: Optional[float] = None,
    tolerance: float = 0.01,
    max_iter: int = 80,
    high_premium_cap: float = 100_000_000.0,
) -> IterativeGuidelineResult:
    """Solve the GLP by endowing the contract, using the real CalcEngine.

    Binary-searches the level annual premium so that the projected account value
    equals the target face at the 7702 maturity age, projecting with:

      * GUARANTEED COI rates (caller supplies ``guaranteed_rates`` — an
        ``IllustrationRates`` built with the guaranteed COI scale),
      * CURRENT premium loads / expenses / fees (already on the policy/plancode),
      * the 7702 interest rate ``glp_rate`` (default 4%), no interest bonus,
      * guideline force-out / cap / exception machinery turned OFF (this is a raw
        endowment projection).

    The account value starts at 0 at the current attained age. ``target_face``
    defaults to the policy face amount.

    NOTE: requires live guaranteed COI rates, so it is validated on the work
    laptop (the home minipc has no UL_Rates DB). The pure-math sibling
    ``calculate_glp`` runs anywhere.
    """
    # Imported lazily so the commutation method has no engine/DB import weight.
    from suiteview.illustration.core.bonus_rates import BonusConfig
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet,
        IllustrationOptions,
        ScheduledTransaction,
        TransactionKind,
    )
    from suiteview.illustration.models.policy_data import IllustrationPolicyData

    face = policy.face_amount if target_face is None else target_face
    months = max(0, (endowment_age - policy.attained_age) * 12)
    if months <= 0 or face <= 0:
        return IterativeGuidelineResult(0.0, 0.0, 0.0, face, 0, True)

    # Guideline policy copy: fresh account value at the 7702 interest rate.
    gpolicy = IllustrationPolicyData(**policy.__dict__)
    gpolicy.account_value = 0.0
    gpolicy.modal_premium = 0.0
    gpolicy.current_interest_rate = glp_rate
    gpolicy.system_monthly_deduction = 0.0
    gpolicy.system_coi_charge = 0.0
    gpolicy.system_expense_charge = 0.0
    gpolicy.system_other_charge = 0.0
    gpolicy.premiums_ytd = 0.0
    gpolicy.premiums_paid_to_date = 0.0
    gpolicy.withdrawals_to_date = 0.0
    gpolicy.regular_loan_principal = 0.0
    gpolicy.regular_loan_accrued = 0.0
    gpolicy.preferred_loan_principal = 0.0
    gpolicy.preferred_loan_accrued = 0.0
    gpolicy.variable_loan_principal = 0.0
    gpolicy.variable_loan_accrued = 0.0

    engine = IllustrationEngine()
    options = IllustrationOptions(
        conform_to_tefra=False, conform_to_tamra=False, allow_exception_prems=False
    )
    zero_bonus = BonusConfig()

    def ending_av(annual_premium: float) -> float:
        inputs = IllustrationInputSet(
            scheduled_transactions=[
                ScheduledTransaction(
                    kind=TransactionKind.PREMIUM, policy_year=1,
                    amount=annual_premium, mode="A",
                )
            ]
        )
        results = engine.project(
            gpolicy, months=months, future_inputs=inputs,
            options=options, bonus_override=zero_bonus,
            rates_override=guaranteed_rates, stop_on_lapse=False,
        )
        return results[-1].av_end_of_month if results else 0.0

    # Bracket the solution.
    low, high = 0.0, max(face / 10.0, 100.0)
    iters = 0
    while ending_av(high) < face:
        high *= 2.0
        iters += 1
        if high > high_premium_cap:
            return IterativeGuidelineResult(high, high, ending_av(high), face, iters, False)

    for _ in range(max_iter):
        iters += 1
        mid = (low + high) / 2.0
        av = ending_av(mid)
        if abs(av - face) <= tolerance:
            return IterativeGuidelineResult(mid, mid, av, face, iters, True)
        if av < face:
            low = mid
        else:
            high = mid

    glp = (low + high) / 2.0
    return IterativeGuidelineResult(glp, glp, ending_av(glp), face, iters, True)


# ── Search routine: GLP/GSP/7-pay by premium solve on the real engine ─────


def search_guideline_premiums(
    policy,
    config,
    guaranteed_rates,
    *,
    attained_age: int,
    as_of=None,
    starting_av: float = 0.0,
    glp_rate_floor: float = 0.04,
    gsp_rate_spread: float = 0.02,
    maturity_age: int = 100,
    tolerance: float = 0.01,
    max_iter: int = 60,
):
    """Solve GLP / GSP / 7-pay by premium search on the CALC ENGINE.

    The "Find GP/TAMRA by Search Routine" path: project the real engine with
    guaranteed COIs, the statutory interest rate, current expenses, no bonus,
    and the guideline machinery off — then binary-search the premium whose
    ending account value endows the face at the 7702 maturity. Because this
    runs the full engine it picks up mechanics the closed-form solve
    approximates (true corridor, the dynamic PW waive basis, per-segment COI
    on multi-coverage policies) — which is exactly where the two methods can
    diverge.

    Returns a ``monthly_guideline.GuidelineSolveResult``.
    """
    import dataclasses

    from suiteview.illustration.core.bonus_rates import BonusConfig
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.monthly_guideline import (
        SEVEN_PAY_YEARS,
        GuidelineSolveResult,
    )
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet,
        IllustrationOptions,
        ScheduledTransaction,
        TransactionKind,
    )

    face = policy.total_face
    months = max(0, (maturity_age - attained_age) * 12)
    if months <= 0 or face <= 0:
        return GuidelineSolveResult()

    glp_rate = max(float(policy.guaranteed_interest_rate or 0.0), glp_rate_floor)
    gsp_rate = max(float(policy.guaranteed_interest_rate or 0.0), glp_rate_floor + gsp_rate_spread)

    # Anchor the projection so the FIRST projected month is the anniversary at
    # ``attained_age`` (policy month 1) — the annual premium then lands on the
    # calculation date, and the last projected row's ending AV falls exactly on
    # the age-``maturity_age`` anniversary (the endowment test point).
    elapsed_years = max(0, attained_age - policy.issue_age)
    base_policy = dataclasses.replace(
        policy,
        attained_age=attained_age,
        policy_year=max(1, elapsed_years),
        policy_month=12 if elapsed_years > 0 else 0,
        duration=elapsed_years * 12,
        valuation_date=as_of or policy.valuation_date or policy.issue_date,
        account_value=0.0,
        modal_premium=0.0,
        premiums_ytd=0.0,
        premiums_paid_to_date=0.0,
        withdrawals_to_date=0.0,
        regular_loan_principal=0.0,
        regular_loan_accrued=0.0,
        preferred_loan_principal=0.0,
        preferred_loan_accrued=0.0,
        variable_loan_principal=0.0,
        variable_loan_accrued=0.0,
    )
    start_policy_year = elapsed_years + 1

    engine = IllustrationEngine()
    options = IllustrationOptions(
        conform_to_tefra=False, conform_to_tamra=False,
        allow_exception_prems=False, exact_days_interest=False,
    )
    zero_bonus = BonusConfig()

    def ending_av(
        annual_premium: float, premium_years: Optional[int], rate: float,
        av0: float, db_option: Optional[str] = None,
    ) -> float:
        overrides = {"current_interest_rate": rate, "account_value": av0}
        if db_option is not None:
            overrides["db_option"] = db_option
        gpolicy = dataclasses.replace(base_policy, **overrides)
        schedule = [ScheduledTransaction(
            kind=TransactionKind.PREMIUM, policy_year=1, amount=annual_premium, mode="A")]
        if premium_years is not None:
            # Stop the schedule after N premium years FROM THE CALC START
            # (schedule years are absolute policy years).
            schedule.append(ScheduledTransaction(
                kind=TransactionKind.PREMIUM,
                policy_year=start_policy_year + premium_years,
                amount=0.0, mode="A"))
        results = engine.project(
            gpolicy, months=months,
            future_inputs=IllustrationInputSet(scheduled_transactions=schedule),
            options=options, bonus_override=zero_bonus,
            rates_override=guaranteed_rates, stop_on_lapse=False,
        )
        return results[-1].av_end_of_month if results else 0.0

    def solve(
        premium_years: Optional[int], rate: float, av0: float = 0.0,
        db_option: Optional[str] = None,
    ) -> float:
        low, high = 0.0, max(face / 10.0, 100.0)
        for _ in range(40):
            if ending_av(high, premium_years, rate, av0, db_option) >= face:
                break
            high *= 2.0
        else:
            return high
        for _ in range(max_iter):
            mid = (low + high) / 2.0
            av = ending_av(mid, premium_years, rate, av0, db_option)
            if abs(av - face) <= tolerance:
                return mid
            if av < face:
                low = mid
            else:
                high = mid
        return (low + high) / 2.0

    # GSP and 7-pay always solve on LEVEL-DB mechanics; GLP honors the
    # contract's actual DB option (same convention as the formula method).
    return GuidelineSolveResult(
        glp=solve(None, glp_rate),
        gsp=solve(1, gsp_rate, db_option="A"),
        seven_pay=solve(SEVEN_PAY_YEARS, glp_rate, av0=starting_av, db_option="A"),
    )
