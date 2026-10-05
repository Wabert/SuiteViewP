"""Decompose RERUN-vs-CyberLife monthliversary account-value differences.

Read-only diagnostic for the RERUN CyberLife baseline (DB2 CKPR and UL_Rates are
only read). Run from the repository root::

    venv\\Scripts\\python.exe tools\\rerun\\baseline_av_decompose.py fetch
        --results <baseline>\\policy_results --work <work_dir>
    venv\\Scripts\\python.exe tools\\rerun\\baseline_av_decompose.py engine
        --results <baseline>\\policy_results --work <work_dir>
    venv\\Scripts\\python.exe tools\\rerun\\baseline_av_decompose.py fit
        --results <baseline>\\policy_results --work <work_dir> --output <out.json>

``fetch``  stores, per policy, the raw CyberLife ``LH_POL_MVRY_VAL`` rows (incl.
           ``TOT_CRE_ITS_AMT`` - interest CyberLife actually credited in the
           month), ``LH_FND_VAL_LOAN`` rows and the FH_FIXED cash-flow rows
           (``NET_AMT``/``GROSS_AMT``/``CHARGE_AMT``/``INT_RT``) after the
           rollback date, plus the ``dbo.CYBERLIFE_PDF`` interest coding.
``engine`` replays each policy exactly as ``baseline_history_compare.py`` does
           (same rollback basis, same bucketed cash flows,
           ``ProjectionTiming.CYBERLIFE_MONTHLIVERSARY``) and stores compact
           monthly engine states.
``fit``    for every pair of consecutive recorded monthliversaries compares
           CyberLife's recorded interest with (a) the documented CyberLife rule
           and (b) the engine's rule, both seeded from CyberLife's own opening
           values, and attributes the RERUN AV difference to its components.

The CyberLife crediting rule (CyberDoc B11 pp. 32-37; compound rule from PDF
``DIFFCMPD``: 1 daily, 2 monthly - CyberDoc D20 FIFFCMPD)::

    unloaned  (CV_prev - LoanPrincipal_prev) * F(i, n)
    loaned    LoanPrincipal_prev * F(i_loan, n)
    premium   NET * F(i, days(receipt -> MV) + 1)        (receipt day and MV day included)
    withdrawal  - GROSS * F(i, days(withdrawal -> MV))
    F(i, n) = (1 + i) ** (n / 365) - 1   (daily)  or  (1 + i) ** (1/12) - 1  (monthly)
    n = days from the previous monthliversary to the current one (Feb 29 excluded)
"""

from __future__ import annotations

import argparse
import calendar
import json
import sys
import traceback
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rerun.baseline_common import REGION, json_dump, json_load, parse_date  # noqa: E402

PREMIUM_CODES = {"PR", "PI", "PA", "PF", "PT", "PB", "PW"}
LOAN_CODES = {"LN", "LG", "LF", "LM", "LA"}
LOAN_REPAYMENT_CODES = {"PL", "PP", "PX", "IP", "IC", "PV"}
WITHDRAWAL_CODES = {"SN", "SG", "SA", "S6", "SW", "SM", "RC", "RD", "SV"}
CASH_FLOW_CODES = PREMIUM_CODES | LOAN_CODES | LOAN_REPAYMENT_CODES | WITHDRAWAL_CODES
PDF_FIELDS = ("DIFFCMPD-FIX-COMPOUND", "DULCVICP-COMPOUND", "DULPRCRD-PREM-CREDIT-INT", "DULLINRT-LOAN-AMT-INT-RATE",
              "DULLPCRT-PREF-INTEREST-RATE", "DIFFGIRT-GUAR-INT-RATE")
ENGINE_FIELDS = (
    "date", "duration", "policy_year", "policy_month", "gross_premium", "requested_premium", "net_premium",
    "premium_capped", "premium_capped_by_guideline", "premium_capped_by_tamra", "tamra_year", "total_deduction",
    "interest_credited", "annual_interest_rate", "bonus_interest_rate", "effective_annual_rate",
    "monthly_interest_rate", "days_in_month", "reg_impaired_int", "pref_impaired_int", "unimpaired_int",
    "input_withdrawal", "max_net_withdrawal", "applied_net_withdrawal", "gross_withdrawal", "policy_debt",
    "rg_loan_princ", "rg_loan_accrued", "pf_loan_princ", "pf_loan_accrued", "end_rg_loan_princ",
    "end_rg_loan_accrued", "end_pf_loan_princ", "end_pf_loan_accrued", "applied_regular_loan",
    "applied_preferred_loan", "applied_loan_repayment", "av_end_of_month", "av_after_deduction",
)


# ── shared helpers ───────────────────────────────────────────────────────────

def _scalar(value: Any) -> Any:
    if isinstance(value, date):
        return str(value)
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)


def _num(value: Any) -> float:
    try:
        return float(str(value).strip() or 0.0) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def interest_days(start: date, end: date) -> int:
    """Days in ``(start, end]`` on CyberLife's 365-day year (Feb 29 earns nothing)."""
    if end <= start:
        return 0
    days = (end - start).days
    for year in range(start.year, end.year + 1):
        if calendar.isleap(year) and start < date(year, 2, 29) <= end:
            days -= 1
    return days


def engine_days(month_date: date) -> int:
    """Day count ``interest_calc._days_in_month`` uses for the engine row dated ``month_date``."""
    days = calendar.monthrange(month_date.year, month_date.month)[1]
    if calendar.isleap(month_date.year) and month_date.month == 2 and month_date.day < 29:
        days -= 1
    return days


def factor(rate: float, days: int, monthly: bool = False) -> float:
    if monthly:
        return (1.0 + rate) ** (1.0 / 12.0) - 1.0
    return (1.0 + rate) ** (max(days, 0) / 365.0) - 1.0


def _results(results_dir: Path, keys: list[str]) -> list[dict[str, Any]]:
    out = []
    for path in sorted(results_dir.glob("*.json")):
        result = json_load(path)
        if keys and result.get("key") not in keys:
            continue
        if result.get("status") != "compared" or not result.get("monthly"):
            continue
        out.append(result)
    return out


# ── fetch ────────────────────────────────────────────────────────────────────

def fetch_pdf_coding(plancodes: list[str]) -> dict[str, dict[str, str]]:
    from suiteview.core.data_access.connections import ConnectionFactory

    coding: dict[str, dict[str, str]] = defaultdict(dict)
    conn = ConnectionFactory().connect_ul_rates(readonly=True)
    try:
        cursor = conn.cursor()
        for start in range(0, len(plancodes), 50):
            chunk = plancodes[start:start + 50]
            marks = ", ".join("?" for _ in chunk)
            fmarks = ", ".join("?" for _ in PDF_FIELDS)
            cursor.execute(
                "SELECT UserID, Plancode, FieldName, FieldValue FROM dbo.CYBERLIFE_PDF "
                f"WHERE LTRIM(RTRIM(Plancode)) IN ({marks}) AND LTRIM(RTRIM(FieldName)) IN ({fmarks})",
                tuple(chunk) + PDF_FIELDS,
            )
            for user, plan, field, value in cursor.fetchall():
                plan_key = str(plan).strip().upper()
                coding[plan_key][str(field).strip()] = None if value is None else str(value).strip()
                coding[plan_key]["UserID"] = str(user).strip()
    finally:
        conn.close()
    return dict(coding)


def cmd_fetch(args) -> int:
    from suiteview.polview.services.policy_service import get_policy_info

    work = Path(args.work)
    cyber_dir = work / "cyber"
    cyber_dir.mkdir(parents=True, exist_ok=True)
    results = _results(Path(args.results), args.policies)
    plancodes = sorted({str(r.get("plancode") or "").strip().upper() for r in results} - {""})
    json_dump(work / "pdf_interest_coding.json", fetch_pdf_coding(plancodes))
    for result in results:
        target = cyber_dir / f"{result['key']}.json"
        if target.exists() and not args.force:
            continue
        start = parse_date(result.get("rollback_date"))
        try:
            pi = get_policy_info(result["policy_number"], REGION, result["company"])
            transactions = []
            for txn in pi.activity.get_transactions():
                code = (txn.trans_code or "").strip().upper()
                if txn.trans_date is None or (start and txn.trans_date <= start) or code not in CASH_FLOW_CODES:
                    continue
                transactions.append({"date": str(txn.trans_date), "code": code, "seq": txn.sequence_number,
                                     "raw": {k: _scalar(v) for k, v in txn.raw_data.items()}})
            json_dump(target, {
                "key": result["key"],
                "LH_POL_MVRY_VAL": [{k: _scalar(v) for k, v in row.items()} for row in pi.fetch_table("LH_POL_MVRY_VAL")],
                "LH_FND_VAL_LOAN": [{k: _scalar(v) for k, v in row.items()} for row in pi.fetch_table("LH_FND_VAL_LOAN")],
                "transactions": transactions,
            })
            print(result["key"], "ok", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(result["key"], "error", f"{type(exc).__name__}: {exc}", flush=True)
    return 0


# ── engine ───────────────────────────────────────────────────────────────────

def replay_engine(result: dict[str, Any]) -> dict[str, Any]:
    """Re-run the harness projection for one policy exactly as baseline_history_compare does."""
    from suiteview.illustration.api import load_policy_data, project_policy
    from suiteview.illustration.core.calc_engine import ProjectionTiming
    from suiteview.illustration.core.rate_loader import load_rates
    from suiteview.illustration.core.value_rollback import apply_value_rollback
    from suiteview.illustration.models.input_set import IllustrationInputSet, ScheduledTransaction, TransactionKind
    from suiteview.illustration.models.plancode_config import load_plancode
    from suiteview.polview.services.policy_service import get_policy_info
    from tools.rerun.baseline_history_compare import (
        _actual_transactions, _baseline_basis_from_snapshot, _exclude_shadow_for_history_replay, _months_between,
    )

    pi = get_policy_info(result["policy_number"], REGION, result["company"])
    policy = load_policy_data(result["policy_number"], region=REGION, company_code=result["company"])
    config = load_plancode(policy.plancode)
    rates = load_rates(policy, config)
    start = parse_date(result["rollback_date"])
    if result.get("rollback_basis") == "canonical rollback":
        historical = apply_value_rollback(policy, start, allow_missing_shadow=True)
    else:
        historical = _baseline_basis_from_snapshot(policy, start)
    _exclude_shadow_for_history_replay(historical)
    dated, _audit, _codes = _actual_transactions(pi, historical, start, policy.valuation_date)
    inputs = IllustrationInputSet(
        scheduled_transactions=[ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=1, amount=0.0, mode="M")],
        dated_transactions=dated,
    )
    run = project_policy(historical, config=config, rates=rates, inputs=inputs,
                         months=_months_between(start, policy.valuation_date), stop_on_lapse=False,
                         timing=ProjectionTiming.CYBERLIFE_MONTHLIVERSARY)
    states = []
    for state in run.states:
        row = {name: _scalar(getattr(state, name, None)) for name in ENGINE_FIELDS}
        detail = getattr(state, "premium_allowance_detail", None) or {}
        row["allowance"] = {k: detail.get(k) for k in ("GP_Allowance0", "NPT Allowance0", "TAMRA_Allowance0", "Annual Cap2")}
        states.append(row)
    return {
        "key": result["key"],
        "policy": {
            "is_cvat": bool(getattr(historical, "is_cvat", False)), "is_gpt": bool(getattr(historical, "is_gpt", False)),
            "is_mec": bool(getattr(historical, "is_mec", False)), "db_option": getattr(historical, "db_option", None),
            "total_face": getattr(historical, "total_face", None),
            "current_interest_rate": getattr(historical, "current_interest_rate", None),
            "current_interest_rate_source": getattr(historical, "current_interest_rate_source", ""),
        },
        "config": {
            "interest_method": config.interest_method, "cint_key": config.cint_key, "gint": config.gint,
            "reg_credit": config.loan_charge_rate_curr or config.loan_charge_rate_guar or historical.guaranteed_interest_rate,
            "pref_credit": config.pref_loan_charge_rate_curr or config.pref_loan_charge_rate_guar or historical.guaranteed_interest_rate,
            "withdrawal_fee": config.withdrawal_fee, "min_face_after_wd": config.min_face_after_wd,
        },
        "states": states,
    }


def cmd_engine(args) -> int:
    engine_dir = Path(args.work) / "engine"
    engine_dir.mkdir(parents=True, exist_ok=True)
    for result in _results(Path(args.results), args.policies):
        target = engine_dir / f"{result['key']}.json"
        if target.exists() and not args.force:
            continue
        try:
            json_dump(target, replay_engine(result))
            print(result["key"], "ok", flush=True)
        except Exception as exc:  # noqa: BLE001
            json_dump(target, {"key": result["key"], "error": f"{type(exc).__name__}: {exc}",
                               "traceback": traceback.format_exc()[-3000:]})
            print(result["key"], "error", f"{type(exc).__name__}: {exc}", flush=True)
    return 0


# ── fit ──────────────────────────────────────────────────────────────────────

def _mv_rows(cyber: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("MVRY_DT"))[:10]: row for row in cyber.get("LH_POL_MVRY_VAL", [])}


def _loan_principal(cyber: dict[str, Any], when: str) -> tuple[float, float]:
    regular = preferred = 0.0
    for row in cyber.get("LH_FND_VAL_LOAN", []):
        if str(row.get("MVRY_DT"))[:10] != when:
            continue
        amount = _num(row.get("LN_PRI_AMT"))
        if str(row.get("PRF_LN_IND") or "").strip() == "1":
            preferred += amount
        else:
            regular += amount
    return regular, preferred


def _cash_flows(cyber: dict[str, Any], prev: date, cur: date) -> dict[str, list[dict[str, Any]]]:
    """FH_FIXED cash flows in ``(prev, cur]`` grouped as CyberLife applies them."""
    flows: dict[str, list[dict[str, Any]]] = {"premium": [], "withdrawal": [], "loan": [], "repay": []}
    withdrawal_events: dict[tuple, dict[str, Any]] = {}
    for txn in cyber.get("transactions", []):
        raw = txn.get("raw") or {}
        when = parse_date(raw.get("ASOF_DT") or txn.get("date"))
        if when is None or when <= prev or when > cur:
            continue
        if str(raw.get("FCB0_REV_IND") or "").strip() == "1" or str(raw.get("FBB3_PROCD_IND") or "").strip() == "0":
            continue
        code = txn["code"]
        gross, net, charge = _num(raw.get("GROSS_AMT")), _num(raw.get("NET_AMT")), _num(raw.get("CHARGE_AMT"))
        item = {"date": str(when), "code": code, "gross": gross, "net": net, "charge": charge,
                "int_rt": _num(raw.get("INT_RT")), "seq": txn.get("seq")}
        if code in PREMIUM_CODES:
            flows["premium"].append(item)
        elif code in WITHDRAWAL_CODES:
            event = withdrawal_events.setdefault((str(when), code), {"date": str(when), "code": code, "gross": 0.0,
                                                                     "net": 0.0, "charge": 0.0, "pieces": 0})
            event["gross"] += gross
            event["net"] += net
            event["charge"] += charge
            event["pieces"] += 1
        elif code in LOAN_CODES:
            flows["loan"].append(item)
        elif code in LOAN_REPAYMENT_CODES:
            flows["repay"].append(item)
    flows["withdrawal"] = list(withdrawal_events.values())
    return flows


class RateBook:
    """Engine-equivalent declared rate per plancode/date and plancode config."""

    def __init__(self):
        self._cache: dict[tuple, Any] = {}

    def plan(self, plancode: str):
        key = ("plan", plancode)
        if key not in self._cache:
            from suiteview.illustration.models.plancode_config import load_plancode
            self._cache[key] = load_plancode(plancode)
        return self._cache[key]

    def declared(self, company: str, plancode: str, as_of: date) -> float:
        key = ("rate", company, plancode, as_of)
        if key not in self._cache:
            from suiteview.illustration.core.declared_rates import ul_current_declared_rate
            cfg = self.plan(plancode)
            found = ul_current_declared_rate(company, plancode, as_of, cfg.gint, cint_key=cfg.cint_key)
            self._cache[key] = found.rate if found else cfg.gint
        return self._cache[key]

    def bonus(self, plancode: str, as_of: date, policy_year: int, av: float,
              fixed_rate: float, gint: float) -> float:
        from suiteview.illustration.core.bonus_rates import load_bonus_config
        cfg = load_bonus_config(plancode, as_of).with_excess_cap(fixed_rate, gint)
        bonus = cfg.duration_bonus(policy_year)
        if cfg.bonus_av_rate > 0 and cfg.bonus_av_threshold > 0 and av >= cfg.bonus_av_threshold:
            bonus += cfg.bonus_av_rate
        return bonus


def decompose_policy(result: dict[str, Any], cyber: dict[str, Any] | None, engine: dict[str, Any] | None,
                     pdf: dict[str, Any], book: RateBook) -> dict[str, Any]:
    company = result["company"]
    plancode = str(result.get("plancode") or "").strip().upper()
    cfg = book.plan(plancode)
    pdf_row = pdf.get(plancode, {})
    cyber_monthly = str(pdf_row.get("DIFFCMPD-FIX-COMPOUND") or "1") == "2"
    engine_monthly = cfg.interest_method != "ExactDays"
    reg_credit = cfg.loan_charge_rate_curr or cfg.loan_charge_rate_guar or cfg.gint
    pref_credit = cfg.pref_loan_charge_rate_curr or cfg.pref_loan_charge_rate_guar or cfg.gint
    mv = _mv_rows(cyber or {})
    engine_states = {s["date"]: s for s in (engine or {}).get("states", []) if s.get("date")}
    monthly = [row for row in result["monthly"] if row.get("date") and row.get("av")]
    rows = []
    cumulative = Counter()
    for prev_row, cur_row in zip(monthly, monthly[1:]):
        prev, cur = parse_date(prev_row["date"]), parse_date(cur_row["date"])
        mv_prev, mv_cur = mv.get(prev_row["date"]), mv.get(cur_row["date"])
        if mv_prev is None or mv_cur is None:
            continue
        open_av, close_av = _num(mv_prev.get("CSV_AMT")), _num(mv_cur.get("CSV_AMT"))
        recorded = _num(mv_cur.get("TOT_CRE_ITS_AMT"))
        guaranteed_recorded = _num(mv_cur.get("GUA_RT_ERN_ITS_AMT"))
        md = _num(mv_cur.get("CINS_AMT")) + _num(mv_cur.get("EXP_CRG_AMT")) + _num(mv_cur.get("OTH_PRM_AMT"))
        flows = _cash_flows(cyber or {}, prev, cur)
        net_premium = sum(p["net"] for p in flows["premium"])
        gross_wd = sum(w["gross"] for w in flows["withdrawal"])
        identity_residual = close_av - (open_av + recorded + net_premium - md - gross_wd)
        reg_loan, pref_loan = _loan_principal(cyber or {}, prev_row["date"])
        loaned = min(reg_loan + pref_loan, max(open_av, 0.0))
        rate = book.declared(company, plancode, cur)
        bonus = book.bonus(plancode, cur, int(cur_row.get("policy_year") or 0), open_av,
                           rate, cfg.gint)
        eff = rate + bonus
        span = interest_days(prev, cur)

        def cv_interest(monthly_rule: bool, days: int) -> float:
            if open_av <= 0:
                return 0.0
            free = open_av - loaned
            total = round(free * factor(eff, days, monthly_rule), 2)
            if loaned:
                reg_share = loaned * (reg_loan / (reg_loan + pref_loan))
                total += round(reg_share * factor(reg_credit, days, monthly_rule), 2)
                total += round((loaned - reg_share) * factor(pref_credit, days, monthly_rule), 2)
            return total

        cl_cv = cv_interest(cyber_monthly, span)
        cl_prem = sum(round(p["net"] * factor(eff, (cur - parse_date(p["date"])).days + 1), 2)
                      for p in flows["premium"])
        cl_wd = -sum(round(w["gross"] * factor(eff, (cur - parse_date(w["date"])).days), 2) for w in flows["withdrawal"])
        cl_loan = sum(round(ln["gross"] * (factor(reg_credit, (cur - parse_date(ln["date"])).days)
                                           - factor(eff, (cur - parse_date(ln["date"])).days)), 2)
                      for ln in flows["loan"])
        cl_repay = sum(round(rp["gross"] * (factor(eff, (cur - parse_date(rp["date"])).days)
                                            - factor(reg_credit, (cur - parse_date(rp["date"])).days)), 2)
                       for rp in flows["repay"])
        cl_total = cl_cv + cl_prem + cl_wd + cl_loan + cl_repay
        eng_cv = cv_interest(engine_monthly, engine_days(cur))
        candidates = {
            "cyberlife_daily_prior_span": cv_interest(False, span),
            "engine_daily_current_month_days": cv_interest(False, engine_days(cur)),
            "monthly_compound_1_12": cv_interest(True, span),
            "simple_daily_prior_span": round(max(open_av, 0.0) * eff * span / 365, 2),
            "simple_1_12": round(max(open_av, 0.0) * eff / 12, 2),
        }
        candidate_hits = {name: abs(recorded - value) <= 0.021 for name, value in candidates.items()}
        engine_state = engine_states.get(cur_row["date"])
        components = {
            "day_count_or_compounding": round(eng_cv - cl_cv, 2),
            "premium_interest_from_receipt": round(-cl_prem, 2),
            "withdrawal_interest_adjustment": round(-cl_wd, 2),
            "loan_tx_interest_adjustment": round(-(cl_loan + cl_repay), 2),
        }
        components["cyber_rule_minus_recorded"] = round(cl_total - recorded, 2)
        engine_view = None
        av_diff = (cur_row.get("av") or {}).get("diff")
        prev_diff = (prev_row.get("av") or {}).get("diff") or 0.0
        if engine_state:
            eng_net = _num(engine_state.get("net_premium"))
            eng_wd = _num(engine_state.get("gross_withdrawal"))
            eng_md = _num(engine_state.get("total_deduction"))
            eng_int = _num(engine_state.get("interest_credited"))
            explained_interest = sum(components.values())
            components.update({
                "interest_on_carried_difference_and_other": round((eng_int - recorded) - explained_interest, 2),
                "net_premium_rerun_minus_cyber": round(eng_net - net_premium, 2),
                "withdrawal_rerun_minus_cyber": round(-(eng_wd - gross_wd), 2),
                "md_rerun_minus_cyber": round(-(eng_md - md), 2),
            })
            if av_diff is not None:
                components["unexplained"] = round((av_diff - prev_diff) - sum(components.values()), 2)
            engine_view = {
                "interest": engine_state.get("interest_credited"), "days": engine_state.get("days_in_month"),
                "rate": engine_state.get("effective_annual_rate"), "gross_premium": engine_state.get("gross_premium"),
                "requested_premium": engine_state.get("requested_premium"), "net_premium": eng_net,
                "premium_capped": engine_state.get("premium_capped"),
                "premium_capped_by_tamra": engine_state.get("premium_capped_by_tamra"),
                "allowance": engine_state.get("allowance"), "input_withdrawal": engine_state.get("input_withdrawal"),
                "max_net_withdrawal": engine_state.get("max_net_withdrawal"), "gross_withdrawal": eng_wd,
                "md": eng_md, "policy_debt": engine_state.get("policy_debt"),
                "rg_loan_princ": engine_state.get("rg_loan_princ"), "rg_loan_accrued": engine_state.get("rg_loan_accrued"),
            }
        for name, value in components.items():
            cumulative[name] += value
        rows.append({
            "prev": prev_row["date"], "cur": cur_row["date"], "span_days": span, "engine_days": engine_days(cur),
            "open_av": open_av, "close_av": close_av, "md": md, "net_premium": net_premium,
            "gross_withdrawal": gross_wd, "identity_residual": round(identity_residual, 2),
            "recorded_interest": recorded, "recorded_guaranteed_interest": guaranteed_recorded,
            "rate": rate, "engine_bonus": bonus, "reg_loan_principal": reg_loan, "pref_loan_principal": pref_loan,
            "cyber_rule": {"cv": cl_cv, "premium": cl_prem, "withdrawal": cl_wd, "loan": cl_loan, "repay": cl_repay,
                           "total": round(cl_total, 2), "residual_vs_recorded": round(recorded - cl_total, 2)},
            "engine_rule_cv_interest": eng_cv,
            "candidate_rules_cv_only": candidate_hits,
            "flows": flows,
            "components_rerun_minus_cyber": components,
            "cumulative_components": {k: round(v, 2) for k, v in cumulative.items()},
            "rerun_av_diff": (cur_row.get("av") or {}).get("diff"),
            "engine": engine_view,
        })
    totals: Counter = Counter()
    for row in rows:
        totals.update({k: v for k, v in row["components_rerun_minus_cyber"].items()})
    final_diff = rows[-1]["rerun_av_diff"] if rows else None
    ranked = sorted(((k, round(v, 2)) for k, v in totals.items()), key=lambda kv: -abs(kv[1]))
    return {
        "key": result["key"], "company": company, "plancode": plancode, "cint_key": cfg.cint_key,
        "interest_method_config": cfg.interest_method, "pdf_compound_rule": pdf_row.get("DIFFCMPD-FIX-COMPOUND"),
        "pdf_premium_credit_rule": pdf_row.get("DULPRCRD-PREM-CREDIT-INT"),
        "engine_policy": (engine or {}).get("policy"), "engine_error": (engine or {}).get("error"),
        "final_av_diff": final_diff, "max_abs_av_diff": max((abs(r["rerun_av_diff"] or 0.0) for r in rows), default=0.0),
        "component_totals": dict(ranked), "dominant_component": ranked[0][0] if ranked else None,
        "rows": rows,
    }


def cmd_fit(args) -> int:
    work = Path(args.work)
    pdf = json_load(work / "pdf_interest_coding.json") if (work / "pdf_interest_coding.json").exists() else {}
    book = RateBook()
    policies = []
    stats = Counter()
    for result in _results(Path(args.results), args.policies):
        cyber_path = work / "cyber" / f"{result['key']}.json"
        engine_path = work / "engine" / f"{result['key']}.json"
        cyber = json_load(cyber_path) if cyber_path.exists() else None
        engine = json_load(engine_path) if engine_path.exists() else None
        try:
            pol = decompose_policy(result, cyber, engine, pdf, book)
        except Exception as exc:  # noqa: BLE001
            print(result["key"], "error", f"{type(exc).__name__}: {exc}", flush=True)
            continue
        policies.append(pol)
        for row in pol["rows"]:
            stats["months"] += 1
            if abs(row["identity_residual"]) <= 0.011:
                stats["identity_exact"] += 1
            tol = 0.021 + 0.01 * len(row["flows"]["premium"])
            cyber_rule = row["cyber_rule"]
            if abs(cyber_rule["residual_vs_recorded"]) <= tol:
                stats["cyber_rule_matches_recorded"] += 1
            non_cv = cyber_rule["premium"] + cyber_rule["withdrawal"] + cyber_rule["loan"] + cyber_rule["repay"]
            if abs(row["recorded_interest"] - row["engine_rule_cv_interest"] - non_cv) <= tol:
                stats["engine_cv_rule_matches_recorded"] += 1
            if row["open_av"] > 0 and not any(row["flows"].values()):
                stats["months_without_cash_flows"] += 1
                for name, hit in row["candidate_rules_cv_only"].items():
                    if hit:
                        stats[f"cv_only_exact:{name}"] += 1
    json_dump(Path(args.output), {"stats": dict(stats), "policies": policies})
    print(json.dumps(dict(stats), indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("fetch", "engine", "fit"):
        p = sub.add_parser(name)
        p.add_argument("--results", required=True, help="policy_results folder from baseline_history_compare.py")
        p.add_argument("--work", required=True, help="working folder for cyber/ and engine/ detail")
        p.add_argument("--policies", nargs="*", default=[], help="optional policy keys such as 01_U0107043")
        p.add_argument("--force", action="store_true")
        if name == "fit":
            p.add_argument("--output", required=True)
    args = parser.parse_args()
    return {"fetch": cmd_fetch, "engine": cmd_engine, "fit": cmd_fit}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
