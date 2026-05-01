"""M1 validation script — run illustration projection for UE000576.

Usage:
    python -m suiteview.illustration.scripts.run_m1
    python -m suiteview.illustration.scripts.run_m1 --excel debug_output.xlsx
    python -m suiteview.illustration.scripts.run_m1 --policy UE000576 --months 24
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import fields
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="M1 Illustration Projection")
    parser.add_argument(
        "--policy", default="UE000576",
        help="Policy number (default: UE000576)",
    )
    parser.add_argument(
        "--months", type=int, default=12,
        help="Months to project (default: 12)",
    )
    parser.add_argument(
        "--region", default="CKPR",
        help="DB2 region (default: CKPR)",
    )
    parser.add_argument(
        "--excel", default=None, metavar="FILE",
        help="Export debug output to Excel file",
    )
    parser.add_argument(
        "--rate", type=float, default=None,
        help="Override current interest rate (e.g., 0.0425)",
    )
    parser.add_argument(
        "--premium", type=float, default=None,
        help="Override modal premium",
    )
    parser.add_argument(
        "--dbo", default=None, choices=["A", "B", "C"],
        help="Override death benefit option (A, B, or C)",
    )
    parser.add_argument(
        "--av", type=float, default=None,
        help="Override account value",
    )
    args = parser.parse_args()

    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.illustration_policy_service import (
        build_illustration_data,
    )
    from suiteview.illustration.models.calc_state import MonthlyState

    # ── Load policy ───────────────────────────────────────────
    print(f"Loading {args.policy} from {args.region}...")
    policy = build_illustration_data(args.policy, args.region)

    print(f"  Plancode:     {policy.plancode}")
    print(f"  Product:      {policy.product_type}")
    print(f"  Issue Date:   {policy.issue_date}")
    print(f"  Issue Age:    {policy.issue_age}")
    print(f"  Attained Age: {policy.attained_age}")
    print(f"  Face:         ${policy.face_amount:,.2f}")
    print(f"  Band:         {policy.band}")
    print(f"  DBO:          {policy.db_option}")
    print(f"  AV:           ${policy.account_value:,.2f}")
    print(f"  Premium:      ${policy.modal_premium:,.2f}/mo")
    print(f"  Rate Sex:     {policy.rate_sex}")
    print(f"  Rate Class:   {policy.rate_class}")
    print(f"  Val Date:     {policy.valuation_date}")
    print(f"  Dur:          {policy.duration} (yr {policy.policy_year} mo {policy.policy_month})")
    print(f"  Guar Rate:    {policy.guaranteed_interest_rate}")
    print(f"  Curr Rate:    {policy.current_interest_rate}")
    print(f"  DOLI:         {policy.def_of_life_ins}")
    print(f"  CTP:          ${policy.ctp:,.2f}")
    print(f"  Segments:     {len(policy.segments)}")
    print(f"  Benefits:     {len(policy.benefits)}")
    for b in policy.benefits:
        bkey = (b.benefit_type or "") + (b.benefit_subtype or "")
        print(f"    [{bkey}] age={b.issue_age} units={b.units:.3f} vpu={b.vpu:.2f}")

    # ── Apply overrides ───────────────────────────────────────
    if args.rate is not None:
        policy.current_interest_rate = args.rate
        print(f"\n  [Override] Interest rate → {args.rate}")
    if args.premium is not None:
        policy.modal_premium = args.premium
        print(f"  [Override] Modal premium → ${args.premium:,.2f}")
    if args.dbo is not None:
        policy.db_option = args.dbo
        print(f"  [Override] DB option → {args.dbo}")
    if args.av is not None:
        policy.account_value = args.av
        print(f"  [Override] Account value → ${args.av:,.2f}")

    # ── Project ───────────────────────────────────────────────
    print(f"\nProjecting {args.months} months...")
    engine = IllustrationEngine()
    results = engine.project(policy, months=args.months)

    # ── Console output ────────────────────────────────────────
    print(f"\n{'='*172}")
    print(f"{'Dur':>4}  {'Yr':>3} {'Mo':>3}  {'Age':>3}  "
          f"{'Gross Prem':>12}  {'Net Prem':>12}  {'AV aft Prem':>12}  "
          f"{'Std DB':>12}  {'Corr Amt':>10}  {'Gross DB':>12}  "
          f"{'NAR Cov1':>12}  {'NAR Corr':>10}  "
          f"{'COI Cov1':>10}  {'COI Corr':>10}  {'COI Tot':>10}  "
          f"{'EPU':>8}  {'BenChg':>8}  {'Tot Ded':>10}  "
          f"{'Interest':>10}  {'End AV':>12}")
    print(f"{'='*172}")

    for s in results:
        flag = " LAPSE" if s.lapsed else ""
        # Mark inforce snapshot row (month 0 — no premium activity)
        label = " [INFORCE]" if s.gross_premium == 0.0 and s == results[0] else ""
        print(
            f"{s.duration:>4}  {s.policy_year:>3} {s.policy_month:>3}  "
            f"{s.attained_age:>3}  "
            f"{s.gross_premium:>12,.2f}  {s.net_premium:>12,.2f}  "
            f"{s.av_after_premium:>12,.2f}  "
            f"{s.standard_db:>12,.2f}  {s.corr_amount:>10,.2f}  "
            f"{s.gross_db:>12,.2f}  "
            f"{s.nar_cov1:>12,.2f}  {s.nar_corr:>10,.2f}  "
            f"{s.coi_charge_cov1:>10,.2f}  {s.coi_charge_corr:>10,.2f}  "
            f"{s.coi_charge:>10,.2f}  "
            f"{s.epu_charge:>8,.2f}  {s.benefit_charges:>8,.2f}  {s.total_deduction:>10,.2f}  "
            f"{s.interest_credited:>10,.2f}  {s.av_end_of_month:>12,.2f}"
            f"{flag}{label}"
        )

    if len(results) > 1:
        last = results[-1]
        print(f"\n--- Summary ---")
        print(f"Final AV:            ${last.av_end_of_month:,.2f}")
        print(f"Final Surrender Val: ${last.surrender_value:,.2f}")
        print(f"Final DB:            ${last.ending_db:,.2f}")
        print(f"Total Interest:      ${last.cumulative_interest:,.2f}")
        print(f"Total Charges:       ${last.cumulative_charges:,.2f}")
        print(f"Total Premiums:      ${last.premiums_to_date:,.2f}")
        if last.lapsed:
            print(f"** LAPSED at duration {last.duration} **")

    # ── Excel export ──────────────────────────────────────────
    if args.excel:
        from suiteview.illustration.debug.excel_export import (
            export_projection_to_excel,
        )

        out_path = export_projection_to_excel(results, args.excel, policy_data=policy)
        print(f"\nExcel debug output saved to: {out_path}")


if __name__ == "__main__":
    main()
