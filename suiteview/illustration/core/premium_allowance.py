"""Premium-acceptance allowances — RERUN CalcEngine columns NC..NZ.

This is the "Apply Premium" cap chain. Given the 7702 guideline limit, the
7-pay (TAMRA) limit and this month's *requested* premium, it works out how much
premium the policy will actually accept and how that splits between a one-off
deposit (lumpsum / unscheduled premium) and the scheduled modal premium.

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


def compute_premium_allowances(
    *,
    is_cvat: bool,
    is_gpt: bool,
    tefra_force: bool,
    tamra_force: bool,
    mec_bypass: bool,
    guideline_limit: float,            # KV — MAX(GSP, AccumGLP)
    prem_less_wd: float,               # KW — PremTD − WithdrawalTD (before force-out)
    force_out: float,                  # vForceOut this month (KX)
    loan_repay_from_forceout: float,   # MJ
    seven_pay_level: float,            # KY — v7PayPrem
    tamra_year: int,                   # LD
    tamra_month_of_year: int,          # LC
    policy_month: int,                 # E — vMonth (1..12)
    amount_in_7pay: float,             # LE
    npt_premium: float,                # vNPT_Premium (CVAT only; 0 for GPT)
    tamra_reset: bool,                 # KZ — new TAMRA period this month
    requested_scheduled: float,        # LS — scheduled modal premium due this month
    requested_lumpsum: float,          # vLumpsum — unscheduled deposit this month
    payment_count_policy_year: int,    # LT
    payment_count_tamra_year: int,     # LU
    loan_repay_from_lumpsum: float,    # MH
    loan_repay_from_scheduled: float,  # MI
    ln_repay_left_over: float,         # vLNRepayLeftOver
    has_loan_balance: bool,            # SUM(LX:LY, MB:MC) > 0
    levelizing_premium: bool,          # sINPUT_LevelizingPremium
    beginning_of_year: bool,           # vBeginningOfYearCalc
    policy_anniversary: bool,          # policy month 1; anchors NV recalculation
    prior_scheduled_prem_cap: float,   # NV (prior month) — for the carry-forward
    prior_scheduled_cap_by_guideline: bool = False,
    prior_scheduled_cap_by_tamra: bool = False,
    dollar_for_dollar_in_transition_year: bool = False,
    prior_guideline_limit_reached: bool = False,
    prior_transition_year_active: bool = False,
) -> PremiumAllowances:
    """Compute the NC..NZ "Apply Premium" chain for one month.

    Returns a :class:`PremiumAllowances` whose ``applied_total_premium`` is the
    gross premium the policy accepts this month (the value the AV pipeline then
    splits into target/excess and loads).
    """
    a = PremiumAllowances(prem_less_wd=prem_less_wd)
    forceout_adj = force_out - loan_repay_from_forceout

    # ── NC / ND / NE — allowances before any premium applied ──
    a.gp_allowance_0 = (
        INF if is_cvat else max(0.0, guideline_limit - prem_less_wd + forceout_adj)
    )
    if is_cvat:
        a.npt_allowance_0 = INF if tamra_year <= 7 else npt_premium
    else:
        a.npt_allowance_0 = INF
    if tamra_year <= 7:
        a.tamra_allowance_0 = max(
            0.0, seven_pay_level * tamra_year - amount_in_7pay + forceout_adj
        )
    else:
        a.tamra_allowance_0 = INF

    # ── NF — annual cap before the 1035 exchange ──
    a.annual_cap_0 = a.gp_allowance_0 if (is_gpt and tefra_force) else INF

    # ── NG..NK — after the 1035 exchange. 1035 (vApplied1035 = MIN(LL, NF)) is
    #    not modeled here, so applied_1035 stays 0 and the "1" allowances equal
    #    the "0" allowances. ──
    a.applied_1035 = 0.0
    a.gp_allowance_1 = a.gp_allowance_0 - a.applied_1035
    a.npt_allowance_1 = a.npt_allowance_0 - a.applied_1035
    a.tamra_allowance_1 = a.tamra_allowance_0
    a.annual_cap_1 = _annual_cap(
        is_gpt=is_gpt, tefra_force=tefra_force, tamra_force=tamra_force,
        mec_bypass=mec_bypass, gp_allowance=a.gp_allowance_1,
        npt_allowance=a.npt_allowance_1, tamra_allowance=a.tamra_allowance_1,
    )

    # ── NL / NM — the lumpsum (unscheduled premium) is applied first, against
    #    the annual cap, reducing the room left for the scheduled premium. ──
    a.lumpsum_remaining = (requested_lumpsum - loan_repay_from_lumpsum) + ln_repay_left_over
    a.applied_lumpsum = min(a.lumpsum_remaining, a.annual_cap_1)

    # ── NN..NQ — allowances after the lumpsum ──
    a.gp_allowance_2 = a.gp_allowance_1 - a.applied_lumpsum
    a.npt_allowance_2 = a.npt_allowance_1 - a.applied_lumpsum
    a.tamra_allowance_2 = max(a.tamra_allowance_1 - a.applied_lumpsum, 0.0)
    a.annual_cap_2 = _annual_cap(
        is_gpt=is_gpt, tefra_force=tefra_force, tamra_force=tamra_force,
        mec_bypass=mec_bypass, gp_allowance=a.gp_allowance_2,
        npt_allowance=a.npt_allowance_2, tamra_allowance=a.tamra_allowance_2,
    )

    # ── NR..NU — per-mode level allowances (allowance spread over the payments
    #    left in the year). LU = TAMRA-year payments, LT = policy-year payments. ──
    lu = payment_count_tamra_year
    lt = payment_count_policy_year
    a.tamra_level_allowance_boy = (
        a.tamra_allowance_2 if lu == 0 else a.tamra_allowance_2 / lu
    )
    if tamra_month_of_year != policy_month and tamra_year < 7:
        eoy_numerator = a.tamra_allowance_2 + (0.0 if tamra_reset else seven_pay_level)
    else:
        eoy_numerator = INF
    a.tamra_level_allowance_eoy = (
        eoy_numerator / lt if payment_count_policy_year > 0 else INF
    )
    a.npt_level_allowance = (
        a.npt_allowance_2 if lu == 0 else a.npt_allowance_2 / lu
    )
    a.gp_level_allowance = (
        a.gp_allowance_2 / lt if lt > 0 else INF
    )

    # ── NV — Scheduled Prem Cap. Start the first level at a new TAMRA period,
    # then recalculate at each policy anniversary from the three RERUN limits:
    # TAMRA room before its off-anniversary increase (NR), TAMRA room after that
    # increase (NS), and policy-year guideline room (NU). Carry NV between those
    # anchors; a later TAMRA anniversary does not restart the policy-year level.
    active_tamra = tamra_force and not mec_bypass and tamra_year <= 7
    tamra_constraint_exit = (
        prior_scheduled_cap_by_tamra and not active_tamra
    )
    cap_uninitialized = (
        prior_scheduled_prem_cap <= 0.0
        and not prior_scheduled_cap_by_guideline
        and not prior_scheduled_cap_by_tamra
    )
    recalculate_cap = (
        tamra_reset
        or policy_anniversary
        or tamra_constraint_exit
        or cap_uninitialized
    )
    if recalculate_cap:
        if not tamra_force or mec_bypass:
            tamra_side = INF
        elif not active_tamra and not is_cvat:
            tamra_side = INF
        else:
            tamra_side = min(
                a.tamra_level_allowance_boy,
                a.tamra_level_allowance_eoy,
                a.npt_level_allowance,
            )
        gp_side = a.gp_level_allowance if (is_gpt and tefra_force) else INF
        a.scheduled_prem_cap = _floor_cent(min(tamra_side, gp_side))
        a.scheduled_cap_by_guideline = (
            gp_side < INF and gp_side <= tamra_side + MONEY_EPSILON
        )
        a.scheduled_cap_by_tamra = (
            tamra_side < INF and tamra_side <= gp_side + MONEY_EPSILON
        )
    else:
        a.scheduled_prem_cap = prior_scheduled_prem_cap
        a.scheduled_cap_by_guideline = prior_scheduled_cap_by_guideline
        a.scheduled_cap_by_tamra = prior_scheduled_cap_by_tamra

    # ── Transition-year dollar-for-dollar (Prem-to-Maturity) ──
    # The FIRST policy year the GP guideline binds the level premium is the year
    # the policy tips into GP exception mode. That year's premium can never be
    # level (it ends on exception premiums), so — when the caller opts in — accept
    # the scheduled premium dollar-for-dollar instead of spreading the freshly
    # opened annual room across the modal payments: the billable premium fills the
    # guideline room and the MD / GP exception premium takes over once it is
    # exhausted, rather than oscillating against the room for the rest of the year.
    # Latched at the anniversary (the SX-flag anchor) and carried through the year;
    # the NEXT year sees ``prior_guideline_limit_reached`` and does not re-enter.
    if beginning_of_year:
        gp_binds_this_year = (is_gpt and tefra_force) and a.scheduled_cap_by_guideline
        a.in_transition_year = (
            dollar_for_dollar_in_transition_year
            and gp_binds_this_year
            and not prior_guideline_limit_reached
        )
    else:
        a.in_transition_year = prior_transition_year_active

    # ── NW / NX / NY / NZ ──
    a.levelized_max_premium = min(a.scheduled_prem_cap, requested_scheduled)
    a.apply_levelized = (
        levelizing_premium and not has_loan_balance and not a.in_transition_year
    )
    a.scheduled_less_loan_repay = requested_scheduled - loan_repay_from_scheduled
    levelized_or_full = (
        min(a.levelized_max_premium, a.scheduled_less_loan_repay)
        if a.apply_levelized else a.scheduled_less_loan_repay
    )
    if tamra_force:
        tamra_scheduled_gate = INF if mec_bypass else a.npt_allowance_0
    else:
        tamra_scheduled_gate = INF
    a.applied_scheduled_premium = min(
        a.annual_cap_2, levelized_or_full, tamra_scheduled_gate
    )

    def annual_cap_sources(
        gp_allowance: float,
        npt_allowance: float,
        tamra_allowance: float,
    ) -> tuple[bool, bool]:
        gp_side = gp_allowance if (is_gpt and tefra_force) else INF
        tamra_side = (
            INF if (not tamra_force or mec_bypass)
            else min(npt_allowance, tamra_allowance)
        )
        return (
            gp_side < INF and gp_side <= tamra_side + MONEY_EPSILON,
            tamra_side < INF and tamra_side <= gp_side + MONEY_EPSILON,
        )

    if a.applied_lumpsum < a.lumpsum_remaining - MONEY_EPSILON:
        gp_binds, tamra_binds = annual_cap_sources(
            a.gp_allowance_1, a.npt_allowance_1, a.tamra_allowance_1)
        a.capped_by_guideline |= gp_binds
        a.capped_by_tamra |= tamra_binds

    if a.applied_scheduled_premium < a.scheduled_less_loan_repay - MONEY_EPSILON:
        if a.annual_cap_2 <= min(levelized_or_full, tamra_scheduled_gate) + MONEY_EPSILON:
            gp_binds, tamra_binds = annual_cap_sources(
                a.gp_allowance_2, a.npt_allowance_2, a.tamra_allowance_2)
            a.capped_by_guideline |= gp_binds
            a.capped_by_tamra |= tamra_binds
        if a.apply_levelized and a.levelized_max_premium < a.scheduled_less_loan_repay - MONEY_EPSILON:
            a.capped_by_guideline |= a.scheduled_cap_by_guideline
            a.capped_by_tamra |= a.scheduled_cap_by_tamra
        if tamra_scheduled_gate <= min(a.annual_cap_2, levelized_or_full) + MONEY_EPSILON:
            a.capped_by_tamra = True

    return a
