"""Live DB2 + UL_Rates: PolView and RERUN reproduce CyberLife's joint survivor COI.

Read-only. Each case is an in-force company-26 joint survivor phase (CKPR,
verified 9/28/2026) whose stored current COI (LH_COV_INS_RNL_RT type C,
JT_INS_IND 0 RNL_RT / 100000) PolView must reproduce exactly to 5 decimals
from UL_Rates ``rates`` JS_Q / PLAN_ATTR through PolicyInformation. They cover
all three plan families, table ratings on either life, B11's cap at
guaranteed, the unisex N91EMB00 and separate 3-year COLA phases. RERUN cases
check the illustration engine's valuation-month charges against CyberLife.

Run: venv\\Scripts\\python.exe -m pytest tests\\test_joint_survivor_live.py -m live_db2
Every in-force phase: tools\\rates\\verify_polview_joint_survivor.py '{"all": true}'
Every in-force policy in RERUN: tools\\rates\\verify_rerun_joint_survivor.py '{}'
"""

import pytest

from suiteview.core.local_dev import local_data_enabled
from suiteview.polview.services.policy_service import get_policy_info

pytestmark = pytest.mark.live_db2

# (policy, PolView coverage index, plancode, rated)
CASES = [
    ("000313486", 1, "B11EP200", False),
    ("000335148", 1, "B11EP200", True),    # joint insured table X; current capped at guaranteed
    ("000326026", 1, "B11EP400", True),    # primary table X
    ("000278731", 1, "N71EP100", True),    # primary table B
    ("000282660", 1, "N71EP100", True),    # joint insured table E
    ("000307872", 1, "N71EMJ00", False),
    ("000259770", 1, "N91EAA00", False),
    ("000259770", 2, "N91EAA00", False),   # COLA increase phase, own issue date and ages
    ("000259770", 4, "N91EAA00", False),
    ("000273662", 1, "N91EAN00", False),
    ("000224130", 1, "N91EMB00", False),   # unisex JS_Q stored under the insured's own sex
    ("000231041", 1, "N91EAJ00", False),
]


@pytest.fixture(scope="module", autouse=True)
def _live_only():
    if local_data_enabled():
        pytest.skip("Needs live DB2/UL_Rates, not SUITEVIEW_LOCAL_DATA.")


@pytest.mark.parametrize("policy_number,index,plancode,rated", CASES,
                         ids=[f"{c[0]}-{c[1]}-{c[2]}" for c in CASES])
def test_polview_reproduces_stored_joint_coi(policy_number, index, plancode, rated):
    policy = get_policy_info(policy_number, region="CKPR", company_code="26", use_cache=False)
    assert policy is not None and policy.exists, f"{policy_number} not found"
    assert policy.coverages.cov_plancode(index) == plancode
    assert policy.rates.cov_is_joint_survivor(index)

    js = policy.rates.rates_joint_survivor(index)
    assert bool(js.ratings) == rated
    assert js.stored_rate is not None
    assert js.comparison_status == "match", js.comparison_text
    assert js.calculated_current == pytest.approx(js.stored_rate, abs=5e-7)
    assert all(0 <= c <= g for c, g in zip(js.schedule.current, js.schedule.guaranteed)
               if js.rules.cap_curr_at_guar)

    matrix = policy.rates.build_coverage_rate_matrix(index)
    headers, rows = matrix[0], matrix[1:]
    check = headers.index("Check")
    marked = [row for row in rows if row[check] != ""]
    assert len(marked) == 1 and marked[0][check] == "Match"
    assert marked[0][headers.index("Year")] == js.policy_year


# RERUN: valuation-month COI and monthly deduction equal CyberLife's recorded
# LH_POL_MVRY_VAL charges. (policy, plancode, what it exercises)
RERUN_CASES = [
    ("000335148", "B11EP200", "joint insured table X; percent-of-target SC in period"),
    ("000326026", "B11EP400", "NJ flat fee; primary table X"),
    ("000313486", "B11EP200", "EP2 $40 fee table"),
    ("000312014", "N71EMR00", "EP workbook reference case"),
    ("000216407", "N91EAB00", "EA workbook reference case; face decreased"),
    ("000231979", "N91EAB00", "corridor NAR at the newest COLA phase's rate"),
    ("000224130", "N91EMB00", "unisex; age 95 corridor 1.00 (NAR negative)"),
    ("000259770", "N91EAA00", "seven phases incl. COLA increases"),
    ("000273662", "N91EAN00", "NJ; four phases"),
]


@pytest.mark.parametrize("policy_number,plancode,_what", RERUN_CASES,
                         ids=[c[0] for c in RERUN_CASES])
def test_rerun_month0_deduction_matches_cyberlife(policy_number, plancode, _what):
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.guaranteed_projection import run_guaranteed_projection
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data

    policy = build_illustration_data(policy_number, region="CKPR", company_code="26")
    assert policy.plancode == plancode and policy.is_joint_survivor
    engine = IllustrationEngine()
    month0 = engine.project(policy, months=0)[0]
    assert month0.total_coi_charge == pytest.approx(policy.system_coi_charge, abs=0.005)
    assert month0.md_check_calculated_deduction == pytest.approx(
        policy.system_monthly_deduction, abs=0.005)
    current = engine.project(policy, months=24)
    assert len(run_guaranteed_projection(policy, current, engine=engine)) > 1
