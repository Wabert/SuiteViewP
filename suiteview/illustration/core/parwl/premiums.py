"""CyberLife modal premiums for a par WL policy on a given date.

Reproduced from billed premiums (``tools/rerun/verify_parwl_inforce.py``):

* each coverage's annual premium (units x ``ANN_PRM_UNT_AMT``) plus the annual premiums
  of the benefits attached to it are modalized together (CyberDoc D10 ``DSBPRMAS`` 0):
  ``round((coverage + benefits) x mode factor, 2)`` (B111A100 14739485: 72.30 x 0.0864);
* each substandard extra premium (units x ``SST_XTR_UNT_AMT``) is modalized on its own
  (E0112582: 69.14 + 16.09; 14738679: 37.91 + 9.86);
* the policy fee is ``round(fee x fee factor, 2)`` when the plan adds it for the mode,
  the fee band chosen by base units (``rates._mode_factors``);
* ``POLICY_FEE_RULE`` Z (B711E100, B111A100) adds the annual fee to the annual premium
  and rounds the modal premium once: ``round((premiums + extras + fee) x factor, 2)``
  (E0022097: 531.80 x 0.0864 = 45.95; NLS02292: 2,250.00 x 0.515 = 1,158.75; the VPMS
  Affinity model's ``CurrModalPremium``). The cent that single rounding moves is shown
  as ``rounding``.

A coverage stops billing at its pay-up date, a benefit or extra at its cease date. The
premium on the record is the one in effect on the valuation date: a rider that expires
at the paid-to date is still in it (13302410).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from suiteview.core.modal_premium import POLICY_FEE_ADD_MODES
from suiteview.illustration.core.fixed_premium import FEE_IN_ANNUAL_PREMIUM, MODES_BY_FREQUENCY, ModeFactors
from suiteview.illustration.core.fixed_premium import cents as _cents
from suiteview.illustration.core.parwl.rates import ParWLRates
from suiteview.illustration.models.parwl import ROLE_BASE, ROLE_PUA_RIDER, ParWLPolicy


@dataclass(frozen=True)
class ModalPremiumParts:
    """A modal premium split the way the Values pages show it."""

    base: float = 0.0
    rider: float = 0.0
    benefit: float = 0.0
    extra: float = 0.0
    fee: float = 0.0
    prem_factor: float = 1.0
    rounding: float = 0.0

    @property
    def total(self) -> float:
        return _cents(self.base + self.rider + self.benefit + self.extra + self.fee + self.rounding)


def policy_mode(policy: ParWLPolicy) -> str:
    return MODES_BY_FREQUENCY.get(int(policy.billing_frequency), "")


def mode_factors(policy: ParWLPolicy, rates: ParWLRates) -> Optional[ModeFactors]:
    return rates.mode_factor(policy_mode(policy))


def _active(cease: Optional[date], when: date) -> bool:
    return cease is None or when < cease


def record_premium_date(policy: ParWLPolicy) -> date:
    """The date whose modal premium the record's billed ``POL_PRM_AMT`` is."""
    return policy.valuation_date


def modal_premium(policy: ParWLPolicy, rates: ParWLRates, when: date) -> ModalPremiumParts:
    """The modal premium due on ``when`` (all coverages, benefits, extras and fee)."""
    mode = policy_mode(policy)
    factors = rates.mode_factor(mode)
    factor = factors.prem_factor if factors is not None else policy.billing_frequency / 12.0
    per_unit_first = factors is not None and factors.multiply_order == "2"

    def modal(units: float, rate: float) -> float:
        if per_unit_first:
            return _cents(units * _cents(rate * factor))
        return _cents(units * rate * factor)

    base = rider = benefit = extra = annual = 0.0
    for cov in policy.coverages:
        if cov.role == ROLE_PUA_RIDER:
            continue
        paying = _active(cov.pay_up_date or cov.maturity_date, when)
        benefits = [b for b in policy.benefits if b.phase == cov.phase and _active(b.cease_date, when)
                    and b.annual_premium > 0]
        rate = cov.annual_premium_per_unit if paying else 0.0
        alone = modal(cov.units, rate)
        if per_unit_first:
            together = alone + sum(modal(b.units, b.annual_premium_per_unit * b.rate_factor) for b in benefits)
        else:
            together = _cents((cov.units * rate + sum(b.annual_premium for b in benefits)) * factor)
        if cov.role == ROLE_BASE:
            base += alone
        else:
            rider += alone
        benefit += together - alone
        annual += cov.units * rate + sum(b.annual_premium for b in benefits)
        if paying:
            for per_unit, cease in cov.extra_premiums:
                if _active(cease, when):
                    extra += modal(cov.units, per_unit)
                    annual += cov.units * per_unit
    fee = fee_annual = 0.0
    if factors is not None and factors.policy_fee_annual and base + rider + benefit + extra > 0:
        if mode in POLICY_FEE_ADD_MODES.get(factors.fee_add, frozenset()):
            fee_annual = factors.policy_fee_annual
            fee = _cents(fee_annual * factors.fee_factor)
    parts = ModalPremiumParts(_cents(base), _cents(rider), _cents(benefit), _cents(extra), fee, factor)
    if factors is not None and not per_unit_first and factors.policy_fee_rule == FEE_IN_ANNUAL_PREMIUM \
            and base + rider + benefit + extra > 0:
        once = _cents(annual * factor + fee_annual * factors.fee_factor)
        rounding = _cents(once - parts.total)
        if rounding:
            parts = ModalPremiumParts(parts.base, parts.rider, parts.benefit, parts.extra, fee, factor, rounding)
    return parts
