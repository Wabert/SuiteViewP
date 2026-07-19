"""Side-by-side scenario comparison for the Illustration app.

Runs TWO OR THREE fully-specified scenarios on the same loaded policy through
the same pipeline Run Values uses (solve layering + engine projection, current
assumptions) and reduces them to:

* a KPI summary per scenario with deltas — lapse year/age vs "sustains to
  maturity", MEC status, first GP-exception year, total premium outlay, and
  AV / SV / DB at policy years 5, 10, 20 and the end of each projection. With
  two scenarios the delta reads B − A (toned green/red); with three, the delta
  line shows both deltas against A ("B +2,000 · C −500", neutral tone — two
  deltas can disagree, so no single color applies); and
* an annual comparison ledger DataFrame laid out as side-by-side scenario
  blocks: shared Year | Age columns, then ALL of each scenario's measures
  (premium outlay, withdrawals / loans when present, AV, SV, DB) as one
  contiguous block, with a separator column between blocks. Deltas live only
  in the KPI summary — the ledger carries values, not arithmetic.

Pure logic — no Qt. The Compare tab (``ui/compare_tab.py``) extracts each
scenario's widget state into a :class:`ScenarioSpec` on the UI thread and this
module does the rest on a worker thread. One scenario failing NEVER loses the
others: :func:`run_comparison` isolates each side and carries the error text on
its :class:`ScenarioOutcome` so the UI can raise a loud per-scenario banner.

Scenario labels ("Current Inputs" or the saved-case name) travel with every
output — KPI rows, and the ledger's grouped block headers via
:func:`ledger_column_groups` — so results are never an anonymous "A/B/C".
Within a block the columns carry plain measure names ("Prem Outlay", "AV");
the DataFrame keys are prefixed ("A: AV" / "B: AV" / "C: AV") only for
uniqueness and :func:`ledger_header_labels` maps them back to the plain
display names.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import pandas as pd

from suiteview.illustration.core.calc_engine import IllustrationEngine

# Policy-year marks the KPI summary samples AV/SV/DB at (plus each side's end).
KPI_YEAR_MARKS = (5, 10, 20)

# Ledger measures: (column stem, annual-row key). The optional group only
# appears when either scenario actually has activity in the measure.
LEDGER_MEASURES = (("Prem Outlay", "outlay"), ("AV", "av"), ("SV", "sv"), ("DB", "db"))
LEDGER_OPTIONAL_MEASURES = (
    ("Withdrawals", "wd"),
    ("New Loans", "new_loan"),
    ("Loan Repay", "loan_repay"),
)
# Where the optional measures slot in: after Prem Outlay, before AV.
_LEDGER_OPTIONAL_AFTER = "Prem Outlay"

# Divider columns between scenario blocks (blank cells, no header text — the
# UI narrows and solid-fills them so they read as vertical rules). The first
# divider is LEDGER_SEPARATOR; later ones append their index ("‖2") for
# DataFrame-key uniqueness. separator_columns() finds them all.
LEDGER_SEPARATOR = "‖"

# Block prefixes: DataFrame column keys need uniqueness across blocks;
# ledger_header_labels() strips these back to the plain measure names.
_PREFIXES = ("A: ", "B: ", "C: ")
_LETTERS = "ABC"
_A_PREFIX = _PREFIXES[0]
_B_PREFIX = _PREFIXES[1]

# The comparison runs 2 or 3 scenarios.
MIN_SCENARIOS = 2
MAX_SCENARIOS = 3

_ZERO = 0.005  # money tolerance


def _separator_name(index: int) -> str:
    """The divider column key before block ``index`` (1-based between blocks)."""
    return LEDGER_SEPARATOR if index == 1 else f"{LEDGER_SEPARATOR}{index}"


def separator_columns(ledger: pd.DataFrame) -> list:
    """Every divider column present in a comparison ledger, in order."""
    return [c for c in ledger.columns if str(c).startswith(LEDGER_SEPARATOR)]


class CompareScenarioError(Exception):
    """A scenario cannot run as specified (e.g. shadow solve, no shadow account)."""


# ── scenario specification & outcome ────────────────────────────────


@dataclass
class ScenarioSpec:
    """Everything one scenario run needs, extracted from an inputs tab.

    ``scenario`` is an ``IllustrationScenario`` (built on the UI thread via
    ``build_illustration_scenario`` — its projectable policy is already a deep
    copy, so two specs never share mutable engine state). The solve requests
    mirror the Run Values pipeline's inputs-tab reads.
    """

    label: str
    scenario: object                       # IllustrationScenario
    months: Optional[int]
    options: object                        # IllustrationOptions
    stop_on_lapse: bool = True
    lumpsum_to_next: bool = False
    max_level: Optional[dict] = None       # {"mode","start_year"}
    min_level: Optional[dict] = None
    shadow_level: Optional[dict] = None
    payoff_requests: list = field(default_factory=list)
    apply_warnings: list = field(default_factory=list)  # saved-case apply notes


@dataclass
class ScenarioOutcome:
    """One side of a comparison: its results, or the error that ate them."""

    label: str
    results: Optional[list] = None         # MonthlyState list; [0] = inforce row
    policy: Optional[object] = None        # projectable policy the run used
    error: Optional[str] = None
    solved: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.results)


@dataclass
class KpiRow:
    """One KPI across all scenarios. ``values`` holds one display string per
    scenario, in order. ``tone`` colors the delta: "good" / "bad" / "neutral"
    (direction already applied; always neutral with three scenarios)."""

    key: str
    caption: str
    values: list
    delta_text: str
    tone: str = "neutral"
    delta_value: Optional[float] = None


@dataclass
class ComparisonResult:
    outcomes: list                                # list[ScenarioOutcome], 2..3
    kpis: list = field(default_factory=list)      # list[KpiRow]
    ledger: pd.DataFrame = field(default_factory=pd.DataFrame)


# ── running one scenario (mirrors main_window Run Values) ───────────


def run_scenario(spec: ScenarioSpec, engine=None) -> ScenarioOutcome:
    """Run one scenario through the Run Values pipeline; raises on failure.

    Solve layering matches ``IllustrationWindow._on_run_values`` exactly:
    Lumpsum to Next Premium first (so later solves see the bridge), then Max
    Level Allowed, Prem to Maturity, Prem to Shadow Maturity, loan pay-offs —
    each merged into the future inputs / run options before the final
    projection.
    """
    engine = engine or IllustrationEngine()
    policy = spec.scenario.projectable_policy
    future_inputs = spec.scenario.future_inputs
    run_options = spec.options
    solved: dict = {}

    if spec.lumpsum_to_next:
        from suiteview.illustration.core.solve_lumpsum_to_next_premium import (
            solve_lumpsum_to_next_premium,
        )
        from suiteview.illustration.models.input_set import (
            DatedTransaction, IllustrationInputSet, TransactionKind,
        )
        lumpsum_result = solve_lumpsum_to_next_premium(
            policy,
            base_future_inputs=future_inputs,
            base_options=run_options,
            engine=engine,
        )
        if lumpsum_result is not None and lumpsum_result.lumpsum > 0:
            dated = list(future_inputs.dated_transactions)
            dated.append(DatedTransaction(
                kind=TransactionKind.PREMIUM,
                effective_date=lumpsum_result.forecast_date,
                amount=lumpsum_result.lumpsum,
                subtype="lumpsum_to_next_premium"))
            future_inputs = IllustrationInputSet(
                scheduled_transactions=list(future_inputs.scheduled_transactions),
                dated_transactions=dated,
                policy_changes=list(future_inputs.policy_changes))
            solved["lumpsum"] = lumpsum_result.lumpsum

    if spec.max_level is not None:
        from suiteview.illustration.core.solve_level_to_exception import (
            level_to_exception_options,
        )
        from suiteview.illustration.core.solve_max_level_allowed import (
            solve_max_level_allowed,
        )
        from suiteview.illustration.models.input_set import (
            IllustrationInputSet, ScheduledTransaction, TransactionKind,
        )
        allow_exceptions = bool(run_options.allow_exception_prems)
        mla = solve_max_level_allowed(
            policy,
            mode=spec.max_level["mode"],
            start_policy_year=spec.max_level["start_year"],
            base_future_inputs=future_inputs,
            allow_exceptions=allow_exceptions,
            base_options=run_options,
            engine=engine)
        sched = list(future_inputs.scheduled_transactions)
        sched.append(ScheduledTransaction(
            kind=TransactionKind.PREMIUM,
            policy_year=int(spec.max_level["start_year"]),
            amount=mla.premium, mode=mla.mode))
        # Premiums stop at age 100 — AccumGLP freezes there (mirrors the
        # solver's own schedule; same rule as Run Values).
        if policy.maturity_age > 100:
            sched.append(ScheduledTransaction(
                kind=TransactionKind.PREMIUM,
                policy_year=100 - int(policy.issue_age or 0) + 1,
                amount=0.0, mode="A"))
        future_inputs = IllustrationInputSet(
            scheduled_transactions=sched,
            dated_transactions=list(future_inputs.dated_transactions),
            policy_changes=list(future_inputs.policy_changes))
        run_options = level_to_exception_options(run_options, allow_exceptions)
        solved["max_level"] = mla.premium

    if spec.min_level is not None:
        from suiteview.illustration.core.solve_level_to_exception import (
            level_to_exception_options, solve_level_to_exception,
        )
        from suiteview.illustration.models.input_set import (
            IllustrationInputSet, ScheduledTransaction, TransactionKind,
        )
        # GPT policies always ride the GLP exception period for this solve;
        # CVAT policies have no guideline cap, so exceptions stay off and the
        # displayed run drops TAMRA conformance to match the solve basis.
        allow_exceptions = not policy.is_cvat
        lte = solve_level_to_exception(
            policy,
            mode=spec.min_level["mode"],
            start_policy_year=spec.min_level["start_year"],
            base_future_inputs=future_inputs,
            allow_exceptions=allow_exceptions,
            base_options=run_options)
        sched = list(future_inputs.scheduled_transactions)
        sched.append(ScheduledTransaction(
            kind=TransactionKind.PREMIUM,
            policy_year=int(spec.min_level["start_year"]),
            amount=lte.premium, mode=lte.mode))
        future_inputs = IllustrationInputSet(
            scheduled_transactions=sched,
            dated_transactions=list(future_inputs.dated_transactions),
            policy_changes=list(future_inputs.policy_changes))
        run_options = level_to_exception_options(
            run_options, allow_exceptions,
            conform_to_tamra=not policy.is_cvat)
        solved["min_level"] = lte.premium

    if spec.shadow_level is not None:
        from suiteview.illustration.core.solve_level_to_exception import (
            level_to_exception_options, solve_level_to_exception,
        )
        from suiteview.illustration.models.input_set import (
            IllustrationInputSet, ScheduledTransaction, TransactionKind,
        )
        if not policy.has_shadow_account:
            raise CompareScenarioError(
                "Prem to Shadow Maturity cannot run: this policy has no active "
                "shadow account benefit (type A).")
        slte = solve_level_to_exception(
            policy,
            mode=spec.shadow_level["mode"],
            start_policy_year=spec.shadow_level["start_year"],
            base_future_inputs=future_inputs,
            allow_exceptions=False,
            base_options=run_options)
        sched = list(future_inputs.scheduled_transactions)
        sched.append(ScheduledTransaction(
            kind=TransactionKind.PREMIUM,
            policy_year=int(spec.shadow_level["start_year"]),
            amount=slte.premium, mode=slte.mode))
        future_inputs = IllustrationInputSet(
            scheduled_transactions=sched,
            dated_transactions=list(future_inputs.dated_transactions),
            policy_changes=list(future_inputs.policy_changes))
        run_options = level_to_exception_options(
            run_options, False,
            conform_to_tamra=not policy.is_cvat)
        solved["shadow_level"] = slte.premium

    if spec.payoff_requests:
        from suiteview.illustration.core.solve_loan_payoff import (
            PAYOFF_SUBTYPE, solve_loan_payoff,
        )
        from suiteview.illustration.models.input_set import (
            DatedTransaction, IllustrationInputSet, TransactionKind,
        )
        payoffs = []
        for request in spec.payoff_requests:
            payoff = solve_loan_payoff(
                policy,
                repayment_dates=request["dates"],
                check_date=request["check_date"],
                base_future_inputs=future_inputs,
                base_options=run_options,
                engine=engine)
            payoffs.append(payoff.repayment)
            if payoff.repayment > 0:
                dated = list(future_inputs.dated_transactions)
                dated.extend(DatedTransaction(
                    kind=TransactionKind.LOAN_REPAYMENT,
                    effective_date=when, amount=payoff.repayment,
                    subtype=PAYOFF_SUBTYPE)
                    for when in request["dates"])
                future_inputs = IllustrationInputSet(
                    scheduled_transactions=list(future_inputs.scheduled_transactions),
                    dated_transactions=dated,
                    policy_changes=list(future_inputs.policy_changes))
        solved["payoffs"] = payoffs

    results = engine.project(
        policy,
        months=spec.months,
        future_inputs=future_inputs,
        options=run_options,
        stop_on_lapse=spec.stop_on_lapse,
    )
    return ScenarioOutcome(
        label=spec.label, results=list(results), policy=policy, solved=solved)


# ── the comparison ──────────────────────────────────────────────────


def run_comparison(
    specs: list,
    *,
    run_fn: Callable[..., ScenarioOutcome] = run_scenario,
    engine=None,
) -> ComparisonResult:
    """Run 2..3 scenarios with per-side error isolation, then reduce.

    A failed side yields a :class:`ScenarioOutcome` carrying ``error`` text;
    the surviving sides' KPIs and ledger columns are still produced.
    """
    if not (MIN_SCENARIOS <= len(specs) <= MAX_SCENARIOS):
        raise ValueError(
            f"run_comparison takes {MIN_SCENARIOS}..{MAX_SCENARIOS} scenarios, "
            f"got {len(specs)}.")
    outcomes = []
    for spec in specs:
        try:
            outcomes.append(run_fn(spec, engine=engine))
        except Exception as exc:
            outcomes.append(ScenarioOutcome(
                label=spec.label, error=str(exc) or type(exc).__name__))
    return ComparisonResult(
        outcomes=outcomes,
        kpis=build_kpi_rows(outcomes),
        ledger=build_comparison_ledger(outcomes),
    )


# ── KPI extraction ──────────────────────────────────────────────────


def _fmt_money(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:,.0f}"


def _fmt_delta_money(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:+,.0f}"


def _mec_status(policy, projected: list) -> str:
    """MEC status from the inforce flag plus the projected 7-pay test.

    Scans the engine's running 7-pay accumulator against the active window's
    limit (``tamra_year × 7-pay level``). A retroactive MEC created by a
    mid-window guideline recalc back-test is not re-derived here — the Values
    tab's MEC Back-Test sheet remains the authority for that edge.
    """
    if getattr(policy, "is_mec", False):
        return "MEC (inforce)"
    for state in projected:
        if (1 <= state.tamra_year <= 7 and state.tamra_7pay_level > 0
                and state.accumulated_7pay
                > state.tamra_year * state.tamra_7pay_level + _ZERO):
            return f"Becomes MEC (Yr {state.policy_year})"
    return "Not a MEC"


def scenario_kpi_values(policy, results: list) -> dict:
    """Raw KPI values for one finished run (``results[0]`` = inforce row)."""
    projected = results[1:] if len(results) > 1 else []
    final = results[-1]
    lapse = next(
        (s for s in projected if s.lapsed and not getattr(s, "matured", False)),
        None)
    matured = bool(getattr(final, "matured", False))
    if lapse is not None:
        outcome = f"Lapses Yr {lapse.policy_year} · Age {lapse.attained_age}"
    elif matured:
        outcome = "Sustains to maturity"
    else:
        outcome = f"In force to Yr {final.policy_year} (end of projection)"

    first_exception = next(
        (s.policy_year for s in projected if s.gp_exception_prem > _ZERO), None)

    points: dict = {}
    by_year: dict[int, object] = {}
    for state in projected:
        by_year[state.policy_year] = state    # last state of each year wins
    for mark in KPI_YEAR_MARKS:
        state = by_year.get(mark)
        points[mark] = None if state is None else {
            "av": state.av_end_of_month,
            "sv": state.ending_sv,
            "db": state.ending_db or state.gross_db,
        }
    points["end"] = None if not projected else {
        "av": final.av_end_of_month,
        "sv": final.ending_sv,
        "db": final.ending_db or final.gross_db,
    }
    return {
        "outcome": outcome,
        "lapse_year": None if lapse is None else int(lapse.policy_year),
        "matured": matured,
        "final_year": int(final.policy_year),
        "mec": _mec_status(policy, projected),
        "first_exception_year": first_exception,
        "total_outlay": sum(s.premium_outlay for s in projected),
        "points": points,
    }


def _money_delta_row(key, caption, vals: list, *, lower_is_better=False) -> KpiRow:
    """A money KPI across all scenarios. Two scenarios keep the toned B − A
    delta; three show both deltas against A ("B +2,000 · C −500", neutral)."""
    base = vals[0]
    if len(vals) == 2:
        delta = None if base is None or vals[1] is None else vals[1] - base
        tone = "neutral"
        if delta is not None and abs(delta) > _ZERO:
            better = delta < 0 if lower_is_better else delta > 0
            tone = "good" if better else "bad"
        delta_text, delta_value = _fmt_delta_money(delta), delta
    else:
        parts = []
        for letter, val in zip(_LETTERS[1:], vals[1:]):
            delta = None if base is None or val is None else val - base
            parts.append(f"{letter} {_fmt_delta_money(delta)}")
        delta_text, tone, delta_value = " · ".join(parts), "neutral", None
    return KpiRow(
        key=key, caption=caption,
        values=[_fmt_money(v) for v in vals],
        delta_text=delta_text, tone=tone, delta_value=delta_value)


def _lapse_delta(la, lb, *, a_tag="A", b_tag="B") -> tuple:
    """(text, tone, value) for one lapse-year pair (None = sustains)."""
    if la is not None and lb is not None:
        value = float(lb - la)
        tone = "good" if lb > la else "bad" if lb < la else "neutral"
        return f"{lb - la:+d} yrs", tone, value
    if la is not None and lb is None:
        return f"{b_tag} sustains; {a_tag} lapses", "good", None
    if lb is not None and la is None:
        return f"{a_tag} sustains; {b_tag} lapses", "bad", None
    return "—", "neutral", None


def build_kpi_rows(outcomes: list) -> list:
    """The KPI summary — one :class:`KpiRow` per KPI. With two scenarios the
    delta reads B − A (toned); with three, both deltas against A on one
    neutral line. A failed side renders "—" everywhere, so the surviving
    scenarios' numbers still land.
    """
    ks = [scenario_kpi_values(o.policy, o.results) if o.ok else None
          for o in outcomes]
    three = len(ks) > 2

    def txt(k, key):
        return "—" if k is None else str(k[key])

    rows: list[KpiRow] = []

    # ── outcome (lapse vs sustains) ──
    lapses = [None if k is None else k["lapse_year"] for k in ks]
    delta_text, tone, delta_value = "—", "neutral", None
    if ks[0] is not None:
        if three:
            parts = []
            for letter, k, lapse in zip(_LETTERS[1:], ks[1:], lapses[1:]):
                if k is None:
                    parts.append(f"{letter} —")
                    continue
                text, _tone, _val = _lapse_delta(
                    lapses[0], lapse, a_tag="A", b_tag=letter)
                parts.append(f"{letter} {text}" if "yrs" in text or text == "—"
                             else text)
            delta_text = " · ".join(parts)
        elif ks[1] is not None:
            delta_text, tone, delta_value = _lapse_delta(lapses[0], lapses[1])
    rows.append(KpiRow(
        key="outcome", caption="Outcome",
        values=[txt(k, "outcome") for k in ks],
        delta_text=delta_text, tone=tone, delta_value=delta_value))

    # ── MEC status ──
    mecs = [None if k is None else k["mec"] for k in ks]
    delta_text, tone = "—", "neutral"
    if all(m is not None for m in mecs) and len(set(mecs)) > 1:
        if three:
            delta_text = "differs"
        elif mecs[1] == "Not a MEC":
            delta_text, tone = "B avoids MEC", "good"
        elif mecs[0] == "Not a MEC":
            delta_text, tone = "B becomes MEC", "bad"
        else:
            delta_text = "differs"
    rows.append(KpiRow(
        key="mec", caption="MEC Status",
        values=[m or "—" for m in mecs],
        delta_text=delta_text, tone=tone))

    # ── first GP-exception year ──
    firsts = [None if k is None else k["first_exception_year"] for k in ks]
    delta_text, delta_value = "—", None
    if three:
        parts = []
        for letter, k, first in zip(_LETTERS[1:], ks[1:], firsts[1:]):
            if k is None or firsts[0] is None or first is None:
                parts.append(f"{letter} —")
            else:
                parts.append(f"{letter} {first - firsts[0]:+d} yrs")
        delta_text = " · ".join(parts)
    elif firsts[0] is not None and firsts[1] is not None:
        delta_value = float(firsts[1] - firsts[0])
        delta_text = f"{firsts[1] - firsts[0]:+d} yrs"
    rows.append(KpiRow(
        key="first_exception", caption="First GP Exception",
        values=["—" if k is None
                else ("None" if first is None else f"Yr {first}")
                for k, first in zip(ks, firsts)],
        delta_text=delta_text, tone="neutral", delta_value=delta_value))

    # ── total premium outlay (lower is better) ──
    rows.append(_money_delta_row(
        "total_outlay", "Total Prem Outlay",
        [None if k is None else k["total_outlay"] for k in ks],
        lower_is_better=True))

    # ── AV / SV / DB at the year marks and each side's end ──
    for mark in (*KPI_YEAR_MARKS, "end"):
        points = [None if k is None else k["points"].get(mark) for k in ks]
        if all(p is None for p in points):
            continue    # no projection reaches this mark
        mark_label = "End" if mark == "end" else f"Yr {mark}"
        for stem, key in (("AV", "av"), ("SV", "sv"), ("DB", "db")):
            rows.append(_money_delta_row(
                f"{key}_{mark}", f"{stem} · {mark_label}",
                [None if p is None else p[key] for p in points]))
    return rows


# ── annual comparison ledger ────────────────────────────────────────


def annual_rows(results: Optional[list]) -> dict:
    """Per-policy-year measures from one run's monthly states.

    Returns ``{year: {"age", "outlay", "wd", "new_loan", "loan_repay",
    "av", "sv", "db"}}`` — annual sums for the flows, end-of-year values for
    the balances (same conventions as the Overview ledger's annual rows).
    """
    if not results or len(results) < 2:
        return {}
    projected = results[1:]
    by_year: dict[int, list] = {}
    for state in projected:
        by_year.setdefault(state.policy_year, []).append(state)
    out: dict[int, dict] = {}
    prior_wd = results[0].withdrawals_to_date
    for year in sorted(by_year):
        months = by_year[year]
        eoy = months[-1]
        withdrawals = eoy.withdrawals_to_date - prior_wd
        prior_wd = eoy.withdrawals_to_date
        out[year] = {
            "age": int(eoy.attained_age),
            "outlay": sum(s.premium_outlay for s in months),
            "wd": withdrawals,
            "new_loan": sum(s.applied_new_loan for s in months),
            "loan_repay": sum(s.applied_loan_repayment for s in months),
            "av": eoy.av_end_of_month,
            "sv": eoy.ending_sv,
            "db": eoy.ending_db or eoy.gross_db,
        }
    return out


def side_tags(*labels) -> tuple:
    """Header tags for the sides — the scenario labels, disambiguated with
    (A)/(B)/(C) suffixes only where labels collide."""
    tags = [(label or "").strip() or f"Scenario {_LETTERS[i]}"
            for i, label in enumerate(labels)]
    counts: dict = {}
    for tag in tags:
        counts[tag] = counts.get(tag, 0) + 1
    return tuple(
        f"{tag} ({_LETTERS[i]})" if counts[tag] > 1 else tag
        for i, tag in enumerate(tags))


def _active_measures(rows_list: list) -> list:
    """Always-on measures plus any optional measure with activity on any side."""
    measures = list(LEDGER_MEASURES)
    insert_at = next(
        i + 1 for i, (stem, _) in enumerate(measures)
        if stem == _LEDGER_OPTIONAL_AFTER)
    optional = [
        (stem, key) for stem, key in LEDGER_OPTIONAL_MEASURES
        if any(abs(row[key]) > _ZERO
               for rows in rows_list for row in rows.values())
    ]
    return measures[:insert_at] + optional + measures[insert_at:]


def build_comparison_ledger(outcomes: list) -> pd.DataFrame:
    """The paired annual ledger as one scenario block per outcome.

    ``Year | Age`` (shared), then each scenario's measures as one contiguous
    block with a divider column between blocks. Column keys are prefixed
    "A: " / "B: " / "C: " for uniqueness only — display names come from
    :func:`ledger_header_labels` and scenario identity from
    :func:`ledger_column_groups`. Years one side never reaches leave that
    block's cells blank. No Δ columns — deltas live in the KPI summary.
    """
    rows_list = [annual_rows(o.results) if o.ok else {} for o in outcomes]
    years = sorted(set().union(*rows_list)) if rows_list else []
    measures = _active_measures(rows_list)

    columns = ["Year", "Age"]
    seps = []
    for i, prefix in enumerate(_PREFIXES[:len(outcomes)]):
        if i:
            sep = _separator_name(i)
            seps.append(sep)
            columns.append(sep)
        columns.extend(f"{prefix}{stem}" for stem, _key in measures)

    records = []
    for year in years:
        year_rows = [rows.get(year) for rows in rows_list]
        age = next(row for row in year_rows if row is not None)["age"]
        record: dict = {"Year": year, "Age": age}
        record.update({sep: "" for sep in seps})
        for prefix, row in zip(_PREFIXES, year_rows):
            for stem, key in measures:
                record[f"{prefix}{stem}"] = None if row is None else row[key]
        records.append(record)
    return pd.DataFrame(records, columns=columns)


def ledger_block_columns(ledger: pd.DataFrame) -> tuple:
    """Each block's column keys, in ledger order — one list per scenario
    present (``(a_columns, b_columns[, c_columns])``)."""
    blocks = tuple(
        [c for c in ledger.columns if str(c).startswith(prefix)]
        for prefix in _PREFIXES)
    return tuple(block for block in blocks if block)


def ledger_header_labels(ledger: pd.DataFrame) -> dict:
    """Display labels for the ledger: plain measure names inside each block
    ("Prem Outlay", "AV" — no scenario suffix) and blank separator headers.
    Scenario identity rides the grouped block headers, not each column."""
    labels: dict = {}
    for column in ledger.columns:
        name = str(column)
        if name.startswith(LEDGER_SEPARATOR):
            labels[column] = ""
        elif name.startswith(_PREFIXES):
            labels[column] = name[len(_A_PREFIX):]
    return labels


def ledger_column_groups(ledger: pd.DataFrame, *labels) -> list:
    """The grouped-header spans: ``[(scenario name, [block columns]), ...]``.

    Feeds ``FilterTableView.set_column_groups`` (and the Excel export's merged
    scenario-name row) so each block is titled with its scenario's name."""
    tags = side_tags(*labels)
    blocks = ledger_block_columns(ledger)
    return [(tag, cols) for tag, cols in zip(tags, blocks) if cols]


def kpi_summary_frame(result: ComparisonResult) -> pd.DataFrame:
    """The KPI rows as a DataFrame (Excel sheet 1), labels in the headers."""
    tags = side_tags(*[o.label for o in result.outcomes])
    delta_header = "Δ (B − A)" if len(tags) == 2 else "Δ (vs A)"
    columns = ["KPI", *tags, delta_header]
    return pd.DataFrame(
        [
            {
                "KPI": row.caption,
                **{tag: value for tag, value in zip(tags, row.values)},
                delta_header: row.delta_text,
            }
            for row in result.kpis
        ],
        columns=columns,
    )
