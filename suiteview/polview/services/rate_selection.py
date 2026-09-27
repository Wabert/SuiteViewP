"""Rate tree selection data shaping."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace


@dataclass(frozen=True)
class RateSelection:
    display_title: str
    matrix: list[list] | None = None
    message: str = ""


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
