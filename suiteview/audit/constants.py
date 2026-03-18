"""
Audit Tool — Listbox / Combobox data.
All values replicated exactly from VBA frmAudit PopulateForm().
"""

# ── Status Code (01) ────────────────────────────────────────────────────
STATUS_CODE_ITEMS = [
    "11-Pending applications",
    "12-No Init Premium Yet",
    "21-Premium Paying",
    "22-Premium Paying",
    "31-Payor Death",
    "32-Disability",
    "33-Disability",
    "34-Disability",
    "41-Paid Up",
    "42-Single Premium",
    "43-Single Premium (none)",
    "44-ETI",
    "45-RPU",
    "46-Fully Paid Up",
    "47-Paid Up",
    "49-Annuitization (none)",
    "54-Lapsing (none)",
    "97-Reinstatement pending",
    "98-Policy not issued",
    "99-Terminated",
]

# ── Product Line Code (02) ──────────────────────────────────────────────
PRODUCT_LINE_CODE_ITEMS = [
    "0 - Traditional (Indeterm Term not includ",
    "B - Blended insurance rider",
    "C - Additional payment paid-up additions",
    "F - Annuity or Annuity Rider",
    "I - Interest sensitive life",
    "N - Indeterminate premium",
    "U - Universal or variable universal life",
    "S - Disability income",
]

# ── Product Indicator (02) — All covs (ANICOProductDictionary) ──────────
PRODUCT_INDICATOR_ITEMS = [
    "A - APB Rider",
    "B - ANICO ROP Rider",
    "C - ANTEX Modified DB",
    "D - ANTEX Graded DB",
    "E - ANTEX Level DB",
    "G - Graded Benefit Life",
    "P - Converted FFL PUAR",
    "R - GSL ROP",
    "S - Single Premium ISWL",
    "U - Converted FFL UL",
    "X - Index UL",
]

# ── State ────────────────────────────────────────────────────────────────
STATE_ITEMS = [
    "AL", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA",
    "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM",
    "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD",
    "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "AK",
    "HI", "PR", "AS", "MP", "VI", "GU",
]

# ── Bill Mode (01) ──────────────────────────────────────────────────────
BILL_MODE_ITEMS = [
    "Monthly",
    "Quarterly",
    "Semiannual",
    "Annual",
    "BiWeekly",
    "SemiMonthly",
    "9thly",
    "10thly",
]

# ── Last Entry Code (01) ────────────────────────────────────────────────
LAST_ENTRY_CODE_ITEMS = [
    "A - New Business (not paid for)",
    "B - Normal entry to file",
    "C - Active policy record",
    "D - Correction entry to database",
    "J - Termination - no pol exhibit",
    "L - Termination - death claim",
    "M - Termination - maturity",
    "N - Termination - expiration",
    "O - Termination - conversion",
    "P - Termination - surrender",
    "Q - Termination - lapse",
    "R - Termination - RPU/ETI",
    "X - Termination - free look",
]

# ── Billing Form (01) ───────────────────────────────────────────────────
BILLING_FORM_ITEMS = [
    "0 - Direct pay notice",
    "G - PAC",
    "H - Salary deduction",
    "F - Government allotment",
    "4 - Discount prem deposit",
]

# ── Grace Indicator (51 or 66) ──────────────────────────────────────────
GRACE_INDICATOR_ITEMS = [
    "0 - Not In Grace",
    "1 - In Grace",
]

# ── Suspense Code (01) ──────────────────────────────────────────────────
SUSPENSE_CODE_ITEMS = [
    "0 - Active",
    "1 - Not used",
    "2 - Suspended",
    "3 - Death claim pending",
]

# ── Company Combobox ────────────────────────────────────────────────────
COMPANY_ITEMS = ["", "01 - ANICO", "04 - ANTEX", "06 - SLAICO", "08 - Garden State", "26 - ANICONY"]

# ── Market Org Combobox ─────────────────────────────────────────────────
MARKET_ORG_ITEMS = ["", "MLM", "CSSD", "IMG", "DIRECT"]

# ── Region Combobox ─────────────────────────────────────────────────────
REGION_ITEMS = ["CKPR", "CKMO", "CKAS", "CKSR"]

# ── System Code Combobox ────────────────────────────────────────────────
SYSTEM_CODE_ITEMS = ["", "I", "P"]

# ── Policynumber criteria Combobox ──────────────────────────────────────
POLICYNUMBER_CRITERIA_ITEMS = ["Starts with", "Ends with", "Contains"]
