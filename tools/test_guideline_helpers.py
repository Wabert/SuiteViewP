"""Offline unit checks for the new guideline/exception pipeline helpers.

Validates the pure logic against the RERUN CalcEngine formulas without needing
SQL Server rates or DB2. Run:

    venv\\Scripts\\python.exe tools/test_guideline_helpers.py
"""
from suiteview.illustration.core.calc_engine import (
    _accumulate_guideline_premium,
    _apply_guideline_forceout,
    _compute_exception_premium,
    _guideline_limit_reached,
    _guideline_premium_cap,
    _tamra_year,
)
from suiteview.illustration.core.loan_handler import LoanState, apply_new_fixed_loan
from suiteview.illustration.core.premium_handler import apply_premium
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import IllustrationOptions
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData

GSP = 12863.52
GLP = 1171.44
RATES = IllustrationRates(tpp=[None] + [0.08] * 60, epp=[None] + [0.04] * 60)
CONFIG = PlancodeConfig(plancode="1U143900", maturity_age=121, prem_flat_load=0.0)

passed = 0


def check(name, cond):
    global passed
    if not cond:
        raise AssertionError(f"FAILED: {name}")
    passed += 1
    print(f"  ok  {name}")


def approx(a, b, tol=0.01):
    return abs(a - b) <= tol


# ── AccumGLP (KU): anniversary add, age-100 stop ──────────────────────
print("AccumGLP accumulation (KU)")
st = MonthlyState(accumulated_glp=GLP)
pol = IllustrationPolicyData(policy_number="T", plancode="1U143900", glp=GLP)
check("adds GLP on anniversary", approx(_accumulate_guideline_premium(st, pol, True, 60), 2 * GLP))
check("no add off-anniversary", approx(_accumulate_guideline_premium(st, pol, False, 60), GLP))
check("stops at attained age 100", approx(_accumulate_guideline_premium(st, pol, True, 100), GLP))

# ── Force-out (KX): GSP floor, AV cap, gating ─────────────────────────
print("Guideline force-out (KX)")
opt = dict(enabled=True, is_cvat=False, prior_exception_mode=False)
# Premium 13,000 > MAX(GSP, AccumGLP)=12,863.52 -> forceout 136.48, AV-capped fine
fo, wd, av = _apply_guideline_forceout(GSP, GLP, 13000.0, 0.0, 5000.0, **opt)
check("force-out = premium over MAX(GSP,AccumGLP)", approx(fo, 13000.0 - GSP))
check("force-out added to withdrawals", approx(wd, 13000.0 - GSP))
check("force-out reduces AV", approx(av, 5000.0 - (13000.0 - GSP)))
# GSP floor: premiums 5,000 < GSP -> NO force-out (old bug would force 5000-GLP)
fo2, _, _ = _apply_guideline_forceout(GSP, GLP, 5000.0, 0.0, 5000.0, **opt)
check("GSP floor: no force-out below GSP", approx(fo2, 0.0))
# AV cap: only 50 of AV available
fo3, _, av3 = _apply_guideline_forceout(GSP, GLP, 13000.0, 0.0, 50.0, **opt)
check("force-out capped by available AV", approx(fo3, 50.0) and approx(av3, 0.0))
# Gating
fo4, _, _ = _apply_guideline_forceout(GSP, GLP, 13000.0, 0.0, 5000.0,
                                      enabled=False, is_cvat=False, prior_exception_mode=False)
check("disabled when TEFRA off", approx(fo4, 0.0))
fo5, _, _ = _apply_guideline_forceout(GSP, GLP, 13000.0, 0.0, 5000.0,
                                      enabled=True, is_cvat=False, prior_exception_mode=True)
check("disabled once exception mode on", approx(fo5, 0.0))

# ── Premium cap (vAppliedScheduledPremium) ────────────────────────────
print("Guideline / TAMRA premium cap")
mec_pol = IllustrationPolicyData(policy_number="T", plancode="1U143900", tamra_7pay_level=0.0)
cap = _guideline_premium_cap(IllustrationOptions(), mec_pol, GSP, 12800.0, 0.0, 0.0, 999)
check("guideline room = limit - (PremTD-WD)", approx(cap, GSP - 12800.0))
tamra_pol = IllustrationPolicyData(policy_number="T", plancode="1U143900", tamra_7pay_level=300.0)
cap2 = _guideline_premium_cap(IllustrationOptions(), tamra_pol, GSP, 0.0, 0.0, 0.0, 1)
check("TAMRA binds when smaller (300 < guideline room)", approx(cap2, 300.0))
cap3 = _guideline_premium_cap(
    IllustrationOptions(conform_to_tefra=False), tamra_pol, GSP, 0.0, 0.0, 0.0, 1)
check("TEFRA off -> only TAMRA cap", approx(cap3, 300.0))
cap4 = _guideline_premium_cap(
    IllustrationOptions(conform_to_tefra=False, conform_to_tamra=False),
    tamra_pol, GSP, 0.0, 0.0, 0.0, 1)
check("both off -> no cap", cap4 is None)
cap5 = _guideline_premium_cap(IllustrationOptions(), tamra_pol, GSP, 0.0, 0.0, 0.0, 8)
check("TAMRA cap skipped past year 7", approx(cap5, GSP))

print("apply_premium honours the cap")
prem_pol = IllustrationPolicyData(policy_number="T", plancode="1U143900",
                                  modal_premium=150.0, ctp=1000.0)
r = apply_premium(0.0, prem_pol, CONFIG, RATES, 1, 0.0, 0.0, 0.0, premium_cap=100.0)
check("premium capped to cap", approx(r.gross_premium, 100.0) and r.premium_capped)
r2 = apply_premium(0.0, prem_pol, CONFIG, RATES, 1, 0.0, 0.0, 0.0, premium_cap=None)
check("no cap -> full premium", approx(r2.gross_premium, 150.0) and not r2.premium_capped)
r3 = apply_premium(0.0, prem_pol, CONFIG, RATES, 1, 0.0, 0.0, 0.0, premium_cap=0.0)
check("zero cap -> pass-through", approx(r3.gross_premium, 0.0))

# ── Guideline limit reached (SX) ──────────────────────────────────────
print("Guideline limit reached (SX)")
check("reached at the ceiling",
      _guideline_limit_reached(IllustrationOptions(), mec_pol, GSP, GSP, 0.0))
check("not reached below ceiling",
      not _guideline_limit_reached(IllustrationOptions(), mec_pol, GSP, 12000.0, 0.0))
check("not reached when TEFRA off",
      not _guideline_limit_reached(IllustrationOptions(conform_to_tefra=False), mec_pol, GSP, GSP, 0.0))

# ── GP exception premium (SY/SZ/TA/TB/TD) ─────────────────────────────
print("GP exception premium")
exc_pol = IllustrationPolicyData(policy_number="T", plancode="1U143900",
                                 def_of_life_ins="GPT", ccv_active=False)
on = IllustrationOptions(allow_exception_prems=True)
e = _compute_exception_premium(on, exc_pol, CONFIG, RATES, 1, av_after_charge=-50.0,
                               coi_rate=0.05, guideline_limit_reached=True, past_snet=True,
                               prior_exception_mode=False, prior_lapsed=False, attained_age=70)
check("exception mode triggers", e.mode)
check("exception gross covers shortfall", approx(e.gross, 50.0))
check("exception brings AV to ~0", approx(e.av_after_exception, 0.0))
check("grossed-up premium > shortfall (loads)", e.prem > 50.0)
e2 = _compute_exception_premium(on, exc_pol, CONFIG, RATES, 1, av_after_charge=-50.0,
                                coi_rate=0.05, guideline_limit_reached=True, past_snet=False,
                                prior_exception_mode=False, prior_lapsed=False, attained_age=70)
check("no exception inside safety-net period", not e2.mode and approx(e2.av_after_exception, -50.0))
off = IllustrationOptions(allow_exception_prems=False)
e3 = _compute_exception_premium(off, exc_pol, CONFIG, RATES, 1, av_after_charge=-50.0,
                                coi_rate=0.05, guideline_limit_reached=True, past_snet=True,
                                prior_exception_mode=False, prior_lapsed=False, attained_age=70)
check("toggle off -> no exception", not e3.mode)
e4 = _compute_exception_premium(on, exc_pol, CONFIG, RATES, 1, av_after_charge=25.0,
                                coi_rate=0.05, guideline_limit_reached=True, past_snet=True,
                                prior_exception_mode=True, prior_lapsed=False, attained_age=70)
check("mode latches; positive AV -> no premium", e4.mode and approx(e4.prem, 0.0))
shadow_pol = IllustrationPolicyData(policy_number="T", plancode="1U143900", ccv_active=True)
e5 = _compute_exception_premium(on, shadow_pol, CONFIG, RATES, 1, av_after_charge=-50.0,
                                coi_rate=0.05, guideline_limit_reached=True, past_snet=True,
                                prior_exception_mode=False, prior_lapsed=False, attained_age=70)
check("CCV active -> no exception", not e5.mode)

# ── New fixed loan split (TR/TW/TX) ───────────────────────────────────
print("New fixed loan gain split")
l1 = apply_new_fixed_loan(LoanState(), 1000.0, 5000.0, 3000.0, 0.0)
check("full loan preferred when gain covers it", approx(l1.pf_loan_princ, 1000.0) and approx(l1.rg_loan_princ, 0.0))
l2 = apply_new_fixed_loan(LoanState(), 1000.0, 3500.0, 3000.0, 0.0)
check("split at the gain boundary", approx(l2.pf_loan_princ, 500.0) and approx(l2.rg_loan_princ, 500.0))
l3 = apply_new_fixed_loan(LoanState(), 1000.0, 2000.0, 3000.0, 0.0)
check("no gain -> all regular", approx(l3.pf_loan_princ, 0.0) and approx(l3.rg_loan_princ, 1000.0))

print(f"\nALL {passed} CHECKS PASSED")
