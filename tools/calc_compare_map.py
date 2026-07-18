"""Column map for the RERUN <-> SuiteView engine comparison.

Mirrors RERUN's CalcEngine column GROUPING and ORDER so the comparison (and,
later, the Values tab) can present the same layout with expand/collapse by group
and a detail-level selector.

Each field tuple is (label, engine_spec, rerun_col, kind):
  engine_spec : a MonthlyState field name, or a list of names to SUM
                (RERUN combines some columns, e.g. rider+benefit -> vRiderBenefitCharge).
  rerun_col   : the CalcEngine column letter (see docs/Illustration_UL/calcengine_map.tsv).
  kind        : "date" | "int" | "val" | "rate" | "bool" — controls tolerance/formatting.

Each group has a detail LEVEL; the comparison includes a group when the requested
level is >= the group's level:  summary(0) < standard(1) < full(2).
"""
from __future__ import annotations

LEVELS = {"summary": 0, "standard": 1, "full": 2}

# Per-kind absolute tolerance for flagging a delta.
KIND_TOL = {"val": 0.01, "rate": 1e-6, "int": 0.0, "date": 0.0, "bool": 0.0}

GROUPS = [
    {"name": "Counters", "level": "summary", "fields": [
        ("date",          "date",         "C", "date"),
        ("policy_year",   "policy_year",  "D", "int"),
        ("attained_age",  "attained_age", "G", "int"),
    ]},
    {"name": "Premium", "level": "summary", "fields": [
        ("premium",          "gross_premium",    "WI", "val"),
        ("av_after_premium", "av_after_premium", "OO", "val"),
    ]},
    {"name": "Withdrawal", "level": "standard", "fields": [
        ("input_wd",      "input_withdrawal",       "AX", "val"),
        ("max_net",       "max_net_withdrawal",     "AY", "val"),
        ("applied_net",   "applied_net_withdrawal", "BA", "val"),
        ("wd_to_date",    "withdrawals_to_date",    "BD", "val"),
        ("partial_sc",    "wd_partial_sc",          "BM", "val"),
        ("gross_wd",      "gross_withdrawal",       "BN", "val"),
        ("av_post_wd",    "av_post_withdrawal",     "BO", "val"),
        ("face_decrease", "wd_face_decrease",       "BP", "val"),
        ("cost_basis",    "cost_basis_after_wd",    "BC", "val"),
    ]},
    {"name": "Guideline", "level": "standard", "fields": [
        ("gsp",             "gsp",                "KS", "val"),
        ("glp",             "glp",                "KT", "val"),
        ("accum_glp",       "accumulated_glp",    "KU", "val"),
        ("guideline_limit", "guideline_limit",    "KV", "val"),
        ("forceout",        "guideline_forceout", "KX", "val"),
    ]},
    {"name": "Targets", "level": "standard", "fields": [
        ("monthly_mtp", "monthly_mtp",     "JE", "val"),
        ("accum_mtp",   "accumulated_mtp", "JF", "val"),
        ("ctp",         "ctp",             "KQ", "val"),
    ]},
    {"name": "TAMRA", "level": "standard", "fields": [
        ("sevenpay_level", "tamra_7pay_level", "KY", "val"),
        ("tamra_year",     "tamra_year",       "LD", "int"),
        ("amount_in_7pay", "amount_in_7pay",   "LE", "val"),
    ]},
    {"name": "Deduction", "level": "standard", "fields": [
        ("coi_charge",    "coi_charge",                          "QZ", "val"),
        ("epu_charge",    "epu_charge",                          "SF", "val"),
        ("mfee_charge",   "mfee_charge",                         "SG", "val"),
        ("av_charge",     "av_charge",                           "SI", "val"),
        ("rider_benefit", ["benefit_charges", "rider_charges"],  "SO", "val"),
        ("total_md",      "total_deduction",                     "SU", "val"),
        ("av_after_ded",  "av_after_deduction",                  "SV", "val"),
    ]},
    {"name": "Interest", "level": "summary", "fields": [
        ("interest", "interest_credited", "VM", "val"),
        ("av_end",   "av_end_of_month",   "VV", "val"),
    ]},
    {"name": "Values", "level": "summary", "fields": [
        ("surr_charge",   "surrender_charge", "TK", "val"),   # vFullSC — all coverages
        # WG vIllustrationSV = MAX(0, vESV) — the ENDING SV (EAV − SC − ELN),
        # not vLapseSV (engine surrender_value).
        ("surr_value",    "ending_sv",        "WG", "val"),
        ("death_benefit", "ending_db",        "WB", "val"),
        # NA displays the BEGINNING-of-month debt (before new loans/accrual).
        ("policy_debt",   ["rg_loan_princ", "rg_loan_accrued", "pf_loan_princ",
                           "pf_loan_accrued", "vbl_loan_princ", "vbl_loan_accrued"],
                          "NA", "val"),
    ]},
    {"name": "Loans", "level": "standard", "fields": [
        ("end_rg_princ",   "end_rg_loan_princ",   "VO", "val"),
        ("end_rg_accrued", "end_rg_loan_accrued", "VP", "val"),
        ("end_pf_princ",   "end_pf_loan_princ",   "VQ", "val"),
        ("end_pf_accrued", "end_pf_loan_accrued", "VR", "val"),
        ("end_vbl_princ",  "end_vbl_loan_princ",  "VS", "val"),
        ("end_vbl_accrued","end_vbl_loan_accrued","VT", "val"),
    ]},
    {"name": "Rates", "level": "full", "fields": [
        ("coi_rate",      "coi_rate",              "OY", "rate"),   # base COI w/ substandard
        ("corridor_rate", "corridor_rate",         "OR", "rate"),
        ("epu_rate",      "epu_rate",              "RX", "rate"),
        ("scr_rate",      "scr_rate",              "AN", "val"),    # surrender charge per unit
        ("interest_rate", "effective_annual_rate", "VL", "rate"),
    ]},
    {"name": "Shadow", "level": "full", "fields": [
        ("shadow_bav",           "shadow_bav",           "WP", "val"),
        ("shadow_sa",            "shadow_sa",            "WR", "val"),
        ("shadow_narav",         "shadow_nar_av",        "XF", "val"),
        ("shadow_db",            "shadow_db",            "XG", "val"),
        ("shadow_coi_rate",      "shadow_coi_rate",      "XI", "rate"),
        ("shadow_nar",           "shadow_nar",           "XK", "val"),
        ("shadow_coi",           "shadow_coi",           "XL", "val"),
        ("shadow_epu",           "shadow_epu",           "XN", "val"),
        ("shadow_mfee",          "shadow_mfee",          "XO", "val"),
        ("shadow_md",            "shadow_md",            "XQ", "val"),
        ("shadow_av",            "shadow_av",            "XR", "val"),
        ("shadow_interest",      "shadow_interest",      "XV", "val"),
        ("shadow_eav",           "shadow_eav",           "XW", "val"),
        ("shadow_eav_less_debt", "shadow_eav_less_debt", "XX", "val"),
    ]},
]


def groups_for_level(level: str):
    want = LEVELS.get(level, 2)
    return [g for g in GROUPS if LEVELS[g["level"]] <= want]


def all_rerun_cols(level: str = "full"):
    cols = []
    for g in groups_for_level(level):
        for _, _, rc, _ in g["fields"]:
            if rc not in cols:
                cols.append(rc)
    return cols


def all_engine_fields(level: str = "full"):
    fields = []
    for g in groups_for_level(level):
        for _, ef, _, _ in g["fields"]:
            for f in (ef if isinstance(ef, (list, tuple)) else [ef]):
                if f not in fields:
                    fields.append(f)
    return fields
