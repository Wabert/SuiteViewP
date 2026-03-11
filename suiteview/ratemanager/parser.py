"""
IAF (Issue Age Factor) Rate File Parser

Parses Cyberlife mainframe IAF fixed-width text files into structured data.
Ported from the VBA ProgressBar.frm Analyze() and storeRate() logic.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Callable


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ProductInfo:
    """Plan-level metadata extracted from each age block header."""
    ref: int = 0
    plancode: str = ""
    version: str = ""
    eff_date: str = ""        # MM/DD/YYYY
    first: int = 0            # attained age (low end of block)
    last: int = 0
    iar_use: int = 0
    pay_age: int = 0
    pay_age_use: int = 0
    me_age: int = 0
    me_age_use: int = 0
    val_per_unit: float = 0.0
    prod_cred_amt: float = 0.0
    prod_cred_use: int = 0
    mdrt: str = ""
    deficient: int = 0
    spec_benefits: str = ""
    r: str = ""
    lv: str = ""
    dur: str = ""

    def key(self):
        """Deduplication key matching the VBA ProductArray equality check."""
        return (
            self.plancode, self.version, self.eff_date, self.first,
            self.iar_use, self.pay_age, self.pay_age_use,
            self.me_age, self.me_age_use, self.val_per_unit,
            self.prod_cred_amt, self.prod_cred_use, self.mdrt,
            self.deficient, self.spec_benefits, self.r, self.lv, self.dur,
        )


@dataclass
class AdvProductInfo:
    """Advanced product control data (premium limits per issue age)."""
    product_ref: int = 0
    issue_age: int = 0
    init_prem_min: str = "0"
    init_prem_max: str = "0"
    rule_code: str = "0"
    per_prem_min: str = "0"
    per_prem_max: str = "0"
    fy_prem: str = "0"
    corr_rule: str = "0"
    corr_pct: str = "0"
    corr_amt: str = "0"
    map_period: str = "0"

    def key(self):
        return (
            self.product_ref, self.issue_age,
            self.init_prem_min, self.init_prem_max, self.rule_code,
            self.per_prem_min, self.per_prem_max, self.fy_prem,
            self.corr_rule, self.corr_pct, self.corr_amt, self.map_period,
        )


@dataclass
class RateRecord:
    """One individual rate value with full dimensional detail."""
    product_ref: int = 0
    rate_type: str = ""       # C, G, M, T, W, etc.
    scale_start: str = ""     # MM/DD/YYYY
    scale_stop: str = ""      # MM/DD/YYYY or 12/31/9999
    attained_age: int = 0     # "First" in VBA
    duration: int = 0
    issue_age: int = 0        # attained_age - duration
    gender: str = ""
    rate_class: str = ""
    band: str = ""
    plan_option: str = ""
    rate: float = 0.0


# ---------------------------------------------------------------------------
# Parse result container
# ---------------------------------------------------------------------------

@dataclass
class ParseResult:
    """All data extracted from an IAF file."""
    products: List[ProductInfo] = field(default_factory=list)
    adv_products: List[AdvProductInfo] = field(default_factory=list)
    rates: List[RateRecord] = field(default_factory=list)
    line_count: int = 0
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _strip(val: str) -> str:
    """Strip whitespace, returning single space if empty (matches VBA RemoveWhiteSpace)."""
    val = val.strip()
    return val if val else " "


def _safe_int(val: str, default: int = 0) -> int:
    try:
        return int(val.strip().replace(',', ''))
    except (ValueError, TypeError):
        return default


def _safe_float(val: str, default: float = 0.0) -> float:
    try:
        return float(val.strip().replace(',', ''))
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Skip-line detection (header/blank lines in the mainframe print)
# ---------------------------------------------------------------------------

_PLAN_HEADER = "   PLAN CODE  V  EFFDATE FST LST USE PAY-AGE USE  ME-AGE USE  VAL PER UNIT  PROD CRED AMT USE MDRT DEF SPEC BENEFITS  R LV DUR       "
_BLANK_LINE  = " " * 133
_ADV_HEADER  = "*** ADV PROD. CTL.  INIT PREM (MIN) - (MAX)    RULE   PER PREM (MIN) - (MAX)     F/Y PREM  CORR RULE    PCNT       AMT  MAP PERIOD"


def _should_skip(line: str) -> bool:
    """Return True if this line is a header/blank that should be skipped."""
    if line.startswith("0DATE"):
        return True
    if len(line) >= 51 and line[:51] == "1" + " " * 50:
        return True
    if len(line) >= 83 and line[50:82] == "PRINT ISSUE AGE DESCRIPTION FILE":
        return True
    if line == _BLANK_LINE or line.rstrip() == "":
        return True
    if line == _PLAN_HEADER:
        return True
    return False


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class IAFParser:
    """
    Parses a Cyberlife IAF text file into products, adv_products, and rates.

    Usage::

        parser = IAFParser()
        result = parser.parse("path/to/file.txt", progress_cb=lambda pct: ...)
    """

    def __init__(self):
        self._reset()

    def _reset(self):
        # Current plan-level state (set on plan header lines)
        self._plancode = ""
        self._version = ""
        self._eff_date = ""
        self._first = 0
        self._last = 0
        self._iar_use = 0
        self._pay_age = 0
        self._pay_age_use = 0
        self._me_age = 0
        self._me_age_use = 0
        self._val_per_unit = 0.0
        self._prod_cred_amt = 0.0
        self._prod_cred_use = 0
        self._mdrt = ""
        self._def = 0
        self._spec_benefits = ""
        self._r = ""
        self._lv = ""
        self._dur = ""

        # ADV product control state
        self._adv_control_pending = False
        self._adv_init_min = ""
        self._adv_init_max = ""
        self._adv_rule = ""
        self._adv_per_min = ""
        self._adv_per_max = ""
        self._adv_fy = ""
        self._adv_corr_rule = ""
        self._adv_corr_pct = ""
        self._adv_corr_amt = ""
        self._adv_map = ""

        # Current rate type state
        self._rate_type = ""
        self._rate_start = ""
        self._rate_stop = ""

        # Collections
        self._products: List[ProductInfo] = []
        self._product_keys: dict = {}     # key -> index
        self._adv_products: List[AdvProductInfo] = []
        self._adv_keys: set = set()
        self._rates: List[RateRecord] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, filepath: str,
              progress_cb: Optional[Callable[[float], None]] = None) -> ParseResult:
        """
        Parse an IAF text file and return a ParseResult.

        Args:
            filepath: Path to the IAF .txt file.
            progress_cb: Optional callback receiving progress 0.0 - 1.0.
        """
        self._reset()

        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as exc:
            return ParseResult(error=f"Could not read file: {exc}")

        total = len(lines)
        if total == 0:
            return ParseResult(error="File is empty")

        last_pct = 0.0
        for i, raw_line in enumerate(lines):
            line = raw_line.rstrip("\n").rstrip("\r")
            self._analyze(line)

            if progress_cb and total > 0:
                pct = (i + 1) / total
                if pct - last_pct >= 0.01:
                    progress_cb(pct)
                    last_pct = pct

        return ParseResult(
            products=self._products,
            adv_products=self._adv_products,
            rates=self._rates,
            line_count=total,
        )

    # ------------------------------------------------------------------
    # Line analysis  (ports VBA Analyze sub)
    # ------------------------------------------------------------------

    def _analyze(self, line: str):
        """Analyze a single line from the IAF file."""

        if _should_skip(line):
            return

        # Pad short lines so fixed-position slicing doesn't IndexError
        if len(line) < 135:
            line = line.ljust(135)

        # --- Plan header line ---
        # VBA: Mid(Line,2,1)=" " AND Mid(Line,3,1)<>" "
        if line[1] == " " and line[2] != " ":
            self._plancode     = _strip(line[2:12])
            self._version      = _strip(line[13:16])
            self._eff_date     = f"{line[16:18]}/{line[18:20]}/{line[20:24]}"
            self._first        = _safe_int(line[25:28])
            self._last         = _safe_int(line[29:32])
            self._iar_use      = _safe_int(line[34:35])
            self._pay_age      = _safe_int(line[41:44])
            self._pay_age_use  = _safe_int(line[46:47])
            self._me_age       = _safe_int(line[53:56])
            self._me_age_use   = _safe_int(line[58:59])
            self._val_per_unit = _safe_float(line[60:74])
            self._prod_cred_amt = _safe_float(line[75:89])
            self._prod_cred_use = _safe_int(line[91:92])
            self._mdrt         = _strip(line[93:97])
            self._def          = _safe_int(line[100:101])
            self._spec_benefits = _strip(line[102:117])
            self._r            = _strip(line[118:119])
            self._lv           = _strip(line[120:122])
            self._dur          = _strip(line[123:133])
            return

        # --- ADV product control header ---
        if len(line) >= 131 and line[1:131] == _ADV_HEADER:
            self._adv_control_pending = True
            return

        # --- ADV product control data line ---
        if self._adv_control_pending:
            # VBA: sometimes a stray "*" header appears on page break
            if len(line) > 1 and line[1] == "*":
                self._adv_control_pending = False
                return

            self._adv_init_min  = _strip(line[28:37])
            self._adv_init_max  = _strip(line[39:48])
            self._adv_rule      = _strip(line[49:50])
            self._adv_per_min   = _strip(line[61:70])
            self._adv_per_max   = _strip(line[72:81])
            self._adv_fy        = _strip(line[82:92])
            self._adv_corr_rule = _strip(line[96:97])
            self._adv_corr_pct  = _strip(line[102:110])
            self._adv_corr_amt  = _strip(line[111:121])
            self._adv_map       = _strip(line[126:130])

            self._adv_control_pending = False
            return

        # --- Rate type header line ---
        # VBA: first 19 chars are spaces AND char 20 is not space
        if line[0:19] == " " * 19 and line[19] != " ":
            self._rate_type  = line[19]
            self._rate_start = f"{line[23:25]}/{line[25:27]}/{line[27:31]}"
            if line[33:35].strip():
                self._rate_stop = f"{line[33:35]}/{line[35:37]}/{line[37:41]}"
            else:
                self._rate_stop = "12/31/9999"
            # Fall through - this line may also contain IDENT/rate data below

        # --- Rate data extraction (4 IDENT/rate pairs) ---
        if line[0:19] == " " * 19:
            # VBA col positions (1-based to 0-based):  44->43, 66->65, 88->87, 110->109
            for ident_start, rate_start in [(43, 51), (65, 73), (87, 95), (109, 117)]:
                if line[ident_start] != " ":
                    duration    = _safe_int(line[ident_start:ident_start + 2])
                    gender      = _strip(line[ident_start + 2:ident_start + 3])
                    rate_class  = _strip(line[ident_start + 3:ident_start + 4])
                    band        = _strip(line[ident_start + 4:ident_start + 5])
                    plan_option = _strip(line[ident_start + 5:ident_start + 7])
                    rate_value  = _safe_float(line[rate_start:rate_start + 12])
                    self._store_rate(duration, gender, rate_class, band,
                                     plan_option, rate_value)

    # ------------------------------------------------------------------
    # Store a parsed rate  (ports VBA storeRate sub)
    # ------------------------------------------------------------------

    def _store_rate(self, duration: int, gender: str, rate_class: str,
                    band: str, plan_option: str, rate_value: float):
        """Deduplicate product/adv, then append the rate record."""

        # --- Deduplicate product ---
        prod = ProductInfo(
            plancode=self._plancode,
            version=self._version,
            eff_date=self._eff_date,
            first=self._first,
            last=self._last,
            iar_use=self._iar_use,
            pay_age=self._pay_age,
            pay_age_use=self._pay_age_use,
            me_age=self._me_age,
            me_age_use=self._me_age_use,
            val_per_unit=self._val_per_unit,
            prod_cred_amt=self._prod_cred_amt,
            prod_cred_use=self._prod_cred_use,
            mdrt=self._mdrt,
            deficient=self._def,
            spec_benefits=self._spec_benefits,
            r=self._r,
            lv=self._lv,
            dur=self._dur,
        )
        pkey = prod.key()
        if pkey not in self._product_keys:
            prod.ref = len(self._products) + 1   # 1-based like VBA
            self._products.append(prod)
            self._product_keys[pkey] = prod.ref
        product_ref = self._product_keys[pkey]

        # --- Deduplicate advanced product ---
        has_adv = any([
            self._adv_init_min, self._adv_init_max, self._adv_rule,
            self._adv_per_min, self._adv_per_max, self._adv_fy,
            self._adv_corr_rule, self._adv_corr_pct, self._adv_corr_amt,
            self._adv_map,
        ])
        if has_adv:
            adv = AdvProductInfo(
                product_ref=product_ref,
                issue_age=self._first,
                init_prem_min=self._adv_init_min,
                init_prem_max=self._adv_init_max,
                rule_code=self._adv_rule,
                per_prem_min=self._adv_per_min,
                per_prem_max=self._adv_per_max,
                fy_prem=self._adv_fy,
                corr_rule=self._adv_corr_rule,
                corr_pct=self._adv_corr_pct,
                corr_amt=self._adv_corr_amt,
                map_period=self._adv_map,
            )
            akey = adv.key()
            if akey not in self._adv_keys:
                self._adv_products.append(adv)
                self._adv_keys.add(akey)

        # --- Always append rate ---
        self._rates.append(RateRecord(
            product_ref=product_ref,
            rate_type=self._rate_type,
            scale_start=self._rate_start,
            scale_stop=self._rate_stop,
            attained_age=self._first,
            duration=duration,
            issue_age=self._first - duration,
            gender=gender,
            rate_class=rate_class,
            band=band,
            plan_option=plan_option,
            rate=rate_value,
        ))
