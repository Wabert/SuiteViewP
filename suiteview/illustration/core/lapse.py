"""Effective lapse basis for optional from-issue account-value protection."""

from math import isfinite

from dateutil.relativedelta import relativedelta

from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def validate_no_lapse_years(years: float) -> float:
    if (isinstance(years, bool) or not isinstance(years, (int, float))
            or not isfinite(years) or years < 0):
        raise ValueError("No Lapse Period must be a finite, nonnegative number of years.")
    return float(years)


def default_issue_no_lapse_years(
    policy: IllustrationPolicyData, config: PlancodeConfig | None,
) -> float:
    if policy.map_cease_date is not None and policy.issue_date is not None:
        issue, cease = policy.issue_date, policy.map_cease_date
        months = (cease.year - issue.year) * 12 + cease.month - issue.month
        if cease < issue + relativedelta(months=months):
            months -= 1
        return max(0, months + 1) / 12.0
    if config is not None and config.snet_period > 0:
        return float(config.snet_period)
    return 0.0


def issue_no_lapse_years(
    policy: IllustrationPolicyData, config: PlancodeConfig | None,
) -> float:
    years = policy.issue_no_lapse_years
    return (
        default_issue_no_lapse_years(policy, config)
        if years is None else validate_no_lapse_years(years)
    )


def lapse_value_for_month(
    policy: IllustrationPolicyData, config: PlancodeConfig, duration: int,
) -> str:
    if policy.run_from_issue:
        # Projections operate in whole months, including the issue deduction.
        months = round(issue_no_lapse_years(policy, config) * 12)
        if 1 <= duration <= months:
            return "AV"
    return config.lapse_value
