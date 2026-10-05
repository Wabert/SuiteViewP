"""Compare blended-rate and segment ("bucket") IUL crediting for one policy.

Runs the same live policy twice — the normal blended rate and the
development-only segment method (``IllustrationOptions.iul_segment_crediting``)
— and prints policy-year-end account values side by side. ``--csv`` also
writes the segment run's monthly Accounts summary.

Usage (from the repository root, running from source):
    venv\\Scripts\\python.exe tools\\engine\\compare_iul_segment_crediting.py UE079729
    venv\\Scripts\\python.exe tools\\engine\\compare_iul_segment_crediting.py UE079729 --from-issue --years 20
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("policy")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--company", default=None)
    parser.add_argument("--from-issue", action="store_true")
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--timing", choices=("illustration", "cyberlife_monthliversary"),
                        default="illustration")
    parser.add_argument("--declared-rate", type=float, default=None,
                        help="Fixed/sweep rate (decimal); default is the plan GINT, "
                             "as the allocations panel defaults it.")
    parser.add_argument("--csv", type=Path, default=None,
                        help="Write the segment run's monthly Accounts summary here.")
    return parser.parse_args(argv)


def _ui_crediting_overrides(policy, declared_rate):
    """The Inputs-tab IUL crediting overrides with the allocations panel defaults."""
    from suiteview.illustration.models.index_strategies import (
        FIXED_FUND_ID,
        compute_blended_rates,
        current_ag49_index,
        load_index_strategies,
        plan_with_ag49_index,
        with_current_index_data,
    )
    from suiteview.illustration.models.input_set import InforceOverrideSet

    plan = plan_with_ag49_index(with_current_index_data(
        load_index_strategies(policy.plancode),
        policy.index_illustration_rates, policy.index_strategy_parameters),
        current_ag49_index())
    gint = policy.guaranteed_interest_rate
    rates = plan.default_rates(gint)
    if declared_rate is not None:
        rates[FIXED_FUND_ID] = declared_rate
    total = sum(v for v in policy.premium_allocations.values() if v) or 1.0
    allocations = {fund: (v or 0.0) / total for fund, v in policy.premium_allocations.items()}
    blended = compute_blended_rates(plan, allocations, rates, gint)
    return InforceOverrideSet(
        current_interest_rate=blended.effective,
        iul_declared_rate=rates.get(FIXED_FUND_ID),
        iul_asset_charge_rate=blended.asset_charge_rate,
        premium_allocations=allocations,
        index_illustration_rates=rates,
    )


def main(argv=None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    from suiteview.illustration.api import load_policy_data
    from suiteview.illustration.core.calc_engine import IllustrationEngine, ProjectionTiming
    from suiteview.illustration.core.scenario_builder import build_illustration_scenario
    from suiteview.illustration.models.input_set import IllustrationOptions

    policy = load_policy_data(args.policy, region=args.region, company_code=args.company)
    scenario = build_illustration_scenario(
        policy, _ui_crediting_overrides(policy, args.declared_rate),
        run_from_issue=args.from_issue)
    start = scenario.projectable_policy
    timing = ProjectionTiming(args.timing)
    base = IllustrationOptions()
    engine = IllustrationEngine()

    def run(options):
        return engine.project(
            start, months=args.years * 12, future_inputs=scenario.future_inputs,
            timing=timing, stop_on_lapse=False, options=options)

    blended = run(base)
    segment = run(replace(base, iul_segment_crediting=True))

    opening = segment[0].iul_segment_detail
    print(f"{args.policy} {start.plancode} issue {start.issue_date} "
          f"{'from issue' if args.from_issue else 'inforce ' + str(start.valuation_date)}")
    print(f"Allocations {start.premium_allocations}  rates {start.index_illustration_rates}  "
          f"blend {start.current_interest_rate}  declared {start.iul_declared_rate}")
    accounts = opening["accounts"]
    print(f"Opening: sweep {accounts.sweep:,.2f} fixed {accounts.fixed:,.2f} "
          f"collateral {accounts.collateral:,.2f} segments {len(accounts.segments)} "
          f"index {accounts.index_total:,.2f} sweep min {accounts.sweep_min:,.2f}")
    for event in opening["events"]:
        if event.step == "Seed":
            print(f"  Seed note: {event.event} {event.account} {event.amount:,.2f} {event.note}")
    print(f"{'Year':>4} {'Date':>10} {'Blended AV':>14} {'Segment AV':>14} {'Diff':>12} "
          f"{'Sweep':>11} {'Fixed':>11} {'Index':>12} {'Segs':>5} {'Max acct diff':>14}")
    worst = 0.0
    for b_state, s_state in zip(blended[1:], segment[1:]):
        summary = s_state.iul_segment_detail["summary"]
        worst = max(worst, abs(summary["Difference"]))
        if s_state.policy_month != 12:
            continue
        acc = s_state.iul_segment_detail["accounts"]
        print(f"{s_state.policy_year:>4} {s_state.date!s:>10} {b_state.av_end_of_month:>14,.2f} "
              f"{s_state.av_end_of_month:>14,.2f} "
              f"{s_state.av_end_of_month - b_state.av_end_of_month:>12,.2f} "
              f"{acc.sweep:>11,.2f} {acc.fixed:>11,.2f} {acc.index_total:>12,.2f} "
              f"{len(acc.segments):>5} {worst:>14.6f}")
    if args.csv is not None:
        rows = [{"Date": s.date, "Year": s.policy_year, "Month": s.policy_month,
                 "Blended AV": b.av_end_of_month, **s.iul_segment_detail["summary"]}
                for b, s in zip(blended[1:], segment[1:])]
        keys = list(dict.fromkeys(key for row in rows for key in row))
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
