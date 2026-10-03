"""SuiteView's CVAT net single premium (CyberLife NS target) per policy, read-only.

Usage:
    venv\\Scripts\\python.exe -B tools\\rerun\\cvat_nsp_check.py --input expected_ns.csv --out results.csv
        [--workers 4] [--region CKPR] [--no-fackler]

``--input`` is a CSV with a company and policy column (``company``/``CK_CMP_CD`` and
``policy``/``CK_POLICY_NBR``). Optional columns ``expected_ns`` (or ``NS_AMT``/``TAR_PRM_AMT``)
and ``ns_date`` (or ``NS_DT``/``TAR_DT``) give CyberLife's NS target and its date; when
absent they are read from DB2 ``LH_POL_TARGET`` (``TAR_TYP_CD = 'NS'``).

For each policy the output row has SuiteView's NS at the NS date by present value
(``sv_ns``), the same NS reached by a Fackler roll-forward from the issue-date NSP
(``fackler_ns``), the per-$1,000 NSP, the interest rate, the difference to the expected
NS and a status (``match`` within half a cent, ``mismatch``, ``error``). Live DB2 only:
``SUITEVIEW_LOCAL_DATA`` must be unset.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FIELDS = [
    "company", "policy", "plancode", "status", "ns_date", "attained_age", "interest",
    "face", "coverages", "expected_ns", "sv_ns", "diff", "sv_nsp_per_1000", "fackler_ns",
    "fackler_diff", "substandard", "ratings", "substd_variants_matching", "nsp_table", "is_cvat", "product",
    "error", "seconds",
]
_ALIASES = {
    "company": ("company", "ck_cmp_cd", "company_code"),
    "policy": ("policy", "ck_policy_nbr", "policy_number"),
    "expected_ns": ("expected_ns", "ns_amt", "tar_prm_amt", "ns_target", "ns"),
    "ns_date": ("ns_date", "ns_dt", "tar_dt"),
}


def _init(profile: str) -> None:
    sys.dont_write_bytecode = True
    os.environ.setdefault("SUITEVIEW_PROFILE_DIR", profile)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def _pick(row: dict, name: str) -> str:
    lowered = {k.strip().lower(): v for k, v in row.items() if k}
    for alias in _ALIASES[name]:
        value = lowered.get(alias)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _parse_date(text: str):
    if not text:
        return None
    return date.fromisoformat(text.strip()[:10])


def _db2_ns_target(company: str, policy: str, region: str):
    from suiteview.core.db2_connection import DB2Connection

    sql = (
        "SELECT T.TAR_PRM_AMT, T.TAR_DT FROM DB2TAB.LH_BAS_POL P JOIN DB2TAB.LH_POL_TARGET T "
        "ON T.CK_SYS_CD = P.CK_SYS_CD AND T.CK_CMP_CD = P.CK_CMP_CD AND T.TCH_POL_ID = P.TCH_POL_ID "
        "WHERE P.CK_CMP_CD = ? AND P.CK_POLICY_NBR = ? AND T.TAR_TYP_CD = 'NS' "
        "ORDER BY T.TAR_DT DESC FETCH FIRST 1 ROW ONLY")
    _, rows = DB2Connection(region).execute_query_with_headers_isolated(sql, (company, policy))
    if not rows:
        return None, None
    amount, when = rows[0]
    return (float(amount) if amount is not None else None), _parse_date(str(when))


def _latest_anniversary(policy) -> date:
    from dateutil.relativedelta import relativedelta

    years = max(0, int(policy.policy_year) - 1)
    return policy.issue_date + relativedelta(years=years)


def check_policy(company: str, policy_number: str, expected=None, ns_date=None,
                 region: str = "CKPR", fackler: bool = True) -> dict:
    """One output row: SuiteView's NS for the policy at the NS date."""
    started = time.time()
    out = {"company": company, "policy": policy_number}
    try:
        from dateutil.relativedelta import relativedelta

        from suiteview.illustration.api import _load_plancode_config, load_policy_data
        from suiteview.illustration.core.cvat_nsp import (
            CvatCorridor, IswlNspBasis, SubstandardBasis, UlNspBasis, nsp_at, nsp_basis, substandard_in_nsp)
        from suiteview.illustration.core.rate_loader import load_rates

        if expected is None or ns_date is None:
            db_amount, db_date = _db2_ns_target(company, policy_number, region)
            expected = db_amount if expected is None else expected
            ns_date = db_date if ns_date is None else ns_date
        policy = load_policy_data(policy_number, region=region, company_code=company)
        config = _load_plancode_config(policy.plancode)
        out.update(plancode=policy.plancode, is_cvat=int(bool(policy.is_cvat)),
                   product="ISWL" if config.is_iswl else "UL")
        as_of = ns_date or _latest_anniversary(policy)
        guaranteed = None if config.is_iswl else load_rates(policy, config, coi_scale=0)
        ns = nsp_at(policy, config, guaranteed, as_of)
        sv_ns = round(ns.amount + 1e-9, 2)
        rated = [s for s in policy.segments if (s.table_rating or 0) > 0 or (s.flat_extra or 0) > 0]
        out["ratings"] = ";".join(
            f"{s.coverage_phase}:T{s.table_rating or 0}/F{s.flat_extra or 0:g}" for s in rated)
        if config.is_iswl:
            out["nsp_table"] = policy.segments[0].nsp_mortality_table
            if expected is not None:
                hits = []
                for name, flag in (("immediate", True), ("curtate", False)):
                    basis = IswlNspBasis(policy, immediate_claims=flag)
                    value = round(nsp_at(policy, config, None, as_of, basis=basis).amount + 1e-9, 2)
                    if abs(value - float(expected)) < 0.005:
                        hits.append(name)
                out["substd_variants_matching"] = "|".join(hits) or "neither"
        if rated and not config.is_iswl:
            rule = substandard_in_nsp(policy)
            out["substandard"] = f"T{int(rule.table)}F{int(rule.flat)}"
            if expected is not None:
                hits = []
                for name, variant in (("none", SubstandardBasis()), ("table", SubstandardBasis(table=True)),
                                      ("flat", SubstandardBasis(flat=True)),
                                      ("both", SubstandardBasis(table=True, flat=True))):
                    basis = UlNspBasis(policy, config, guaranteed, substandard=variant)
                    value = round(nsp_at(policy, config, guaranteed, as_of, basis=basis).amount + 1e-9, 2)
                    if abs(value - float(expected)) < 0.005:
                        hits.append(name)
                out["substd_variants_matching"] = "|".join(hits) or "neither"
        years = relativedelta(as_of, policy.issue_date).years
        out.update(
            ns_date=as_of.isoformat(), attained_age=policy.issue_age + years,
            interest=ns.annual_rate, face=round(ns.face, 2), coverages=len(ns.coverages),
            sv_ns=f"{sv_ns:.2f}", sv_nsp_per_1000=f"{ns.per_thousand:.6f}")
        if fackler:
            # Present value once at issue, then Fackler steps to the NS date.
            corridor = CvatCorridor(nsp_basis(policy, config, guaranteed))
            corridor.nsp_by_coverage(policy.issue_date)
            out["fackler_ns"] = f"{round(corridor.ns_amount(as_of) + 1e-9, 2):.2f}"
        if expected is not None:
            out["expected_ns"] = f"{float(expected):.2f}"
            out["diff"] = f"{sv_ns - float(expected):.2f}"
            if fackler:
                out["fackler_diff"] = f"{float(out['fackler_ns']) - float(expected):.2f}"
            out["status"] = "match" if abs(sv_ns - float(expected)) < 0.005 else "mismatch"
        else:
            out["status"] = "no_expected"
    except Exception as exc:  # reported per policy, never hidden
        out.update(status="error", error=f"{type(exc).__name__}: {str(exc)[:300]}",
                   expected_ns="" if expected is None else f"{float(expected):.2f}")
    out["seconds"] = round(time.time() - started, 2)
    return out

def _read_input(path: Path) -> list[tuple]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    keys = []
    for row in rows:
        company, policy = _pick(row, "company"), _pick(row, "policy")
        if not policy:
            continue
        expected = _pick(row, "expected_ns")
        keys.append((company.zfill(2) if company.isdigit() else company, policy,
                     float(expected) if expected else None, _parse_date(_pick(row, "ns_date"))))
    return keys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--no-fackler", action="store_true")
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA"):
        raise SystemExit("cvat_nsp_check reads live DB2 only; unset SUITEVIEW_LOCAL_DATA.")
    keys = _read_input(args.input)
    profile = tempfile.mkdtemp(prefix="suiteview-cvat-nsp-")
    results = []
    with ProcessPoolExecutor(max_workers=max(1, args.workers), initializer=_init,
                             initargs=(profile,)) as pool:
        futures = [pool.submit(check_policy, c, p, e, d, args.region, not args.no_fackler)
                   for c, p, e, d in keys]
        for done, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if done % 25 == 0 or done == len(futures):
                print(f"{done}/{len(futures)}", flush=True)
    order = {(c, p): i for i, (c, p, _, _) in enumerate(keys)}
    results.sort(key=lambda r: order.get((r["company"], r["policy"]), 0))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    counts: dict = {}
    for row in results:
        counts[row.get("status")] = counts.get(row.get("status"), 0) + 1
    print("status:", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
