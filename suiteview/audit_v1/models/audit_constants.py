"""
Audit Tool Constants
=====================
Lookup dictionaries and code translation tables specific to the audit tool.

Re-exports shared constants from polview.models.policy_constants and adds
audit-specific ones (product indicators, lives covered, state codes, etc.).

These mirror the VBA dictionaries from frmAudit.frm PopulateForm().
"""

# ── Re-export shared constants from PolView ─────────────────────────────
from suiteview.polview.models.cl_polrec.policy_translations import (
    STATUS_CODES,
    PREMIUM_PAY_STATUS_CODES,
    SUSPENSE_CODES,
    PRODUCT_LINE_CODES,
    SEX_CODES,
    RATE_CLASS_CODES,
    BILLING_MODE_CODES,
    NON_STANDARD_BILL_MODE_CODES,
    DEF_OF_LIFE_INS_CODES,
    DB_OPTION_CODES,
    DIV_OPTION_CODES,
    NFO_CODES,
    PERSON_CODES,
    COMPANY_CODES,
    NXT_CHG_TYP_CODES,
    LOAN_TYPE_CODES,
    LAST_ENTRY_CODES,
    BENEFIT_TYPE_CODES,
    GRACE_RULE_CODES,
    BILL_FORM_CODES,
)


# =============================================================================
# AUDIT-SPECIFIC CONSTANTS (not in PolView)
# =============================================================================

# ANICO Product Indicator codes (ANICOProductDictionary in VBA)
PRODUCT_INDICATOR_CODES = {
    "01": "Whole Life",
    "02": "Endowment",
    "03": "Term",
    "04": "Annuity",
    "05": "Paid Up Additions",
    "06": "One Year Term",
    "07": "Interest Sensitive Whole Life",
    "08": "Current Assumption Whole Life",
    "09": "Universal Life",
    "10": "Variable Universal Life",
    "11": "Indexed Universal Life",
    "12": "Disability Income",
    "99": "Other",
}

# Lives Covered codes (VBA LivesCoveredDictionary)
LIVES_COVERED_CODES = {
    "0": "Proposed Insured or Joint Insureds",
    "1": "Proposed insured, spouse, and dependents",
    "2": "Spouse and dependents",
    "3": "Single dependents",
    "4": "Proposed insured, spouse, and dependents",
    "5": "Spouse and dependents",
    "6": "Dependents only",
    "7": "Proposed insured and dependents",
    "8": "Proposed insured and dependents",
    "A": "Family medical expense",
}

# Mortality Table codes (VBA MortalityTableDictionary)
MORTALITY_TABLE_CODES = {
    "#": "2001CSO SM/NS",
    "@": "80 CSO SMKR/N",
    "A": "1926 CL 3 AE  A",
    "J": "PROG ANNUITY  J",
    "K": "A/E CRAIG     K",
    "L": "A/E BUTTOLPH  L",
    "M": "AMERICAN MEN  M",
    "N": "1941 CSO      N",
    "O": "1958 CSO MALE O",
    "P": "1958 CSO FEM  P",
    "S": "1958 CSO MLX  S",
    "T": "1958 CSO FLX  T",
    "0": "OLD JOINT LIF",
    "$": "2001CSO COMPU",
    "*": "1949 A FEMALE",
    "**": "1949 A FEMALE",
    "LA": "80 CETMNS ALB",
    "LC": "2001CSOMNS LS",
    "LD": "2001CSOFNS LS",
    "LF": "2001CSOMS L S",
    "LG": "2001CSOFS L S",
    "LJ": "80 CSOJT ALB",
    "LK": "2001CSOMNS LU",
    "LL": "2001CSOFNS LU",
    "LN": "2001CSOMS L U",
    "LO": "2001CSOFS L U",
    "LP": "2001CSOM L  U",
    "LQ": "2001CSOF L  U",
    "L0": "80 CSOMNS ALB 0",
    "L1": "80 CSOFNS ALB 1",
    "L2": "80 CSOMS ALB  2",
    "L3": "80 CSOFS ALB  3",
    "L4": "80 CSOM ALB   4",
    "L5": "80 CSOF ALB   5",
    "L6": "80 CETMS ALB  6",
    "NC": "2001CSOMNS NS",
    "ND": "2001CSOFNS NS",
    "NF": "2001CSOMS N S",
    "NG": "2001CSOFS N S",
    "NJ": "80 CSOJT ANB",
    "NK": "2001CSOMNS NU",
    "NL": "2001CSOFNS NU",
    "NN": "2001CSOMS N U",
    "NO": "2001CSOFS N U",
    "NP": "2001CSOM N  U",
    "NQ": "2001CSOF N  U",
    "NW": "",
    "NX": "",
    "N0": "80 CSOMNS ANB",
    "N1": "80 CSOFNS ANB",
    "N2": "80 CSOMS ANB",
    "N3": "80 CFOFS ANB",
    "N4": "80 CSOM ANB",
    "N5": "80 CSOF ANB",
    "P1": "",
    "UA": "80CSO US ALB",
    "UC": "2001CSO US LS",
    "UE": "2001CSO UN NS",
    "UF": "2001CSO US NS",
    "UH": "2001CSO UN LS",
    "UK": "2001CSO US LU",
    "UM": "2001CSO UN NU",
    "UN": "2001CSO US NU",
    "UO": "2001CSOC80/20",
    "UP": "2001CSO UN LU",
    "UR": "80CSONSU40",
    "US": "80CSOSKU40",
    "UX": "2001CSOC40/60",
    "U0": "80CSO-E ANB",
    "U2": "80CSO UN ANB",
    "U4": "80CSO US ANB",
    "U6": "80CSO U ALB",
    "U8": "80CSO UN ALB",
    "4B": "1941 SI ALB",
    "4D": "41 130%SI ANB",
    "4E": "1961 CSI  ALB",
    "4F": "1949 A FEMALE",
    "4G": "1941 SI ANB",
    "4I": "1941 SSI ANB",
    "4J": "1961 CSI ANB",
}

# State codes for the State listbox (VBA TranslateStateCodeToText)
# Maps 2-letter abbreviation to Cyberlife state number (used in SQL WHERE)
# NOTE: These are Cyberlife internal codes, NOT standard FIPS codes.
STATE_CODES = {
    "AL": "01", "AZ": "02", "AR": "03", "CA": "04", "CO": "05",
    "CT": "06", "DE": "07", "DC": "08", "FL": "09", "GA": "10",
    "ID": "11", "IL": "12", "IN": "13", "IA": "14", "KS": "15",
    "KY": "16", "LA": "17", "ME": "18", "MD": "19", "MA": "20",
    "MI": "21", "MN": "22", "MS": "23", "MO": "24", "MT": "25",
    "NE": "26", "NV": "27", "NH": "28", "NJ": "29", "NM": "30",
    "NY": "31", "NC": "32", "ND": "33", "OH": "34", "OK": "35",
    "OR": "36", "PA": "37", "RI": "38", "SC": "39", "SD": "40",
    "TN": "41", "TX": "42", "UT": "43", "VT": "44", "VA": "45",
    "WA": "46", "WV": "47", "WI": "48", "WY": "49", "AK": "50",
    "HI": "51", "PR": "52", "AS": "55", "MP": "60", "VI": "65",
    "GU": "66",
}

# Reverse map: Cyberlife number → state abbreviation (for display)
STATE_NUMBER_TO_ABBR = {v: k for k, v in STATE_CODES.items()}

# Market organization codes
MARKET_ORG_CODES = {
    "MLM": "Multi-Level Marketing",
    "CSSD": "Career Sales & Service Distribution",
    "IMG": "Independent Marketing Group",
    "DIRECT": "Direct",
}

# Region codes and DSNs (also in core.db2_constants, but listed here for UI)
REGIONS = ["CKPR", "CKMO", "CKAS", "CKSR"]

# Company codes for dropdown (with blank default)
COMPANY_LIST = ["", "01 - ANICO", "04 - ANTEX", "06 - SLAICO", "08 - Garden State", "26 - ANICONY"]

# System codes
SYSTEM_CODES = {
    "I": "Inforce",
    "P": "Pending",
}

# Transaction type categories (VBA GetTransactionTypeDictionary)
# Single-letter type that is the first character of the 2-char transaction code
TRANSACTION_TYPE_CATEGORIES = {
    "A": "Accounting",
    "B": "Policyowner Reward",
    "C": "Charge",
    "D": "Dread Disease",
    "E": "Exchange",
    "F": "Premium Fund Addition",
    "G": "Agent Ledger",
    "H": "Home health care",
    "I": "Interest/Internal",
    "L": "Loans",
    "M": "Miscellaneous",
    "N": "Withdrawal interest",
    "O": "Paid-up additions option",
    "P": "Premium payments/loan payments",
    "Q": "Automatic transactions",
    "R": "Refund",
    "S": "Surrenders",
    "T": "Terminations",
    "U": "Unapplied cash suspense",
    "W": "Waiver of Premium",
    "X": "Long term care",
    "Y": "User defined",
    "Z": "Forecast (only if subtype is A, C, G, P, S, or V)",
    "1": "Dividends earned - premium paying policies",
    "2": "Other forms of participation earned",
    "3": "Dividend values - on converted policies",
    "4": "Other participation on converted policies",
    "5": "Dividend processing - online",
    "6": "Other participation - online",
    "7": "Additions PUA and OYT - online",
    "8": "Pro rata dividends on withdrawal",
    "9": "Pro rata other forms on withdrawal",
}

# Transaction codes — type + subtype (VBA TranslateTransactionCodeToText)
TRANSACTION_CODES = {
    "A_": "Policyowner statement revision",
    "AA": "Policyowner statement automatic on anniversary",
    "AC": "Policyowner confirmation",
    "AF": "Policyowner statement off anniversary",
    "AL": "Lag/loss accounting",
    "AR": "Policyowner statement request prior 12 months",
    "AS": "Split accounting for the fixed fund portion when the exchange includes both fixed and variable funds.",
    "AY": "Policyowner statement request year-to-date",
    "B1": "Cost of Insurance",
    "B2": "Expenses",
    "B3": "Cost of insurance and expenses",
    "B4": "First year load",
    "B5": "Cash value",
    "B6": "Current interest",
    "B7": "Guaranteed interest",
    "BA": "Cost of insurance and expense reversal",
    "BB": "Current interest reversal (retrospective)",
    "BC": "Guaranteed interest reversal (prospective)",
    "CA": "Charge allocation (adjustment)",
    "CC": "Cumulative charge",
    "CD": "Charge deduction",
    "CY": "Calendar year expense charge",
    "DK": "Dread disease, expense charge",
    "DP": "Dread disease, claim payment",
    "EF": "Exchange from",
    "EK": "Exchange charge",
    "ET": "Exchange to",
    "FE": "Discounted premium",
    "FF": "Premium depositor fund",
    "GL": "Accounting",
    "GP": "External variable fund purchase",
    "GR": "External variable fund redemption",
    "HB": "Beginning payments",
    "HE": "Ending payment",
    "HP": "Claim payment",
    "HX": "Dread disease claim reduction",
    "HZ": "LTC/HHC claim reduction",
    "IA": "Dividends on deposit",
    "IB": "Other forms on deposit",
    "IC": "Accrued interest, loan payoff",
    "ID": "Death claims",
    "IE": "Discounted premiums",
    "IF": "Premium depositor fund",
    "IH": "Pro rata",
    "IL": "Lien payoffs",
    "IN": "Long term care/dread disease accumulated claims lien amount",
    "IP": "Loan payoff",
    "IR": "Accrued interest, lien payoff",
    "IT": "Dread disease lien interest",
    "IV": "Interest on discounted premium withdrawal",
    "IW": "Interest, premium depositor fund withdrawal",
    "LA": "Automatic premium loan",
    "LC": "Capitalized accrued loan interest",
    "LF": "Maximum preferred loan",
    "LG": "Gross loan request",
    "LM": "Maximum loan request",
    "LN": "Net loan request",
    "LP": "Loan principal reduction",
    "LV": "Capitalized advance loan interest",
    "LZ": "Premiums withheld from loans",
    "MA": "Accounting",
    "MS": "Moves money from the clearing account to the external clearing suspense account.",
    "N3": "Deposit at interest",
    "N4": "Interest on dividends on deposit at conversion to ETI/RPU",
    "NC": "Pro rata interest on new deposits",
    "ON": "ISL, paid-up additions option not elected",
    "OS": "Over/short",
    "OY": "ISL, elect paid-up additions option",
    "P6": "Current value adjustment for payments and surrenders",
    "P7": "Annuitization account value adjustment increase",
    "P8": "Excess interest",
    "PA": "Additional (or unscheduled) premium payment",
    "PB": "Reinstatement payment",
    "PC": "Loan/lien interest (accrued)",
    "PD": "Automatic payment, PDF",
    "PE": "Automatic payment, discounted premium",
    "PF": "Initial internal rollover payment",
    "PI": "Initial premium payment",
    "PK": "Premium load",
    "PL": "Loan/lien payment",
    "PM": "Payment from dividends and PUAs",
    "PN": "Premium payment by automatic premium loan",
    "PO": "Premium or loan/lien payoff overage",
    "PP": "Loan/lien payoff",
    "PQ": "Automatic payment, AP fixed premium",
    "PR": "Regular (or scheduled) premium payment",
    "PS": "Premium or loan/lien payoff shortage",
    "PT": "Rollover additional",
    "PU": "Reinstatement value",
    "PV": "Advance loan interest payment",
    "PW": "Premium Waiver",
    "PX": "Loan/lien interest payment",
    "PZ": "Premium tax calculation",
    "QA": "Automatic transaction, annuitization",
    "QD": "Automatic transactions, automatic disbursement",
    "QG": "Automatic transactions, initial gain",
    "QI": "Automatic transactions, initial refresh",
    "QR": "Automatic transactions, automatic refresh",
    "QV": "Automatic transactions, fund value quote",
    "QX": "Equity index increase",
    "RC": "Refund of cash value, face amount decrease",
    "RD": "Refund of premium, face amount decrease",
    "RI": "Reinstatement interest",
    "RP": "RPU refund excess",
    "S4": "Paid-up additions partial surrender",
    "S5": "One year term additions partial surrender",
    "S6": "Current value withdrawal",
    "S7": "Annuitization account value adjustment decrease",
    "S8": "Fund optimization fee",
    "SA": "Excess accumulation withdrawal",
    "SB": "Fund optimization fee",
    "SC": "Surrender, conversion",
    "SD D": "Premiums due on death claim",
    "SF": "Full surrender",
    "SG": "Surrenders, gross withdrawal request",
    "SH": "Surrenders, home/custodial care claim payment",
    "SI": "Internal surrender",
    "SJ": "Forced lapse",
    "SK": "Surrender charge",
    "SL": "Free look",
    "SM": "Maximum withdrawal",
    "SN": "Net withdrawal",
    "SP": "Purchase paid-up additions",
    "SR": "Refunded premium on surrender",
    "ST": "TSA loan repayment surrender",
    "SV": "Discounted premium withdrawal",
    "SW": "Premium depositor fund withdrawal",
    "SX": "Reversal of premium waiver for death claims and surrenders.",
    "T9": "Policy level surrender or termination",
    "TB": "Beneficiary payout, surrender or termination",
    "TD": "Death claim, primary insured",
    "TE": "Extended term",
    "TF": "Fully paid-up conversion",
    "TL": "Lapse",
    "TM": "Maturity",
    "TN": "Expiry",
    "TO": "Other insured death claim",
    "TR": "Reduced paid-up",
    "TV": "Lapse, daily cost basis",
    "TZ": "Premium tax",
    "UI R": "Unapplied cash in, returned item",
    "UI": "Unapplied cash suspense in",
    "UO": "Unapplied cash suspense out",
    "UP": "Unmatched payment - batch",
    "WO": "Waiver of premium off",
    "WP": "Waiver of premium on",
    "XB": "Long term care, beginning payments",
    "XE": "Long term care, ending payments",
    "XP": "Long term care, claim payment",
    "Y0": "User defined",
    "ZA": "Forecasts, annual projection",
    "ZC": "Forecasts, current premium solve for target cash surrender value",
    "ZG": "Forecasts, guaranteed premium solve for target cash surrender value",
    "ZN": "Vanishing (offset) premium request - NVP",
    "ZP": "Forecasts, current projection",
    "ZR": "Vanishing (offset) premium request - APP",
    "ZS": "Forecasts, premium solve",
    "ZV": "Forecasts, vanishing (offset) premium",
    "ZZ": "Suppress check special accounting.",
}

# 68-segment change codes (VBA ChangeCodeArray)
CHANGE_CODES_68 = {
    "1": "Plan option change A to B or B to A",
    "2": "Planned periodic premium change",
    "3": "Specified amount increase",
    "4": "Specified amount decrease",
    "5": "Rate class",
    "6": "Mode change, fixed premium products only",
    "7": "Automatic increase, the result of a cost of living benefit",
    "8": "Variable loan interest change.",
    "9": "Termination data.",
    "A": "Plan rerating.",
    "B": "Sex code change.",
    "C": "Band code change.",
    "D": "Internal decrease in specified amount.",
    "E": "RMD payout/calculation rule change.",
    "F": "Policy fee (EIL only).",
    "G": "Fund restriction (variable funds only).",
    "H": "Long term care/dread disease monthliversary decrease.",
    "I": "Element structure change.",
    "J": "Bonus type change.",
    "L": "Lump sum deposit or unscheduled payment (proposals only).",
    "O": "Plan option change other than A to B or B to A.",
    "P": "Benefit/elimination period change (A&H).",
    "Q": "Loan repayment.",
    "R": "Re-entry term.",
    "S": "Mortality and expense (M&E) band change.",
    "T": "Remaining lifetime benefit change (LTC only).",
    "U": "Maturity date extension.",
    "Z": "Set up reoccuring payments",
}

# Premium allocation fund IDs for IUL policies
IUL_FUND_CODES = {
    "IC": "Index 1yr PTP with 1.5% and Cap",
    "IF": "Index 1yr PTP uncapped with fee",
    "IS": "Index 1yr PTP with Specified Rate",
    "IX": "Index 1yr PTP with Cap",
    "IP": "Index with Multiplier",
    "IR": "Index with high Multiplier",
    "NX": "NASDAQ100",
    "M1": "SPMARC5",
    "U1": "Fixed Fund",
}

# Reinsurance codes
REINSURANCE_CODES = {
    " ": "none (space)",
    "F": "Facultative",
    "A": "Administrative",
    "N": "",
    "1": "Partial Reinsurance",
    "2": "Multiple Cov Reinsured",
}

# Billing form codes for audit (VBA TranslateBillFormCode)
AUDIT_BILLING_FORMS = {
    "0": "Direct pay notice",
    "1": "Home office",
    "A": "Home office",
    "2": "Permanent APL",
    "B": "Permanent APL",
    "3": "Premium depositor fund",
    "C": "Premium depositor fund",
    "4": "Discounted premium deposit",
    "6": "Government allotment",
    "F": "Government allotment",
    "7": "PAC",
    "G": "PAC",
    "8": "Salary deduction",
    "H": "Salary deduction",
    "9": "Bank deduction",
    "I": "Bank deduction",
    "J": "Dividend",
    "Q": "Permanent APP",
    "V": "Net vanish (offset) premium",
}

# Billing mode codes (VBA TranslateBillModeCodeToText)
# Mode is determined by bill mode code + non-standard mode code
BILL_MODE_DISPLAY = {
    "1": "M - Monthly",
    "3": "Q - Quarterly",
    "6": "S - SemiAnnually",
    "12": "A - Annually",
}

# Non-standard mode overrides for mode code "1"
# "2" with mode "1" → BiWeekly, "S" with mode "1" → SemiMonthly
NON_STANDARD_MODE_DISPLAY = {
    "1": "Weekly",
    "2": "B - BiWeekly",
    "4": "13thly (every 4 weeks)",
    "9": "9thly",
    "A": "10thly",
    "S": "SM - SemiMonthly",
}

# Grace period indicator
GRACE_INDICATOR_CODES = {
    "0": "Not in Grace",
    "1": "In Grace",
}

# Overloan indicator
OVERLOAN_INDICATOR_CODES = {
    "0": "FALSE",
    "1": "TRUE",
}

# Non-traditional indicator
NON_TRAD_INDICATOR_CODES = {
    "0": "Traditional",
    "1": "Advanced Product (UL/VUL/IUL)",
}

# Standard Loan Payment (20) — SLR billing form codes
STANDARD_LOAN_PAYMENT_CODES = {
    "0": "Direct pay notice",
    "G": "PAC",
    "H": "Salary deduction",
    "F": "Government allotment",
    "4": "Discount prem deposit",
}

# Policy number search patterns
POLICY_NUMBER_CRITERIA = {
    "1": "Starts with",
    "2": "Ends with",
    "3": "Contains",
}

# Rider change type codes
RIDER_CHANGE_TYPES = {
    "0": "Terminated",
    "1": "Paid Up",
    "2": "Premium paying",
}

# Benefit cease date comparison
BENEFIT_CEASE_DATE_STATUS = {
    "1": "Cease Dt = Original Cease Dt",
    "2": "Cease Dt < Original Cease Dt",
    "3": "Cease Dt > Original Cease Dt",
}

# Rider additional plancode criteria
RIDER_PLANCODE_CRITERIA = {
    "1": "Same as base",
    "2": "Different than base",
}

# Sex codes for 02 segment
SEX_CODES_02 = {
    "1": "Male",
    "2": "Female",
    "3": "Joint",
}

# Elimination period codes for A&H (accident) — codes only, no descriptions in VBA
ELIMINATION_PERIOD_ACCIDENT = {
    "0": "0", "1": "1", "2": "2", "3": "3",
    "4": "4", "5": "5", "6": "6", "7": "7",
    "9": "9",
}

# Elimination period codes for A&H (sickness) — codes only
ELIMINATION_PERIOD_SICKNESS = {
    "0": "0", "1": "1", "2": "2", "3": "3",
    "4": "4", "5": "5", "6": "6", "7": "7",
    "8": "8", "9": "9",
}

# Benefit period codes for A&H — codes only
BENEFIT_PERIOD_CODES = {
    "B": "B", "E": "E", "F": "F",
    "G": "G", "J": "J", "L": "L",
    "R": "R", "S": "S", "X": "X",
}

# Initial term renewal periods (for listbox)
INITIAL_TERM_PERIODS = [
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
    "30", "65", "70", "85", "90", "99", "100", "121",
]

# Last entry codes for listbox (abbreviated set used in audit)
AUDIT_LAST_ENTRY_CODES = {
    "A": "Entry-New Bus Not Paid For",
    "B": "Normal Entry",
    "C": "Active Record",
    "D": "Correction Entry",
    "E": "Replacement",
    "F": "Replacement with Exhibits",
    "J": "Term - No Exhibits",
    "K": "Term - With Exhibits",
    "L": "Term - Death Claim",
    "M": "Term - Maturity",
    "N": "Term - Expiration",
    "O": "Term - Conversion",
    "P": "Term - Surrender",
    "Q": "Term - Lapse",
    "R": "Term - RPU/ETI",
    "X": "Term - Free Look",
}

# DB2 table prefix
DB2_SCHEMA = "DB2TAB"


# =============================================================================
# SQL CASE expression for state code translation (50 states → 2-letter abbr)
# Used in SELECT clause to translate ISS_STA_CD to state abbreviation
# =============================================================================

# Company codes valid for each market org (used for SQL filtering)
COMPANY_MARKET_ORG_MAP = {
    "CSSD": ["01"],
    "IMG": ["01", "26"],
    "MLM": ["01", "26"],
    "DIRECT": ["01", "26"],
    "GSL": ["08"],
    "ANTEX": ["04"],
    "SLAICO": ["06"],
}

# Market org → first-character agent code mapping (VBA)
MARKET_ORG_AGENT_CODES = {
    "MLM": "1",
    "CSSD": "2",
    "IMG": "7",
    "DIRECT": "D",
}


def build_state_case_expression(table_alias: str = "POLICY1") -> str:
    """Build a SQL CASE expression to translate Cyberlife state numbers to abbreviations."""
    cases = []
    for abbr, num in STATE_CODES.items():
        cases.append(f"WHEN {table_alias}.POL_ISS_ST_CD = '{num:>02}' THEN '{abbr}'")
    case_expr = " ".join(cases)
    return f"CASE {case_expr} ELSE {table_alias}.POL_ISS_ST_CD END"
