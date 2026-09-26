"""Premium-acceptance allowances — RERUN CalcEngine columns NC..NZ.

This is the "Apply Premium" cap chain. Given the 7702 guideline limit, the
7-pay (TAMRA) limit and this month's *requested* premium, it works out how much
premium the policy will actually accept and how that splits between a one-off
deposit (lumpsum / unscheduled premium) and the scheduled modal premium.

All money inputs/outputs are dollars. ``INF`` is the internal unbounded-room
sentinel for disabled caps; it is never a payable premium. Guideline room is
tested by policy year, while 7-pay room is tested by TAMRA year/month from the
active material-change start date. Values are floored to payable whole cents at
the same hand-off points as RERUN.

The chain mirrors the workbook column-for-column so the Values tab can show the
same intermediate allowances RERUN does:

    NC/ND/NE  GP / NPT / TAMRA allowance *before any premium applied*
    NF        Annual Cap0
    NG..NK    after the 1035 exchange     (1035 is not modeled here -> applied=0,
              so the "1" allowances equal the "0" allowances)
    NL/NM     lumpsum (unscheduled) remaining + applied
    NN..NQ    GP / NPT / TAMRA allowance *after the lumpsum*, Annual Cap2
    NR..NU    the per-mode *level* allowances (the allowance spread across the
              remaining modal payments in the year)
    NV        Scheduled Prem Cap — the binding per-payment level cap, initialized
              at a new 7-pay start, recalculated each policy year, and carried
              between those anchors
    NW        Levelized Max Premium = MIN(NV, requested scheduled)
    NX        Apply Levelized Premium? — the levelizing option, off when the
              policy carries a loan
    NY        Scheduled Premium less loan repay
    NZ        vAppliedScheduledPremium — the scheduled premium finally accepted

Two ideas drive the level machinery (NR..NW):

  * **Levelizing.** When a premium cap binds you can either apply premium
    dollar-for-dollar until the annual room runs out mid-year, or spread the
    allowed premium evenly across the year's modal payments. NX selects the
    behaviour; when it is on, each payment is capped at NW instead of being
    billed in full until NQ is exhausted.

  * **BOY vs EOY.** The TAMRA (7-pay) year is measured from the 7-pay start
    date, which need not coincide with the policy anniversary. When the TAMRA
    anniversary falls mid-policy-year, the limit governing the early part of the
    year (NR, beginning-of-year, divided over the TAMRA-year payment count LU)
    differs from the limit governing the later part (NS, end-of-year, which adds
    the next 7-pay premium becoming available, divided over the policy-year
    payment count LT). NV takes the smaller so a level premium breaches neither.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

from suiteview.illustration.constants import INF, MONEY_EPSILON


@dataclass(frozen=True)
class PremiumAllowanceInput:
    """Inputs to the NC..NZ premium-acceptance chain for one projection month.

    Amounts are dollars unless labelled as counts/flags.  ``policy_month`` is
    policy-year month 1..12; TAMRA year/month are measured from the active
    7-pay start, which can be off-anniversary.  Loan-repayment fields are the
    RERUN MH/MI/MY hand-off from the loan step before premium is applied.
    """

    is_cvat: bool                         # CVAT policies use NPT/TAMRA room
    is_gpt: bool                          # GPT policies use GLP/GSP room
    tefra_force: bool                     # enforce guideline cap
    tamra_force: bool                     # enforce 7-pay cap
    mec_bypass: bool                      # loaded/inforce MEC bypasses 7-pay cap
    guideline_limit: float                # KV — MAX(GSP, AccumGLP)
    prem_less_wd: float                   # KW — PremTD − WithdrawalTD
    force_out: float                      # KX — force-out distribution this month
    loan_repay_from_forceout: float       # MJ — force-out used for loan repay
    seven_pay_level: float                # KY — annual 7-pay level
    tamra_year: int                       # LD — active 7-pay year
    tamra_month_of_year: int              # LC — month within active TAMRA year
    policy_month: int                     # E — month within policy year
    amount_in_7pay: float                 # LE — cumulative 7-pay before month
    npt_premium: float                    # CVAT necessary premium; 0 for GPT
    tamra_reset: bool                     # KZ — new 7-pay period this month
    requested_scheduled: float            # LS — scheduled modal premium requested
    requested_lumpsum: float              # unscheduled/lump-sum premium requested
    payment_count_policy_year: int        # LT — remaining policy-year payments
    payment_count_tamra_year: int         # LU — remaining TAMRA-year payments
    loan_repay_from_lumpsum: float        # MH — premium-to-loan from lump sum
    loan_repay_from_scheduled: float      # MI — premium-to-loan from scheduled
    ln_repay_left_over: float             # MY — over-repayment returned to premium
    has_loan_balance: bool                # any fixed/variable debt before repay
    levelizing_premium: bool              # sINPUT_LevelizingPremium
    beginning_of_year: bool               # vBeginningOfYearCalc
    policy_anniversary: bool              # anchors scheduled cap recalculation
    prior_scheduled_prem_cap: float       # prior NV
    prior_scheduled_cap_by_guideline: bool = False
    prior_scheduled_cap_by_tamra: bool = False
    dollar_for_dollar_in_transition_year: bool = False
    prior_guideline_limit_reached: bool = False
    prior_transition_year_active: bool = False


def _floor_cent(value: float) -> float:
    """Floor a nonnegative modal premium to a payable whole-cent amount."""
    cents = (Decimal(f"{value:.10f}") * 100).to_integral_value(rounding=ROUND_FLOOR)
    return float(cents) / 100.0


@dataclass
class PremiumAllowances:
    """Every named column of the NC..NZ "Apply Premium" chain for one month."""

    # ── NC / ND / NE — before any premium applied ──
    gp_allowance_0: float = 0.0
    npt_allowance_0: float = 0.0
    tamra_allowance_0: float = 0.0
    annual_cap_0: float = 0.0                # NF
    # ── NG..NK — after the 1035 exchange (1035 not modeled -> applied_1035 == 0) ──
    applied_1035: float = 0.0
    gp_allowance_1: float = 0.0
    npt_allowance_1: float = 0.0
    tamra_allowance_1: float = 0.0
    annual_cap_1: float = 0.0                # NK
    # ── NL / NM — lumpsum (unscheduled) ──
    lumpsum_remaining: float = 0.0
    applied_lumpsum: float = 0.0
    # ── NN..NQ — after the lumpsum ──
    gp_allowance_2: float = 0.0
    npt_allowance_2: float = 0.0
    tamra_allowance_2: float = 0.0
    annual_cap_2: float = 0.0                # NQ
    # ── NR..NU — per-mode level allowances ──
    tamra_level_allowance_boy: float = 0.0
    tamra_level_allowance_eoy: float = 0.0
    npt_level_allowance: float = 0.0
    gp_level_allowance: float = 0.0
    # ── NV..NZ — scheduled-premium cap chain ──
    scheduled_prem_cap: float = 0.0          # NV
    levelized_max_premium: float = 0.0       # NW
    apply_levelized: bool = False            # NX
    scheduled_less_loan_repay: float = 0.0   # NY
    applied_scheduled_premium: float = 0.0   # NZ
    scheduled_cap_by_guideline: bool = False
    scheduled_cap_by_tamra: bool = False
    capped_by_guideline: bool = False
    capped_by_tamra: bool = False
    # True in the transition year when levelizing is suppressed dollar-for-dollar
    # (see ``dollar_for_dollar_in_transition_year``); carried across the year.
    in_transition_year: bool = False
    # ── carried for display only ──
    prem_less_wd: float = 0.0                # KW = PremTD − WithdrawalTD

    @property
    def applied_total_premium(self) -> float:
        """vAppliedTotalPremium = 1035 + lumpsum + scheduled (OD/OO basis)."""
        return self.applied_1035 + self.applied_lumpsum + self.applied_scheduled_premium

    def to_detail(self) -> dict:
        """The "Apply Premium" Values-tab columns keyed by their RERUN names."""
        return {
            "GP_Allowance0": self.gp_allowance_0,
            "NPT Allowance0": self.npt_allowance_0,
            "TAMRA_Allowance0": self.tamra_allowance_0,
            "Annual Cap0": self.annual_cap_0,
            "Applied1035": self.applied_1035,
            "GP_Allowance1": self.gp_allowance_1,
            "NPT Allowance 1": self.npt_allowance_1,
            "TAMRA_Allowance1": self.tamra_allowance_1,
            "Annual Cap1": self.annual_cap_1,
            "Lumpsum Remaining": self.lumpsum_remaining,
            "vAppliedLumpsum": self.applied_lumpsum,
            "GP_Allowance2": self.gp_allowance_2,
            "NPT Allowance 2": self.npt_allowance_2,
            "TAMRA_Allowance2": self.tamra_allowance_2,
            "Annual Cap2": self.annual_cap_2,
            "TAMRA_Level_Allowance_BOY": self.tamra_level_allowance_boy,
            "TAMRA_Level_Allowance_EOY": self.tamra_level_allowance_eoy,
            "NPT_Level_Allowance": self.npt_level_allowance,
            "GP_Level_Allowance": self.gp_level_allowance,
            "Scheduled Prem Cap": self.scheduled_prem_cap,
            "Levelized Max Premium": self.levelized_max_premium,
            "Apply Levelized Premium": self.apply_levelized,
            "In Transition Year": self.in_transition_year,
            "Scheduled Premium less Loan Repay": self.scheduled_less_loan_repay,
            "AppliedScheduledPremium": self.applied_scheduled_premium,
        }


def _annual_cap(
    *, is_gpt: bool, tefra_force: bool, tamra_force: bool, mec_bypass: bool,
    gp_allowance: float, npt_allowance: float, tamra_allowance: float,
) -> float:
    """Annual Cap (NF / NK / NQ): the binding annual room from both tests.

    GP side binds only under GPT + TEFRA force; the TAMRA side binds under TAMRA
    force unless the policy is already an inforce MEC (then the 7-pay limit no
    longer applies).
    """
    gp_side = gp_allowance if (is_gpt and tefra_force) else INF
    if tamra_force:
        tamra_side = INF if mec_bypass else min(npt_allowance, tamra_allowance)
    else:
        tamra_side = INF
    return min(gp_side, tamra_side)


def _annual_cap_sources(
    inputs: PremiumAllowanceInput,
    gp_allowance: float,
    npt_allowance: float,
    tamra_allowance: float,
) -> tuple[bool, bool]:
    gp_side = gp_allowance if (inputs.is_gpt and inputs.tefra_force) else INF
    tamra_side = (
        INF if (not inputs.tamra_force or inputs.mec_bypass)
        else min(npt_allowance, tamra_allowance)
    )
    return (
        gp_side < INF and gp_side <= tamra_side + MONEY_EPSILON,
        tamra_side < INF and tamra_side <= gp_side + MONEY_EPSILON,
    )


def _active_tamra(inputs: PremiumAllowanceInput) -> bool:
    return inputs.tamra_force and not inputs.mec_bypass and inputs.tamra_year <= 7


def _set_initial_allowances(
    result: PremiumAllowances,
    inputs: PremiumAllowanceInput,
    forceout_adj: float,
) -> None:
    """Populate NC..NF, the room available before premium is applied."""
    result.gp_allowance_0 = (
        INF if inputs.is_cvat
        else max(0.0, inputs.guideline_limit - inputs.prem_less_wd + forceout_adj)
    )
    result.npt_allowance_0 = (
        INF if not inputs.is_cvat or inputs.tamra_year <= 7
        else inputs.npt_premium
    )
    result.tamra_allowance_0 = (
        max(
            0.0,
            inputs.seven_pay_level * inputs.tamra_year
            - inputs.amount_in_7pay
            + forceout_adj,
        )
        if inputs.tamra_year <= 7 else INF
    )
    result.annual_cap_0 = (
        result.gp_allowance_0 if (inputs.is_gpt and inputs.tefra_force) else INF
    )


def _apply_lumpsum_chain(
    result: PremiumAllowances,
    inputs: PremiumAllowanceInput,
) -> None:
    """Apply the zero-modeled 1035 and unscheduled premium columns NG..NQ."""
    result.applied_1035 = 0.0
    result.gp_allowance_1 = result.gp_allowance_0 - result.applied_1035
    result.npt_allowance_1 = result.npt_allowance_0 - result.applied_1035
    result.tamra_allowance_1 = result.tamra_allowance_0
    result.annual_cap_1 = _annual_cap(
        is_gpt=inputs.is_gpt,
        tefra_force=inputs.tefra_force,
        tamra_force=inputs.tamra_force,
        mec_bypass=inputs.mec_bypass,
        gp_allowance=result.gp_allowance_1,
        npt_allowance=result.npt_allowance_1,
        tamra_allowance=result.tamra_allowance_1,
    )

    result.lumpsum_remaining = (
        inputs.requested_lumpsum
        - inputs.loan_repay_from_lumpsum
        + inputs.ln_repay_left_over
    )
    result.applied_lumpsum = min(result.lumpsum_remaining, result.annual_cap_1)

    result.gp_allowance_2 = result.gp_allowance_1 - result.applied_lumpsum
    result.npt_allowance_2 = result.npt_allowance_1 - result.applied_lumpsum
    result.tamra_allowance_2 = max(
        result.tamra_allowance_1 - result.applied_lumpsum,
        0.0,
    )
    result.annual_cap_2 = _annual_cap(
        is_gpt=inputs.is_gpt,
        tefra_force=inputs.tefra_force,
        tamra_force=inputs.tamra_force,
        mec_bypass=inputs.mec_bypass,
        gp_allowance=result.gp_allowance_2,
        npt_allowance=result.npt_allowance_2,
        tamra_allowance=result.tamra_allowance_2,
    )


def _set_level_allowances(
    result: PremiumAllowances,
    inputs: PremiumAllowanceInput,
) -> None:
    """Populate NR..NU by spreading annual room over remaining modal payments."""
    lu = inputs.payment_count_tamra_year
    lt = inputs.payment_count_policy_year
    result.tamra_level_allowance_boy = (
        result.tamra_allowance_2 if lu == 0 else result.tamra_allowance_2 / lu
    )
    if inputs.tamra_month_of_year != inputs.policy_month and inputs.tamra_year < 7:
        eoy_numerator = (
            result.tamra_allowance_2
            + (0.0 if inputs.tamra_reset else inputs.seven_pay_level)
        )
    else:
        eoy_numerator = INF
    result.tamra_level_allowance_eoy = (
        eoy_numerator / lt if inputs.payment_count_policy_year > 0 else INF
    )
    result.npt_level_allowance = (
        result.npt_allowance_2 if lu == 0 else result.npt_allowance_2 / lu
    )
    result.gp_level_allowance = result.gp_allowance_2 / lt if lt > 0 else INF


def _scheduled_tamra_side(
    result: PremiumAllowances,
    inputs: PremiumAllowanceInput,
    active_tamra: bool,
) -> float:
    if not inputs.tamra_force or inputs.mec_bypass:
        return INF
    if not active_tamra and not inputs.is_cvat:
        return INF
    return min(
        result.tamra_level_allowance_boy,
        result.tamra_level_allowance_eoy,
        result.npt_level_allowance,
    )


def _set_scheduled_cap(
    result: PremiumAllowances,
    inputs: PremiumAllowanceInput,
) -> None:
    active_tamra = _active_tamra(inputs)
    tamra_constraint_exit = (
        inputs.prior_scheduled_cap_by_tamra
        and not active_tamra
    )
    cap_uninitialized = (
        inputs.prior_scheduled_prem_cap <= 0.0
        and not inputs.prior_scheduled_cap_by_guideline
        and not inputs.prior_scheduled_cap_by_tamra
    )
    recalculate_cap = (
        inputs.tamra_reset
        or inputs.policy_anniversary
        or tamra_constraint_exit
        or cap_uninitialized
    )
    if not recalculate_cap:
        result.scheduled_prem_cap = inputs.prior_scheduled_prem_cap
        result.scheduled_cap_by_guideline = inputs.prior_scheduled_cap_by_guideline
        result.scheduled_cap_by_tamra = inputs.prior_scheduled_cap_by_tamra
        return

    tamra_side = _scheduled_tamra_side(result, inputs, active_tamra)
    gp_side = (
        result.gp_level_allowance if (inputs.is_gpt and inputs.tefra_force)
        else INF
    )
    result.scheduled_prem_cap = _floor_cent(min(tamra_side, gp_side))
    result.scheduled_cap_by_guideline = (
        gp_side < INF and gp_side <= tamra_side + MONEY_EPSILON
    )
    result.scheduled_cap_by_tamra = (
        tamra_side < INF and tamra_side <= gp_side + MONEY_EPSILON
    )


def _apply_transition_year(
    result: PremiumAllowances,
    inputs: PremiumAllowanceInput,
) -> None:
    if inputs.beginning_of_year:
        gp_binds_this_year = (
            inputs.is_gpt
            and inputs.tefra_force
            and result.scheduled_cap_by_guideline
        )
        result.in_transition_year = (
            inputs.dollar_for_dollar_in_transition_year
            and gp_binds_this_year
            and not inputs.prior_guideline_limit_reached
        )
    else:
        result.in_transition_year = inputs.prior_transition_year_active


def _tamra_scheduled_gate(inputs: PremiumAllowanceInput, result: PremiumAllowances) -> float:
    if not inputs.tamra_force:
        return INF
    return INF if inputs.mec_bypass else result.npt_allowance_0


def _apply_lumpsum_cap_flags(
    result: PremiumAllowances,
    inputs: PremiumAllowanceInput,
) -> None:
    if result.applied_lumpsum >= result.lumpsum_remaining - MONEY_EPSILON:
        return
    gp_binds, tamra_binds = _annual_cap_sources(
        inputs,
        result.gp_allowance_1,
        result.npt_allowance_1,
        result.tamra_allowance_1,
    )
    result.capped_by_guideline |= gp_binds
    result.capped_by_tamra |= tamra_binds


def _apply_scheduled_cap_flags(
    result: PremiumAllowances,
    inputs: PremiumAllowanceInput,
    *,
    levelized_or_full: float,
    tamra_scheduled_gate: float,
) -> None:
    if result.applied_scheduled_premium >= (
        result.scheduled_less_loan_repay - MONEY_EPSILON
    ):
        return
    if result.annual_cap_2 <= min(levelized_or_full, tamra_scheduled_gate) + MONEY_EPSILON:
        gp_binds, tamra_binds = _annual_cap_sources(
            inputs,
            result.gp_allowance_2,
            result.npt_allowance_2,
            result.tamra_allowance_2,
        )
        result.capped_by_guideline |= gp_binds
        result.capped_by_tamra |= tamra_binds
    if (
        result.apply_levelized
        and result.levelized_max_premium
        < result.scheduled_less_loan_repay - MONEY_EPSILON
    ):
        result.capped_by_guideline |= result.scheduled_cap_by_guideline
        result.capped_by_tamra |= result.scheduled_cap_by_tamra
    if tamra_scheduled_gate <= min(result.annual_cap_2, levelized_or_full) + MONEY_EPSILON:
        result.capped_by_tamra = True


def _apply_scheduled_premium(
    result: PremiumAllowances,
    inputs: PremiumAllowanceInput,
) -> None:
    result.levelized_max_premium = min(
        result.scheduled_prem_cap,
        inputs.requested_scheduled,
    )
    result.apply_levelized = (
        inputs.levelizing_premium
        and not inputs.has_loan_balance
        and not result.in_transition_year
    )
    result.scheduled_less_loan_repay = (
        inputs.requested_scheduled - inputs.loan_repay_from_scheduled
    )
    levelized_or_full = (
        min(result.levelized_max_premium, result.scheduled_less_loan_repay)
        if result.apply_levelized else result.scheduled_less_loan_repay
    )
    tamra_scheduled_gate = _tamra_scheduled_gate(inputs, result)
    result.applied_scheduled_premium = min(
        result.annual_cap_2,
        levelized_or_full,
        tamra_scheduled_gate,
    )
    _apply_lumpsum_cap_flags(result, inputs)
    _apply_scheduled_cap_flags(
        result,
        inputs,
        levelized_or_full=levelized_or_full,
        tamra_scheduled_gate=tamra_scheduled_gate,
    )


def compute_premium_allowances(inputs: PremiumAllowanceInput) -> PremiumAllowances:
    """Compute the NC..NZ "Apply Premium" chain for one month.

    Returns a :class:`PremiumAllowances` whose ``applied_total_premium`` is the
    gross premium the policy accepts this month (the value the AV pipeline then
    splits into target/excess and loads).
    """
    result = PremiumAllowances(prem_less_wd=inputs.prem_less_wd)
    forceout_adj = inputs.force_out - inputs.loan_repay_from_forceout

    _set_initial_allowances(result, inputs, forceout_adj)
    _apply_lumpsum_chain(result, inputs)
    _set_level_allowances(result, inputs)
    _set_scheduled_cap(result, inputs)
    _apply_transition_year(result, inputs)
    _apply_scheduled_premium(result, inputs)
    return result
