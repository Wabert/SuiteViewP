"""Roll ISWL policies forward from recorded values and compare with CyberLife, read-only.

Usage:
    venv\\Scripts\\python.exe tools\\rerun\\verify_iswl_rollforward.py 11580276:01 [13034048:01 ...]
        [--output report.json] [--tolerance 0.10] [--quiet]
    venv\\Scripts\\python.exe tools\\rerun\\verify_iswl_rollforward.py --sample <csv> [--limit 40] ...

The RERUN engine (``project_policy``, ISWL rates from schema ``rates``) is started from
CyberLife's recorded post-deduction account value (``LH_POL_MVRY_VAL.CSV_AMT``) and fed
the premiums CyberLife processed: each unreversed, processed ``FH_FIXED`` PR row is one
billed payment, applied on the first monthliversary on or after its date. Two runs are
compared with the recorded monthliversary values of the last six months:

* **one-step** - each month starts again from CyberLife's recorded value on the prior
  monthliversary and projects one month. This isolates the month's mechanics: net
  premium, COI (``CINS_AMT``) and interest (``TOT_CRE_ITS_AMT``) against the record.
* **cumulative** - one projection from the oldest recorded value to the valuation date,
  showing how the monthly differences accumulate.

CyberLife keeps a fixed-fund bucket per premium and rounds each bucket's monthly interest
to the cent, and it credits a direct-bill receipt interest from its receipt date. The
engine credits one account value from the monthliversary. ``stub`` is that
receipt-date interest (net x ((1 + rate) ** (days / 365) - 1), informational); PAC
drafts taken before their due date and advance payments showed none. A month passes
when the one-step net premium and COI match to the cent and the one-step account value
(``diff``, or ``residual = diff + stub``) is within ``--tolerance`` (default 0.10); the
rest of the tolerance absorbs CyberLife's per-bucket interest rounding. Months with other financial
transactions (withdrawals, surrenders, premiums paid from the account value, loans
other than interest capitalization or a same-day equal loan and repayment) are
reported and excluded.
``--sample`` reads policies from a ``find_iswl_policies.py``/``sample_iswl_receipts.py``
CSV (columns CK_CMP_CD, CK_POLICY_NBR).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import traceback
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path

from dateutil.relativedelta import relativedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.local_dev import local_data_enabled

_PREMIUM = "PR"
# Premiums, monthly deductions, suspense in/out and anniversary loan-interest
# capitalization (the engine capitalizes loan interest itself).
_MODELLED = {"PR", "CD", "UI", "UO", "LC"}
# A same-day policy loan and loan payment of equal amounts leaves the AV unchanged.
_LOAN_PAIR = {"PL", "LP"}
_LOAN_FIELDS = tuple(
    f"{kind}_loan_{part}" for kind in ("regular", "preferred", "variable") for part in ("principal", "accrued"))


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except ValueError:
        return None


def _money(value):
    return None if value is None else round(float(value), 2)


def _history(pi, start: date, end: date):
    """Processed, unreversed FH_FIXED rows with start < ASOF_DT <= end."""
    rows = []
    for row in pi.fetch_table("FH_FIXED"):
        when = _as_date(row.get("ASOF_DT"))
        if when is None or not (start < when <= end):
            continue
        if str(row.get("FBB3_PROCD_IND", "")).strip() != "1":
            continue
        if any(str(row.get(flag, "")).strip() != "0" for flag in ("FCB0_REV_IND", "FCB2_REV_APPL_IND")):
            continue
        rows.append((when, str(row.get("TRANS") or "").strip().upper(), row))
    return sorted(rows, key=lambda item: (item[0], str(item[2].get("SEQ_NO"))))


def _monthliversaries(policy, start: date, end: date) -> list[date]:
    months = (start.year - policy.issue_date.year) * 12 + start.month - policy.issue_date.month
    dates = []
    while True:
        months += 1
        when = policy.issue_date + relativedelta(months=months)
        if when > end:
            return dates
        dates.append(when)


def _recorded(pi) -> dict:
    values = {}
    for row in pi.fetch_table("LH_POL_MVRY_VAL"):
        when = _as_date(row.get("MVRY_DT"))
        if when is not None:
            values[when] = {
                "av": _money(row.get("CSV_AMT")),
                "coi": _money(row.get("CINS_AMT")),
                "interest": _money(row.get("TOT_CRE_ITS_AMT")),
            }
    return values


def _start_basis(policy, start: date):
    """The basis on a recorded monthliversary: Value Rollback when it validates, else
    the recorded post-deduction AV, charges and loans only.

    The fallback is enough here: with TEFRA/TAMRA and forceouts off, ISWL account
    values do not depend on premiums-to-date, cost basis or targets, which Value
    Rollback refuses to reverse when retained history does not reconcile to totals.
    """
    from suiteview.illustration.core.value_rollback import apply_value_rollback

    if start == policy.valuation_date:
        return deepcopy(policy), "loaded valuation"
    try:
        return apply_value_rollback(policy, start), "value_rollback"
    except ValueError as exc:
        reason = str(exc).splitlines()[-1].lstrip("- ")
    snapshot = next(s for s in policy.rollback_snapshots if s.valuation_date == start)
    if snapshot.account_value is None:
        raise ValueError(f"No recorded account value on {start}.")
    result = deepcopy(policy)
    result.account_value = float(snapshot.account_value)
    for name in ("system_coi_charge", "system_expense_charge", "system_other_charge",
                 "system_monthly_deduction"):
        setattr(result, name, float(getattr(snapshot, name) or 0.0))
    for name in _LOAN_FIELDS:
        value = getattr(snapshot, name)
        if value is None and getattr(policy, name):
            raise ValueError(f"Historical {name} on {start} is not recoverable ({reason}).")
        setattr(result, name, float(value or 0.0))
    months = (start.year - policy.issue_date.year) * 12 + start.month - policy.issue_date.month
    year, month = divmod(months, 12)
    result.valuation_date = start
    result.policy_year, result.policy_month = year + 1, month + 1
    result.duration = months + 1
    result.attained_age = policy.issue_age + year
    return result, f"recorded AV only ({reason})"


def _project(basis, payments: dict, months: int):
    from suiteview.illustration.api import project_policy
    from suiteview.illustration.models.input_set import (
        DatedTransaction, IllustrationInputSet, IllustrationOptions, ScheduledTransaction, TransactionKind,
    )

    modal = float(basis.modal_premium or 0.0)
    dated = [
        DatedTransaction(TransactionKind.PREMIUM, when, count * modal,
                         metadata={"scheduled_current_year": True, "mode": "M"})
        for when, count in payments.items() if count
    ]
    inputs = IllustrationInputSet(
        scheduled_transactions=[ScheduledTransaction(TransactionKind.PREMIUM, 1, 0.0, mode="M")],
        dated_transactions=dated,
    )
    options = IllustrationOptions(conform_to_tefra=False, conform_to_tamra=False, guideline_forceouts=False)
    return project_policy(basis, inputs=inputs, options=options, months=months, stop_on_lapse=False).states


def verify(policy_number: str, company: str | None, tolerance: float) -> dict:
    from suiteview.illustration.api import load_policy_data
    from suiteview.illustration.core.interest_calc import interest_days
    from suiteview.illustration.core.value_rollback import available_rollback_dates
    from suiteview.polview.services.policy_service import get_policy_info

    pi = get_policy_info(policy_number, company_code=company)
    policy = load_policy_data(policy_number, company_code=company)
    rollback_dates = available_rollback_dates(policy)
    if not rollback_dates:
        return {"policy": policy_number, "error": "no recorded monthliversary values in the last six months"}
    start, end = rollback_dates[-1], policy.valuation_date
    mv_dates = _monthliversaries(policy, start, end)
    recorded = _recorded(pi)
    modal = float(policy.modal_premium or 0.0)

    receipts: dict[date, list] = {d: [] for d in mv_dates}
    other: dict[date, list] = {d: [] for d in mv_dates}
    loan_pairs: dict[tuple, float] = {}
    for when, code, row in _history(pi, start, end):
        target = next((d for d in mv_dates if when <= d), None)
        if target is None:
            continue
        amount = float(row.get("GROSS_AMT") or 0.0)
        if code == _PREMIUM:
            receipts[target].append((when, amount, float(row.get("NET_AMT") or 0.0)))
        elif code in _LOAN_PAIR:
            key = (target, when)
            loan_pairs[key] = loan_pairs.get(key, 0.0) + (amount if code == "PL" else -amount)
            other[target].append(f"{when} {code} {_money(amount)}")
        elif code not in _MODELLED:
            other[target].append(f"{when} {code} {_money(amount)}")
    neutral = {
        target for target in mv_dates
        if other[target] and all(code.split()[1] in _LOAN_PAIR for code in other[target])
        and all(abs(total) < 0.005 for (t, _d), total in loan_pairs.items() if t == target)
    }
    payments = {d: len(items) for d, items in receipts.items()}
    billing_notes = sorted({
        f"receipt {gross:.2f} differs from the billed premium {modal:.2f}"
        for items in receipts.values() for _d, gross, _n in items if abs(gross - modal) > 0.005
    })

    cumulative = _project(_start_basis(policy, start)[0], payments, len(mv_dates))[1:]
    rows = []
    prior = start
    rate = policy.current_interest_rate
    for index, when in enumerate(mv_dates):
        basis, basis_note = _start_basis(policy, prior)
        step = _project(basis, {when: payments[when]}, 1)
        state = step[1]
        record = recorded.get(when, {})
        stub = sum(net * ((1.0 + rate) ** (interest_days(day, when) / 365.0) - 1.0)
                   for day, _g, net in receipts[when])
        cyberlife_net = round(sum(n for _d, _g, n in receipts[when]), 2)
        diff = None if record.get("av") is None else round(state.av_after_deduction - record["av"], 2)
        residual = None if diff is None else round(diff + stub, 2)
        excluded = bool(other[when]) and when not in neutral
        month_ok = (
            not excluded and residual is not None
            and min(abs(diff), abs(residual)) <= tolerance
            and abs(round(state.net_premium, 2) - cyberlife_net) <= 0.005
            and record.get("coi") is not None and abs(round(state.total_coi_charge, 2) - record["coi"]) <= 0.015
        )
        rows.append({
            "date": when.isoformat(),
            "start_basis": basis_note,
            "payments": payments[when],
            "engine_net": _money(state.net_premium),
            "cyberlife_net": cyberlife_net,
            "engine_coi": _money(state.total_coi_charge),
            "cyberlife_coi": record.get("coi"),
            "engine_interest": _money(step[0].interest_credited),
            "cyberlife_interest": record.get("interest"),
            "engine_av": _money(state.av_after_deduction),
            "cyberlife_av": record.get("av"),
            "one_step_diff": diff,
            "stub": round(stub, 2),
            "residual": residual,
            "cumulative_av": _money(cumulative[index].av_after_deduction),
            "cumulative_diff": None if record.get("av") is None else round(
                cumulative[index].av_after_deduction - record["av"], 2),
            "excluded": [] if when in neutral else other[when],
            "neutral": other[when] if when in neutral else [],
            "passed": month_ok,
        })
        prior = when
    checked = [r for r in rows if not r["excluded"]]
    return {
        "policy": policy.policy_number,
        "company": policy.company_code,
        "plancode": policy.plancode,
        "rollback_from": start.isoformat(),
        "valuation_date": end.isoformat() if end else None,
        "modal_premium": modal,
        "billing_frequency": policy.billing_frequency,
        "bill_form": policy.bill_form_code,
        "current_interest_rate": policy.current_interest_rate,
        "months_checked": len(checked),
        "months_excluded": len(rows) - len(checked),
        "max_one_step_diff": max((abs(r["one_step_diff"]) for r in checked if r["one_step_diff"] is not None),
                                 default=None),
        "max_one_step_residual": max((abs(r["residual"]) for r in checked if r["residual"] is not None),
                                     default=None),
        "max_cumulative_diff": max((abs(r["cumulative_diff"]) for r in checked if r["cumulative_diff"] is not None),
                                   default=None),
        "passed": bool(checked) and all(r["passed"] for r in checked),
        "billing_notes": billing_notes,
        "rows": rows,
    }


def _targets(args) -> list[tuple[str, str | None]]:
    targets = []
    for item in args.policies:
        number, _, company = item.partition(":")
        targets.append((number.strip(), company.strip() or None))
    if args.sample:
        with open(args.sample, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                targets.append((row["CK_POLICY_NBR"].strip(), row["CK_CMP_CD"].strip()))
    return targets[: args.limit] if args.limit else targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policies", nargs="*", help="policy[:company]")
    parser.add_argument("--sample", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--tolerance", type=float, default=0.10)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true", help="print one summary line per policy")
    args = parser.parse_args()
    if local_data_enabled():
        raise RuntimeError("The roll-forward check reads live CyberLife records only.")
    reports = []
    for number, company in _targets(args):
        try:
            report = verify(number, company, args.tolerance)
        except Exception as exc:  # keep checking the remaining policies
            report = {"policy": number, "company": company, "error": f"{type(exc).__name__}: {exc}",
                      "trace": traceback.format_exc()[-1500:]}
        reports.append(report)
        if args.quiet:
            keys = ("policy", "plancode", "billing_frequency", "bill_form", "months_checked", "months_excluded",
                    "max_one_step_diff", "max_one_step_residual", "max_cumulative_diff", "passed", "error")
            print(json.dumps({k: report.get(k) for k in keys}, default=str))
        else:
            print(json.dumps(report, indent=1, default=str))
        sys.stdout.flush()
    summary = {
        "checked": len(reports),
        "passed": sum(1 for r in reports if r.get("passed")),
        "errors": sum(1 for r in reports if r.get("error")),
        "months_checked": sum(r.get("months_checked") or 0 for r in reports),
        "months_passed": sum(1 for r in reports for row in r.get("rows") or [] if row["passed"]),
    }
    print(json.dumps({"summary": summary}))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"summary": summary, "reports": reports}, indent=1, default=str),
                               encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
