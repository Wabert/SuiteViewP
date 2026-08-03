"""Column map: RERUN "Debug File" sheet  <->  SuiteView engine MonthlyState.

The Debug File sheet is RERUN's per-month projection in a clean ~45-column
layout.  Labels live on row 12; data starts on row 13 (the policy's current
inforce month) and runs forward.  Column A is ``vID`` = (Year-1)*12 + Month,
which equals the engine's MonthlyState.duration — so the two sides align by
vID == duration, no date arithmetic.

Each entry:
  col    : Debug File column letter (read positionally A=1..AU=47).
  label  : the row-12 header text (also a sanity check against the live sheet).
  engine : MonthlyState field name, a list of names to SUM, or None.
           None  => RERUN-only: shown in the workbook for reference but NOT
                    diffed (no confident 1:1 engine field yet).
  kind   : "key" | "int" | "val" | "rate"  — controls tolerance & formatting.

Refinement is expected: when a tentative mapping shows a large, systematic
delta in the comparison output, it usually means the engine field is wrong —
fix the one entry here, not the engine.  Mappings flagged ``tentative`` in the
trailing comment are the first candidates to revisit.
"""
from __future__ import annotations

# Absolute tolerance per kind for flagging a delta (mirrors calc_compare_map).
KIND_TOL = {"val": 0.01, "rate": 1e-6, "int": 0.0, "key": 0.0}

# Ordered exactly as the Debug File columns A..AU.
DEBUG_COLUMNS = [
    {"col": "A",  "label": "vID",              "engine": "duration",              "kind": "key"},
    {"col": "B",  "label": "Year",             "engine": "policy_year",           "kind": "int"},
    {"col": "C",  "label": "Month",            "engine": "policy_month",          "kind": "int"},
    {"col": "D",  "label": "Premium",          "engine": "gross_premium",         "kind": "val"},
    {"col": "E",  "label": "Load",             "engine": "total_premium_load",    "kind": "val"},
    {"col": "F",  "label": "Fee",              "engine": ["mfee_charge", "epu_charge", "av_charge"], "kind": "val"},  # RERUN "Fee" = vTotalFees = AVCharge + MFee + EPU
    {"col": "G",  "label": "Riders",           "engine": ["benefit_charges", "rider_charges"], "kind": "val"},
    {"col": "H",  "label": "COI",              "engine": "coi_charge",            "kind": "val"},
    {"col": "I",  "label": "COI Rate",         "engine": "coi_rate",              "kind": "rate"},
    # J/K = RERUN vBlendedAssetRate (SU) / vAssetCharge (SV) — the IUL AG49
    # asset charge, engine fields asset_charge_rate/asset_charge (2026-07-18).
    # RERUN's PoAV charge is inside F "Fee" (vTotalFees = AVCharge+MFee+EPU).
    {"col": "J",  "label": "Asset Pct",        "engine": "asset_charge_rate",     "kind": "rate"},
    {"col": "K",  "label": "Asset Charge",     "engine": "asset_charge",          "kind": "val"},
    {"col": "L",  "label": "Interest",         "engine": "interest_credited",     "kind": "val"},
    {"col": "M",  "label": "AInt Rate",        "engine": "effective_annual_rate", "kind": "rate"},
    {"col": "N",  "label": "Account Value",    "engine": "av_end_of_month",       "kind": "val"},
    {"col": "O",  "label": "Face",             "engine": None,                    "kind": "val"},    # no per-month engine field (constant for level cases)
    {"col": "P",  "label": "Illustration DB",  "engine": "ending_db",             "kind": "val"},
    {"col": "Q",  "label": "Surrender Charge", "engine": "surrender_charge",      "kind": "val"},
    {"col": "R",  "label": "Cost Basis",       "engine": "cost_basis",            "kind": "val"},
    # S = vPolicyDebtDisplay = SUM(MS:MX): the post-capitalize/repay,
    # PRE-accrual (beginning-of-month) balance — NOT the ending debt. The
    # engine's Set-1 buckets are the same stage (before new loans/accrual).
    {"col": "S",  "label": "Loan Balance",
     "engine": ["rg_loan_princ", "rg_loan_accrued", "pf_loan_princ",
                "pf_loan_accrued", "vbl_loan_princ", "vbl_loan_accrued"],
     "kind": "val"},
    # T/U/V are PRINCIPAL-ONLY (=INDEX(vVarLoanPrinciple,...) etc.) — accrued
    # interest lives only in S vPolicyDebtDisplay. (Advance loans carry accrued
    # 0, which is why the old principal+accrued sum never showed a delta.)
    {"col": "T",  "label": "Var Loan",         "engine": "end_vbl_loan_princ",    "kind": "val"},
    {"col": "U",  "label": "Pref Loan",        "engine": "end_pf_loan_princ",     "kind": "val"},
    {"col": "V",  "label": "STD Loan",         "engine": "end_rg_loan_princ",     "kind": "val"},
    {"col": "W",  "label": "Withdrawal",       "engine": "gross_withdrawal",      "kind": "val"},
    {"col": "X",  "label": "Accum WD",         "engine": "withdrawals_to_date",   "kind": "val"},
    # ── CCV block = SuiteView shadow account (pipeline comment: "SHADOW ACCOUNT (CCV)") ──
    {"col": "Y",  "label": "CCV Value",        "engine": "shadow_eav",            "kind": "val"},    # =INDEX(vShadowEAV,...)
    {"col": "Z",  "label": "CCV Load",         "engine": "shadow_prem_load",      "kind": "val"},    # tentative
    {"col": "AA", "label": "CCV Fee",          "engine": ["shadow_epu", "shadow_mfee"], "kind": "val"},  # RERUN CCV Fee = shadow EPU + MFEE
    {"col": "AB", "label": "CCV Riders",       "engine": "shadow_rider_charges",  "kind": "val"},    # tentative
    {"col": "AC", "label": "CCV COI",          "engine": "shadow_coi",            "kind": "val"},    # tentative
    {"col": "AD", "label": "CCV COI Rate",     "engine": "shadow_coi_rate",       "kind": "rate"},   # tentative
    {"col": "AE", "label": "CCV AInt Rate",    "engine": "shadow_int_rate",       "kind": "rate"},   # tentative (nominal shadow annual rate)
    {"col": "AF", "label": "CCV Interest",     "engine": "shadow_interest",       "kind": "val"},    # tentative
    {"col": "AG", "label": "DCV Value",        "engine": None,                    "kind": "val"},    # RERUN-only (DCV meaning TBD)
    {"col": "AH", "label": "PSC",              "engine": "wd_partial_sc",         "kind": "val"},    # tentative (partial surr charge)
    # AI =INDEX(vMTPwoPW,...) and AK =INDEX(vMTP,...) — both RECOMPUTED from
    # rates each month (ceased riders/benefits drop out); Accum MTP (AJ) still
    # accrues the LOADED CyberLife target.
    {"col": "AI", "label": "MTP",              "engine": "mtp_wo_pw_recomputed",  "kind": "val"},
    {"col": "AJ", "label": "Accum MTP",        "engine": "accumulated_mtp",       "kind": "val"},
    {"col": "AK", "label": "Min Prem",         "engine": "mtp_recomputed_annual", "kind": "val"},
    # AL = vTotalNAAR = PG+PH+PI: the per-COVERAGE NARs only — the corridor
    # slice (PJ) is excluded, so at high ages / big AVs this column reads 0
    # while COI still charges the corridor NAR.
    {"col": "AL", "label": "Net Amount At Risk","engine": ["nar_cov1", "nar_cov2", "nar_cov3"], "kind": "val"},
    {"col": "AM", "label": "Necessary Prem",   "engine": None,                    "kind": "val"},    # RERUN-only
    {"col": "AN", "label": "NPT NSP",          "engine": None,                    "kind": "val"},    # RERUN-only
    {"col": "AO", "label": "NPT NSP Riders",   "engine": None,                    "kind": "val"},    # RERUN-only
    {"col": "AP", "label": "DCV Mint",         "engine": None,                    "kind": "val"},    # RERUN-only
    {"col": "AQ", "label": "Excess Prem",      "engine": None,                    "kind": "val"},    # tentative: prem_over_target?
    {"col": "AR", "label": "",                 "engine": None,                    "kind": "val"},    # blank column in sheet
    {"col": "AS", "label": "",                 "engine": None,                    "kind": "val"},    # blank column in sheet
    {"col": "AT", "label": "EPU Rate",         "engine": "epu_rate",              "kind": "rate"},
    {"col": "AU", "label": "EPU",              "engine": "epu_charge",            "kind": "val"},
]

# Sheet geometry (1-based).
LABEL_ROW = 12      # row holding the column headers (vID, Year, Month, ...)
FIRST_DATA_ROW = 13  # first projected (inforce) month
LAST_COL = 47       # AU
KEY_COL = "A"       # vID

# Columns we actually diff (engine field present and not the key/blank columns).
def comparable_columns():
    return [c for c in DEBUG_COLUMNS
            if c["engine"] is not None and c["kind"] != "key" and c["label"]]
