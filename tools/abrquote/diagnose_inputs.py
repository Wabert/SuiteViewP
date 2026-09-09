"""Run the resolver with read-only tracing of the unchanged dual-survival solver."""
import sys
from pathlib import Path
from dataclasses import asdict, replace
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.abrquote import resolve_inputs as resolver
from suiteview.abrquote.ui import assessment_panel
from suiteview.abrquote.core.mortality_engine import MortalityEngine


def survival_boundaries(params, table_1):
    pm = params.policy_month
    rows = []
    for table_2 in (-4.0, -1.0, 0.0, 1.0, 10.0):
        candidate = replace(
            params, table_rating_1=table_1,
            table_1_start_month=pm, table_1_last_month=pm + 59,
            table_rating_2=table_2, table_2_start_month=pm + 60,
            table_2_last_month=pm + 119,
        )
        engine = MortalityEngine(candidate)
        rows.append({"table_2": table_2,
                     "survival_5yr": engine.compute_survival_probability(5),
                     "survival_10yr": engine.compute_survival_probability(10)})
    return rows


def main():
    original_solve = assessment_panel.find_dual_table_ratings
    original_resolve = resolver.resolve_inputs
    traces = []

    def trace(params, five, ten, **kwargs):
        result = original_solve(params, five, ten, **kwargs)
        boundaries = survival_boundaries(params, result[0])
        ceiling = next(row["survival_10yr"] for row in boundaries if row["table_2"] == 0)
        traces.append({
            "base_params": asdict(params), "requested": {"five": five, "ten": ten},
            "canonical_solve_return": result, "boundary_projections": boundaries,
            "ten_year_target_above_nonnegative_table_ceiling": ten > ceiling + 0.0001,
            "semantics": "UI calls find_dual_table_ratings for cumulative 60/120 months "
                         "from current absolute policy month. MortalityEngine applies "
                         "table_2 only when positive; negative trials equal zero. "
                         "No horizon or formula was changed by this diagnostic.",
        })
        return result

    def resolve(source):
        package = original_resolve(source)
        package["output"]["provenance"]["medical_root_cause"] = traces
        return package

    with patch.object(assessment_panel, "find_dual_table_ratings", trace), \
            patch.object(resolver, "resolve_inputs", resolve):
        return resolver.main()


if __name__ == "__main__":
    raise SystemExit(main())
