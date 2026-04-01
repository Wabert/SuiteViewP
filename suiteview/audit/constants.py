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

# ── Loan Type (01) ──────────────────────────────────────────────────────
LOAN_TYPE_ITEMS = [
    "0 - Advance, fixed",
    "1 - Arrears, fixed",
    "6 - Advance, variable",
    "7 - Arrears - Variable",
    "9 - Loans not allowed",
]

# ── Trad Overloan Ind (01) ──────────────────────────────────────────────
TRAD_OVERLOAN_IND_ITEMS = [
    "0 - FALSE",
    "1 - TRUE",
]

# ── Non Trad Indicator (02) ─────────────────────────────────────────────
NON_TRAD_INDICATOR_ITEMS = [
    "0 - Trad",
    "1 - Advanced",
]
# ── Definition of Life Insurance (66) ─────────────────────────────────────────
DEFINITION_OF_LIFE_ITEMS = [
    "1 - TEFRA GP",
    "2 - DEFRA GP",
    "3 - DEFRA CVAT",
    "4 - GP Selected",
    "5 - CVAT Selected",
]

# ── Reinsurance Code ──────────────────────────────────────────────────────────
REINSURANCE_CODE_ITEMS = [
    "  - none (space)",
    "F - Facultative",
    "A - Administrative",
    "N - ",
    "1 - Partial Reinsurance",
    "2 - Multiple Cov Reinsured",
]

# ── Scheduled Loan Payment (20) ────────────────────────────────────────────────
STANDARD_LOAN_PAYMENT_ITEMS = [
    "0 - Direct pay notice",
    "G - PAC",
    "H - Salary deduction",
    "F - Government allotment",
    "4 - Discount prem deposit",
]

# ── Has Change Seq (68) — 68 Segment Change Codes ────────────────────────────
CHANGE_SEQ_68_ITEMS = [
    "1 - Plan option change A to B or B to A",
    "2 - Planned periodic premium change",
    "3 - Specified amount increase",
    "4 - Specified amount decrease",
    "5 - Rate class",
    "6 - Mode change, fixed premium products only",
    "7 - Automatic increase, the result of a cost of living benefit",
    "8 - Variable loan interest change.",
    "9 - Termination data.",
    "A - Plan rerating.",
    "B - Sex code change.",
    "C - Band code change.",
    "D - Internal decrease in specified amount.",
    "E - RMD payout/calculation rule change.",
    "F - Policy fee (EIL only).",
    "G - Fund restriction (variable funds only).",
    "H - Long term care/dread disease monthliversary decrease.",
    "I - Element structure change.",
    "J - Bonus type change.",
    "L - Lump sum deposit or unscheduled payment (proposals only).",
    "O - Plan option change other than A to B or B to A.",
    "P - Benefit/elimination period change (A&H).",
    "Q - Loan repayment.",
    "R - Re-entry term.",
    "S - Mortality and expense (M&E) band change.",
    "T - Remaining lifetime benefit change (LTC only).",
    "U - Maturity date extension.",
    "Z - Set up reoccuring payments",
]

# ── Init Term Period (02) ─────────────────────────────────────────────────────
INIT_TERM_PERIOD_ITEMS = [
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
    "30", "65", "70", "85", "90", "99", "100", "121",
]

# =============================================================================
# COVERAGES TAB
# =============================================================================

# ── Mortality Table Codes ─────────────────────────────────────────────────────
MORTALITY_TABLE_CODE_ITEMS = [
    "# - 2001CSO SM/NS",
    "## - 01CSO/COMPOSITE",
    "#1 - PRF 2001 S&U",
    "#2 - 2017CSO ULT",
    "#3 - 2017CSO COMPS",
    "#4 - 2017CSO COMPU",
    "#5 - 2017CSO SM/NS",
    "#6 - 2017CSO SM/NU",
    "#7 - PRF 2017 S&U",
    "#8 - PRF 2017 ULT",
    "$ - 2001CSO COMPU",
    "% - 80 CSO COMP",
    "@ - 80 CSO SMKR/N",
    "* - 1949 A FEMALE",
    "** - 1949 A FEMALE",
    "0 - OLD JOINT LIF",
    "A - 1926 CL 3 AE  A",
    "J - PROG ANNUITY  J",
    "K - A/E CRAIG     K",
    "L - A/E BUTTOLPH  L",
    "M - AMERICAN MEN  M",
    "N - 1941 CSO      N",
    "O - 1958 CSO MALE O",
    "P - 1958 CSO FEM  P",
    "S - 1958 CSO MLX  S",
    "T - 1958 CSO FLX  T",
    "4B - 1941 SI ALB",
    "4D - 41 130%SI ANB",
    "4E - 1961 CSI  ALB",
    "4F - 1949 A FEMALE",
    "4G - 1941 SI ANB",
    "4I - 1941 SSI ANB",
    "4J - 1961 CSI ANB",
    "LA - 80 CETMNS ALB",
    "LC - 2001CSOMNS LS",
    "LD - 2001CSOFNS LS",
    "LF - 2001CSOMS L S",
    "LG - 2001CSOFS L S",
    "LJ - 80 CSOJT ALB",
    "LK - 2001CSOMNS LU",
    "LL - 2001CSOFNS LU",
    "LN - 2001CSOMS L U",
    "LO - 2001CSOFS L U",
    "LP - 2001CSOM L  U",
    "LQ - 2001CSOF L  U",
    "L0 - 80 CSOMNS ALB 0",
    "L1 - 80 CSOFNS ALB 1",
    "L2 - 80 CSOMS ALB  2",
    "L3 - 80 CSOFS ALB  3",
    "L4 - 80 CSOM ALB   4",
    "L5 - 80 CSOF ALB   5",
    "L6 - 80 CETMS ALB  6",
    "NC - 2001CSOMNS NS",
    "ND - 2001CSOFNS NS",
    "NF - 2001CSOMS N S",
    "NG - 2001CSOFS N S",
    "NJ - 80 CSOJT ANB",
    "NK - 2001CSOMNS NU",
    "NL - 2001CSOFNS NU",
    "NN - 2001CSOMS N U",
    "NO - 2001CSOFS N U",
    "NP - 2001CSOM N  U",
    "NQ - 2001CSOF N  U",
    "N0 - 80 CSOMNS ANB",
    "N1 - 80 CSOFNS ANB",
    "N2 - 80 CSOMS ANB",
    "N3 - 80 CFOFS ANB",
    "N4 - 80 CSOM ANB",
    "N5 - 80 CSOF ANB",
    "UA - 80CSO US ALB",
    "UC - 2001CSO US LS",
    "UE - 2001CSO UN NS",
    "UF - 2001CSO US NS",
    "UH - 2001CSO UN LS",
    "UK - 2001CSO US LU",
    "UM - 2001CSO UN NU",
    "UN - 2001CSO US NU",
    "UO - 2001CSOC80/20",
    "UP - 2001CSO UN LU",
    "UR - 80CSONSU40",
    "US - 80CSOSKU40",
    "UX - 2001CSOC40/60",
    "U0 - 80CSO-E ANB",
    "U2 - 80CSO UN ANB",
    "U4 - 80CSO US ANB",
    "U6 - 80CSO U ALB",
    "U8 - 80CSO UN ALB",
]

# ── Sex Code (02) ─────────────────────────────────────────────────────────────
SEX_CODE_02_ITEMS = [
    "1 - Male",
    "2 - Female",
    "3 - Joint",
]

# ── Sex Code (67) ─────────────────────────────────────────────────────────────
SEX_CODE_67_ITEMS = [
    "1 - Male",
    "2 - Female",
    "3 - Unisex",
    "M - Male",
    "F - Female",
    "U - Unisex",
]

# ── Rateclass Code (67) ──────────────────────────────────────────────────────
RATECLASS_67_ITEMS = [
    "A - nonsmoker",
    "B - smoker",
    "D - preferred",
    "E - non tobacco pref best",
    "F - non tobacco pref plus",
    "G - non tobacco preferred",
    "H - non tobacco standard",
    "I - tobacco preferred",
    "J - standard",
    "K - nonsmoker or tobacco standard",
    "L - guaranteed issue",
    "N - nicotine non user",
    "P - Preferred nonsmoker",
    "Q - Preferred smoker",
    "R - Preferred Plus nonsmoker",
    "S - Standard nicotine user",
    "T - Standard plus nicotine non user",
    "V - Standard",
    "X - Substandard",
    "Y - Substandard plus",
    "Z - Substandard best",
    "0 - rates do not vary by class",
]

# ── Lives Covered Code (02) ──────────────────────────────────────────────────
LIVES_COVERED_ITEMS = [
    "0 - Proposed Insured or Joint Insureds",
    "1 - Proposed insured, spouse, and dependents",
    "2 - Spouse and dependents",
    "3 - Single dependents",
    "4 - Proposed insured, spouse, and dependents",
    "5 - Spouse and dependents",
    "6 - Dependents only",
    "7 - Proposed insured and dependents",
    "8 - Proposed insured and dependents",
    "A - Family medical expense",
]

# ── Change Type (02) ─────────────────────────────────────────────────────────
CHANGE_TYPE_02_ITEMS = [
    "0 - Terminated",
    "1 - Paid Up",
    "2 - Prem paying",
]

# ── COLA Ind ──────────────────────────────────────────────────────────────────
COLA_IND_ITEMS = ["", "0", "1"]

# ── GIO/FIO ───────────────────────────────────────────────────────────────────
GIO_FIO_ITEMS = ["", "N", "Y"]

# ── Covered Person ────────────────────────────────────────────────────────────
PERSON_ITEMS = [
    "",
    "00 - Insured or primary insured",
    "01 - Joint insured",
    "40 - Spouse",
    "50 - Dependent",
    "60 - Other",
]

# ── Additional Plancode Criteria ──────────────────────────────────────────────
ADDL_PLANCODE_ITEMS = [
    "",
    "1 - Same as base",
    "2 - Different than base",
]

# =============================================================================
# ADV TAB
# =============================================================================

# ── Grace Period Rule Code (66) ───────────────────────────────────────────────
GRACE_PERIOD_RULE_CODE_ITEMS = [
    "C - Unloaned CV < 0.",
    "S - SV < 0.",
    "N - Adjusted Prem < MAP.  Then Rule S.",
    "R - Adjusted Prem < MAP AND Unloaned CV < 0.  Then rule C.",
    "T - Adjusted Prem < MAP AND SV < 0.  Then Rule S.",
]

# ── Death Benefit Option (66) ─────────────────────────────────────────────────
DEATH_BENEFIT_OPTION_ITEMS = [
    "1 - Level(A)",
    "2 - Increasing(B)",
    "3 - Return Of Prem(C)",
]

# ── Orig Entry Code (01) ─────────────────────────────────────────────────────
ORIG_ENTRY_CODE_ITEMS = [
    "A - New business",
    "B - Group conversion",
    "C - Block reinsurance",
    "D - Reinstatement",
    "E - Exchange or conversion with a new policy number assigned",
    "F - Exchange or conversion retaining the original policy number",
    "G - Policy change",
    "H - Advanced product complex change",
    "Z - Old life business converted to the system",
]

# ── IUL Only — Premium Allocation Funds (57) ─────────────────────────────────
PREMIUM_ALLOCATION_FUND_ITEMS = [
    "IC - Index 1 yr PTP with 1.5% and Cap",
    "IF - Index 1 yr PTP uncapped with fee",
    "IS - Index 1 yr PTP with Specified Rate",
    "IX - Index 1 yr PTP with Cap",
    "IP - Index with Multiplier",
    "IR - Index with high Multiplier",
    "NX - NASDAQ100",
    "M1 - SPMARC5",
    "U1 - Fixed Fund",
]

# =============================================================================
# WL TAB
# =============================================================================

# ── Primary / Secondary Dividend Option (01) ─────────────────────────────────
DIVIDEND_OPTION_ITEMS = [
    "0 - Non Participating",
    "1 - Cash",
    "2 - Premium reduction",
    "3 - Deposit at interest",
    "4 - Paid-up additions",
    "5 - OYT",
    "6 - OYT. Limit CV",
    "7 - OYT. Limit Face",
    "8 - Loan reduction",
    "9 - No further values",
    "D - OYT. Other",
]

# ── NFO Code (01) ────────────────────────────────────────────────────────────
NFO_CODE_ITEMS = [
    "0 - No cash value",
    "1 - APL-->ETI",
    "2 - APL-->RPU",
    "3 - APL",
    "4 - ETI",
    "5 - RPU",
    "9 - Special Other",
]

# =============================================================================
# DI TAB
# =============================================================================

# ── Benefit Period Code (02) — Accident ──────────────────────────────────────
BENEFIT_PERIOD_ACCIDENT_ITEMS = ["B", "E", "F", "G", "J", "L", "R", "S", "X"]

# ── Benefit Period Code (02) — Sickness ──────────────────────────────────────
BENEFIT_PERIOD_SICKNESS_ITEMS = ["B", "E", "F", "G", "J", "L", "R", "S", "X"]

# ── Elimination Period Code (02) — Accident ──────────────────────────────────
ELIM_PERIOD_ACCIDENT_ITEMS = ["0", "1", "2", "3", "4", "5", "6", "7", "9"]

# ── Elimination Period Code (02) — Sickness ──────────────────────────────────
ELIM_PERIOD_SICKNESS_ITEMS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]

# =============================================================================
# BENEFITS TAB
# =============================================================================

# ── Benefit Type (04) ────────────────────────────────────────────────────────
BENEFIT_TYPE_ITEMS = [
    "",
    "1 - ADB",
    "2 - ADnD",
    "3 - PWoC",
    "4 - PWoT",
    "7 - GIO",
    "9 - PPB",
    "# - ABR",
    "A - CCV",
    "U - COLA",
    "B - LTC",
    "V - GCO",
]

# ── Benefit Cease Date Status (04) ───────────────────────────────────────────
BENEFIT_CEASE_STATUS_ITEMS = [
    "",
    "1 - Cease Dt = Orig Cease Dt",
    "2 - Cease Dt < Orig Cease Dt",
    "3 - Cease Dt > Orig Cease Dt",
]

# =============================================================================
# TRANSACTION TAB
# =============================================================================

# ── Transaction Type and Subtype — imported from PolView TRANSACTION_CODES ───
def _build_transaction_items() -> list[str]:
    from suiteview.polview.models.cl_polrec.policy_translations import TRANSACTION_CODES
    return [f"{k} - {v}" for k, v in TRANSACTION_CODES.items()]

TRANSACTION_TYPE_ITEMS: list[str] = _build_transaction_items()