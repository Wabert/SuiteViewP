"""Compare a Rate Workup output folder to a legacy {plancode}_DB reference.

Usage:
    venv\\Scripts\\python.exe tools/compare_workup_to_reference.py <workup_dir> <reference_dir>

Checks (JSON to stdout):
  * POINT_PVSRB AA rows  vs  POINTER.csv (Sex/RateClass/Band → COI/TRGPREM)
  * RATE_COI             vs  RATE_COI_CURRENT.csv + RATE_COI_GUARANTEED.csv
  * RATE_TRGPREM         vs  RATE_TRGPRM.csv (column remap, values by
                              (Index, IssueAge))
"""

import csv
import json
import os
import sys


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return rows[0], [r for r in rows[1:] if r]


def _f(v):
    """Normalize a rate cell for comparison ('' stays '')."""
    v = (v or "").strip()
    return f"{float(v):.6f}" if v else ""


def compare(workup_dir, ref_dir):
    out = {"pointer": {}, "coi": {}, "trgprem": {}}

    # ── Pointer ────────────────────────────────────────────────────────
    _h, pvsrb = _read(os.path.join(workup_dir, "POINT_PVSRB.csv"))
    _h, ref_ptr = _read(os.path.join(ref_dir, "POINTER.csv"))
    # POINT_PVSRB: Plancode,IssueVersion,Sex,Rateclass,Band,State,PREMLOAD,
    #              TRGPREM,MFEE,SCR,COI,EPU,GLP,MORTID,SHDINT,TRAD_CV
    new_map = {
        (r[2], r[3], r[4]): (r[10], r[7])
        for r in pvsrb if r[5] == "AA"
    }
    # The legacy reference uses sex 1/2 and band letters; the workup emits
    # M/F and numeric bands (X, Y first, then A, B, C…). Translate the
    # reference keys before comparing.
    sex_map = {"1": "M", "2": "F"}
    ref_bands = sorted({r[4] for r in ref_ptr if r[4] not in ("0", "")})
    ordered = [b for b in ("X", "Y") if b in ref_bands]
    ordered += [b for b in ref_bands if b not in ("X", "Y")]
    band_map = {b: str(i + 1) for i, b in enumerate(ordered)}
    band_map["0"] = "0"
    ref_map = {
        (sex_map.get(r[2], r[2]), r[3], band_map.get(r[4], r[4])): (r[6], r[7])
        for r in ref_ptr
    }
    only_new = sorted(set(new_map) - set(ref_map))
    only_ref = sorted(set(ref_map) - set(new_map))
    diffs = {
        str(k): {"new": new_map[k], "ref": ref_map[k]}
        for k in set(new_map) & set(ref_map) if new_map[k] != ref_map[k]
    }
    out["pointer"] = {
        "new_rows": len(new_map), "ref_rows": len(ref_map),
        "only_in_new": [",".join(k) for k in only_new],
        "only_in_ref": [",".join(k) for k in only_ref],
        "value_diffs": diffs,
    }

    # ── COI (merged vs current+guaranteed) ─────────────────────────────
    _h, coi = _read(os.path.join(workup_dir, "RATE_COI.csv"))
    new_coi = {(r[0], r[1], r[2], r[3]): _f(r[4]) for r in coi}
    ref_coi = {}
    for name in ("RATE_COI_CURRENT.csv", "RATE_COI_GUARANTEED.csv"):
        _h, rows = _read(os.path.join(ref_dir, name))
        for r in rows:
            ref_coi[(r[0], r[1], r[2], r[3])] = _f(r[4])
    # The workup drops artifact issue-age series (first duration > 1 —
    # padding outside the true issue range); apply the same rule to the
    # legacy reference before comparing.
    first_dur = {}
    for (idx, sc, ia, dur) in ref_coi:
        k = (idx, sc, ia)
        d = int(dur)
        if k not in first_dur or d < first_dur[k]:
            first_dur[k] = d
    ref_coi = {
        k: v for k, v in ref_coi.items()
        if first_dur[(k[0], k[1], k[2])] == 1
    }
    coi_only_new = set(new_coi) - set(ref_coi)
    coi_only_ref = set(ref_coi) - set(new_coi)
    coi_diffs = [
        {"key": list(k), "new": new_coi[k], "ref": ref_coi[k]}
        for k in set(new_coi) & set(ref_coi) if new_coi[k] != ref_coi[k]
    ]
    out["coi"] = {
        "new_rows": len(new_coi), "ref_rows": len(ref_coi),
        "only_in_new": len(coi_only_new),
        "only_in_ref": len(coi_only_ref),
        "sample_only_in_new": [list(k) for k in sorted(coi_only_new)[:5]],
        "sample_only_in_ref": [list(k) for k in sorted(coi_only_ref)[:5]],
        "value_diff_count": len(coi_diffs),
        "sample_value_diffs": coi_diffs[:5],
    }

    # ── Target premiums (column remap) ─────────────────────────────────
    # new: Index(TRGPREM),IssueAge,Rate(MTP),Rate(CTP),Rate(TBL4PREM),
    #      Rate(TBL1MTP),Rate(TBL1CTP)
    # ref: Index,IssueAge,CTP,TBL1CTP,MTP,TBL1MTP
    _h, trg = _read(os.path.join(workup_dir, "RATE_TRGPREM.csv"))
    new_trg = {
        (r[0], r[1]): (_f(r[3]), _f(r[6]), _f(r[2]), _f(r[5]))  # ctp,tbl1ctp,mtp,tbl1mtp
        for r in trg
    }
    _h, rows = _read(os.path.join(ref_dir, "RATE_TRGPRM.csv"))
    ref_trg = {(r[0], r[1]): (_f(r[2]), _f(r[3]), _f(r[4]), _f(r[5])) for r in rows}
    trg_diffs = [
        {"key": list(k), "new": new_trg[k], "ref": ref_trg[k]}
        for k in set(new_trg) & set(ref_trg) if new_trg[k] != ref_trg[k]
    ]
    out["trgprem"] = {
        "new_rows": len(new_trg), "ref_rows": len(ref_trg),
        "only_in_new": len(set(new_trg) - set(ref_trg)),
        "only_in_ref": len(set(ref_trg) - set(new_trg)),
        "value_diff_count": len(trg_diffs),
        "sample_value_diffs": trg_diffs[:5],
    }

    match = (
        not out["pointer"]["only_in_new"] and not out["pointer"]["only_in_ref"]
        and not out["pointer"]["value_diffs"]
        and out["coi"]["only_in_new"] == 0 and out["coi"]["only_in_ref"] == 0
        and out["coi"]["value_diff_count"] == 0
        and out["trgprem"]["only_in_new"] == 0
        and out["trgprem"]["only_in_ref"] == 0
        and out["trgprem"]["value_diff_count"] == 0
    )
    out["MATCH"] = match
    return out


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage: compare_workup_to_reference.py <workup_dir> <ref_dir>"}))
        return 1
    result = compare(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2))
    return 0 if result["MATCH"] else 2


if __name__ == "__main__":
    sys.exit(main())
