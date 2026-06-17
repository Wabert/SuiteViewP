"""Inspect the FPL83 ratchet-banding test data in the local SQLite fixtures.

Single-purpose helper for the ratchet_banding_coi work: report the plancode(s)
for the FPL83 test policies, then for each plancode show the band specs and the
distinct COI bands present, so we can confirm the data needed for a 2-band
ratchet COI calc is locally available.

Usage:
    venv\\Scripts\\python.exe tools/inspect_ratchet_data.py
    venv\\Scripts\\python.exe tools/inspect_ratchet_data.py '{"policies":["UL054426","UL058426"]}'
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_DB = ROOT / "bundled_data" / "dev" / "policy_records.sqlite"
RATES_DB = ROOT / "bundled_data" / "dev" / "rates.sqlite"

DEFAULT_POLICIES = ["UL054426", "UL058426"]


def _ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _coverage_plancodes(conn: sqlite3.Connection, policy_nbr: str) -> list[dict]:
    # Resolve TCH_POL_ID then read coverage phases.
    pol = conn.execute(
        "SELECT TCH_POL_ID, CK_CMP_CD, CK_SYS_CD FROM LH_BAS_POL WHERE CK_POLICY_NBR = ?",
        (policy_nbr,),
    ).fetchone()
    if pol is None:
        return []
    cols = [str(r[1]).upper() for r in conn.execute("PRAGMA table_info(LH_COV_PHA)")]
    plan_col = "PLN_DES_SER_CD" if "PLN_DES_SER_CD" in cols else None
    want = [c for c in ("COV_PHA_NBR", plan_col, "COV_UNT_QTY", "ANN_PRM_UNT_AMT") if c]
    rows = conn.execute(
        f"SELECT {', '.join(want)} FROM LH_COV_PHA WHERE TCH_POL_ID = ? ORDER BY COV_PHA_NBR",
        (pol["TCH_POL_ID"],),
    ).fetchall()
    return [dict(r) for r in rows]


def _rate_table_cols(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})")]


def _plancode_rate_summary(conn: sqlite3.Connection, plancode: str) -> dict:
    out: dict = {"plancode": plancode}

    # Band specs
    try:
        specs = conn.execute(
            "SELECT * FROM Select_RATE_BANDSPECS WHERE Plancode = ? ORDER BY rowid",
            (plancode,),
        ).fetchall()
        out["bandspecs"] = [dict(r) for r in specs]
    except Exception as exc:
        out["bandspecs_error"] = str(exc)

    # Distinct COI bands / scales
    try:
        bands = conn.execute(
            "SELECT DISTINCT [Band] FROM Select_RATE_COI WHERE Plancode = ? ORDER BY [Band]",
            (plancode,),
        ).fetchall()
        out["coi_bands"] = [r[0] for r in bands]
        scales = conn.execute(
            "SELECT DISTINCT Scale FROM Select_RATE_COI WHERE Plancode = ? ORDER BY Scale",
            (plancode,),
        ).fetchall()
        out["coi_scales"] = [r[0] for r in scales]
        # Sample: count of COI rows per band for a single age/sex/class/scale key
        key = conn.execute(
            "SELECT IssueAge, Sex, Rateclass, Scale FROM Select_RATE_COI "
            "WHERE Plancode = ? LIMIT 1",
            (plancode,),
        ).fetchone()
        if key is not None:
            out["coi_sample_key"] = dict(key)
            per_band = {}
            for b in out["coi_bands"]:
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM Select_RATE_COI WHERE Plancode = ? AND IssueAge = ? "
                    "AND Sex = ? AND Rateclass = ? AND Scale = ? AND [Band] = ?",
                    (plancode, key["IssueAge"], key["Sex"], key["Rateclass"], key["Scale"], b),
                ).fetchone()[0]
                per_band[str(b)] = cnt
            out["coi_rows_per_band_for_sample_key"] = per_band
    except Exception as exc:
        out["coi_error"] = str(exc)

    # Select_SCALE_COI (which scale is active)
    try:
        sc = conn.execute(
            "SELECT * FROM Select_SCALE_COI WHERE Plancode = ?",
            (plancode,),
        ).fetchall()
        out["select_scale_coi"] = [dict(r) for r in sc]
    except Exception as exc:
        out["select_scale_coi_error"] = str(exc)

    return out


def main() -> None:
    policies = DEFAULT_POLICIES
    if len(sys.argv) > 1:
        policies = json.loads(sys.argv[1]).get("policies", DEFAULT_POLICIES)

    pconn = _ro(POLICY_DB)
    rconn = _ro(RATES_DB)
    try:
        result: dict = {"policies": [], "rate_summaries": []}
        plancodes: set[str] = set()
        for pol in policies:
            covs = _coverage_plancodes(pconn, pol)
            for c in covs:
                pc = c.get("PLN_DES_SER_CD")
                if pc:
                    plancodes.add(str(pc).strip())
            result["policies"].append({"policy": pol, "coverages": covs})

        # Also list any plancodes present in the rates DB that look like FPL83
        try:
            all_pc = rconn.execute(
                "SELECT DISTINCT Plancode FROM Select_RATE_BANDSPECS ORDER BY Plancode"
            ).fetchall()
            result["all_bandspec_plancodes"] = [r[0] for r in all_pc]
        except Exception as exc:
            result["all_bandspec_plancodes_error"] = str(exc)

        for pc in sorted(plancodes):
            result["rate_summaries"].append(_plancode_rate_summary(rconn, pc))

        print(json.dumps(result, indent=2, default=str))
    finally:
        pconn.close()
        rconn.close()


if __name__ == "__main__":
    main()
