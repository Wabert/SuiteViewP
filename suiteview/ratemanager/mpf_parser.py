"""
Misc Premium File (MPF) parser.

The MPF is a fixed-column mainframe print of miscellaneous premium tables.
Records are grouped in blocks under a section header
(``SPECIAL`` / ``PAYOR`` / ``SUP.BEN``). Each record's first line carries a
15-char KEY plus a run of ``AGE  PREMIUM`` pairs; continuation lines (blank
key region) carry more pairs.

KEY layout (1-based):
    1     'M'  (Misc Premium File constant)
    2-3   company code
    4     record type  (0=Special Class, 1=Payor, 2=Supplemental, 3=Select)
    5-6   benefit type + subtype
    7     sex          (1=M, 2=F, U/Y/X=unisex)
    8     rate class
    9     band
    10-12 premium code (3 chars, e.g. '312', 'ADB', 'FUL')
    13-15 issue age (types 0/1) or sequence number (types 2/3)

This module targets the type-2 (Supplemental) records: the age/premium pairs
begin at column 31 on both the key line and its continuation lines.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterator, List, Optional, Tuple

KEY_COL = 9            # 0-based start of the 15-char KEY
KEY_LEN = 15
CONT_COL = 24          # CONT field region
DATA_COL = 31          # first AGE token column (type-2 layout)


@dataclass
class MPFKey:
    company: str = ""
    rectype: str = ""
    benefit: str = ""       # type + subtype (2 chars)
    sex: str = ""
    rate_class: str = ""
    band: str = ""
    premcode: str = ""
    seq: str = ""

    @property
    def combo(self) -> Tuple[str, str, str, str, str]:
        """(benefit, sex, class, band, premcode) — identifies a rate table."""
        return (self.benefit, self.sex, self.rate_class, self.band, self.premcode)


@dataclass
class MPFRecord:
    key: MPFKey
    cont: str = ""
    # Each pair: (age:int, premium_str:str, premium_val:float, is_percent:bool)
    pairs: List[Tuple[int, str, float, bool]] = field(default_factory=list)


def split_key(key: str) -> MPFKey:
    key = (key + " " * KEY_LEN)[:KEY_LEN]
    return MPFKey(
        company=key[1:3],
        rectype=key[3],
        benefit=key[4:6].strip(),
        sex=key[6],
        rate_class=key[7],
        band=key[8],
        premcode=key[9:12].strip(),
        seq=key[12:15],
    )


def _parse_pairs(region: str) -> List[Tuple[int, str, float, bool]]:
    toks = region.split()
    pairs: List[Tuple[int, str, float, bool]] = []
    i = 0
    while i + 1 < len(toks):
        age_tok, prem_tok = toks[i], toks[i + 1]
        if not age_tok.isdigit():
            break
        is_pct = prem_tok.endswith("%")
        try:
            val = float(prem_tok.rstrip("%"))
        except ValueError:
            break
        pairs.append((int(age_tok), prem_tok, val, is_pct))
        i += 2
    return pairs


def _is_section_or_page(line: str) -> bool:
    if "-----KEY----" in line:
        return True
    if line[:1] == "1":                  # page break (ASA carriage control)
        return True
    if line.startswith("0DATE"):
        return True
    return False


def iter_records(
    path: str,
    rectype: Optional[str] = "2",
    progress_cb: Optional[Callable[[float], None]] = None,
) -> Iterator[MPFRecord]:
    """Stream MPF records of ``rectype`` (default type 2), one per KEY line.

    Continuation lines are merged into the preceding record. Sequence records
    (000/001/002) are yielded separately — use :func:`group_by_combo` to stitch
    them into a full age table.
    """
    size = os.path.getsize(path) or 1
    current: Optional[MPFRecord] = None
    seen = 0

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        # NOTE: read via readline() rather than ``for line in fh`` — the file
        # iterator protocol disables fh.tell() ("telling position disabled by
        # next() call"), which we need for progress reporting.
        while True:
            line = fh.readline()
            if not line:
                break
            seen += 1
            if progress_cb is not None and (seen & 0x3FFF) == 0:
                progress_cb(min(fh.tell() / size, 1.0))

            s = line.rstrip("\n").rstrip("\r")
            if not s.strip() or _is_section_or_page(s):
                continue
            if len(s) <= KEY_COL or s[0] != "0":
                continue

            if s[KEY_COL] == "M":
                if current is not None:
                    yield current
                    current = None
                key = split_key(s[KEY_COL:KEY_COL + KEY_LEN])
                if rectype and key.rectype != rectype:
                    continue          # skip non-matching record + its continuations
                cont = s[CONT_COL:DATA_COL].strip()
                current = MPFRecord(key=key, cont=cont, pairs=_parse_pairs(s[DATA_COL:]))
            elif current is not None and s[KEY_COL:DATA_COL].strip() == "":
                current.pairs.extend(_parse_pairs(s[DATA_COL:]))

    if current is not None:
        yield current

    if progress_cb is not None:
        progress_cb(1.0)


def group_by_combo(records: Iterator[MPFRecord]) -> "OrderedDict":
    """Stitch sequence records into ``{combo_key: {age: (val, str, is_pct)}}``.

    ``combo_key`` = ``(company, benefit, sex, class, band, premcode)``.
    """
    grouped: "OrderedDict[tuple, dict]" = OrderedDict()
    for rec in records:
        k = rec.key
        ck = (k.company, k.benefit, k.sex, k.rate_class, k.band, k.premcode)
        table = grouped.setdefault(ck, {})
        for age, prem_str, val, is_pct in rec.pairs:
            table.setdefault(age, (val, prem_str, is_pct))
    return grouped
