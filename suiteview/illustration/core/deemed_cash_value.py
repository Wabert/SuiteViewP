"""Deemed Cash Value roll-forward and the CVAT Necessary Premium Test (NPT).

RERUN CalcEngine columns mirrored here (docs/Illustration_UL/calcengine_map_v20.tsv):

* ``YW..AAK`` — the DCV roll. BDCV = prior vEDCV; less the gross withdrawal
  (vDCV_AfterChanges); plus the net premium, or the entered deemed cash value
  on the inforce valuation row (vDCV_AfterPremium); a DCV monthly deduction
  (DCV COI on a DCV NAAR discounted at the 7702 GLP rate, current EPU, monthly
  fee, PoAV, rider/benefit charges, PW39 on MAX(MTP/12, MD)); DCV interest at
  the 7702 GLP rate over the month's interest days (vEDCV).
* ``LG`` vValue_for_NPT = MIN(vDCV_AfterChanges, vAV_AfterChanges).
* ``LH`` vNPT_NSP = INDEX(mNSPs, vPolicyMonth − vChangeMonth + 2, vChangeCount + 1).
* ``LI`` vNPT_Premium — the gross-up of MAX(0, NSP − Value) by the target /
  excess premium loads relative to the CTP; 0 for GPT.

``mNSPs`` is the named range ``NSP!B18:D1475`` on RERUN's NSP sheet ("Net
Single Premium for the Necessary Premium Test"). Column B is schedule 1 (built
at issue, or on the inforce valuation row) and column C schedule 2 (built at the
first 7702 policy change); column D is blank in RERUN v20. Each schedule is a
monthly backward recursion from the schedule's anchor row:

* interest ``i = MAX(sRates_GINT, s7702_GLP_Rate)``; ``v = (1 + i)^(−1/12)``;
* ``Q`` = guaranteed (ultimate GCOI) COI per $1,000 at the attained age,
  substandard-adjusted with the anchor's table/flat extras, capped at 1000/12;
* ``W = Q / (1 + Q/1000)`` (q per 1,000);
* NSP per 1,000: ``Y = v·W + v·(1 − W/1000)·Y_next``, with ``Y = 1000`` at age 100;
* rider NSP: ``AH = AF·(1 − W/1000) + v·(1 − W/1000)·AH_next`` where AF is the
  month's QAB rider/benefit charge stream (CTR, PW39 on the MTP, PWoT, GIO);
* total NSP ``= Y × (lowest 7-pay death benefit at the anchor) / 1000 + AH``.

The monthly COI and QAB charge stream is the same guaranteed-COI basis the
engine already builds for the monthly guideline solve
(:func:`monthly_guideline.build_guideline_basis`), so no new rate machinery is
introduced. Intent-over-workbook choice: RERUN's ``vChangeCount`` is capped at
``sMax7702RecalcsAllowed`` (2) and its third NSP column is blank, so a second
7702 change would read an NSP of 0 there; SuiteView builds a fresh schedule at
every 7702 change instead.

The deemed cash value itself is not in the DB2 tables (RERUN's
``mdl_GetCyberlifePolicy`` sets ``sInput_DeemedCashValue = 0`` with a note that
it must be looked up manually). SuiteView never defaults it: the user enters it
from the 93 segment, and an unknown DCV fails loud once the NPT limits a premium
(:class:`premium_allowance.DeemedCashValueRequiredError`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional, Sequence

from suiteview.illustration.constants import (
    DAYS_PER_YEAR,
    DB_OPTION_INCREASING,
    DB_OPTION_RETURN_OF_PREMIUM,
    MONTHS_PER_YEAR,
    PER_THOUSAND,
)
from suiteview.illustration.core.monthly_deduction import (
    _adjusted_coi_rate,
    _coi_rate_year,
    _coverage_year,
    _pending_segments,
    _rate_from_schedule,
    _segment_charge_inactive,
)
from suiteview.illustration.core.monthly_guideline import (
    DEEMED_MATURITY_AGE,
    build_guideline_basis,
    statutory_guideline_rates,
)
from suiteview.illustration.core.rate_loader import IllustrationRates, get_rate
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    IllustrationPolicyData,
    benefit_rate_keys,
)

GuaranteedRatesLoader = Callable[[IllustrationPolicyData], IllustrationRates]


# ── LI — vNPT_Premium ──────────────────────────────────────────────────────


def npt_premium(
    *,
    is_gpt: bool,
    nsp: float,
    value_for_npt: float,
    ctp: float,
    tpp: float,
    epp: float,
) -> float:
    """RERUN LI: the gross premium that lifts the NPT value up to the NSP.

    ``IF(GPT, 0, IF(MAX(0,NSP−V)/(1−TPP) < CTP, MAX(0,NSP−V)/(1−TPP),
    MAX(0, NSP−V + (TPP−EPP)·CTP)/(1−EPP)))`` — all premium under the CTP
    carries the target load; above it, the excess load applies with the
    target/excess load difference charged on the CTP.
    """
    if is_gpt:
        return 0.0
    shortfall = max(0.0, nsp - value_for_npt)
    at_target_load = shortfall / (1.0 - tpp)
    if at_target_load < ctp:
        return at_target_load
    return max(0.0, nsp - value_for_npt + (tpp - epp) * ctp) / (1.0 - epp)


# ── mNSPs — the NSP sheet schedules ────────────────────────────────────────


@dataclass(frozen=True)
class NspMonth:
    """One NSP-sheet row: guaranteed COI and the QAB charge stream."""

    coi_rate: float              # Q — guaranteed COI per $1,000/month (substandard, capped)
    rider_charges: float = 0.0   # AF — monthly QAB rider/benefit charges ($)


def npt_nsp_values(
    months: Sequence[NspMonth], *, annual_rate: float, death_benefit: float,
) -> list[float]:
    """Total NSP (NSP!AK) at each month, by backward recursion from age 100."""
    v = 1.0 / (1.0 + annual_rate) ** (1.0 / MONTHS_PER_YEAR)
    per_thousand = PER_THOUSAND           # Y at the deemed maturity (age 100)
    rider_nsp = 0.0                       # AH at the deemed maturity
    values = [0.0] * len(months)
    for index in range(len(months) - 1, -1, -1):
        month = months[index]
        q = month.coi_rate / (1.0 + month.coi_rate / PER_THOUSAND)       # W
        survival = 1.0 - q / PER_THOUSAND
        per_thousand = v * q + v * survival * per_thousand                # Y
        rider_nsp = month.rider_charges * survival + v * survival * rider_nsp  # AH
        values[index] = per_thousand * death_benefit / PER_THOUSAND + rider_nsp
    return values


@dataclass(frozen=True)
class NspSchedule:
    """One mNSPs column: NSPs by policy month from the schedule's anchor row."""

    anchor_duration: int          # policy month (from issue) of ``values[0]``
    death_benefit: float          # J7 — lowest 7-pay death benefit at the anchor
    annual_rate: float            # J8 — MAX(guaranteed rate, 7702 GLP rate)
    values: tuple[float, ...]

    def nsp_at(self, duration: int) -> float:
        """NSP for policy month ``duration``; age 100 and later is the face."""
        index = duration - self.anchor_duration
        if index < 0:
            raise ValueError(
                f"NSP requested for policy month {duration}, before the schedule "
                f"anchor month {self.anchor_duration}.")
        if index >= len(self.values):
            return self.death_benefit
        return self.values[index]


def build_nsp_schedule(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    guaranteed: IllustrationRates,
    *,
    anchor_duration: int,
    attained_age: int,
    months_into_year: int,
    as_of: Optional[date],
    death_benefit: float,
) -> NspSchedule:
    """Build an NSP schedule from the policy's CURRENT coverage state.

    ``guaranteed`` must be loaded at the guaranteed COI scale. Months past the
    guideline maturity (a contract maturing before 100) carry no COI, exactly
    as the NSP sheet zeroes the rate from ``sMaturityAge`` to its fixed 100.
    """
    basis = build_guideline_basis(
        policy, config, guaranteed,
        attained_age=attained_age, as_of=as_of,
        months_into_year=months_into_year, active_as_of=as_of,
    )
    months = [
        NspMonth(month.coi_rate * PER_THOUSAND, month.benefit_charges + month.rider_charges)
        for month in basis.months
    ]
    months_to_100 = max(0, (DEEMED_MATURITY_AGE - attained_age) * MONTHS_PER_YEAR - months_into_year)
    months.extend([NspMonth(0.0)] * max(0, months_to_100 - len(months)))
    annual_rate = max(float(policy.guaranteed_interest_rate or 0.0), glp_rate_for(policy))
    return NspSchedule(
        anchor_duration=anchor_duration,
        death_benefit=death_benefit,
        annual_rate=annual_rate,
        values=tuple(npt_nsp_values(months, annual_rate=annual_rate, death_benefit=death_benefit)),
    )


def glp_rate_for(policy: IllustrationPolicyData) -> float:
    """s7702_GLP_Rate — the statutory GLP interest floor for the issue date."""
    return statutory_guideline_rates(policy.issue_date)[0]


# ── YW..AAK — the DCV roll ─────────────────────────────────────────────────


@dataclass(frozen=True)
class DcvCoverage:
    """One base coverage of the DCV death benefit (ZD..ZS)."""

    specified_amount: float      # vCurrentSA<n>; 0 while the coverage is not yet issued
    coi_rate: float              # ZG..ZI — guaranteed COI per $1,000, substandard-adjusted


@dataclass(frozen=True)
class DcvCharges:
    """The non-COI parts of the DCV monthly deduction (the run's expense basis)."""

    epu: float = 0.0             # ZY..AAA current EPU charges
    monthly_fee: float = 0.0     # AAB
    poav_rate: float = 0.0       # AAC — percent-of-AV charge rate
    rider_benefit: float = 0.0   # ZU — rider/benefit charges other than the PW charge
    pw_rate: float = 0.0         # SM — premium waiver COI rate
    monthly_mtp: float = 0.0     # vMTP/12


@dataclass(frozen=True)
class DcvMonthInput:
    """Inputs for one month of the DCV roll."""

    begin_dcv: float                         # YW — prior vEDCV
    gross_withdrawal: float = 0.0            # YX — vGrossWD
    net_premium: float = 0.0                 # YZ — vNetPremium
    valuation_dcv: Optional[float] = None    # sInput_DeemedCashValue on the valuation row
    db_option: str = "A"                     # CT
    premiums_less_withdrawals: float = 0.0   # OB − BD (option C death benefit)
    coverages: tuple[DcvCoverage, ...] = ()
    charges: DcvCharges = field(default_factory=DcvCharges)
    glp_rate: float = 0.04                   # ZJ — s7702_GLP_Rate
    days: float = DAYS_PER_YEAR / MONTHS_PER_YEAR   # UD — interest days
    # CyberLife monthliversary timing credits interest at the start of the month
    # (before the withdrawal) instead of RERUN's end-of-month AAJ.
    interest_at_start: bool = False


@dataclass(frozen=True)
class DcvMonth:
    """Every named column of one month of the DCV roll."""

    begin_dcv: float
    begin_interest: float
    after_changes: float
    after_premium: float
    naar_av: float
    death_benefit: float
    coi_charge: float
    poav_charge: float
    md_without_pw: float
    premium_to_waive: float
    pw_charge: float
    monthly_deduction: float
    after_deduction: float
    interest: float
    end_dcv: float

    def to_detail(self) -> dict:
        """The DCV columns keyed by their RERUN names."""
        return {
            "BDCV": self.begin_dcv,
            "vDCV_AfterChanges": self.after_changes,
            "vDCV_AfterPremium": self.after_premium,
            "DCV DB": self.death_benefit,
            "DCV COI Charge": self.coi_charge,
            "DCV MD": self.monthly_deduction,
            "DCV Interest": self.interest + self.begin_interest,
            "vEDCV": self.end_dcv,
        }


def _period_interest(value: float, annual_rate: float, days: float) -> float:
    """AAJ — MAX(0, value·((1+i)^(days/365) − 1))."""
    return max(0.0, value * ((1.0 + annual_rate) ** (days / DAYS_PER_YEAR) - 1.0))


def dcv_after_changes(
    begin_dcv: float,
    gross_withdrawal: float,
    *,
    glp_rate: float,
    days: float,
    interest_at_start: bool,
) -> tuple[float, float]:
    """``(start-of-month interest, vDCV_AfterChanges)`` for one month (YY)."""
    begin_interest = _period_interest(begin_dcv, glp_rate, days) if interest_at_start else 0.0
    return begin_interest, begin_dcv + begin_interest - gross_withdrawal


def _dcv_naars(dbds: Sequence[float], naar_av: float) -> list[float]:
    """ZN..ZP exactly as the workbook writes them.

    Coverage 1 nets the whole DCV; later coverages net
    ``MAX(DCV − MAX(SUM(NAAR so far) − SUM(DBD so far), 0), 0)``. Because a
    NAAR never exceeds its DBD that inner term is always 0, so every coverage
    nets the full DCV — kept literal to mirror RERUN.
    """
    naars: list[float] = []
    for index, dbd in enumerate(dbds):
        if index == 0:
            naars.append(max(dbd - naar_av, 0.0))
            continue
        absorbed = max(sum(naars) - sum(dbds[:index]), 0.0)
        naars.append(max(dbd - max(naar_av - absorbed, 0.0), 0.0))
    return naars


def roll_deemed_cash_value(inputs: DcvMonthInput) -> DcvMonth:
    """One month of the RERUN DCV roll (YW..AAK)."""
    begin_interest, after_changes = dcv_after_changes(
        inputs.begin_dcv, inputs.gross_withdrawal,
        glp_rate=inputs.glp_rate, days=inputs.days,
        interest_at_start=inputs.interest_at_start,
    )
    after_premium = (
        float(inputs.valuation_dcv) if inputs.valuation_dcv is not None
        else after_changes + inputs.net_premium
    )
    naar_av = max(after_premium, 0.0)
    option = str(inputs.db_option or "A").upper()
    amounts = [coverage.specified_amount for coverage in inputs.coverages]
    death_benefit = sum(amounts)
    if option == DB_OPTION_INCREASING:
        death_benefit += naar_av
    elif option == DB_OPTION_RETURN_OF_PREMIUM:
        death_benefit += max(0.0, inputs.premiums_less_withdrawals)
    discount = (1.0 + inputs.glp_rate) ** (1.0 / MONTHS_PER_YEAR)
    dbds = [
        (amount + (naar_av if index == 0 and option == DB_OPTION_INCREASING else 0.0)) / discount
        for index, amount in enumerate(amounts)
    ]
    naars = _dcv_naars(dbds, naar_av)
    coi_charge = sum(
        coverage.coi_rate * naar / PER_THOUSAND
        for coverage, naar in zip(inputs.coverages, naars)
    )
    charges = inputs.charges
    poav_charge = max(0.0, charges.poav_rate * after_premium)
    md_without_pw = (
        poav_charge + charges.monthly_fee + charges.epu
        + charges.rider_benefit + coi_charge
    )
    premium_to_waive = max(charges.monthly_mtp, md_without_pw)
    pw_charge = charges.pw_rate * premium_to_waive
    monthly_deduction = md_without_pw + pw_charge
    after_deduction = after_premium - monthly_deduction
    interest = (
        0.0 if inputs.interest_at_start
        else _period_interest(after_deduction, inputs.glp_rate, inputs.days)
    )
    return DcvMonth(
        begin_dcv=inputs.begin_dcv,
        begin_interest=begin_interest,
        after_changes=after_changes,
        after_premium=after_premium,
        naar_av=naar_av,
        death_benefit=death_benefit,
        coi_charge=coi_charge,
        poav_charge=poav_charge,
        md_without_pw=md_without_pw,
        premium_to_waive=premium_to_waive,
        pw_charge=pw_charge,
        monthly_deduction=monthly_deduction,
        after_deduction=after_deduction,
        interest=interest,
        end_dcv=after_deduction + interest,
    )


# ── Engine inputs from the policy state ────────────────────────────────────


def dcv_coverages(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    guaranteed: IllustrationRates,
    month_date: Optional[date],
    rate_year: int,
) -> tuple[DcvCoverage, ...]:
    """ZD..ZI per base coverage: PolicyRates!FR..FT (guaranteed ultimate COI).

    The rate is zero from the premium-cease age and while the coverage is not
    charging; the substandard adjustment uses coverage 1's table and flat
    extras for every coverage (the workbook's ``$FK``/``$FN``/``$FO``).
    """
    segments = [segment for segment in policy.segments if segment is not None]
    base = policy.base_segment
    pending = _pending_segments(policy, month_date) if segments else []
    coverages = []
    for index, segment in enumerate(segments):
        schedule = guaranteed.segment_coi.get(segment.coverage_phase, guaranteed.coi)
        coverage_year = _coverage_year(segment, month_date, rate_year)
        age = segment.issue_age + coverage_year - 1
        raw = _rate_from_schedule(
            schedule, _coi_rate_year(segment, policy, month_date, rate_year))
        if age >= config.premium_cease_age or _segment_charge_inactive(segment, month_date):
            raw = 0.0
        coverages.append(DcvCoverage(
            specified_amount=0.0 if pending[index] else float(segment.face_amount),
            coi_rate=_adjusted_coi_rate(raw, base, config, month_date),
        ))
    return tuple(coverages)


def _pw_rate(policy: IllustrationPolicyData, benefit_rates: dict) -> float:
    """SM — the premium-waiver COI rate before the benefit's own rating."""
    keys = benefit_rate_keys(policy.benefits)
    for benefit in policy.benefits:
        if (benefit.benefit_type or "") != "3":
            continue
        rate = (benefit_rates or {}).get(keys[id(benefit)])
        if rate is None:
            continue
        factor = benefit.rating_factor if benefit.rating_factor and benefit.rating_factor > 0 else 1.0
        return float(rate) / factor
    return 0.0


def dcv_charges(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    deduction,
    rate_year: int,
) -> DcvCharges:
    """DCV deduction pieces from the month's AV deduction (``DeductionResult``
    or a ``MonthlyState`` row, which carry the same charge fields)."""
    poav_rate = (
        get_rate(rates, "poav", rate_year) if config.poav_table != "0" else 0.0
    )
    pw_charge = float(deduction.pw_charge or 0.0)
    return DcvCharges(
        epu=float(deduction.epu_charge or 0.0),
        monthly_fee=float(deduction.mfee_charge or 0.0),
        poav_rate=poav_rate,
        rider_benefit=(
            float(deduction.rider_charges or 0.0)
            + float(deduction.benefit_charges or 0.0) - pw_charge
        ),
        pw_rate=_pw_rate(policy, deduction.benefit_rates),
        monthly_mtp=float(policy.mtp or 0.0),
    )


# ── Run-level tracker ──────────────────────────────────────────────────────


@dataclass
class NptTracker:
    """DCV and NSP state carried through one projection.

    Created only for a CVAT run with Conform to TAMRA on that reaches TAMRA
    year 8. With no deemed cash value entered the tracker stays empty and the
    allowance chain fails loud at the first month the NPT limits a premium.
    """

    load_guaranteed: GuaranteedRatesLoader
    glp_rate: float
    interest_at_start: bool = False
    edcv: Optional[float] = None
    guaranteed: Optional[IllustrationRates] = None
    schedule: Optional[NspSchedule] = None
    nsp_schedules_built: int = 0

    @property
    def dcv_known(self) -> bool:
        return self.edcv is not None

    def start(
        self,
        policy: IllustrationPolicyData,
        config: PlancodeConfig,
        rates: IllustrationRates,
        valuation_row,
        *,
        lowest_death_benefit: float,
    ) -> dict:
        """Seed vEDCV from the valuation row and build NSP schedule 1.

        From issue the DCV starts at zero (RERUN has no valuation row then);
        an inforce run starts from the entered deemed cash value. Returns the
        valuation row's DCV detail (empty when no DCV was entered or the
        projection starts at issue).
        """
        if policy.run_from_issue:
            self._build_schedule(
                policy, config, anchor_duration=1, attained_age=policy.issue_age,
                months_into_year=0, as_of=policy.issue_date,
                death_benefit=float(policy.total_face))
            self.edcv = 0.0
            return {}
        dcv = policy.deemed_cash_value
        if dcv is None:
            return {}
        duration = max(1, int(policy.duration))
        self._build_schedule(
            policy, config, anchor_duration=duration,
            attained_age=policy.issue_age + (duration - 1) // MONTHS_PER_YEAR,
            months_into_year=(duration - 1) % MONTHS_PER_YEAR,
            as_of=policy.valuation_date, death_benefit=lowest_death_benefit)
        month = roll_deemed_cash_value(DcvMonthInput(
            begin_dcv=0.0,
            valuation_dcv=float(dcv),
            db_option=policy.db_option,
            premiums_less_withdrawals=(
                float(policy.premiums_paid_to_date)
                - (float(policy.withdrawals_to_date) - policy.inforce_withdrawal_fees)),
            coverages=dcv_coverages(
                policy, config, self.guaranteed, policy.valuation_date, policy.policy_year),
            charges=dcv_charges(policy, config, rates, valuation_row, policy.policy_year),
            glp_rate=self.glp_rate,
            days=float(valuation_row.days_in_month or DAYS_PER_YEAR / MONTHS_PER_YEAR),
            interest_at_start=self.interest_at_start,
        ))
        self.edcv = month.end_dcv
        return month.to_detail()

    def policy_changed(
        self,
        policy: IllustrationPolicyData,
        config: PlancodeConfig,
        *,
        duration: int,
        attained_age: int,
        months_into_year: int,
        as_of: Optional[date],
        lowest_death_benefit: float,
    ) -> None:
        """A 7702 change starts a new NSP schedule (mNSPs column) at this month."""
        if not self.dcv_known:
            return
        self._build_schedule(
            policy, config, anchor_duration=duration, attained_age=attained_age,
            months_into_year=months_into_year, as_of=as_of,
            death_benefit=lowest_death_benefit)

    def _build_schedule(self, policy, config, **anchor) -> None:
        self.guaranteed = self.load_guaranteed(policy)
        self.schedule = build_nsp_schedule(policy, config, self.guaranteed, **anchor)
        self.nsp_schedules_built += 1

    def npt_for_month(
        self,
        policy: IllustrationPolicyData,
        *,
        duration: int,
        gross_withdrawal: float,
        av_after_changes: float,
        tpp: float,
        epp: float,
        days: float,
    ) -> tuple[Optional[float], dict]:
        """``(vNPT_Premium, detail)``; ``(None, {})`` while the DCV is unknown."""
        if not self.dcv_known:
            return None, {}
        _begin_interest, after_changes = dcv_after_changes(
            self.edcv, gross_withdrawal, glp_rate=self.glp_rate, days=days,
            interest_at_start=self.interest_at_start)
        value = min(after_changes, av_after_changes)
        nsp = self.schedule.nsp_at(duration)
        premium = npt_premium(
            is_gpt=policy.is_gpt, nsp=nsp, value_for_npt=value,
            ctp=float(policy.ctp or 0.0), tpp=tpp, epp=epp)
        return premium, {"vValue_for_NPT": value, "vNPT_NSP": nsp, "vNPT_Premium": premium}

    def roll_month(
        self,
        policy: IllustrationPolicyData,
        config: PlancodeConfig,
        rates: IllustrationRates,
        deduction,
        *,
        month_date: Optional[date],
        rate_year: int,
        gross_withdrawal: float,
        net_premium: float,
        premiums_less_withdrawals: float,
        days: float,
    ) -> dict:
        """Close the month's DCV roll; returns its detail columns."""
        if not self.dcv_known:
            return {}
        month = roll_deemed_cash_value(DcvMonthInput(
            begin_dcv=self.edcv,
            gross_withdrawal=gross_withdrawal,
            net_premium=net_premium,
            db_option=policy.db_option,
            premiums_less_withdrawals=premiums_less_withdrawals,
            coverages=dcv_coverages(policy, config, self.guaranteed, month_date, rate_year),
            charges=dcv_charges(policy, config, rates, deduction, rate_year),
            glp_rate=self.glp_rate,
            days=days,
            interest_at_start=self.interest_at_start,
        ))
        self.edcv = month.end_dcv
        return month.to_detail()
