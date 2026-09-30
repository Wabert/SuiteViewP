"""Reproduce CyberLife's current par WL values from the rates and the engine.

Each check compares a value CyberLife holds on the record with SuiteView's own
calculation, so a user (and the verification tool) can see whether the illustration
starts from the admin system's numbers:

* **Premium** - the modal premium from stored per-unit premiums and the plan's mode
  factors against the billed ``POL_PRM_AMT``; stored ``ANN_PRM_UNT_AMT`` against schema ``PREM``.
* **Cash values** - schema ``CV`` per unit against the four stored ``LOW_DUR_*_CSV_AMT``.
* **RPU NSP** - the NSP calculation against stored ``LOW_DUR_*_NSP_AMT`` (reduced paid-up).
* **Dividends** - per-unit cash/PUA/OYT from the dividend scale against the dividend
  values CyberLife placed for the last and the next anniversary, and the dollar
  dividend the engine calculates from the additions CyberLife held going into it.
* **Additions** - the additions before the last anniversary plus those the dividend
  bought against the current additions.
* **Loan** - advance interest ``principal x rate`` against ``POL_LN_ITS_AMT``.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Tuple

from suiteview.illustration.core.inforce_check import CheckLine
from suiteview.illustration.core.inforce_check import check_line as _line
from suiteview.illustration.core.parwl.engine import ParWLEngine, cents, completed_months
from suiteview.illustration.core.parwl.nsp import NSPError, net_single_premium
from suiteview.illustration.core.parwl.premiums import modal_premium, policy_mode, record_premium_date
from suiteview.illustration.core.parwl.rates import ParWLRateError, ParWLRates
from suiteview.illustration.models.parwl import ROLE_PUA_RIDER, ROLE_TERM_RIDER, ParWLPolicy


def premium_checks(policy: ParWLPolicy, rates: ParWLRates) -> List[CheckLine]:
    lines: List[CheckLine] = []
    for cov in policy.coverages:
        if cov.role == ROLE_PUA_RIDER or policy.is_rpu:
            continue
        schema = rates.coverage(cov.phase).premium_per_unit
        if cov.role == ROLE_TERM_RIDER:
            continue
        lines.append(_line("Premium", f"{cov.plancode} premium per unit", cov.annual_premium_per_unit, schema,
                           "stored ANN_PRM_UNT_AMT vs schema PREM" if schema is not None
                           else "schema PREM is not loaded"))
    if policy.premium_status not in ("22", "32"):
        return lines
    parts = modal_premium(policy, rates, record_premium_date(policy))
    factors = rates.mode_factor(policy_mode(policy))
    detail = (f"base {parts.base:,.2f} + riders {parts.rider:,.2f} + benefits {parts.benefit:,.2f} + extras "
              f"{parts.extra:,.2f} + fee {parts.fee:,.2f}"
              + (f" + rounding {parts.rounding:,.2f}" if parts.rounding else "")
              + f" at factor {parts.prem_factor}"
              + ("" if factors is not None else " (no RATE_MODEFACT factors: months / 12)"))
    line = _line("Premium", "Modal premium", policy.modal_premium, parts.total, detail)
    if line.status == "differs" and policy.forced_premium:
        line = CheckLine(line.area, line.item, line.cyberlife, line.calculated, "info",
                         detail + "; forced premium on the record (billed as forced)")
    lines.append(line)
    return lines


def cash_value_checks(policy: ParWLPolicy, rates: ParWLRates) -> List[CheckLine]:
    lines: List[CheckLine] = []
    for cov in policy.coverages:
        if cov.role == ROLE_PUA_RIDER or cov.stored_low_duration is None:
            continue
        cov_rates = rates.coverage(cov.phase)
        for offset, stored in enumerate(cov.stored_cash_values):
            if stored is None or (stored == 0 and offset > 0):
                continue
            duration = cov.stored_low_duration + offset
            calc = cov_rates.cash_values[duration] if duration < len(cov_rates.cash_values) else None
            if stored < 0 and calc == 0:
                lines.append(CheckLine("Cash value", f"{cov.plancode} CV per unit, duration {duration}", stored,
                                       calc, "info", "CyberLife stores a negative early value (14318679: -7.00); "
                                       "schema CV and the cash value floor it at zero"))
                continue
            lines.append(_line("Cash value", f"{cov.plancode} CV per unit, duration {duration}", stored, calc,
                               "stored LOW_DUR CSV vs schema CV"))
        if policy.is_rpu and cov.nsp_table and cov.nsp_interest is not None:
            for offset, stored in enumerate(cov.stored_nsp_values[:2]):
                if not stored:
                    continue
                duration = cov.stored_low_duration + offset
                try:
                    calc = round(net_single_premium(cov.nsp_table, cov.nsp_interest, cov.issue_age + duration)
                                 * cov.value_per_unit / 1000.0, 2)
                except NSPError as exc:
                    lines.append(CheckLine("Cash value", f"RPU NSP duration {duration}", stored, None, "info", str(exc)))
                    continue
                lines.append(_line("Cash value", f"RPU NSP per unit, duration {duration}", stored, calc,
                                   f"table {cov.nsp_table} at {cov.nsp_interest:.3%}, age {cov.issue_age + duration}"))
    return lines


def _grouped(records, when: date):
    """Placed values for ``when`` by (phase, source); a split application (OYT limit, premium
    reduction and its excess) stores the per-unit values in parts that add up to the rate."""
    groups: Dict[Tuple[int, str], list] = {}
    for rec in records:
        if rec.earn_date == when:
            groups.setdefault((rec.phase, rec.source), []).append(rec)
    return groups


def _record_lines(policy: ParWLPolicy, rates: ParWLRates, when: date, label: str,
                  records, engine: ParWLEngine, applied: bool = False) -> List[CheckLine]:
    """Per-unit dividend values CyberLife placed for ``when`` against the dividend scale.

    ``applied``: the values were applied at an anniversary, so an OYT limit has already
    prorated them; values placed for a coming anniversary carry the full rates."""
    lines: List[CheckLine] = []
    for (phase, source), recs in sorted(_grouped(records, when).items()):
        rec = recs[0]
        cov = next((c for c in policy.coverages if c.phase == phase), None)
        if cov is None:
            continue
        cov_rates = rates.coverage(cov.phase).dividends
        if cov_rates is None:
            lines.append(CheckLine("Dividend", f"{label} phase {phase}", rec.cash_per_unit, None, "info",
                                   f"{cov.plancode} has no dividend scale in schema rates"))
            continue
        duration = completed_months(cov.issue_date, when) // 12
        if cov.role == ROLE_PUA_RIDER:
            duration += engine.rider_duration_offset
        if rec.direct_recognition:
            record = "P" if rec.rpu_values else "L"
        else:
            record = "R" if rec.rpu_values else "D"
        try:
            set_ = cov_rates.rates(record, when, duration, cov.issue_age)
        except ParWLRateError as exc:
            lines.append(CheckLine("Dividend", f"{label} phase {phase}", rec.cash_per_unit, None, "info", str(exc)))
            continue
        what = "coverage" if source == "0" else "additions"
        cash = round(sum(r.cash_per_unit for r in recs), 6)
        pua = round(sum(r.pua_per_unit for r in recs), 6)
        oyt = round(sum(r.oyt_per_unit for r in recs), 6)
        detail = f"record {record}, scale from {set_.scale_from:%m/%d/%Y}"
        tolerance = 0.00005
        if source == "0":
            expected = (set_.base_div, set_.base_pua, set_.base_oyt)
            pua_recs = _grouped(records, when).get((phase, "1"), [])
            limit = _oyt_limit_fraction(policy, rates, cov, set_, when, pua_recs) if applied else None
            if limit is not None:
                fraction, per_unit_limit = limit
                expected = (set_.base_div * fraction, set_.base_pua * fraction, per_unit_limit)
                detail += f"; OYT limited to the next cash value ({fraction:.5f} of the dividend)"
                tolerance = 0.0001
        else:
            expected = (set_.pua_div, set_.pua_pua, set_.pua_oyt)
        if len(recs) > 1:
            detail += f"; {len(recs)} placed parts"
            tolerance = 0.0006
        for name, stored, calc in zip(("cash", "PUA", "OYT"), (cash, pua, oyt), expected):
            if not stored and not calc:
                continue
            lines.append(_line("Dividend", f"{label} {cov.plancode} {what} {name} per unit (yr {duration})",
                               stored, calc, detail, tolerance=tolerance))
    return lines


def _oyt_limit_fraction(policy: ParWLPolicy, rates: ParWLRates, cov, set_, when: date, pua_recs):
    """(fraction of the coverage dividend used, OYT per unit) when option 6 limits the OYT
    to the base coverage's cash value at the next anniversary. The additions' OYT is bought
    first and the coverage's OYT takes the rest (14139154: 1,590.00 = 362.60 + 1,227.40)."""
    if policy.dividend_option != "6" or cov.role != "BASE" or not set_.base_oyt or not cov.units:
        return None
    duration = completed_months(cov.issue_date, when) // 12
    try:
        limit = cov.units * rates.coverage(cov.phase).cash_value_per_unit(duration + 1)
    except ParWLRateError:
        return None
    additions_oyt = sum(cents(r.units * r.oyt_per_unit) for r in pua_recs)
    room = max(0.0, limit - additions_oyt)
    available = cov.units * set_.base_oyt
    if room >= available:
        return None
    return room / available, room / cov.units


def dividend_checks(policy: ParWLPolicy, rates: ParWLRates, engine: ParWLEngine) -> List[CheckLine]:
    lines: List[CheckLine] = []
    last = policy.last_anniversary
    records = list(policy.unapplied_dividends) + [r for r in policy.applied_dividends
                                                  if not any(u.earn_date == r.earn_date for u in policy.unapplied_dividends)]
    lines += _record_lines(policy, rates, last, "Last anniversary", records, engine, applied=True)
    upcoming = sorted({r.earn_date for r in policy.unapplied_dividends if r.earn_date > last})
    for when in upcoming:
        lines += _record_lines(policy, rates, when, "Next anniversary", policy.unapplied_dividends, engine)
    # dollar dividend at the last anniversary from the additions held going into it
    placed = [r for r in policy.unapplied_dividends if r.earn_date == last and r.units]
    if placed and policy.dividend_option not in ("", "0", "9"):
        state = engine.state_before_last_anniversary()
        duration = completed_months(policy.base.issue_date, last) // 12
        try:
            pieces = engine.dividend_pieces(state, last, duration)
        except (ParWLRateError, ValueError) as exc:
            lines.append(CheckLine("Dividend", "Last anniversary dividend", None, None, "info", str(exc)))
            pieces = []
        by_key: Dict[Tuple[int, str], object] = {(p.phase, p.source): p for p in pieces}
        for (phase, source), recs in sorted(_grouped(placed, last).items()):
            piece = by_key.get((phase, source))
            stored_units = recs[0].units
            stored_amount = cents(sum(cents(r.units * r.cash_per_unit) for r in recs))
            if piece is None:
                lines.append(CheckLine("Dividend", f"Last dividend phase {phase} source {source}",
                                       stored_amount, None, "differs", "not calculated"))
                continue
            lines.append(_line("Dividend", f"Last dividend units phase {phase} source {source}",
                               stored_units, piece.units, "coverage units or additions / 1,000", tolerance=0.0005))
            if policy.dividend_option in ("6", "7") and source == "0":
                lines.append(CheckLine("Dividend", f"Last dividend phase {phase} source {source}", stored_amount,
                                       piece.cash, "info", "OYT limited: CyberLife keeps the part that bought "
                                       "OYT; the rest went to the secondary option"))
                continue
            lines.append(_line("Dividend", f"Last dividend phase {phase} source {source}",
                               stored_amount, piece.cash, f"{piece.units:,.3f} x {piece.cash_rate}"))
        if policy.dividend_option == "4" and policy.additions_before_anniversary:
            for phase in sorted({a.phase for a in policy.additions}):
                before = sum(a.amount for a in state.additions if a.phase == phase and a.source == "0")
                bought = sum(p.pua for p in pieces if p.phase == phase)
                current = sum(a.amount for a in policy.additions if a.phase == phase and a.source == "0")
                lines.append(_line("Additions", f"Phase {phase} dividend additions after the last anniversary",
                                   current, cents(before + bought), f"{before:,.2f} before + {bought:,.2f} bought"))
    # the engine's first dividend against the value CyberLife placed for the next anniversary
    for when in upcoming:
        placed_next = [r for r in policy.unapplied_dividends if r.earn_date == when and r.units]
        if not placed_next:
            continue
        stored_total = cents(sum(cents(r.units * r.cash_per_unit) for r in placed_next))
        state = engine.record_state()
        duration = completed_months(policy.base.issue_date, when) // 12
        try:
            calc = cents(sum(p.cash for p in engine.dividend_pieces(state, when, duration)))
        except (ParWLRateError, ValueError) as exc:
            lines.append(CheckLine("Dividend", f"Dividend {when:%m/%d/%Y}", stored_total, None, "info", str(exc)))
            continue
        lines.append(_line("Dividend", f"Next dividend {when:%m/%d/%Y}", stored_total, calc,
                           "units x per-unit values CyberLife placed vs the engine"))
    return lines


def loan_checks(policy: ParWLPolicy) -> List[CheckLine]:
    lines: List[CheckLine] = []
    for loan in policy.loans:
        if loan.in_advance and loan.capitalized and loan.last_activity == policy.last_anniversary:
            lines.append(_line("Loan", "Advance interest for the policy year", loan.interest_amount,
                               cents(loan.principal * loan.rate),
                               f"principal {loan.principal:,.2f} x {loan.rate:.3%}, capitalized at the "
                               f"{policy.last_anniversary:%m/%d/%Y} anniversary"))
        elif loan.in_advance:
            lines.append(CheckLine("Loan", "Advance interest", loan.interest_amount, None, "info",
                                   "loan activity since the last anniversary; interest covers part of the year"))
        else:
            lines.append(CheckLine("Loan", "Accrued interest", loan.interest_amount, None, "info",
                                   "interest in arrears, accrued to the last loan activity"))
    return lines


def inforce_checks(policy: ParWLPolicy, rates: ParWLRates, engine: Optional[ParWLEngine] = None) -> List[CheckLine]:
    """Every in-force check for ``policy``; ``engine`` defaults to a record-option engine."""
    engine = engine or ParWLEngine(policy, rates)
    return (premium_checks(policy, rates) + cash_value_checks(policy, rates)
            + dividend_checks(policy, rates, engine) + loan_checks(policy))
