"""Joint survivor (second-to-die) UL COI: the VP/MS JSURVCOI port and PolView's view.

Expected series were produced by the Cyberlife_Rates reference implementation
(``Rates_Database/scripts/joint_survivor_coi.py``) with
``tools/rates/capture_joint_survivor_reference.py``. The four live cases use
UL_Rates ``rates`` JS_Q vectors of real in-force phases; their final current
rate equals CyberLife's stored LH_COV_INS_RNL_RT (type C, JT_INS_IND 0) value.
Everything here is offline: no DB2 or UL_Rates access.
"""

import json
import os
from types import SimpleNamespace
from datetime import date

import pytest

from suiteview.core.joint_survivor_coi import (
    VPMS_UNAVAILABLE_TEXT, Insured, JointRules, JointSurvivorError, Rating,
    anniversary_year, calculate_joint_survivor_rates, compare_stored_rate,
    joint_monthly_coi, joint_schedule, rated_q, vround,
)

TABLE_PCT = "0=1;A=1.25;AA=1.375;B=1.5;BB=1.625;C=1.75;D=2;E=2.25;F=2.5;H=3;J=3.5;L=4;P=5;T=6;X=9.99"

# name, PLAN_ATTR (live cases), rules, ratings, JS_Q (cx/cy current, gx/gy guaranteed; primary x = person 00),
# and the reference implementation's monthly joint COI per $1,000 (C current, G guaranteed).
REFERENCE_CASES = json.loads("""[{"name":"N91EAB00 F/H/49 + M/H/49","attrs":{"JS_CAP_CURR_AT_GUAR":"N","JS_FLAT_FACTOR":"0.012","JS_TABLE_PCT":"0=1;A=1.25;AA=1.375;B=1.5;BB=1.625;C=1.75;D=2;E=2.25;F=2.5;H=3;J=3.5;L=4;P=5;T=6;X=9.99","JS_ZERO_CURR_AT_Q0":"Y","JS_ZERO_GUAR_AT_Q1":"N","LIVES":"3"},"rules":{"cap_curr_at_guar":false,"zero_guar_at_q1":false,"zero_curr_at_q0":true,"flat_factor":0.012},"ratings":[],"cx":[0.00267,0.00287,0.00308,0.00332,0.0036,0.00389,0.0042,0.00451,0.00483,0.00513,0.00545,0.00583,0.00627,0.00684,0.00754,0.00838,0.00928,0.01025,0.01124,0.01223,0.0133,0.01452,0.01599,0.0178,0.02002,0.02262,0.02556,0.0288],"cy":[0.00311,0.00336,0.00366,0.00401,0.0044,0.00486,0.00536,0.00591,0.0065,0.00714,0.00786,0.00866,0.00955,0.01056,0.01172,0.01303,0.01447,0.01603,0.01771,0.01952,0.0215,0.02372,0.02665,0.02915,0.0325,0.03625,0.04028,0.04457],"gx":[0.0039,0.00419,0.0045,0.00485,0.00526,0.00568,0.00613,0.00659,0.00705,0.00749,0.00796,0.00851,0.00916,0.00998,0.01101,0.01223,0.01355,0.01497,0.01641,0.01786,0.01941,0.0212,0.02334,0.02599,0.02922,0.03302,0.03732,0.04204],"gy":[0.00454,0.00491,0.00535,0.00586,0.00643,0.00709,0.00782,0.00863,0.00949,0.01042,0.01147,0.01264,0.01394,0.01542,0.01711,0.01902,0.02113,0.0234,0.02586,0.0285,0.03138,0.03463,0.03891,0.04256,0.04744,0.05292,0.0588,0.06506],"C":[0.00069,0.00229,0.00425,0.0067,0.00976,0.01354,0.01817,0.02375,0.0304,0.03817,0.04741,0.05857,0.07201,0.08874,0.10964,0.13566,0.16696,0.20431,0.24797,0.29833,0.35736,0.42776,0.51773,0.6197,0.75142,0.912,1.10295,1.32634],"G":[0.00148,0.00487,0.00904,0.01422,0.02065,0.02855,0.03819,0.0498,0.0635,0.07944,0.09834,0.12096,0.14817,0.1817,0.22347,0.27498,0.33668,0.40955,0.49387,0.59021,0.70158,0.83381,1.00109,1.1886,1.42841,1.71829,2.05869,2.45104]},
{"name":"B11EP200 F/H/58 + M/H/62 joint table X","attrs":{"JS_CAP_CURR_AT_GUAR":"Y","JS_FLAT_FACTOR":"0.012","JS_TABLE_PCT":"0=1;A=1.25;AA=1.375;B=1.5;BB=1.625;C=1.75;D=2;E=2.25;F=2.5;H=3;J=3.5;L=4;P=5;T=6;X=9.99","JS_ZERO_CURR_AT_Q0":"Y","JS_ZERO_GUAR_AT_Q1":"Y","LIVES":"3"},"rules":{"cap_curr_at_guar":true,"zero_guar_at_q1":true,"zero_curr_at_q0":true,"flat_factor":0.012},"ratings":[{"person":"01","type_code":"1","table_code":"X","effective_year":0,"cease_year":42}],"cx":[0.00142,0.002,0.00263,0.0033,0.00399,0.00473,0.00547,0.00623,0.00704,0.00778,0.00878,0.00977,0.0109],"cy":[0.00373,0.00548,0.0085,0.00999,0.01236,0.01262,0.01418,0.01623,0.01819,0.02109,0.02473,0.02796,0.03207],"gx":[0.00626,0.00682,0.0074,0.00803,0.00872,0.00943,0.0102,0.01105,0.01199,0.01302,0.01417,0.01543,0.01682],"gy":[0.01114,0.01251,0.01395,0.01547,0.01701,0.01857,0.02025,0.02199,0.0241,0.02646,0.02956,0.03283,0.03627],"C":[0.00441,0.02121,0.05857,0.11043,0.18546,0.25875,0.35197,0.45947,0.57247,0.6923,0.82952,0.9479,1.0679],"G":[0.05807,0.18383,0.32052,0.46424,0.61,0.75142,0.88803,1.01736,1.14383,1.26334,1.38312,1.49241,1.59559]},
{"name":"N71EP100 F/H/57 + M/H/59 primary table B","attrs":{"JS_CAP_CURR_AT_GUAR":"N","JS_FLAT_FACTOR":"0.012","JS_TABLE_PCT":"0=1;A=1.25;AA=1.375;B=1.5;BB=1.625;C=1.75;D=2;E=2.25;F=2.5;H=3;J=3.5;L=4;P=5;T=6;X=9.99","JS_ZERO_CURR_AT_Q0":"Y","JS_ZERO_GUAR_AT_Q1":"N","LIVES":"3"},"rules":{"cap_curr_at_guar":false,"zero_guar_at_q1":false,"zero_curr_at_q0":true,"flat_factor":0.012},"ratings":[{"person":"00","type_code":"1","table_code":"B","effective_year":0,"cease_year":43}],"cx":[0.00119,0.00167,0.00219,0.00278,0.00339,0.00401,0.00467,0.00534,0.00598,0.00665,0.00732,0.0082,0.00915,0.01073,0.01197,0.01638,0.01812,0.02014,0.0225,0.02522,0.02835,0.03193,0.03596,0.04044,0.04536,0.05074],"cy":[0.00258,0.00363,0.00499,0.0061,0.00738,0.00817,0.00934,0.01064,0.01203,0.01404,0.01684,0.01953,0.02233,0.0249,0.02886,0.03787,0.0415,0.0455,0.04992,0.05476,0.06002,0.06571,0.07182,0.07827,0.08511,0.09265],"gx":[0.00705,0.00749,0.00796,0.00851,0.00916,0.00998,0.01101,0.01223,0.01355,0.01497,0.01641,0.01786,0.01941,0.0212,0.02334,0.02599,0.02922,0.03302,0.03732,0.04204,0.04711,0.05253,0.05845,0.06512,0.07276,0.08159],"gy":[0.01147,0.01264,0.01394,0.01542,0.01711,0.01902,0.02113,0.0234,0.02586,0.0285,0.03138,0.03463,0.03891,0.04256,0.04744,0.05292,0.0588,0.06506,0.07164,0.07847,0.08572,0.09367,0.10252,0.11252,0.12379,0.13611],"C":[0.00038,0.00183,0.00481,0.00973,0.01731,0.0271,0.04074,0.05861,0.08099,0.11114,0.15192,0.20355,0.26725,0.35163,0.4571,0.70382,0.88621,1.10376,1.36372,1.67221,2.03655,2.46418,2.96034,3.52789,4.17062,4.89975],"G":[0.01011,0.03322,0.06122,0.09533,0.13718,0.18917,0.25405,0.33401,0.43039,0.54498,0.67851,0.83354,1.02344,1.23226,1.49362,1.81125,2.19195,2.64234,3.16447,3.7572,4.42325,5.17147,6.01861,6.9921,8.11778,9.41319]},
{"name":"N91EMB00 unisex M/H/61 + M/H/61","attrs":{"JS_CAP_CURR_AT_GUAR":"N","JS_FLAT_FACTOR":"0.012","JS_TABLE_PCT":"0=1;A=1.25;AA=1.375;B=1.5;BB=1.625;C=1.75;D=2;E=2.25;F=2.5;H=3;J=3.5;L=4;P=5;T=6;X=9.99","JS_ZERO_CURR_AT_Q0":"Y","JS_ZERO_GUAR_AT_Q1":"N","LIVES":"3"},"rules":{"cap_curr_at_guar":false,"zero_guar_at_q1":false,"zero_curr_at_q0":true,"flat_factor":0.012},"ratings":[],"cx":[0.00855,0.00944,0.01047,0.01163,0.0129,0.01428,0.01575,0.01732,0.01902,0.02095,0.02344,0.02567,0.02862,0.03194,0.03553,0.03937,0.04341,0.04761,0.05209,0.05702,0.06255,0.06881,0.07591,0.08369,0.09204,0.10072,0.10981,0.1191,0.12872,0.13879,0.1495,0.16113,0.17427,0.19098,0.21443],"cy":[0.00855,0.00944,0.01047,0.01163,0.0129,0.01428,0.01575,0.01732,0.01902,0.02095,0.02344,0.02567,0.02862,0.03194,0.03553,0.03937,0.04341,0.04761,0.05209,0.05702,0.06255,0.06881,0.07591,0.08369,0.09204,0.10072,0.10981,0.1191,0.12872,0.13879,0.1495,0.16113,0.17427,0.19098,0.21443],"gx":[0.01296,0.0143,0.01586,0.01762,0.01955,0.02164,0.02387,0.02624,0.02882,0.03174,0.03551,0.03889,0.04337,0.04839,0.05384,0.05965,0.06577,0.07213,0.07892,0.0864,0.09477,0.10426,0.11502,0.1268,0.13945,0.15261,0.16638,0.18045,0.19503,0.21029,0.22651,0.24413,0.26404,0.28936,0.32489],"gy":[0.01296,0.0143,0.01586,0.01762,0.01955,0.02164,0.02387,0.02624,0.02882,0.03174,0.03551,0.03889,0.04337,0.04839,0.05384,0.05965,0.06577,0.07213,0.07892,0.0864,0.09477,0.10426,0.11502,0.1268,0.13945,0.15261,0.16638,0.18045,0.19503,0.21029,0.22651,0.24413,0.26404,0.28936,0.32489],"C":[0.00609,0.02064,0.03952,0.06382,0.09455,0.13281,0.1795,0.23578,0.30323,0.3852,0.49152,0.60756,0.758,0.94013,1.15476,1.40395,1.68793,2.0061,2.36451,2.7734,3.24435,3.7898,4.42251,5.1387,5.93442,6.79369,7.72013,8.69537,9.72553,10.81781,11.98719,13.25922,14.69166,16.4905,19.00193],"G":[0.014,0.04711,0.08958,0.14361,0.21115,0.29411,0.39404,0.51258,0.65293,0.82096,1.03652,1.26723,1.56375,1.91662,2.32662,2.79383,3.31737,3.89351,4.53253,5.25213,6.06977,7.00764,8.08467,9.28931,10.61282,12.02498,13.53064,15.09837,16.74263,18.47794,20.33329,22.35928,24.66247,27.61514,31.85464]},
{"name":"synthetic B11 rules: flats, percent, windows, q=0, q=1","attrs":null,"rules":{"cap_curr_at_guar":true,"zero_guar_at_q1":true,"zero_curr_at_q0":true,"flat_factor":0.012},"ratings":[{"person":"00","type_code":"2","flat_per_1000":5.0,"effective_year":0,"cease_year":3},{"person":"01","type_code":"4","flat_per_1000":2.5,"effective_year":0,"cease_year":5},{"person":"01","type_code":"0","percent":150,"effective_year":2,"cease_year":6},{"person":"00","type_code":"3","table_code":"D","effective_year":0,"cease_year":99},{"person":"01","type_code":"1","table_code":"AA","effective_year":4,"cease_year":8}],"cx":[0.0,0.0012,0.0015,0.002,0.0031,0.0045,0.3,0.8,1.0,1.0],"cy":[0.0008,0.001,0.0013,0.0017,0.0024,0.0035,0.05,0.1,0.2,0.5],"gx":[0.0011,0.0016,0.002,0.0027,0.004,0.006,0.4,0.9,1.0,1.0],"gy":[0.001,0.0013,0.0017,0.0022,0.003,0.0045,0.07,0.15,0.3,0.6],"C":[0.0,0.46218,0.74842,0.50255,0.57282,0.25014,5.91805,12.25102,0.0,0.0],"G":[0.16083,0.46218,0.74842,0.50255,0.57282,0.25014,16.04386,23.12246,0.0,0.0]},
{"name":"synthetic N91 rules: same inputs, no cap, no zero-guar","attrs":null,"rules":{"cap_curr_at_guar":false,"zero_guar_at_q1":false,"zero_curr_at_q0":true,"flat_factor":0.012},"ratings":[{"person":"00","type_code":"2","flat_per_1000":5.0,"effective_year":0,"cease_year":3},{"person":"01","type_code":"4","flat_per_1000":2.5,"effective_year":0,"cease_year":5},{"person":"01","type_code":"0","percent":150,"effective_year":2,"cease_year":6},{"person":"00","type_code":"3","table_code":"D","effective_year":0,"cease_year":99},{"person":"01","type_code":"1","table_code":"AA","effective_year":4,"cease_year":8}],"cx":[0.0,0.0012,0.0015,0.002,0.0031,0.0045,0.3,0.8,1.0,1.0],"cy":[0.0008,0.001,0.0013,0.0017,0.0024,0.0035,0.05,0.1,0.2,0.5],"gx":[0.0011,0.0016,0.002,0.0027,0.004,0.006,0.4,0.9,1.0,1.0],"gy":[0.001,0.0013,0.0017,0.0022,0.003,0.0045,0.07,0.15,0.3,0.6],"C":[0.0,2.62078,2.7023,2.75383,2.92149,0.54853,5.91805,12.25102,18.42347,56.12569],"G":[0.16083,0.46218,0.74842,0.50255,0.57282,0.25014,16.04386,23.12246,29.28553,73.51513]}

]""")

# CyberLife's stored current COI (RNL_RT / 100000) at the final year of each live case.
IN_FORCE_STORED = {
    "N91EAB00 F/H/49 + M/H/49": 1.32634,
    "B11EP200 F/H/58 + M/H/62 joint table X": 1.06790,
    "N71EP100 F/H/57 + M/H/59 primary table B": 4.89975,
    "N91EMB00 unisex M/H/61 + M/H/61": 19.00193,
}


def _attrs(case):
    if case["attrs"]:
        return case["attrs"]
    rules = case["rules"]
    yn = lambda flag: "Y" if flag else "N"  # noqa: E731
    return {
        "LIVES": "3", "JS_TABLE_PCT": TABLE_PCT, "JS_FLAT_FACTOR": str(rules["flat_factor"]),
        "JS_CAP_CURR_AT_GUAR": yn(rules["cap_curr_at_guar"]),
        "JS_ZERO_GUAR_AT_Q1": yn(rules["zero_guar_at_q1"]),
        "JS_ZERO_CURR_AT_Q0": yn(rules["zero_curr_at_q0"]),
    }


def _base(case):
    return {"C": (case["cx"], case["cy"]), "G": (case["gx"], case["gy"])}


@pytest.mark.parametrize("case", REFERENCE_CASES, ids=lambda case: case["name"])
def test_port_reproduces_reference_implementation(case):
    rules = JointRules.from_plan_attributes(_attrs(case))
    ratings = [Rating(**r) for r in case["ratings"]]
    schedule = joint_schedule(_base(case), ratings, rules)
    assert list(schedule.current) == case["C"]
    assert list(schedule.guaranteed) == case["G"]
    assert joint_monthly_coi(_base(case), "C", ratings, rules) == case["C"]
    assert joint_monthly_coi(_base(case), "G", ratings, rules) == case["G"]


@pytest.mark.parametrize("name,stored", IN_FORCE_STORED.items())
def test_live_cases_reproduce_cyberlife_stored_rate(name, stored):
    case = next(c for c in REFERENCE_CASES if c["name"] == name)
    ratings = [Rating(**r) for r in case["ratings"]]
    current = joint_schedule(_base(case), ratings, JointRules.from_plan_attributes(_attrs(case))).current
    assert compare_stored_rate(current, len(current), stored) == ("match", "Match")


def test_synthetic_rules_zero_current_at_q0_zero_guar_at_q1_and_cap():
    b11, n91 = REFERENCE_CASES[4], REFERENCE_CASES[5]
    assert b11["C"][0] == 0.0 and n91["C"][0] == 0.0          # primary current q = 0 in year 1
    assert b11["G"][-1] == 0.0 and n91["G"][-1] > 0            # guaranteed qx = 1 in t and t-1
    assert all(c <= g for c, g in zip(b11["C"], b11["G"]))     # B11 caps current at guaranteed


@pytest.mark.parametrize("value,places,expected", [
    (0.000125, 5, 0.00013), (2.5, 0, 3.0), (-2.5, 0, -3.0), (0.30000000000000004, 1, 0.3),
    # 15 significant digits, not the shortest repr (which would give 0.123456789 and 0.000001).
    (0.12345678949999998, 9, 0.12345679), (1.4999999999999998e-06, 6, 0.000002),
])
def test_vround_is_half_up_on_fifteen_significant_digits(value, places, expected):
    assert vround(value, places) == expected


def test_rated_q_table_percent_flat_and_primary_base_quirk():
    rules = JointRules.from_plan_attributes(_attrs(REFERENCE_CASES[4]))
    ratings = [Rating("00", "1", "D"), Rating("01", "0", percent=150),
               Rating("01", "2", flat_per_1000=5.0, cease_year=2)]
    assert rated_q(0.01, 0.01, "00", 1, ratings, rules) == pytest.approx(0.02)
    assert rated_q(0.01, 0.01, "01", 1, ratings, rules) == pytest.approx(0.015 + 0.06)
    # Flats on the joint life are tested against the PRIMARY's base rate.
    assert rated_q(0.01, 0.0, "01", 1, ratings, rules) == pytest.approx(0.015)
    assert rated_q(0.01, 0.01, "01", 3, ratings, rules) == pytest.approx(0.015)  # flat ceased
    assert rated_q(0.9, 0.9, "00", 1, ratings, rules) == 1.0
    with pytest.raises(JointSurvivorError, match="ZZ"):
        rated_q(0.01, 0.01, "00", 1, [Rating("00", "1", "ZZ")], rules)


def test_anniversary_year_is_ceiling_of_yyyymmdd_difference():
    assert anniversary_year(20100315, 20100315) == 0
    assert anniversary_year(20100316, 20100315) == 1
    assert anniversary_year(20200315, 20100315) == 10
    assert anniversary_year(20200316, 20100315) == 11
    assert anniversary_year(99991231, 20100315) > 900


def test_plan_rules_must_be_explicit():
    attrs = _attrs(REFERENCE_CASES[0])
    for missing in ("JS_TABLE_PCT", "JS_FLAT_FACTOR", "JS_CAP_CURR_AT_GUAR",
                    "JS_ZERO_GUAR_AT_Q1", "JS_ZERO_CURR_AT_Q0"):
        with pytest.raises(JointSurvivorError, match=missing):
            JointRules.from_plan_attributes({k: v for k, v in attrs.items() if k != missing})
    with pytest.raises(JointSurvivorError, match="LIVES"):
        JointRules.from_plan_attributes({**attrs, "LIVES": "1"})


def test_compare_stored_rate_outcomes():
    schedule = [0.1, 0.2, 0.3]
    assert compare_stored_rate(schedule, 2, 0.2) == ("match", "Match")
    assert compare_stored_rate(schedule, 3, 0.2)[0] == "prior_year"
    status, text = compare_stored_rate(schedule, 3, 0.31)
    assert status == "differs" and "+0.01000" in text
    assert compare_stored_rate(schedule, 2, None)[0] == "unavailable"
    assert compare_stored_rate(schedule, 4, 0.3)[0] == "unavailable"


class _FakeRates:
    """Stands in for suiteview.core.rates.Rates (schema ``rates`` lookups)."""

    def __init__(self, case, maturity_age=100, durations=None):
        self.case, self.maturity_age, self.durations = case, maturity_age, durations
        self.lookups = []

    def get_plan_attributes(self, company, plancode):
        return _attrs(self.case)

    def get_plan_definition(self, company, plancode):
        return {"DESCRIPTION": f"{plancode} universal life", "MATURITY_AGE": self.maturity_age}

    def get_joint_survivor_q(self, company, plancode, scale, sex, rate_class, issue_age):
        self.lookups.append((company, plancode, scale, sex, rate_class, issue_age))
        person = "x" if (sex, rate_class, issue_age) == ("F", "H", 49) else "y"
        values = self.case[f"{scale.lower()}{person}"]
        durations = range(1, len(values) + 1) if self.durations is None else self.durations
        return {t: values[t - 1] for t in durations}


def test_calculate_joint_survivor_rates_horizon_year_and_comparison():
    case = REFERENCE_CASES[0]  # 28 JS_Q durations loaded in the fake
    x, y = Insured("F", "H", 49), Insured("M", "H", 50)
    rates = _FakeRates(case, maturity_age=70)
    js = calculate_joint_survivor_rates(rates, "26", "N91EAB00", date(1998, 6, 1), x, y, [],
                                        date(2025, 6, 1), 1.32634)
    assert js.horizon == 21 and "younger issue age 49" in js.horizon_note
    assert js.policy_year == 28 and js.comparison_status == "unavailable"
    assert {lookup[2:] for lookup in rates.lookups} == {
        ("C", "F", "H", 49), ("C", "M", "H", 50), ("G", "F", "H", 49), ("G", "M", "H", 50)}

    js = calculate_joint_survivor_rates(_FakeRates(case), "26", "N91EAB00", date(1998, 6, 1), x, y, [],
                                        date(2025, 6, 1), 1.32634)
    assert js.horizon == 28 and "JS_Q ends at duration 28" in js.horizon_note
    assert js.calculated_current == 1.32634 and js.comparison_status == "match"
    assert js.vpms_unavailable == ("MTP", "CTP", "PTP")

    # CyberLife still on the prior year's rate (anniversary not yet processed).
    js = calculate_joint_survivor_rates(_FakeRates(case), "26", "N91EAB00", date(1998, 6, 1), x, y, [],
                                        date(2025, 6, 1), case["C"][26])
    assert js.policy_year == 28 and js.comparison_status == "prior_year"


def test_calculate_joint_survivor_rates_rejects_gaps_and_missing_rates():
    case = REFERENCE_CASES[0]
    x, y = Insured("F", "H", 49), Insured("M", "H", 50)
    with pytest.raises(JointSurvivorError, match="missing duration 5"):
        calculate_joint_survivor_rates(_FakeRates(case, durations=[1, 2, 3, 4, 6]), "26", "N91EAB00",
                                       date(1998, 6, 1), x, y, [], date(2025, 6, 1), None)
    with pytest.raises(JointSurvivorError, match="No JS_Q"):
        calculate_joint_survivor_rates(_FakeRates(case, durations=[]), "26", "N91EAB00",
                                       date(1998, 6, 1), x, y, [], date(2025, 6, 1), None)


def test_local_sqlite_mode_refuses_rates_schema_lookups(monkeypatch):
    from suiteview.core import rates as rates_module

    monkeypatch.setattr(rates_module, "local_data_enabled", lambda: True)
    with pytest.raises(rates_module.RatesError, match="schema 'rates'"):
        rates_module.Rates().get_plan_attributes("26", "N91EAB00")


# -- PolicyInformation / PolView ------------------------------------------------------------------

_QT_APP = None

from suiteview.polview.models.cl_polrec.policy_data_classes import CoverageInfo  # noqa: E402
from suiteview.polview.models.policy_sections.rates import RatesSection  # noqa: E402


def _coverage(phase=4, lives="3", plancode="B11EP200"):
    fields = {name: None for name in CoverageInfo.__dataclass_fields__}
    fields.update(cov_pha_nbr=phase, plancode=plancode, issue_date=date(2013, 12, 9), issue_age=58,
                  joint_issue_age=62, number_of_lives_code=lives, joint_mortality_table_code="",
                  is_base=True, raw_data={})
    return CoverageInfo(**fields)


class _JointPolicy:
    """Just enough of PolicyInformation for its rates section's joint methods."""

    company_code = "26"
    policy_number = "TEST0001"

    def __init__(self, coverage, tables, rates):
        self._tables = tables
        self.coverages = SimpleNamespace(get_coverages=lambda: [coverage])
        self.product = SimpleNamespace(
            is_advanced_product=True,
            _product_rules_for_rate_display=lambda: SimpleNamespace(rate_family="UL", is_advanced=True))
        self.values = SimpleNamespace(valuation_date=date(2026, 1, 9))
        self.rates = RatesSection(self)
        self.rates._get_rates = lambda: rates

    def fetch_table(self, table_name):
        return self._tables[table_name]


def _b11_policy(lives="3", stored="106790", extras=None):
    case = REFERENCE_CASES[1]

    class Rates(_FakeRates):
        def get_joint_survivor_q(self, company, plancode, scale, sex, rate_class, issue_age):
            values = case[f"{scale.lower()}{'x' if issue_age == 58 else 'y'}"]
            return {t: v for t, v in enumerate(values, start=1)}

    tables = {
        "LH_COV_INS_RNL_RT": [
            {"COV_PHA_NBR": 4, "PRM_RT_TYP_CD": "C", "JT_INS_IND": "0", "RT_SEX_CD": "2",
             "RT_CLS_CD": "H ", "RNL_RT": stored},
            {"COV_PHA_NBR": 4, "PRM_RT_TYP_CD": "C", "JT_INS_IND": "1", "RT_SEX_CD": "1",
             "RT_CLS_CD": "H", "RNL_RT": None},
            {"COV_PHA_NBR": 4, "PRM_RT_TYP_CD": "M", "JT_INS_IND": "0", "RT_SEX_CD": "2",
             "RT_CLS_CD": "H", "RNL_RT": "1"},
        ],
        "LH_SST_XTR_CRG": extras if extras is not None else [
            {"COV_PHA_NBR": 4, "PRS_CD": "01", "SST_XTR_TYP_CD": "1", "SST_XTR_RT_TBL_CD": "X ",
             "SST_XTR_PCT": "0", "XTR_PER_1000_AMT": "0", "SST_XTR_EFF_DT": date(2013, 12, 9),
             "SST_XTR_CEA_DT": date(2055, 12, 9)},
            {"COV_PHA_NBR": 9, "PRS_CD": "00", "SST_XTR_TYP_CD": "2", "SST_XTR_RT_TBL_CD": "",
             "SST_XTR_PCT": "0", "XTR_PER_1000_AMT": "5", "SST_XTR_EFF_DT": None, "SST_XTR_CEA_DT": None},
        ],
    }
    return _JointPolicy(_coverage(lives=lives), tables, Rates(case, maturity_age=121))


def test_policy_gathers_both_insureds_extras_and_stored_rate():
    policy = _b11_policy()
    assert policy.rates.cov_is_joint_survivor(1)
    assert policy.rates.cov_joint_insureds(1) == (Insured("F", "H", 58), Insured("M", "H", 62))
    assert policy.rates.cov_joint_ratings(1) == [Rating("01", "1", "X", 0.0, 0.0, 0, 42)]
    assert policy.rates.cov_joint_stored_coi(1) == 1.0679
    js = policy.rates.rates_joint_survivor(1)
    assert (js.policy_year, js.comparison_status, js.horizon) == (13, "match", 13)


def test_lives_code_gates_the_joint_view():
    policy = _b11_policy(lives="1")
    assert not policy.rates.cov_is_joint_survivor(1)


def test_unexpected_joint_inputs_are_loud():
    policy = _b11_policy(extras=[{"COV_PHA_NBR": 4, "PRS_CD": "02", "SST_XTR_TYP_CD": "1"}])
    with pytest.raises(JointSurvivorError, match="person '02'"):
        policy.rates.cov_joint_ratings(1)
    policy = _b11_policy()
    policy._tables["LH_COV_INS_RNL_RT"].pop(1)
    with pytest.raises(JointSurvivorError, match="JT_INS_IND 1"):
        policy.rates.cov_joint_insureds(1)


def test_joint_matrix_shows_both_lives_blended_coi_and_vpms_targets():
    matrix = _b11_policy().rates.build_coverage_rate_matrix(1)
    headers, rows = matrix[0], matrix[1:]
    assert "COI" not in headers and "GuarCOI" not in headers
    for column in ("JS_Q 00 C", "JS_Q 01 C", "JS_Q 00 G", "JS_Q 01 G", "Rated q 01 C",
                   "JointCOI", "GuarJointCOI", "CyberLife", "Check"):
        assert column in headers
    info = {row[0]: row[1] for row in rows if row[0].strip()}
    assert info["Primary (00)"] == "F / class H / age 58"
    assert info["Joint (01)"] == "M / class H / age 62"
    assert info["  Extras 01"] == "Table X (yrs 1-42)" and info["  Extras 00"] == "None"
    assert info["Base COI"].startswith("Not IAF")
    for rate_type in ("MTP", "CTP", "STP", "SCR"):
        assert info[rate_type] == VPMS_UNAVAILABLE_TEXT
    assert info["Check"] == "Match" and info["CyberLife RNL_RT"] == "1.06790"
    marked = [row for row in rows if row[headers.index("Check")] != ""]
    assert len(marked) == 1 and marked[0][headers.index("Year")] == 13
    assert marked[0][headers.index("JointCOI")] == marked[0][headers.index("CyberLife")] == 1.0679
    assert [row[headers.index("JointCOI")] for row in rows[:13]] == REFERENCE_CASES[1]["C"]


def test_schema_grid_adds_joint_columns_and_cyberlife_check():
    from suiteview.polview.models.schema_rates import column_layout, joint_survivor_parts

    parts, meta = joint_survivor_parts(_b11_policy(), 1)
    keys = [c.key for c in parts.columns]
    for key in ("C JointCOI", "C JS_Q 01", "C Rated q 01", "G JointCOI", "G JS_Q 01",
                "CyberLife RNL_RT", "CyberLife Check"):
        assert key in keys
    by_key = {c.key: c for c in parts.columns}
    assert [by_key["C JointCOI"].value(t, None) for t in range(1, 14)] == REFERENCE_CASES[1]["C"]
    assert by_key["CyberLife Check"].value(13, None) == "Match"
    assert by_key["CyberLife Check"].value(12, None) == ""
    assert by_key["C JointCOI"].value(parts.max_year + 1, None) == ""
    info = dict(meta)
    assert info["Joint (01)"] == "M / class H / age 62" and info["STP"] == VPMS_UNAVAILABLE_TEXT
    labels, groups = column_layout(keys)
    assert labels["CyberLife Check"] == "Check"
    assert ("CyberLife", ["CyberLife RNL_RT", "CyberLife Check"]) in groups


def test_polview_window_recognizes_both_joint_grids():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from suiteview.polview.ui.main_window import joint_survivor_columns

    schema = ["Year", "C JointCOI", "CyberLife RNL_RT", "CyberLife Check"]
    legacy = ["Year", "JointCOI", "CyberLife", "Check"]
    assert joint_survivor_columns(schema) == tuple(schema[1:])
    assert joint_survivor_columns(legacy) == tuple(legacy[1:])
    assert joint_survivor_columns(["Year", "C COI"]) is None


def test_raw_table_highlights_the_current_policy_year():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from suiteview.polview.ui.tabs.raw_table_tab import RawTableTab

    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    matrix = _b11_policy().rates.build_coverage_rate_matrix(1)
    tab = RawTableTab()
    tab.set_data(matrix[0], matrix[1:], "Joint Survivor Rates - Coverage 1", transposed=False)
    tab.highlight_row(12, "#D4EDDA")
    assert {row for row, _ in tab._normal_grid.model._highlighted_cells} == {12}
    assert {column for _, column in tab._transposed_grid.model._highlighted_cells} == {"Row 13"}
    # The ledger stylesheet hides BackgroundRole unless the shared delegate paints it.
    assert type(tab._normal_grid.table_view.itemDelegate()).__name__ == "_RowAndGroupDelegate"

    from PyQt6.QtCore import Qt
    model = tab._normal_grid.model
    year = model._original_df.columns.get_loc("Year")

    def highlighted_years():
        return {model.data(model.index(r, year)) for r in range(model.rowCount())
                if model.data(model.index(r, year), Qt.ItemDataRole.BackgroundRole) is not None}

    assert highlighted_years() == {"13"}
    model.set_display_indices(model._original_df.index[::-1])  # as a descending sort does
    assert highlighted_years() == {"13"}
    tab.deleteLater()
