"""Premiums received after the valuation date, added to an illustration's starting values.

CyberLife's starting values are as of the valuation monthliversary: the U1MV account
value (LH_POL_MVRY_VAL.CSV_AMT), the premium totals (LH_POL_TOTALS / LH_POL_YR_TOT)
and the coverage-target XP shadow value. A premium received since is pending in
FH_FIXED (FBB3_PROCD_IND = 0) until the next monthliversary processes it, so it is in
none of them. Live UE000576 (valuation 09/27/2026) shows this: its 10/04/2026 PR is
pending and LH_POL_TOTALS equals the processed premiums only (see
``value_rollback._processed_history``). FH_FIXED already carries the receipt's net
amount after premium load.

**Include Prem after Val date** adds those receipts to a scenario copy:

* premiums to date, premiums YTD, cost basis and the receipt's 7-pay year: + gross,
  in the starting values (the premiums are paid);
* account value: + CyberLife's recorded net (FH_FIXED NET_AMT, after premium load);
* shadow account: + gross less the shadow premium load (``shadow_calc``).

The account value and shadow amounts are credited on the forecast date, the first
projected monthliversary, like a premium paid then: the engine adds them at the start of
that month (``calc_engine.credit_premiums_received_after_valuation``). They earn no
interest between the valuation date and the forecast date, which would overstate the
values. A post-valuation receipt that is already processed would be in the premium
totals, so it blocks the option rather than being counted twice.
"""
from __future__ import annotations

from math import isfinite

from suiteview.illustration.core.interim_value import (
    add_received_premium_accumulators,
    next_monthliversary,
)
from suiteview.illustration.models.policy_data import (
    IllustrationPolicyData,
    PremiumAfterValuation,
)


def capture_premiums_after_valuation(
    pi, policy: IllustrationPolicyData,
) -> tuple[list[PremiumAfterValuation], str]:
    """Unreversed premiums received after ``policy.valuation_date``, or why not.

    Returns ``(premiums, "")`` or ``([], reason)``. Reasons are explicit so the
    option can be shown unavailable instead of silently including a partial set.
    """
    valuation = policy.valuation_date
    if valuation is None or policy.issue_date is None:
        return [], ""
    transactions = pi.activity.get_premium_transactions()
    error = pi.table_error("FH_FIXED")
    if error:
        return [], f"Financial history (FH_FIXED) is unavailable: {error}"
    following = next_monthliversary(policy)
    premiums = []
    for transaction in transactions:
        if transaction.trans_date is None or transaction.trans_date <= valuation:
            continue
        try:
            premiums.append(_premium_after_valuation(transaction, valuation, following))
        except ValueError as exc:
            return [], str(exc)
    return premiums, ""


def _premium_after_valuation(transaction, valuation, following) -> PremiumAfterValuation:
    row = transaction.raw_data or {}
    received = transaction.trans_date
    label = f"The premium received {received:%m/%d/%Y}"
    processed = str(row.get("FBB3_PROCD_IND", "") or "").strip()
    if processed == "1":
        raise ValueError(
            f"{label} is already processed into CyberLife's premium totals but not into "
            f"the {valuation:%m/%d/%Y} account value; it cannot be added without double "
            "counting.")
    if processed != "0":
        raise ValueError(f"{label} has no FH_FIXED processing indicator (FBB3_PROCD_IND).")
    if str(row.get("FEB3_1035_EXCH_IND", "0") or "0").strip() != "0":
        raise ValueError(f"{label} is a 1035 exchange; its transferred cost basis is not captured.")
    if received >= following:
        raise ValueError(
            f"{label} is on or after the {following:%m/%d/%Y} monthliversary, which has not "
            f"been processed yet (values are as of {valuation:%m/%d/%Y}).")
    if transaction.net_amount is None:
        raise ValueError(f"{label} has no net amount after premium load.")
    gross = float(transaction.gross_amount)
    net = float(transaction.net_amount)
    if not (isfinite(gross) and isfinite(net)) or gross < 0 or net < 0:
        raise ValueError(f"{label} has a negative or invalid amount; corrections are not modeled.")
    return PremiumAfterValuation(
        received=received, gross=gross, net=net,
        transaction_type=transaction.trans_code or "PR")


def premiums_after_valuation_unavailable_reason(policy: IllustrationPolicyData | None) -> str:
    """Why the option cannot be selected for ``policy`` (``""`` when it can)."""
    if policy is None:
        return "Load a policy first."
    if policy.run_from_issue or policy.rollback_date is not None:
        return "Available only on the loaded inforce valuation."
    if policy.premiums_after_valuation_error:
        return policy.premiums_after_valuation_error
    if not policy.premiums_after_valuation:
        when = policy.valuation_date
        return (f"No premiums were received after the {when:%m/%d/%Y} valuation date."
                if when else "No valuation date was found.")
    return ""


def gross_premiums_after_valuation(policy: IllustrationPolicyData) -> float:
    return round(sum(premium.gross for premium in policy.premiums_after_valuation), 2)


def net_premiums_after_valuation(policy: IllustrationPolicyData) -> float:
    return round(sum(premium.net for premium in policy.premiums_after_valuation), 2)


def describe_premiums_after_valuation(policy: IllustrationPolicyData) -> str:
    """One line per receipt: ``10/04/2026 PR $150.00 gross, $138.00 net``."""
    return "\n".join(
        f"{premium.received:%m/%d/%Y} {premium.transaction_type} "
        f"${premium.gross:,.2f} gross, ${premium.net:,.2f} net of premium load"
        for premium in policy.premiums_after_valuation)


def forecast_date(policy: IllustrationPolicyData):
    """The first projected monthliversary, when the receipts are credited."""
    return next_monthliversary(policy)


def account_value_with_receipts(policy: IllustrationPolicyData) -> float:
    """Valuation AV plus the receipts' net, the amount the forecast month opens with."""
    added = net_premiums_after_valuation(policy) if policy.premiums_after_valuation_included else 0.0
    return round(float(policy.account_value) + added, 2)


def shadow_value_with_receipts(policy: IllustrationPolicyData) -> float:
    added = (float(policy.premiums_after_valuation_shadow_net or 0.0)
             if policy.premiums_after_valuation_included else 0.0)
    return round(float(policy.shadow_account_value) + added, 2)


def include_premiums_after_valuation(
    policy: IllustrationPolicyData, *, config=None, rates=None,
) -> IllustrationPolicyData:
    """Include the captured receipts in ``policy``, a scenario copy, in place.

    Premium totals take the gross now; the AV net and shadow net are kept for the
    engine to credit on the forecast date. ``config``/``rates`` are loaded through
    the engine's loaders when the shadow load needs them and none are supplied.
    """
    if policy.premiums_after_valuation_included:
        raise ValueError("Premiums after the valuation date are already included.")
    reason = premiums_after_valuation_unavailable_reason(policy)
    if reason:
        raise ValueError(f"Premiums after the valuation date cannot be included: {reason}")
    received = [(premium.received, premium.gross) for premium in policy.premiums_after_valuation]
    shadow_net = 0.0
    if policy.has_shadow_account:
        if config is None:
            from suiteview.illustration.models.plancode_config import load_plancode

            config = load_plancode(policy.plancode)
        if rates is None:
            from suiteview.illustration.core.rate_loader import load_rates

            rates = load_rates(policy, config)
        from suiteview.illustration.core.shadow_calc import shadow_net_premiums_received

        # The load sees the premium totals before these receipts.
        shadow_net = round(sum(shadow_net_premiums_received(
            policy, config, rates, received,
            next_monthliversary=next_monthliversary(policy))), 2)
    add_received_premium_accumulators(policy, received)
    policy.premiums_after_valuation_included = True
    policy.premiums_after_valuation_shadow_net = shadow_net
    return policy
