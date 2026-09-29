"""Rate tree selection data shaping."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace


@dataclass(frozen=True)
class RateSelection:
    """A Rates-tree grid: title, matrix (header row first) or a not-available message.

    ``header_labels`` / ``column_groups`` are the two-level header of the schema grids:
    each rate column's key (``"C COI"``) shows its rate type, under a band naming its
    scale group, for ``FilterTableView.set_header_labels`` / ``set_column_groups``.
    """
    display_title: str
    matrix: list[list] | None = None
    message: str = ""
    header_labels: dict = field(default_factory=dict)
    column_groups: list = field(default_factory=list)


# Rates-tree categories read from UL_Rates schema ``rates``. The older categories
# (Coverages, Benefits, Cash Values, Premium Rates, Modal Premium, Policy) read the
# legacy dbo rate tables and are listed under the tree's "Legacy (dbo)" branch.
SCHEMA_COVERAGE = "Schema Coverage"
SCHEMA_SCALES = "Schema Scales"
SCHEMA_BENEFIT = "Schema Benefit"
SCHEMA_POLICY = "Schema Policy"
SCHEMA_FIXED_FUNDS = "Schema Fixed Funds"
SCHEMA_INDEX_FUNDS = "Schema Index Funds"
SCHEMA_MODAL = "Schema Modal"
SCHEMA_SPACE = "Schema Rate Space"
SCHEMA_CATEGORIES = (
    SCHEMA_COVERAGE, SCHEMA_SCALES, SCHEMA_BENEFIT, SCHEMA_POLICY, SCHEMA_FIXED_FUNDS, SCHEMA_INDEX_FUNDS,
    SCHEMA_MODAL, SCHEMA_SPACE,
)


def _schema_selection(policy, category: str, index: int) -> RateSelection:
    from suiteview.polview.models.schema_rates import RatesNotLoaded, column_layout

    rates = policy.rates
    builders = {
        SCHEMA_COVERAGE: (f"Rates for Coverage {index}", "build_schema_coverage_matrix", (index,)),
        SCHEMA_SCALES: ("Coverage Rate Scales", "build_schema_scales_matrix", ()),
        SCHEMA_BENEFIT: (f"Rates for Benefit {index}", "build_schema_benefit_matrix", (index,)),
        SCHEMA_POLICY: ("Policy Level Rates", "build_schema_policy_matrix", ()),
        SCHEMA_FIXED_FUNDS: ("Fixed Fund Rates", "build_schema_fixed_fund_matrix", ()),
        SCHEMA_INDEX_FUNDS: ("Index Fund Rates", "build_schema_index_fund_matrix", ()),
        SCHEMA_MODAL: ("Modal Factors", "build_schema_modal_matrix", ()),
        SCHEMA_SPACE: ("Rate Space", "build_schema_rate_space_matrix", ()),
    }
    title, builder, args = builders[category]
    try:
        matrix = getattr(rates, builder)(*args)
    except RatesNotLoaded as exc:
        return RateSelection(title, message=str(exc))
    if category in (SCHEMA_COVERAGE, SCHEMA_BENEFIT, SCHEMA_POLICY) and matrix:
        labels, groups = column_layout(matrix[0])
        return RateSelection(title, matrix, header_labels=labels, column_groups=groups)
    return RateSelection(title, matrix)


def _product_rules(policy):
    try:
        rules = getattr(getattr(policy, "product", None), "product_rules", None)
    except Exception:
        rules = None
    if rules is not None:
        return rules
    product = getattr(policy, "product", None)
    product_type = str(getattr(product, "product_type", "") or "").strip().upper()
    rate_family = "WL" if product_type == "WL" else product_type
    return SimpleNamespace(
        rate_family=rate_family,
        is_advanced=bool(getattr(product, "is_advanced_product", False)),
    )


def build_rate_selection(policy, category: str, index: int) -> RateSelection:
    """Build the selected rates matrix or the user-facing not-available message."""
    if category in SCHEMA_CATEGORIES:
        return _schema_selection(policy, category, index)
    if category == "Coverages":
        rules = _product_rules(policy)
        if (rules.rate_family == "WL" and not rules.is_advanced
                and policy.status.premium_pay_status_code.strip() in ("44", "45")):
            return RateSelection(
                f"Whole Life Cash Value Rates - Coverage {index}",
                message="Cash value file is not available for policies on ETI or RPU.",
            )
        matrix = policy.rates.build_coverage_rate_matrix(index)
        title = f"Rates for Coverage {index}"
        if matrix and "CV" in matrix[0]:
            title = f"Whole Life Cash Value Rates - Coverage {index}"
        return RateSelection(title, matrix)
    if category == "Cash Values":
        title = f"Cash Value Rates - Coverage {index}"
        if policy.status.premium_pay_status_code.strip() in ("44", "45"):
            return RateSelection(
                title,
                message="Cash value file is not available for policies on ETI or RPU.",
            )
        return RateSelection(title, policy.rates.build_whole_life_coverage_rate_matrix(index))
    if category == "Premium Rates":
        return RateSelection(f"Premium Rates - Coverage {index}", policy.rates.build_premium_rate_matrix(index))
    if category == "Modal Premium":
        return RateSelection("Modal Premium", policy.rates.build_modal_premium_matrix())
    if category == "Benefits":
        return RateSelection(f"Rates for Benefit {index}", policy.rates.build_benefit_rate_matrix(index))
    if category == "Policy":
        return RateSelection("Policy Level Rates", policy.rates.build_policy_rate_matrix())
    return RateSelection("")


def missing_rate_diagnostic(policy, category: str, index: int) -> str:
    """Explain a missing rate matrix without doing UI work."""
    ok = "OK"
    missing = "MISSING"

    def wl_cv() -> str:
        return (
            f" (WL_RATE_CV: user={policy.rates.cyberlife_rate_user_code} "
            f"(company {policy.company_code}), "
            f"key={policy.rates.cov_cash_value_key(index)!r}, "
            f"issue_age={policy.coverages.cov_issue_age(index)}, user_defined=blank)"
        )

    if category == "Cash Values":
        return wl_cv()
    if category == "Coverages":
        rules = _product_rules(policy)
        if rules.rate_family == "WL" and not rules.is_advanced:
            return wl_cv()
        issue_date = policy.coverages.cov_issue_date(index)
        issue_age = policy.coverages.cov_issue_age(index)
        band = policy.rates.cov_band(index)
        missing_rates = "MISSING -- check UL_Rates connection"
        return (
            f" (issue_date={ok if issue_date else missing}"
            f", issue_age={ok if issue_age is not None else missing}"
            f", band={ok if band is not None else missing_rates})"
        )
    if category == "Benefits":
        issue_date = policy.coverages.cov_issue_date(1)
        benefits = policy.benefits.get_benefits()
        benefit_age = benefits[index - 1].issue_age if index <= len(benefits) else None
        return (
            f" (cov1_date={ok if issue_date else missing}"
            f", ben_age={ok if benefit_age is not None else missing})"
        )
    return ""
