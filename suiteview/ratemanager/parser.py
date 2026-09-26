"""
IAF (Issue Age Factor) Rate File Parser

Parses Cyberlife mainframe IAF fixed-width text files into structured data.
Ported from the legacy converter VBA ProgressBar.frm Analyze()/storeRate() (retired from docs/, see git history).
"""

from dataclasses import dataclass, field, replace
from typing import List, Optional, Callable

from suiteview.ratemanager.layouts import Field, LineRule, RepeatedGroup


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


def _field_strip(raw: str, _context) -> str:
    return _strip(raw)


def _field_int(raw: str, _context) -> int:
    return _safe_int(raw)


def _field_float(raw: str, _context) -> float:
    return _safe_float(raw)


def _field_date(raw: str, _context) -> str:
    raw = raw.ljust(8)
    return f"{raw[0:2]}/{raw[2:4]}/{raw[4:8]}"


def _field_stop_date(raw: str, _context) -> str:
    if raw.strip():
        return _field_date(raw, _context)
    return "12/31/9999"


# ---------------------------------------------------------------------------
# Skip-line detection (header/blank lines in the mainframe print)
# ---------------------------------------------------------------------------

_PLAN_HEADER = "   PLAN CODE  V  EFFDATE FST LST USE PAY-AGE USE  ME-AGE USE  VAL PER UNIT  PROD CRED AMT USE MDRT DEF SPEC BENEFITS  R LV DUR       "
_BLANK_LINE  = " " * 133
_ADV_HEADER  = "*** ADV PROD. CTL.  INIT PREM (MIN) - (MAX)    RULE   PER PREM (MIN) - (MAX)     F/Y PREM  CORR RULE    PCNT       AMT  MAP PERIOD"

_PRODUCT_RULE = LineRule("iaf-product", (
    Field("plancode", 2, 12, _field_strip),
    Field("version", 13, 16, _field_strip),
    Field("eff_date", 16, 24, _field_date),
    Field("first", 25, 28, _field_int),
    Field("last", 29, 32, _field_int),
    Field("iar_use", 34, 35, _field_int),
    Field("pay_age", 41, 44, _field_int),
    Field("pay_age_use", 46, 47, _field_int),
    Field("me_age", 53, 56, _field_int),
    Field("me_age_use", 58, 59, _field_int),
    Field("val_per_unit", 60, 74, _field_float),
    Field("prod_cred_amt", 75, 89, _field_float),
    Field("prod_cred_use", 91, 92, _field_int),
    Field("mdrt", 93, 97, _field_strip),
    Field("deficient", 100, 101, _field_int),
    Field("spec_benefits", 102, 117, _field_strip),
    Field("r", 118, 119, _field_strip),
    Field("lv", 120, 122, _field_strip),
    Field("dur", 123, 133, _field_strip),
))

_ADV_RULE = LineRule("iaf-advanced-control", (
    Field("init_prem_min", 28, 37, _field_strip),
    Field("init_prem_max", 39, 48, _field_strip),
    Field("rule_code", 49, 50, _field_strip),
    Field("per_prem_min", 61, 70, _field_strip),
    Field("per_prem_max", 72, 81, _field_strip),
    Field("fy_prem", 82, 92, _field_strip),
    Field("corr_rule", 96, 97, _field_strip),
    Field("corr_pct", 102, 110, _field_strip),
    Field("corr_amt", 111, 121, _field_strip),
    Field("map_period", 126, 130, _field_strip),
))

_RATE_HEADER_RULE = LineRule("iaf-rate-header", (
    Field("rate_type", 19, 20, _field_strip),
    Field("scale_start", 23, 31, _field_date),
    Field("scale_stop", 33, 41, _field_stop_date),
))

_RATE_CELL_GROUP = RepeatedGroup("iaf-rate-cells", (43, 65, 87, 109), (
    Field("duration", 0, 2, _field_int),
    Field("gender", 2, 3, _field_strip),
    Field("rate_class", 3, 4, _field_strip),
    Field("band", 4, 5, _field_strip),
    Field("plan_option", 5, 7, _field_strip),
    Field("rate", 8, 20, _field_float),
), required_field="duration")


@dataclass
class _IAFParseState:
    """Mutable line-state for the simple IAF layout interpreter."""

    product: ProductInfo = field(default_factory=ProductInfo)
    adv_control_pending: bool = False
    adv: dict[str, str] = field(default_factory=dict)
    rate_type: str = ""
    rate_start: str = ""
    rate_stop: str = ""


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
        self._state = _IAFParseState()

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
            self._state.product = ProductInfo(**_PRODUCT_RULE.parse(line))
            return

        # --- ADV product control header ---
        if len(line) >= 131 and line[1:131] == _ADV_HEADER:
            self._state.adv_control_pending = True
            return

        # --- ADV product control data line ---
        if self._state.adv_control_pending:
            # VBA: sometimes a stray "*" header appears on page break
            if len(line) > 1 and line[1] == "*":
                self._state.adv_control_pending = False
                return

            self._state.adv = _ADV_RULE.parse(line)
            self._state.adv_control_pending = False
            return

        # --- Rate type header line ---
        # VBA: first 19 chars are spaces AND char 20 is not space
        if line[0:19] == " " * 19 and line[19] != " ":
            header = _RATE_HEADER_RULE.parse(line)
            self._state.rate_type = header["rate_type"]
            self._state.rate_start = header["scale_start"]
            self._state.rate_stop = header["scale_stop"]
            # Fall through - this line may also contain IDENT/rate data below

        # --- Rate data extraction (4 IDENT/rate pairs) ---
        if line[0:19] == " " * 19:
            for rate in _RATE_CELL_GROUP.parse(line):
                self._store_rate(
                    rate["duration"], rate["gender"], rate["rate_class"],
                    rate["band"], rate["plan_option"], rate["rate"],
                )

    # ------------------------------------------------------------------
    # Store a parsed rate  (ports VBA storeRate sub)
    # ------------------------------------------------------------------

    def _store_rate(self, duration: int, gender: str, rate_class: str,
                    band: str, plan_option: str, rate_value: float):
        """Deduplicate product/adv, then append the rate record."""

        # --- Deduplicate product ---
        prod = replace(self._state.product, ref=0)
        pkey = prod.key()
        if pkey not in self._product_keys:
            prod.ref = len(self._products) + 1   # 1-based like VBA
            self._products.append(prod)
            self._product_keys[pkey] = prod.ref
        product_ref = self._product_keys[pkey]

        # --- Deduplicate advanced product ---
        has_adv = any(self._state.adv.values())
        if has_adv:
            adv_state = self._state.adv
            adv = AdvProductInfo(
                product_ref=product_ref,
                issue_age=self._state.product.first,
                init_prem_min=adv_state["init_prem_min"],
                init_prem_max=adv_state["init_prem_max"],
                rule_code=adv_state["rule_code"],
                per_prem_min=adv_state["per_prem_min"],
                per_prem_max=adv_state["per_prem_max"],
                fy_prem=adv_state["fy_prem"],
                corr_rule=adv_state["corr_rule"],
                corr_pct=adv_state["corr_pct"],
                corr_amt=adv_state["corr_amt"],
                map_period=adv_state["map_period"],
            )
            akey = adv.key()
            if akey not in self._adv_keys:
                self._adv_products.append(adv)
                self._adv_keys.add(akey)

        # --- Always append rate ---
        self._rates.append(RateRecord(
            product_ref=product_ref,
            rate_type=self._state.rate_type,
            scale_start=self._state.rate_start,
            scale_stop=self._state.rate_stop,
            attained_age=self._state.product.first,
            duration=duration,
            issue_age=self._state.product.first - duration,
            gender=gender,
            rate_class=rate_class,
            band=band,
            plan_option=plan_option,
            rate=rate_value,
        ))
