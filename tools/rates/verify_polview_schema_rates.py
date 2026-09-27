"""Cross-check PolView's schema-``rates`` grids against the database's own lookup functions.

Usage: venv\\Scripts\\python.exe tools\\rates\\verify_polview_schema_rates.py '<json>'
JSON: {"policies": [{"policy": "UE063797", "company": "01"}], "region": "CKPR"}

For every coverage and benefit leaf, each duration column built by
``polview.models.schema_rates`` (keyed ``"<scale> <rate type>"``) is compared row by row with ``rates.fn_RATE`` /
``rates.fn_RATE_SUB`` (CELL), ``rates.fn_PLAN_RATE`` (PLAN) and ``rates.fn_DIV_RATE``
(base dividends), called with the cell the grid chose, the row's date (CALENDAR) or
the issue date (ISSUE), and the row's duration. Single-value rates are checked the
same way at duration 0. Read-only; prints a summary per leaf and each difference as it
is found. A lock timeout or deadlock (a rate load in progress) is retried; a policy that
still fails is reported as not checked and the run continues.
``@path.json`` reads the JSON from a file.
"""

import json
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dateutil.relativedelta import relativedelta

from suiteview.core.data_access.connections import connection_factory
from suiteview.core.local_dev import local_data_enabled
from suiteview.core.rates_schema import RatesSchemaRepository
from suiteview.polview.models import schema_rates as sr
from suiteview.polview.services.policy_service import get_policy_info

RETRIES = 4
RETRY_SECONDS = 15


def _norm(value):
    if value in (None, "", "NA"):
        return None
    try:
        return Decimal(str(value)).normalize()
    except ArithmeticError:
        return str(value)


class Checker:
    def __init__(self, connection):
        self.cursor = connection.cursor()
        self.checked = 0
        self.differences = []

    def one(self, sql, params):
        # The legacy SQL Server ODBC driver cannot bind datetime.date; pass ISO text.
        params = [p.isoformat() if hasattr(p, "isoformat") else p for p in params]
        for attempt in range(1, RETRIES + 1):
            try:
                row = self.cursor.execute(sql, params).fetchone()
                return None if row is None else row[0]
            except Exception as exc:
                # A rate load in progress (lock timeout HYT00 / deadlock victim 40001) is retried.
                if attempt == RETRIES or not any(code in str(exc) for code in ("HYT00", "40001")):
                    raise
                time.sleep(RETRY_SECONDS * attempt)

    def compare(self, label, column, year, grid_value, expected):
        self.checked += 1
        if _norm(grid_value) != (None if expected is None else Decimal(str(expected)).normalize()):
            line = f"{label} {column} year {year}: grid {grid_value!r} vs function {expected!r}"
            self.differences.append(line)
            print("DIFF", line, flush=True)


def _cell_expected(checker, ctx, assignment, rate_type, scale, on, year, point):
    duration = year - 1 if point else year
    if assignment.subseries:
        return checker.one(
            "SELECT RATE FROM rates.fn_RATE_SUB(?,?,?,?,?,?,?,?,?,?,?)",
            [ctx.plan.company, ctx.plancode, ctx.benefit, assignment.subseries, assignment.band,
             ctx.key.state or "**", rate_type, scale, on, ctx.issue_age, duration],
        )
    return checker.one(
        "SELECT RATE FROM rates.fn_RATE(?,?,?,?,?,?,?,?,?,?,?,?)",
        [ctx.plan.company, ctx.plancode, ctx.benefit, assignment.sex, assignment.rate_class, assignment.band,
         ctx.key.state or "**", rate_type, scale, on, ctx.issue_age, duration],
    )


def _single_rates(rows):
    """``{"<scale> <rate type>": value}`` from the grid's *Single rates (X)* metadata sections."""
    values, group = {}, None
    for row in rows:
        name = str(row[0])
        if name.startswith("Single rates (") and name.endswith(")"):
            group = name[len("Single rates ("):-1]
        elif group and name.startswith("  "):
            values[f"{group} {name.strip()}"] = row[1]
        else:
            group = None
    return values


def _check_leaf(checker, repo, policy, ctx, matrix, include_plan: bool):
    header = matrix[0]
    rows = matrix[1:]
    assignments = repo.cell_assignments(ctx.plan.company, ctx.plancode)
    rows_for_benefit = [a for a in assignments if a.benefit == ctx.benefit]
    subseries = repo.plan_subseries(ctx.plan.company, ctx.plancode)
    rate_types = repo.rate_types()
    meta = _single_rates(rows)
    before = checker.checked
    for rate_type in {a.rate_type for a in rows_for_benefit}:
        assignment, _ = sr.choose_cell(rows_for_benefit, rate_type, ctx.key, subseries)
        if assignment is None:
            continue
        calendar = rate_types[rate_type].date_meaning == "CALENDAR"
        point = rate_type in sr.POINT_IN_TIME_RATE_TYPES
        for scale in sr.SCALE_ORDER:
            name = f"{scale} {rate_type}"
            if name in header:
                column = header.index(name)
                for row in rows:
                    year = row[4]
                    on = ctx.issue_date + relativedelta(years=year - 1) if calendar else ctx.issue_date
                    expected = _cell_expected(checker, ctx, assignment, rate_type, scale, on, year, point)
                    checker.compare(ctx.label, name, year, row[column], expected)
            elif name in meta:
                expected = _cell_expected(checker, ctx, assignment, rate_type, scale, ctx.issue_date, 0, False)
                checker.compare(ctx.label, name, "single", meta[name], expected)
    if include_plan:
        _check_plan(checker, ctx.label, ctx.plan, ctx.key.state, ctx.issue_age, header, rows, meta)
    if "Dividend DIV" in header:
        column = header.index("Dividend DIV")
        for row in rows:
            year = row[4]
            on = ctx.issue_date + relativedelta(years=year - 1)
            expected = checker.one(
                "SELECT BASE_DIV FROM rates.fn_DIV_RATE(?,?,?,?,?,?,?,?,?,?,?,?)",
                [ctx.plan.company, ctx.plancode, *_div_key(repo, ctx), "D", ctx.issue_date, on,
                 ctx.issue_age, year],
            )
            checker.compare(ctx.label, "Dividend DIV", year, row[column], expected)
    return checker.checked - before


def _div_key(repo, ctx):
    chosen, _ = sr.choose_div(repo.div_assignments(ctx.plan.company, ctx.plancode), ctx.key, ctx.rein)
    return [chosen.sex, chosen.rate_class, chosen.band, ctx.key.state or "**", chosen.rein]


def _check_plan(checker, label, plan, state, issue_age, header, rows, meta):
    for name in [h for h in header if " " in h] + list(meta):
        scale, _, rate_type = name.partition(" ")
        if scale not in sr.SCALE_ORDER:
            continue
        exists = checker.one(
            "SELECT COUNT(*) FROM rates.RATE_ASSIGN_PLAN WHERE COMPANY = ? AND PLANCODE = ? AND RATE_TYPE = ? AND SCALE = ?",
            [plan.company, plan.plancode, rate_type, scale],
        )
        if not exists:
            continue
        if name in meta and name not in header:
            expected = checker.one("SELECT RATE FROM rates.fn_PLAN_RATE(?,?,?,?,?,?,?)",
                                   [plan.company, plan.plancode, state or "**", rate_type, scale, issue_age, 0])
            checker.compare(label, name, "single", meta[name], expected)
            continue
        column = header.index(name)
        for row in rows:
            year = row[4]
            expected = checker.one("SELECT RATE FROM rates.fn_PLAN_RATE(?,?,?,?,?,?,?)",
                                   [plan.company, plan.plancode, state or "**", rate_type, scale, issue_age, year])
            checker.compare(label, name, year, row[column], expected)


def _verify(entry, config, checker, repo):
    policy = get_policy_info(entry["policy"], region=entry.get("region", config.get("region", "CKPR")),
                             company_code=entry.get("company"), use_cache=False)
    if policy is None or not policy.exists:
        print(f"{entry['policy']}: not found or live policy access failed")
        return
    base = policy.coverages.base_plancode
    for index, cov in enumerate(policy.coverages.get_coverages(), start=1):
        try:
            ctx = sr.coverage_context(repo, policy, index)
            matrix = sr.build_coverage_matrix(repo, policy, index)
        except sr.RatesNotLoaded as exc:
            print(f"{policy.policy_number} Cov {index:02d}: skipped - {exc}")
            continue
        count = _check_leaf(checker, repo, policy, ctx, matrix, include_plan=cov.plancode != base)
        print(f"{policy.policy_number} Cov {index:02d} {cov.plancode}: {count} values checked")
    for index, _ben in enumerate(policy.benefits.get_benefits(), start=1):
        try:
            ctx = sr.benefit_context(repo, policy, index)
            matrix = sr.build_benefit_matrix(repo, policy, index)
        except sr.RatesNotLoaded as exc:
            print(f"{policy.policy_number} Ben {index:02d}: skipped - {exc}")
            continue
        count = _check_leaf(checker, repo, policy, ctx, matrix, include_plan=False)
        print(f"{policy.policy_number} Ben {index:02d} {ctx.benefit}: {count} values checked")
    try:
        matrix = sr.build_policy_matrix(repo, policy)
    except sr.RatesNotLoaded as exc:
        print(f"{policy.policy_number} Policy: skipped - {exc}")
        return
    plan, _ = sr._plan_for(repo, policy, base)
    cov = policy.coverages.get_coverages()[0]
    meta = _single_rates(matrix[1:])
    before = checker.checked
    _check_plan(checker, "Policy", plan, str(policy.product.issue_state or "").strip().upper(),
                int(cov.issue_age), matrix[0], matrix[1:], meta)
    print(f"{policy.policy_number} Policy {base}: {checker.checked - before} values checked")


def main():
    arg = sys.argv[1]
    config = json.loads(Path(arg[1:]).read_text(encoding="utf-8")) if arg.startswith("@") else json.loads(arg)
    if local_data_enabled():
        raise RuntimeError("This helper requires live data, not SUITEVIEW_LOCAL_DATA.")
    connection = connection_factory.connect_ul_rates(autocommit=True, timeout=30)
    checker = Checker(connection)
    failed = []
    try:
        with RatesSchemaRepository() as repo:
            for entry in config["policies"]:
                try:
                    _verify(entry, config, checker, repo)
                except Exception as exc:  # one locked or failing policy must not end the run
                    failed.append(entry["policy"])
                    print(f"{entry['policy']}: NOT CHECKED - {type(exc).__name__}: {exc}")
                sys.stdout.flush()
    finally:
        connection.close()
    print(json.dumps({"checked": checker.checked, "differences": len(checker.differences),
                      "policies_not_checked": failed}))
    return 1 if checker.differences or failed else 0


if __name__ == "__main__":
    sys.exit(main())
