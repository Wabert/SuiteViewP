"""
Field Dictionary — friendly labels for cryptic DB2 / CyberLife columns.
======================================================================

CyberLife column names are terse and inconsistent (``XTR_PER_1000_AMT``,
``RT_SEX_CD``, ``NON_TRD_POL_IND``).  A business analyst should never have to
decode them.  This module maps a technical column name to a **human label**
(primary display) plus an optional **description** (tooltip), so every field
picker, filter chip, and results header across SuiteView can show
``Flat Extra per $1,000`` with ``XTR_PER_1000_AMT`` tucked into the tooltip.

Two layers:

1. **Curated** — a high-confidence dictionary of documented columns
   (``COLUMN_LABELS``), sourced from ``Agent.md`` and the policy-record
   table mappings.  Only entries we are sure about live here.
2. **Humanizer fallback** — for anything not curated, ``humanize()`` mechanically
   expands known abbreviations (``CD``→Code, ``AMT``→Amount, ``NBR``→Number…)
   and title-cases the rest.  This is clearly a *derived* label, never an
   authoritative claim — when in doubt we expand, we do not invent meaning.

A runtime ``register_labels()`` hook lets callers layer in extra names (e.g. the
``ABATBL_FIELD_REG.display_name`` registry, or a user dictionary) without this
pure module depending on the database.

This module is intentionally Qt-free and DB-free so it is unit-testable on the
minipc and importable from any sub-app.  It does **not** translate *values*
(status code ``10`` → "Active") — that is ``policy_translations.py``.
"""
from __future__ import annotations

__all__ = [
    "friendly_label",
    "friendly_description",
    "label_and_description",
    "humanize",
    "is_known",
    "register_labels",
    "COLUMN_LABELS",
]


# =============================================================================
# CURATED LABELS  —  UPPER-CASED technical column -> (label, description)
# =============================================================================
# High-confidence only.  Sourced from Agent.md "Key DB2 Tables", the column
# verification table, and the billing/domain notes.  When unsure, leave it out
# and let humanize() derive a mechanical label rather than assert a wrong one.

COLUMN_LABELS: dict[str, tuple[str, str]] = {
    # ── Identifiers / composite key ──────────────────────────────────
    "CK_POLICY_NBR": ("Policy Number", "The policy number (LH_BAS_POL.CK_POLICY_NBR)."),
    "TCH_POL_ID": ("Technical Policy ID",
                   "Internal policy identifier — NOT the policy number "
                   "(policy number + space + 4 chars)."),
    "CK_SYS_CD": ("System Code", "'I' = inforce, 'P' = pending (almost always 'I')."),
    "CK_CMP_CD": ("Company Code", "01 ANICO, 04 ANTEX, 06 SLAICO, 08 GSL, 26 ANICO NY."),
    "COV_PHA_NBR": ("Coverage Phase Number", "1 = base coverage, >1 = riders."),

    # ── Status / dates ───────────────────────────────────────────────
    "PRM_PAY_STA_REA_CD": ("Premium Pay Status Reason", "Premium-paying status reason code."),
    "PAID_TO_DT": ("Paid-To Date", "Date premiums are paid through."),
    "ASOF_DT": ("As-Of Date", ""),

    # ── Product type ─────────────────────────────────────────────────
    "NON_TRD_POL_IND": ("Non-Traditional Policy Indicator",
                        "1 = Advanced (UL/IUL/VUL); 0 or blank = Traditional."),
    "PRD_LIN_TYP_CD": ("Product Line Type",
                       "0 = Traditional, I = ISL, U = UL/VUL, etc."),
    "AN_PRD_ID": ("Advanced Product ID", "Advanced-product identifier (TH_BAS_POL)."),
    "TFDF_CD": ("Tax Definition Code (GP/CVAT)",
                "1 TEFRA GP, 2 DEFRA GP, 3 DEFRA CVAT, 4 GP Selected, 5 CVAT Selected."),

    # ── Coverage / plan ──────────────────────────────────────────────
    "PLN_DES_SER_CD": ("Plan Design Series Code", ""),
    "ANN_PRM_UNT_AMT": ("Annual Premium per Unit", "Traditional rate source (LH_COV_PHA)."),
    "COV_UNT_QTY": ("Coverage Unit Quantity", ""),
    "COV_VPU_AMT": ("Coverage Value per Unit", ""),

    # ── Renewal rates ────────────────────────────────────────────────
    "RNL_RT": ("Renewal Rate", "Advanced rate source (LH_COV_INS_RNL_RT, type 'C')."),
    "RT_CLS_CD": ("Rate Class", "Underwriting rate class code."),
    "RT_SEX_CD": ("Sex (rate)", "Per-coverage rate sex code (LH_COV_INS_RNL_RT)."),
    "PRM_RT_TYP_CD": ("Premium Rate Type", "A Annual/Level, C Current, G Guaranteed, M Minimum, S Single."),
    "INS_SEX_CD": ("Insured Sex Code", ""),

    # ── Additional coverage data ─────────────────────────────────────
    "COLA_INCR_IND": ("COLA Increase Indicator", ""),
    "OPT_EXER_IND": ("Option Exercised Indicator", ""),
    "CV_AMT": ("Cash Value Amount", "Traditional values (TH_COV_PHA)."),
    "NSP_AMT": ("Net Single Premium Amount", ""),

    # ── Supplemental benefits ────────────────────────────────────────
    "SPM_BNF_TYP_CD": ("Supplemental Benefit Type", ""),
    "SPM_BNF_SBY_CD": ("Supplemental Benefit Subtype", ""),

    # ── Substandard / flat extras (verification-table columns) ───────
    "SST_XTR_TYP_CD": ("Substandard Extra Type", "T = Table rating, F = Flat extra."),
    "SST_XTR_RT_TBL_CD": ("Substandard Rating Table Code", ""),
    "XTR_PER_1000_AMT": ("Flat Extra per $1,000", "Flat extra amount per $1,000 of coverage."),
    "SST_XTR_CEA_DT": ("Substandard Extra Cease Date", ""),
    "SST_XTR_CEA_DUR": ("Substandard Extra Cease Duration", ""),

    # ── Targets ──────────────────────────────────────────────────────
    "TAR_TYP_CD": ("Target Type", "MT = MTP, MA = Accum MTP, CT = Commission Target."),

    # ── UL anniversary values ────────────────────────────────────────
    "CSV_AMT": ("Cash Surrender Value", "Monthly anniversary value (LH_POL_MVRY_VAL)."),

    # ── Financial history ────────────────────────────────────────────
    "TRN_TYP_CD": ("Transaction Type", ""),
    "TOT_TRS_AMT": ("Total Transaction Amount", ""),

    # ── Agent / commission ───────────────────────────────────────────
    "AGT_ID": ("Agent ID", ""),
    "COM_PCT": ("Commission Percent", ""),

    # ── Billing ──────────────────────────────────────────────────────
    "PMT_FQY_PER": ("Payment Frequency (months)",
                    "Months between payments: 1 Monthly, 3 Quarterly, 6 Semi-Annual, 12 Annual."),
    "NSD_MD_CD": ("Non-Standard Mode Code", "Overrides payment frequency when set (e.g. 2 = Bi-Weekly)."),
    "POL_PRM_AMT": ("Policy Premium Amount (monthly)",
                    "Always a monthly premium, even for non-standard modes."),
}


# =============================================================================
# HUMANIZER  —  mechanical abbreviation expansion for non-curated columns
# =============================================================================

# Single-token abbreviation expansions.  Conservative and reusable.
_ABBREV: dict[str, str] = {
    "CD": "Code", "CDS": "Codes",
    "NBR": "Number", "NUM": "Number", "NO": "Number",
    "AMT": "Amount", "AMTS": "Amounts",
    "DT": "Date", "DTS": "Dates",
    "IND": "Indicator", "INDS": "Indicators",
    "PCT": "Percent",
    "QTY": "Quantity",
    "RT": "Rate", "RTS": "Rates",
    "CLS": "Class",
    "COV": "Coverage",
    "POL": "Policy",
    "PRM": "Premium", "PREM": "Premium",
    "SST": "Substandard",
    "XTR": "Extra",
    "CEA": "Cease",
    "DUR": "Duration",
    "BNF": "Benefit",
    "SPM": "Supplemental",
    "SBY": "Subtype",
    "CMP": "Company",
    "SYS": "System",
    "TCH": "Technical",
    "PHA": "Phase",
    "ANN": "Annual",
    "MVRY": "Anniversary",
    "FQY": "Frequency",
    "PER": "Period",
    "MD": "Mode",
    "NSD": "Non-Standard",
    "PLN": "Plan",
    "DES": "Design",
    "SER": "Series",
    "VPU": "Value per Unit",
    "UNT": "Unit",
    "AGT": "Agent",
    "COM": "Commission",
    "TYP": "Type",
    "STA": "Status",
    "REA": "Reason",
    "PAY": "Pay",
    "PMT": "Payment",
    "TRN": "Transaction",
    "TRS": "Transaction",
    "TOT": "Total",
    "INS": "Insured",
    "SEX": "Sex",
    "PRD": "Product",
    "LIN": "Line",
    "TAR": "Target",
    "OPT": "Option",
    "EXER": "Exercised",
    "INCR": "Increase",
    "FCT": "Factor",
    "ORD": "Order",
    "MUL": "Multiply",
    "MDL": "Modal",
    "GDL": "Guideline",
    "VAL": "Value",
    "FND": "Fund",
    "CSH": "Cash",
    "WDL": "Withdrawal",
    "BAL": "Balance",
    "EFF": "Effective",
    "EXP": "Expiry",
    "ISS": "Issue",
    "MAT": "Maturity",
    "ANV": "Anniversary",
    "CUR": "Current",
    "GTD": "Guaranteed",
    "ACCT": "Account",
    "SUR": "Surrender",
}

# Multi-token acronyms kept verbatim (recognised as a whole token).
_KEEP_ACRONYM: dict[str, str] = {
    "CV": "Cash Value",
    "CSV": "Cash Surrender Value",
    "NSP": "Net Single Premium",
    "GAV": "Guaranteed Account Value",
    "GLP": "Guideline Level Premium",
    "GSP": "Guideline Single Premium",
    "MTP": "Minimum Target Premium",
    "COLA": "COLA",
    "ABR": "ABR",
    "APL": "APL",
    "ETI": "ETI",
    "RPU": "RPU",
    "PUA": "PUA",
    "ID": "ID",
}

# Noise tokens dropped from derived labels (never when they are the whole name).
_DROP_TOKENS = {"CK"}


def _bare_column(ref: str) -> str:
    """Strip schema/table/alias qualifiers and any trailing 'AS alias'.

    ``DB2TAB.LH_BAS_POL.CK_POLICY_NBR`` -> ``CK_POLICY_NBR``
    ``pol.NON_TRD_POL_IND``             -> ``NON_TRD_POL_IND``
    ``CK_POLICY_NBR AS pol_num``        -> ``CK_POLICY_NBR``
    """
    s = (ref or "").strip()
    if not s:
        return ""
    # Drop a trailing alias ("col AS x" or "col x") by keeping the first token.
    s = s.split()[0]
    if "." in s:
        s = s.rsplit(".", 1)[-1]
    return s.strip().strip('"[]`')


def humanize(column: str) -> str:
    """Derive a readable label by expanding abbreviations and title-casing.

    Purely mechanical — used only as a fallback for columns not in
    ``COLUMN_LABELS``.  Expands ``CD``→Code, ``AMT``→Amount, etc., drops the
    CyberLife ``CK`` prefix, and keeps digits and known acronyms intact.
    """
    name = _bare_column(column)
    if not name:
        return column
    tokens = [t for t in name.split("_") if t]
    if not tokens:
        return name
    out: list[str] = []
    for tok in tokens:
        u = tok.upper()
        if u in _DROP_TOKENS and len(tokens) > 1:
            continue
        if u in _KEEP_ACRONYM:
            out.append(_KEEP_ACRONYM[u])
        elif u in _ABBREV:
            out.append(_ABBREV[u])
        elif u.isdigit():
            out.append(u)
        else:
            out.append(tok.capitalize())
    return " ".join(out) if out else name


# =============================================================================
# RUNTIME OVERRIDES
# =============================================================================

# Caller-supplied labels (e.g. ABATBL_FIELD_REG.display_name, user dictionary).
# Checked before the curated table so deployments can correct/extend names
# without editing this module.  Keyed by UPPER-CASED bare column name.
_OVERRIDES: dict[str, tuple[str, str]] = {}


def register_labels(mapping: dict[str, object]) -> None:
    """Layer in extra labels at runtime.

    ``mapping`` values may be a plain ``label`` string or a
    ``(label, description)`` tuple.  Keys are column names (case-insensitive);
    schema/table qualifiers are stripped.
    """
    for col, val in mapping.items():
        key = _bare_column(col).upper()
        if not key:
            continue
        if isinstance(val, (tuple, list)):
            label = str(val[0])
            desc = str(val[1]) if len(val) > 1 and val[1] is not None else ""
        else:
            label, desc = str(val), ""
        if label:
            _OVERRIDES[key] = (label, desc)


# =============================================================================
# PUBLIC LOOKUP API
# =============================================================================

def _lookup(column: str) -> tuple[str, str] | None:
    key = _bare_column(column).upper()
    if not key:
        return None
    if key in _OVERRIDES:
        return _OVERRIDES[key]
    if key in COLUMN_LABELS:
        return COLUMN_LABELS[key]
    return None


def friendly_label(column: str, table: str | None = None) -> str:
    """Return a human label for a column, or a humanized fallback.

    ``table`` is accepted for future table-qualified disambiguation; lookups
    are currently keyed by the bare column name.
    """
    hit = _lookup(column)
    if hit is not None:
        return hit[0]
    return humanize(column)


def friendly_description(column: str, table: str | None = None) -> str:
    """Return a one-line description for a column, or '' if none is curated."""
    hit = _lookup(column)
    return hit[1] if hit is not None else ""


def label_and_description(column: str, table: str | None = None) -> tuple[str, str]:
    """Return ``(label, description)`` in one call."""
    hit = _lookup(column)
    if hit is not None:
        return hit
    return humanize(column), ""


def is_known(column: str) -> bool:
    """True if the column has a curated or registered (non-derived) label."""
    return _lookup(column) is not None
