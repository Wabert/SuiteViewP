"""Offline checks for the commutation engine + GLP/GSP + Fackler reserves.

Validates against table-agnostic actuarial identities and exact no-mortality
hand values (no DB / rates needed). Run:

    PYTHONPATH=. venv\\Scripts\\python.exe tools/test_commutation_glp.py
"""
from suiteview.illustration.core.commutation import (
    CommutationFunctions,
    MortalityTable,
    SubstandardRating,
    fackler_backward,
    fackler_forward,
)
from suiteview.illustration.core.guideline_calc import (
    AdditionalBenefitCharge,
    ExpenseAssumptions,
    GuidelinePremiumInputs,
    calculate_glp,
    calculate_gsp,
    calculate_7pay_premium,
    calculate_glp_iterative,  # import-only (needs live rates to run)
    glp_on_change,
)

passed = 0


def check(name, cond):
    global passed
    if not cond:
        raise AssertionError(f"FAILED: {name}")
    passed += 1
    print(f"  ok  {name}")


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


# Increasing toy table (ages 0..119, q=1 at 120) for identity checks.
inc_rates = [min(0.0005 * max(age - 20, 0) + 0.001, 0.5) for age in range(0, 120)]
INC = MortalityTable.from_rates(inc_rates, start_age=0, name="toy-increasing", sex="U")
# No-mortality table (q=0 up to omega) for exact hand values.
NOMORT = MortalityTable.from_rates([0.0] * 100, start_age=0, name="no-mortality")


# ── Commutation identities (interest/mortality agnostic) ─────────────────
print("Commutation identities (i=0.05, toy table)")
i = 0.05
d = i / (1.0 + i)
c = CommutationFunctions.build(INC, i, start_age=0)
x, n = 45, 30
check("A_x = 1 - d*ä_x (whole life)",
      approx(c.whole_life_insurance(x), 1 - d * c.annuity_due_whole(x), 1e-9))
check("A_{x:n} = 1 - d*ä_{x:n} (endowment)",
      approx(c.endowment_insurance(x, n), 1 - d * c.annuity_due(x, n), 1e-9))
check("pure endowment + term = endowment insurance",
      approx(c.pure_endowment(x, n) + c.term_insurance(x, n), c.endowment_insurance(x, n), 1e-12))
check("net level premium = A_{x:n} / ä_{x:n}",
      approx(c.net_level_premium(x, n, 1.0, 1.0),
             c.endowment_insurance(x, n) / c.annuity_due(x, n), 1e-12))

# ── Reserves: prospective + Fackler roll ─────────────────────────────────
print("Reserves and Fackler roll")
check("reserve at t=0 is 0", approx(c.reserve(x, n, 0, 1.0, 1.0), 0.0, 1e-9))
check("reserve at t=n is the endowment", approx(c.reserve(x, n, n, 1.0, 1.0), 1.0, 1e-9))
P = c.net_level_premium(x, n, 1.0, 1.0)
# Roll the reserve forward across the whole contract -> endows at 1.
rolled = c.roll_reserve(0.0, x, x + n, premium=P, benefit=1.0)
check("Fackler roll-forward endows to 1.0", approx(rolled, 1.0, 1e-9))
# Roll forward to a midpoint matches the prospective reserve there.
mid = c.roll_reserve(0.0, x, x + 10, premium=P, benefit=1.0)
check("Fackler roll matches prospective reserve at t=10",
      approx(mid, c.reserve(x, n, 10, 1.0, 1.0), 1e-9))
# Backward undoes forward.
back = c.roll_reserve(mid, x + 10, x, premium=P, benefit=1.0)
check("Fackler roll-backward undoes roll-forward", approx(back, 0.0, 1e-9))
# Standalone q/i Fackler primitives are inverses.
v1 = fackler_forward(100.0, 20.0, 1000.0, q=0.01, i=0.05)
check("standalone Fackler forward/backward inverse",
      approx(fackler_backward(v1, 20.0, 1000.0, 0.01, 0.05), 100.0, 1e-9))

# ── Exact no-mortality hand values ───────────────────────────────────────
print("No-mortality exact values")
i4 = 0.04
v4 = 1.0 / (1.0 + i4)
d4 = i4 / (1.0 + i4)
cn = CommutationFunctions.build(NOMORT, i4, start_age=0)
expected_pe = v4 ** 20
check("endowment insurance = v^n with no mortality",
      approx(cn.endowment_insurance(40, 20), expected_pe, 1e-9))
expected_P = d4 * expected_pe / (1.0 - expected_pe)
check("net level premium = d*v^n/(1-v^n) with no mortality",
      approx(cn.net_level_premium(40, 20, 1.0, 1.0), expected_P, 1e-9))

# ── GLP / GSP ────────────────────────────────────────────────────────────
print("GLP / GSP (commutation method)")
base = GuidelinePremiumInputs(
    attained_age=40, mortality=NOMORT, specified_amount=100_000.0,
    endowment_age=60, guaranteed_rate=0.03, glp_rate=0.04, gsp_rate=0.06,
)
glp = calculate_glp(base)
check("GLP (no expense/load) = SA * net level premium",
      approx(glp, 100_000.0 * expected_P, 1e-4))
# GSP at 6%, no expense = SA * endowment insurance at 6%.
v6 = 1.0 / 1.06
check("GSP (no expense/load) = SA * v^n at 6%",
      approx(calculate_gsp(base), 100_000.0 * (v6 ** 20), 1e-3))
check("GSP > GLP (single vs level)", calculate_gsp(base) > glp)

# Expenses raise the GLP.
with_exp = GuidelinePremiumInputs(
    attained_age=40, mortality=NOMORT, specified_amount=100_000.0, endowment_age=60,
    guaranteed_rate=0.03, glp_rate=0.04, gsp_rate=0.06,
    expenses=ExpenseAssumptions(premium_load_target=0.06, per_policy_fee_annual=60.0,
                                per_unit_charge_annual=1.0, units=100.0),
    additional_charges=[AdditionalBenefitCharge(annual_charge=50.0, years=10)],
)
check("expenses / loads raise the GLP", calculate_glp(with_exp) > glp)

# Substandard raises the GLP (more mortality -> more cost).
sub = GuidelinePremiumInputs(
    attained_age=45, mortality=INC, specified_amount=100_000.0, endowment_age=100,
    substandard=SubstandardRating(table_multiple=2.0),
)
std = GuidelinePremiumInputs(
    attained_age=45, mortality=INC, specified_amount=100_000.0, endowment_age=100,
)
check("substandard 200% raises the GLP", calculate_glp(sub) > calculate_glp(std))

# ── Policy-change recalc: new GLP = current + (GLPa - GLPb) ───────────────
print("GLP on change")
check("no change -> GLP unchanged", approx(glp_on_change(1200.0, base, base), 1200.0, 1e-9))
bigger = GuidelinePremiumInputs(
    attained_age=40, mortality=NOMORT, specified_amount=150_000.0, endowment_age=60,
    guaranteed_rate=0.03, glp_rate=0.04, gsp_rate=0.06,
)
new_glp = glp_on_change(1200.0, base, bigger)
check("face increase raises new GLP", new_glp > 1200.0)
check("new GLP = current + delta",
      approx(new_glp, 1200.0 + (calculate_glp(bigger) - calculate_glp(base)), 1e-6))

# ── 7702A 7-pay premium ──────────────────────────────────────────────────
print("7-pay premium (7702A)")
sevenpay = calculate_7pay_premium(base)
_i = max(base.glp_rate, base.guaranteed_rate)
_cc = CommutationFunctions.build(base.mortality, _i, start_age=base.attained_age)
_a7 = _cc.annuity_due(base.attained_age, 7)
_an = _cc.annuity_due(base.attained_age, base.years_to_maturity())
check("7-pay funds same benefit: 7pay*ä7 == GLP*än", approx(sevenpay * _a7, glp * _an, 1e-3))
check("7-pay premium exceeds GLP (7 pays vs n)", sevenpay > glp)
check("pay_years=n collapses to the GLP",
      approx(calculate_7pay_premium(base, pay_years=base.years_to_maturity()), glp, 1e-6))
# Change recalc works with the 7-pay method too (reuses glp_on_change).
new_7pay = glp_on_change(3000.0, base, bigger, method=calculate_7pay_premium)
check("7-pay on face increase rises", new_7pay > 3000.0)

check("iterative GLP symbol importable", callable(calculate_glp_iterative))

print(f"\nALL {passed} CHECKS PASSED")
