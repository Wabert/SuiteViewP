"""
Policy Translations & Constants
================================
Single source of truth for all code-to-description lookup tables
and translation functions used by CL_POLREC record modules.

Merged from:
- policy_constants.py  (lookup dictionaries)
- policy_translations.py  (translation functions)
"""

from __future__ import annotations

from enum import Enum


# =============================================================================
# CONFIGURATION
# =============================================================================

class Region(str, Enum):
    """Database region codes."""
    CKPR = "CKPR"  # Production
    CKMO = "CKMO"  # Model Office
    CKAS = "CKAS"  # Acceptance/Test
    CKSR = "CKSR"  # System Region
    CKCS = "CKCS"  # Cybertek


# =============================================================================
# STATUS / SUSPENSE
# =============================================================================

STATUS_CODES = {
    "10": "Active",
    "14": "Active – Disability Waiver",
    "15": "Active – Pending Policy Loan",
    "20": "Suspended",
    "25": "Pending Death Claim",
    "30": "Pending Surrender",
    "35": "Pending Maturity",
    "40": "Surrendered",
    "45": "Reduced Paid-Up",
    "46": "Extended Term Insurance",
    "50": "Lapsed – No Cash Value",
    "55": "Lapsed – With Cash Value",
    "60": "Matured",
    "65": "Death Claim Paid",
    "70": "Rescinded/Voided",
    "75": "Not Taken",
    "80": "Free Look Refund",
    "85": "Converted",
    "90": "Expired",
    "95": "Replacement",
}

SUSPENSE_CODES = {
    "0": "None",
    "1": "Admin Hold",
    "2": "Premium Notice",
    "3": "Death Claim Pending",
    "4": "Surrender Pending",
    "5": "Maturity Pending",
    "6": "Lapse Pending",
    "7": "Loan Processing",
    "8": "Policy Change Pending",
    "9": "Investigation",
}

PREMIUM_PAY_STATUS_CODES = {
    "11": "Pending applications",
    "12": "No Init Premium Yet",
    "21": "Premium Paying (at issue)",
    "22": "Premium Paying",
    "31": "Payor Death",
    "32": "Waiver of Premium",
    "33": "Waiver of Charges",
    "34": "Waiver of COI",
    "41": "Paid-Up (at issue)",
    "42": "Single Premium",
    "43": "Single Premium (endowment)",
    "44": "ETI",
    "45": "RPU",
    "46": "Fully Paid-Up",
    "47": "Paid-Up (multiple)",
    "49": "Annuitization",
    "54": "Lapsing",
    "97": "Reinstatement Pending",
    "98": "Not Issued",
    "99": "Terminated",
}







# =============================================================================
# COMPANY / PRODUCT
# =============================================================================

COMPANY_CODES = {
    "01": "ANICO",
    "04": "ANTEX",
    "06": "SLAICO",
    "08": "Garden State",
    "26": "ANICO NY",
}

PRODUCT_LINE_CODES = {
    "0": "Trad (non ind. Term)",
    "B": "Blended insurance rider",
    "C": "Additional payment paid-up additions rider",
    "F": "Annuity or Annuity Rider",
    "I": "Interest sensitive life",
    "N": "Indeterminate premium",
    "U": "Universal or variable universal life",
    "S": "Disability income",
}


# =============================================================================
# COVERAGE / PERSON
# =============================================================================

SEX_CODES = {
    "1": "Male",
    "2": "Female",
    "3": "Unisex",
    "M": "Male",
    "F": "Female",
    "U": "Unisex",
}

SEX_CODE_DISPLAY = {
    "1": "M",
    "2": "F",
    "3": "U",
    "M": "M",
    "F": "F",
    "U": "U",
}

RATE_CLASS_CODES = {
    "A": "nonsmoker",
    "B": "smoker",
    "D": "preferred",
    "E": "non tobacco pref best",
    "F": "non tobacco pref plus",
    "G": "non tobacco preferred",
    "H": "non tobacco standard",
    "I": "tobacco preferred",
    "J": "standard",
    "K": "nonsmoker or tobacco standard",
    "L": "guaranteed issue",
    "N": "nicotine non user",
    "P": "Preferred nonsmoker",
    "Q": "Preferred smokder",
    "R": "Preferred Plus nonsmoker",
    "S": "Standard nicotine user",
    "T": "Standard plus nicotine non user",
    "V": "Standard",
    "X": "Substandard",
    "Y": "Substandard plus",
    "Z": "Substandard best",
    "0": "rates do not vary by class"
}

PERSON_CODES = {
    "00": "Primary Insured",
    "01": "Joint Insured",
    "02": "Second Insured",
    "03": "Third Insured",
    "40": "Spouse",
    "50": "Child/Dependent",
    "60": "Other Insured",
    "70": "Owner",
    "80": "Payor",
}

NXT_CHG_TYP_CODES = {
    "0": "terminated",
    "1": "paid up",
    "2": "premium paying",
}


# =============================================================================
# BILLING
# =============================================================================

BILLING_MODE_CODES = {
    1: "Monthly",
    3: "Quarterly",
    6: "Semi-Annual",
    12: "Annual",
}

NON_STANDARD_BILL_MODE_CODES = {
    "1": "Weekly",
    "2": "Bi-Weekly",
    "9": "9thly",
    "A": "10thly",
    "S": "Semi-Monthly",
}

BILL_FORM_CODES = {
    "0": "Direct pay notice",
    "A": "Home office",
    "B": "Permanent APL",
    "C": "Premium depositor fund",
    "4": "Discounted premium deposit",
    "F": "Government allotment",
    "G": "PAC",
    "H": "Salary deduction",
    "I": "Bank deduction",
    "J": "Dividend",
    "Q": "Permanent APP",
    "V": "Net vanish (offset) premium",
}

BILL_MODE_CODES = {
    "A": "Annual",
    "S": "Semi-Annual",
    "Q": "Quarterly",
    "M": "Monthly",
    "B": "Bi-Weekly",
}

MODE_FREQUENCY_MAP = {
    "A": 1,
    "S": 2,
    "Q": 4,
    "M": 12,
    "B": 26,
}


# =============================================================================
# OPTIONS
# =============================================================================

DIV_OPTION_CODES = {
    "0": "None",
    "1": "Cash",
    "2": "Apply to Premium",
    "3": "Accumulate at Interest",
    "4": "Paid-Up Additions",
    "5": "One-Year Term (Unlimited)",
    "6": "One-Year Term (Limited to CV)",
    "7": "One-Year Term (Limited to Face)",
    "8": "Loan Reduction",
    "9": "Combination",
}

NFO_CODES = {
    "0": "No Value – Lapse",
    "1": "APL then ETI",
    "2": "APL then RPU",
    "3": "APL until Exhausted",
    "4": "Extended Term Insurance",
    "5": "Reduced Paid-Up",
    "9": "Special Agreement",
}

DB_OPTION_CODES = {
    "1": "Level Death Benefit (Option A)",
    "2": "Increasing Death Benefit (Option B)",
    "3": "Return of Premium (Option C)",
}

DEF_OF_LIFE_INS_CODES = {
    "1": "TEFRA Guideline Premium",
    "2": "DEFRA Guideline Premium",
    "3": "DEFRA Cash Value Accumulation Test",
    "4": "GP Selected",
    "5": "CVAT Selected",
}


# =============================================================================
# LOANS
# =============================================================================

LOAN_TYPE_CODES = {
    "0": "Advance, Fixed Interest",
    "1": "Arrears, Fixed Interest",
    "6": "Advance, Variable Interest",
    "7": "Arrears, Variable Interest",
    "9": "Loans not allowed",
}

LOAN_INTEREST_STATUS_CODES = {
    "1": "Capitalized",
    "2": "Accrued",
    "3": "Due and Unpaid",
}

LOAN_INTEREST_TYPE_CODES = {
    "1": "Capitalized",
    "2": "Simple Interest",
    "3": "Compound Interest",
}


# =============================================================================
# ENTRY CODES
# =============================================================================

LAST_ENTRY_CODES = {
    "A": "Entry - New Business, Not Paid For",
    "B": "Normal Entry to the file",
    "C": "Active Policy Record",
    "D": "Correction Entry to Database",
    "E": "Replacement",
    "F": "Replacement with Policy Exhibit Transactions",
    "J": "Termination - Without Policy Exhibit Transactions",
    "K": "Termination - With Policy Exhibit Transactions",
    "L": "Termination - Death Claim Settled",
    "M": "Termination - Maturity",
    "N": "Termination - Expiration",
    "O": "Termination - Conversion",
    "P": "Termination - Surrender",
    "Q": "Termination - Lapse",
    "R": "Termination - Conversion to RPU or ETI",
    "X": "Termination - Free Look Surrender",
}


# =============================================================================
# BENEFIT TYPE CODES
# =============================================================================

BENEFIT_TYPE_CODES = {
    "1": "ADB",    # Accidental Death Benefit
    "2": "ADnD",   # Accidental Death and Dismemberment
    "3": "PWoC",   # Premium Waiver of Cost
    "4": "PWoT",   # Premium Waiver of Target
    "7": "GIO",    # Guaranteed Increase Option
    "9": "PPB",    # Premium Payor Benefit
    "#": "ABR",    # Accelerated Benefit Rider
    "A": "CCV",    # Coverage Continuation Rider
    "U": "COLA",   # Cost of Living Adjustment
    "B": "LTC",    # Long Term Care
    "V": "GCO",    # Guaranteed Cash Out
}

ABR_SUBTYPE_MAP = {
    "1": "ABRTM", "2": "ABRCT", "3": "ABRCH", "4": "ABRTM",
    "5": "ABRCT", "6": "ABRCH", "L": "ABRLN",
}

GCO_SUBTYPE_MAP = {"1": "GCO15", "2": "GCO20", "3": "GCO25"}


# =============================================================================
# GRACE RULES
# =============================================================================

GRACE_RULE_CODES = {
    "C": "Unloaned CV < 0",
    "S": "SV < 0",
    "N": "Adjusted Prem < MAP, then Rule S",
    "R": "Adjusted Prem < MAP AND Unloaned CV < 0, then rule C",
    "T": "Adjusted Prem < MAP AND SV < 0, then Rule S",
}


# =============================================================================
# DIVIDEND TYPE CODES
# =============================================================================

DIV_TYPE_CODES = {
    "1": "Participating Dividend",
    "2": "Experience Refund",
    "3": "Interest Credit",
    "4": "Investment Earnings",
}


# =============================================================================
# MEC INDICATOR CODES
# =============================================================================

MEC_CODES = {
    "0": "Not a MEC",
    "1": "Policy is a MEC",
    "2": "Plan is subject to the 7-pay test",
}


# =============================================================================
# FUND NAMES
# =============================================================================

FUND_NAMES = {
    "IX": "Index 1 yr PTP with Cap",
    "IC": "Index 1 yr PTP with 1.5% and Cap",
    "IF": "Index 1 yr PTP uncapped with fee",
    "IS": "Index 1 yr PTP with Specified Rate",
    "SW": "Sweep Fund",
    "GP": "Grace Fund",
    "U1": "General Fund",
    "LZ": "Variable Loan Fund",
    "LN": "Loan Fund",
}


# =============================================================================
# TRANSACTION CODES
# =============================================================================

TRANSACTION_CODES = {
    "A_": "Policyowner statement revision",
    "AA": "Policyowner statement automatic on anniversary",
    "AC": "Policyowner confirmation",
    "AF": "Policyowner statement off anniversary",
    "AL": "Lag/loss accounting",
    "AR": "Policyowner statement request prior 12 months",
    "AS": "Split accounting for fixed fund exchange",
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
    "DK": "Dread disease expense charge",
    "DP": "Dread disease claim payment",
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
    "IN": "LTC/DD accumulated claims lien amount",
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
    "MS": "Move to external clearing suspense",
    "N3": "Deposit at interest",
    "N4": "Interest on dividends at ETI/RPU conversion",
    "NC": "Pro rata interest on new deposits",
    "ON": "ISL, paid-up additions option not elected",
    "OS": "Over/short",
    "OY": "ISL, elect paid-up additions option",
    "P6": "Current value adjustment for payments/surrenders",
    "P7": "Annuitization account value adjustment increase",
    "P8": "Excess interest",
    "PA": "Additional (unscheduled) premium payment",
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
    "PR": "Regular (scheduled) premium payment",
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
    "SD": "Premiums due on death claim",
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
    "SX": "Reversal of premium waiver for death claims/surrenders",
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
    "TZ": "Premium Tax",
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
    "ZC": "Forecasts, current premium solve for target CSV",
    "ZG": "Forecasts, guaranteed premium solve for target CSV",
    "ZN": "Vanishing (offset) premium request - NVP",
    "ZP": "Forecasts, current projection",
    "ZR": "Vanishing (offset) premium request - APP",
    "ZS": "Forecasts, premium solve",
    "ZV": "Forecasts, vanishing (offset) premium",
    "ZZ": "Suppress check special accounting",
    # Numeric dividend option / transaction subtype codes
    "11": "Cash",
    "13": "Deposit at interest",
    "14": "Paid-up additions",
    "15": "One year term additions, unlimited",
    "16": "One year term additions, limit CV",
    "18": "L",
    "21": "Cash",
    "23": "Deposit at interest",
    "24": "Paid-up additions",
    "33": "Deposit at interest",
    "34": "Paid-up additions",
    "35": "One year term additions, unlimited",
    "43": "Deposit at interest",
}

TRANSACTION_TYPE_CODES = {
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
    "Z": "Forecast",
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


# =============================================================================
# RENEWAL RATE TYPES
# =============================================================================

RENEWAL_RATE_TYPE_CODES = {
    "A": "Annual/Level (GLP)",
    "C": "Current",
    "G": "Guaranteed",
    "M": "Minimum",
    "S": "Single (GSP)",
}


# =============================================================================
# COVERAGE TARGETS
# =============================================================================

COVERAGE_TARGET_TYPES = {
    "CV": "CCV (Coverage Continuation Value)",
    "SU": "Surrender Target",
    "NS": "NSP Base",
    "NT": "NSP Other",
}


# =============================================================================
# DI PERIODS
# =============================================================================

ELIMINATION_PERIOD_CODES = {
    "0": "0", "3": "30", "4": "14", "5": "180",
    "6": "60", "7": "7", "9": "90",
}

BENEFIT_PERIOD_CODES = {
    "E": "5", "B": "2", "G": "Life", "L": "1",
    "F": "To age 65", "S": "To age 67", "R": "1.5",
    "J": "10", "X": "2",
}


# =============================================================================
# REINSURANCE
# =============================================================================

REINSURANCE_CODES = {
    "A": "Automatic",
    "F": "Facultative",
    "N": "Not reinsured",
    "1": "Part reinsured",
    "2": "Multiple policy records",
    " ": "Not reinsured",
    "": "Not reinsured",
}


# =============================================================================
# MARKET ORGANIZATION
# =============================================================================

MARKET_ORG_MAP = {
    "01": {"1": "MLM", "2": "CSSD", "7": "IMG", "D": "DIRECT"},
    "30": {"1": "MLM", "7": "IMG", "D": "DIRECT"},
    "04": {"": "ANTEX"},
    "06": {"": "SLAICO"},
    "08": {"": "GSL"},
    "26": {"": "FFL"},
}


# =============================================================================
# RATE CLASS ORDER
# =============================================================================

ANICO_RATECLASS_ORDER = {
    "R": 1, "P": 2, "T": 3, "N": 4, "Q": 5, "S": 6,
}

FFL_RATECLASS_ORDER = {
    "E": 1, "F": 2, "G": 3, "H": 4, "I": 5, "J": 6,
}


# =============================================================================
# TEFRA/DEFRA
# =============================================================================

TEFRA_DEFRA_IND_CODES = {
    "0": "Not applicable",
    "1": "DEFRA",
}

GRACE_INDICATOR_CODES = {
    "0": "Not in Grace",
    "1": "In Grace",
}


# =============================================================================
# MODAL PREMIUM ORDER (MDL_PRM_MUL_ORD_CD / MDL_PRM_ORD_CD)
# =============================================================================

MULTIPLY_ORDER_CODES = {
    "1": "P*U*M",
    "2": "P*M*U",
}


# =============================================================================
# RATING ORDER CODE (RT_FCT_ORD_CD)
# =============================================================================

RATING_ORDER_CODES = {
    "1": "Rating after P",
    "2": "Rating after U",
    "3": "Rating after M",
}


# =============================================================================
# STATE CODES
# =============================================================================

STATE_CODE_TO_ABBR = {
    1: "AL", 2: "AZ", 3: "AR", 4: "CA", 5: "CO", 6: "CT", 7: "DE", 8: "DC",
    9: "FL", 10: "GA", 11: "ID", 12: "IL", 13: "IN", 14: "IA", 15: "KS",
    16: "KY", 17: "LA", 18: "ME", 19: "MD", 20: "MA", 21: "MI", 22: "MN",
    23: "MS", 24: "MO", 25: "MT", 26: "NE", 27: "NV", 28: "NH", 29: "NJ",
    30: "NM", 31: "NY", 32: "NC", 33: "ND", 34: "OH", 35: "OK", 36: "OR",
    37: "PA", 38: "RI", 39: "SC", 40: "SD", 41: "TN", 42: "TX", 43: "UT",
    44: "VT", 45: "VA", 46: "WA", 47: "WV", 48: "WI", 49: "WY", 50: "AK",
    51: "HI", 52: "PR", 55: "AS", 60: "MP", 65: "VI", 66: "GU",
}

STATE_ABBR_TO_CODE = {v: k for k, v in STATE_CODE_TO_ABBR.items()}


# =============================================================================
# TABLE RATING MAP
# =============================================================================

TABLE_RATING_MAP = {
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "I": 9, "J": 10, "K": 11, "L": 12, "M": 13, "N": 14, "O": 15, "P": 16,
}


# =============================================================================
# TRANSLATION FUNCTIONS
# =============================================================================

def translate_state_code(state_code: int) -> str:
    """Translate numeric state code to abbreviation."""
    return STATE_CODE_TO_ABBR.get(state_code, str(state_code))


def translate_state_abbr_to_code(abbr: str) -> int:
    """Translate state abbreviation to numeric code."""
    return STATE_ABBR_TO_CODE.get(abbr.upper(), 0)


def translate_table_rating(letter: str) -> int:
    """Translate table rating letter to number."""
    if not letter or letter.strip() == "" or letter.strip() == "0":
        return 0
    return TABLE_RATING_MAP.get(letter.strip().upper(), 0)


def translate_substandard_type_code(code: str) -> str:
    """Translate substandard type code: T=Table, F=Flat."""
    if code in ("0", "1", "3"):
        return "T"
    elif code in ("2", "4"):
        return "F"
    return code


def translate_elimination_period_code(code: str) -> str:
    """Translate elimination period code to days."""
    return ELIMINATION_PERIOD_CODES.get(code, code)


def translate_benefit_period_code(code: str) -> str:
    """Translate benefit period code to years/description."""
    return BENEFIT_PERIOD_CODES.get(code, code)


def translate_renewal_rate_type_code(code: str) -> str:
    """Translate renewal rate type code to description."""
    return RENEWAL_RATE_TYPE_CODES.get(code, code)


def translate_coverage_target_type(code: str) -> str:
    """Translate coverage target type code."""
    return COVERAGE_TARGET_TYPES.get(code, code)


def translate_fund_id(fund_id: str) -> str:
    """Translate fund ID to descriptive name."""
    return FUND_NAMES.get(fund_id, fund_id)


def translate_transaction_code(code: str) -> str:
    """Translate transaction code to description."""
    return TRANSACTION_CODES.get(code, code)


def translate_transaction_type_code(type_code: str) -> str:
    """Translate transaction type to description."""
    return TRANSACTION_TYPE_CODES.get(type_code, type_code)


def translate_benefit_type(type_code: str, subtype: str = "") -> str:
    """Translate benefit type codes to description."""
    if type_code == "#":
        return ABR_SUBTYPE_MAP.get(subtype, f"ABR{subtype}")
    if type_code == "V":
        return GCO_SUBTYPE_MAP.get(subtype, f"GCO{subtype}")
    return BENEFIT_TYPE_CODES.get(type_code, type_code)


def translate_div_type_code(code: str) -> str:
    """Translate dividend type code to description."""
    return DIV_TYPE_CODES.get(code, code)


def translate_loan_interest_status_code(code: str) -> str:
    """Translate loan interest status code to description."""
    return LOAN_INTEREST_STATUS_CODES.get(code, code)


def translate_loan_interest_type_code(code: str) -> str:
    """Translate loan interest type code to description."""
    return LOAN_INTEREST_TYPE_CODES.get(code, code)


def translate_market_org(company_code: str, agent_code: str) -> str:
    """Translate company and agent code to market organization."""
    if company_code in MARKET_ORG_MAP:
        org_map = MARKET_ORG_MAP[company_code]
        if agent_code in org_map:
            return org_map[agent_code]
        if "" in org_map:
            return org_map[""]
    return agent_code


def translate_mec_indicator(code: str) -> str:
    """Translate MEC indicator code to description."""
    return MEC_CODES.get(code, code)


def translate_grace_indicator(code: str) -> str:
    """Translate grace indicator code to description."""
    return GRACE_INDICATOR_CODES.get(str(code), str(code))


def translate_bill_mode_from_frequency(frequency_period: str, non_std_mode: str = "") -> str:
    """Translate PMT_FQY_PER and NSD_MD_CD to billing mode text."""
    frequency_period = str(frequency_period)
    non_std_mode = str(non_std_mode)

    if frequency_period == "1":
        if non_std_mode == "2":
            return "B - BiWeekly"
        elif non_std_mode == "S":
            return "SM - SemiMonthly"
        return "M - Monthly"
    elif frequency_period == "3":
        return "Q - Quarterly"
    elif frequency_period == "6":
        return "S - SemiAnnually"
    elif frequency_period == "12":
        return "A - Annually"
    return frequency_period


# =============================================================================
# SIMPLE LOOKUP TRANSLATION FUNCTIONS
# =============================================================================

def translate_status_code(code: str) -> str:
    """Translate policy status code to description."""
    return PREMIUM_PAY_STATUS_CODES.get(code, STATUS_CODES.get(code, code))


def translate_suspense_code(code: str) -> str:
    """Translate suspense code to description."""
    return SUSPENSE_CODES.get(code, code)


def translate_div_option_code(code: str) -> str:
    """Translate dividend option code to description."""
    return DIV_OPTION_CODES.get(code, code)


def translate_db_option_code(code: str) -> str:
    """Translate death benefit option code to description."""
    return DB_OPTION_CODES.get(code, code)


def translate_product_line_code(code: str) -> str:
    """Translate product line code to description."""
    return PRODUCT_LINE_CODES.get(code, code)


def translate_nonstandard_mode_code(code: str) -> str:
    """Translate non-standard billing mode code to description."""
    return NON_STANDARD_BILL_MODE_CODES.get(code, code)


def translate_person_code(code: str) -> str:
    """Translate person code to description."""
    return PERSON_CODES.get(code, code)


def translate_entry_code(code: str) -> str:
    """Translate original entry code to description."""
    return LAST_ENTRY_CODES.get(code, code)


def translate_last_entry_code(code: str) -> str:
    """Translate last entry code to description."""
    return LAST_ENTRY_CODES.get(code, code)


def translate_company_code(code: str) -> str:
    """Translate company code to name."""
    return COMPANY_CODES.get(code, code)


def translate_company_name_to_code(name: str) -> str:
    """Translate company name to code."""
    name_upper = name.upper()
    for code, cname in COMPANY_CODES.items():
        if cname.upper() == name_upper:
            return code
    return name


def translate_rate_class_code(code: str) -> str:
    """Translate rate class code to description."""
    return RATE_CLASS_CODES.get(code, code)


def translate_grace_rule_code(code: str) -> str:
    """Translate grace period rule code to description."""
    return GRACE_RULE_CODES.get(code, code)


def translate_bill_mode_code(code: str) -> str:
    """Translate billing mode code to description."""
    return BILL_MODE_CODES.get(code, code)


def translate_mode_code_to_frequency(code: str) -> int:
    """Translate mode code to frequency per year."""
    return MODE_FREQUENCY_MAP.get(code, 0)


def translate_sex_code(code: str) -> str:
    """Translate sex code to description."""
    return SEX_CODES.get(code, code)


def translate_reinsurance_code(code: str) -> str:
    """Translate reinsurance code to description."""
    return REINSURANCE_CODES.get(code, code)


def translate_nfo_code(code: str) -> str:
    """Translate NFO option type code to description."""
    return NFO_CODES.get(code, code)


def translate_bill_form_code(code: str) -> str:
    """Translate billing form code to description."""
    return BILL_FORM_CODES.get(code, code)


def translate_loan_type_code(code: str) -> str:
    """Translate loan type code to description."""
    return LOAN_TYPE_CODES.get(code, code)


def translate_anico_rateclass_order(code: str) -> int:
    """Get sort order for ANICO rate class codes."""
    return ANICO_RATECLASS_ORDER.get(code, 99)


def translate_ffl_rateclass_order(code: str) -> int:
    """Get sort order for FFL rate class codes."""
    return FFL_RATECLASS_ORDER.get(code, 99)


def translate_mortality_table_code(code: str) -> str:
    """Translate mortality table code to description.
    
    Uses CKAPTB32 data loaded from data/ckaptb32_mortality_tables.json.
    """
    from ...data import lookup as _data_lookup
    return _data_lookup.get_mortality_description(code)


def translate_tefra_defra_ind(code: str) -> str:
    """Translate TFDF_GDL_IND code to description."""
    return TEFRA_DEFRA_IND_CODES.get(str(code), str(code))


def translate_multiply_order_code(code: str) -> str:
    """Translate modal premium multiply order code to description."""
    return MULTIPLY_ORDER_CODES.get(str(code).strip(), str(code))


def translate_rating_order_code(code: str) -> str:
    """Translate rating order code to description."""
    return RATING_ORDER_CODES.get(str(code).strip(), str(code))
