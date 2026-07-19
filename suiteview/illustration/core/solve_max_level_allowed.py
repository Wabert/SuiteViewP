"""Solve the "Max Level Allowed" premium — the level modal premium that spreads
the policy's remaining lifetime guideline room evenly over every payment from
its start year to age 100 (or maturity if sooner).

Definition (closed-form room, 2026-07-19): the answer is

    premium = (guideline limit at the end of the paying window
               − net premiums the base inputs consume)
              / number of modal payments in the window

computed off a ZERO-premium engine projection, so the guideline limit is the
engine's own MAX(GSP, AccumGLP) as it stands at the end — any face-amount or
DB-option change in the base inputs, and the guideline recalc it triggers,
is fully reflected — and the consumed premiums are the engine's cumulative
PremTD − WithdrawalTD (KW). The payment count comes from the same projection's
month stream, so a mid-year forecast start pays exactly the remaining modal
due dates the engine will actually collect.

The final projection then APPLIES that premium and lets the guideline
acceptance chain cap individual payments where a year is transiently tight —
a policy funded right up to its guideline today may be clipped for the first
year or two until AccumGLP outruns the level premium, and that clipping is
expected, not an error. This replaces the previous "never capped at any
month" bisection, which collapsed the whole level premium to the tightest
early year even when every later year had ever-growing room — and could
return a "maximum" premium that underfunded the policy into a lapse.

CAVEAT — future policy changes: a guideline recalc can depend on the state of
the policy at the change (e.g. a DB-option change under a level death benefit
reads the account value, which depends on premiums paid). The closed form
reads the guideline chain at ZERO premium, so a change scheduled AFTER the
premium's start date may recalc differently once the solved premium is
actually paid. Changes ON the forecast date are safe (the recalc happens
before any solved premium lands). The UI surfaces this caveat and still
allows the run.

The premium schedule still stops at age 100 — AccumGLP stops growing there
(CalcEngine KU), so payments past it could never be inside the room.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.solve_level_to_exception import (
    level_to_exception_options,
)
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    IllustrationOptions,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData

# Months-between-payments → RERUN modal code.
_MODE_FROM_FREQ = {1: "M", 3: "Q", 6: "S", 12: "A"}
# Modal code → months between payments (due months are 1, 1+interval, …).
_MODE_INTERVALS = {"M": 1, "Q": 3, "S": 6, "A": 12}


class MaxLevelAllowedError(ValueError):
    """The solve cannot run for this policy (CVAT, base inputs already over the
    guideline limit, or no premium-paying window remains)."""


@dataclass
class MaxLevelAllowedResult:
    premium: float                 # solved modal level premium, rounded down
    mode: str                      # M / Q / S / A
    survives_to_maturity: bool     # in force at maturity at the solved premium
    end_age: int                   # attained age the projection reached
    maturity_av: float             # account value at the projection's last month
    total_premium_paid: float      # lifetime premiums at the solved premium
    iterations: int                # engine projections spent solving


def _default_mode(policy: IllustrationPolicyData) -> str:
    return _MODE_FROM_FREQ.get(int(policy.billing_frequency or 1), "M")


def solve_max_level_allowed(
    policy: IllustrationPolicyData,
    *,
    mode: Optional[str] = None,
    start_policy_year: int = 1,
    base_future_inputs: Optional[IllustrationInputSet] = None,
    allow_exceptions: bool = True,
    resolution: float = 0.01,
    base_options: Optional[IllustrationOptions] = None,
    engine: Optional[IllustrationEngine] = None,
) -> MaxLevelAllowedResult:
    """Closed-form maximum level premium: lifetime room over lifetime payments.

    Args:
        mode: modal cadence of the solved premium (M/Q/S/A); defaults to the
            policy's billing frequency.
        start_policy_year: policy year the level premium begins. Earlier years
            are governed by ``base_future_inputs`` (the honored prior premium
            rows); the level premium runs from this year to age 100 (or
            maturity if sooner), then stops.
        base_future_inputs: prior premium schedule AND any policy changes (face
            amount / DB option) to honor — the zero-premium probe carries them,
            so both the guideline limit (post-recalc) and the room they consume
            are reflected in the answer.
        allow_exceptions: whether the RESULT projection may ride GP exception
            premiums (follows the user's Allow GP Exception toggle so the solve
            basis matches the displayed run).
        resolution: rounding granularity; the result is rounded DOWN to this so
            the lifetime total lands inside the room.
        base_options: only ``exact_days_interest``, ``levelizing_premium`` and
            ``apply_prem_to_loan`` are read from it; the guideline and TAMRA
            conformance toggles are forced on (there is no premium room to
            measure without them).
    """
    if policy.is_cvat:
        raise MaxLevelAllowedError("Max Level Allowed applies to GPT policies only.")

    mode = (mode or _default_mode(policy)).upper()
    interval = _MODE_INTERVALS.get(mode)
    if interval is None:
        raise MaxLevelAllowedError(f"Unknown premium mode {mode!r}.")
    options = level_to_exception_options(base_options, allow_exceptions)
    engine = engine or IllustrationEngine()
    base = base_future_inputs

    # Premiums stop at age 100 — AccumGLP freezes there (CalcEngine KU), so any
    # level payment past it would always be outside the room. Maturity before
    # 100 needs no stop: the engine collects no premium on or after the
    # maturity date.
    stop_year: Optional[int] = None
    if policy.maturity_age > 100:
        stop_year = 100 - int(policy.issue_age or 0) + 1
        if stop_year <= int(start_policy_year):
            raise MaxLevelAllowedError(
                "No level-premium window remains — the policy is at or past "
                "the age-100 premium limit.")

    def project(premium: float, *, stop_on_lapse: bool = True) -> List[MonthlyState]:
        # The level row is appended even at zero: a 0-amount schedule at the
        # start year TERMINATES any base scheduled premium from that year on,
        # exactly as the real level premium will — so the probe's consumed
        # premiums match the final run's base contribution.
        scheds = list(base.scheduled_transactions) if base is not None else []
        scheds.append(ScheduledTransaction(
            kind=TransactionKind.PREMIUM, policy_year=int(start_policy_year),
            amount=float(premium), mode=mode))
        if stop_year is not None:
            scheds.append(ScheduledTransaction(
                kind=TransactionKind.PREMIUM, policy_year=int(stop_year),
                amount=0.0, mode="A"))
        future = IllustrationInputSet(
            scheduled_transactions=scheds,
            dated_transactions=list(base.dated_transactions) if base is not None else [],
            policy_changes=list(base.policy_changes) if base is not None else [],
        )
        return engine.project(policy, options=options, future_inputs=future,
                              stop_on_lapse=stop_on_lapse)

    # ── 1. Zero-premium probe: the guideline chain is premium-independent, so
    # one full-horizon run (no lapse stop — an unfunded policy may well lapse)
    # yields the end-of-window limit, the room the base inputs consume, and
    # the exact payment calendar.
    probe = project(0.0, stop_on_lapse=False)
    if len(probe) < 2:                      # [0] is the inforce seed row
        raise MaxLevelAllowedError(
            "The projection produced no forecast months to pay into.")
    final = probe[-1]
    limit = max(float(final.gsp or 0.0), float(final.accumulated_glp or 0.0))
    consumed = float(final.prem_less_wd or 0.0)
    room = limit - consumed
    if room < resolution:
        raise MaxLevelAllowedError(
            "The base inputs already consume the lifetime guideline room — "
            "no additional level premium is allowed.")

    # ── 2. Payment count: modal due months (policy months 1, 1+interval, …)
    # the level schedule spans, read off the probe's own month stream so a
    # mid-year start counts exactly the due dates the engine will collect.
    # probe[0] is the inforce seed row (current month, no premium) — skip it.
    payments = 0
    for state in probe[1:]:
        year = int(state.policy_year or 0)
        if year < int(start_policy_year):
            continue
        if stop_year is not None and year >= stop_year:
            continue
        if int(state.attained_age or 0) >= int(policy.maturity_age or 0):
            continue                        # no premium on/after maturity
        if (int(state.policy_month or 1) - 1) % interval == 0:
            payments += 1
    if payments <= 0:
        raise MaxLevelAllowedError(
            "No level-premium payment dates remain before the age-100 "
            "premium limit.")

    premium = max(0.0, math.floor(room / payments / resolution) * resolution)

    # ── 3. Apply it. The guideline cap clips any transiently tight year —
    # expected for a policy already funded to its guideline today.
    states = project(premium)
    return _build_result(premium, mode, policy, states, iterations=2)


def _build_result(
    premium: float,
    mode: str,
    policy: IllustrationPolicyData,
    states: List[MonthlyState],
    iterations: int,
) -> MaxLevelAllowedResult:
    end_age = int(states[-1].attained_age) if states else int(policy.attained_age or 0)
    survives = bool(states) and states[-1].attained_age >= policy.maturity_age
    maturity_av = float(states[-1].av_end_of_month) if states else 0.0
    applied_to_date = float(states[-1].premiums_to_date) if states else 0.0
    exception_paid = sum(float(s.gp_exception_prem_gross or 0.0) for s in states)
    loan_repaid = sum(float(s.applied_loan_repayment or 0.0) for s in states)
    return MaxLevelAllowedResult(
        premium=round(premium, 2),
        mode=mode,
        survives_to_maturity=survives,
        end_age=end_age,
        maturity_av=maturity_av,
        total_premium_paid=round(applied_to_date + exception_paid + loan_repaid, 2),
        iterations=iterations,
    )
