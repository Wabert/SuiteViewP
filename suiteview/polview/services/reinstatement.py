"""Read-only UL reinstatement quotes (continuous coverage).

A quote shows the policy's values at lapse, the monthly deduction on the
reinstatement date and the reinstatement premium::

    subtotal              = surrender charge + policy debt + 2 x COI + 2 x fees
                            - account value
    reinstatement premium = subtotal + premium load

COI is the base coverage COI plus rider and benefit charges. Fees are the EPU,
the monthly policy fee and any account-value charge. Charges, surrender charges
and premium loads come from the canonical illustration engine. Durations run
from the original issue date because coverage is continuous: nothing restarts
on reinstatement.

The lapse date is CyberLife's TL (termination - lapse) or SI (internal surrender)
transaction, falling back to PLN_TMN_DT. A full surrender (SF) is not reinstatable.

Lapse values are the last monthliversary values record.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from math import isfinite

from dateutil.relativedelta import relativedelta

from suiteview.core.db2_connection import DB2ConnectionError
from suiteview.core.rates_errors import RatesError
from suiteview.illustration.api import load_projection_basis
from suiteview.illustration.core.calc_engine import (
    IllustrationEngine,
    _calculate_surrender_charge,
    cvat_corridor_rate,
)
from suiteview.illustration.core.illustration_policy_service import _charge_end_date
from suiteview.illustration.core.monthly_deduction import calculate_deduction
from suiteview.illustration.core.premium_handler import (
    gross_up_for_premium_load,
    premium_load_rates,
)
from suiteview.illustration.core.rate_loader import IllustrationRates, RateLookupError
from suiteview.illustration.core.skipped_coverage import skipped_monthliversaries
from suiteview.illustration.core.target_premium import truncate_monthly_mtp
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.polview.models.cl_polrec.policy_translations import LAST_ENTRY_CODES
from suiteview.polview.models.policy_sections.lookup import policy_attr

LAPSE_TRANSACTION_CODE = "TL"
INTERNAL_SURRENDER_CODE = "SI"
FULL_SURRENDER_CODE = "SF"
SKIPPED_COVERAGE_CODE = "3"
CCV_BENEFIT_TYPE = "A"
_CENT = Decimal("0.01")


class ReinstatementError(ValueError):
    """A reinstatement quote cannot be produced from the available data."""


@dataclass(frozen=True)
class ReinstatementEligibility:
    last_entry_code: str
    last_entry_description: str
    eligible: bool
    message: str


@dataclass(frozen=True)
class LapseValues:
    lapse_date: date
    values_date: date | None
    account_value: Decimal
    loan_balance: Decimal
    surrender_charge: Decimal
    snet_expiry_date: date | None
    has_ccv: bool
    ccv_cease_date: date | None


@dataclass(frozen=True)
class MonthlyDeduction:
    deduction_date: date
    policy_year: int
    policy_month: int
    attained_age: int
    base_coi: Decimal
    rider_coi: Decimal
    benefit_charges: Decimal
    epu: Decimal
    monthly_fee: Decimal
    av_charge: Decimal

    @property
    def coi_total(self) -> Decimal:
        return self.base_coi + self.rider_coi + self.benefit_charges

    @property
    def fee_total(self) -> Decimal:
        return self.epu + self.monthly_fee + self.av_charge

    @property
    def total(self) -> Decimal:
        return self.coi_total + self.fee_total


@dataclass(frozen=True)
class ReinstatementPremium:
    account_value: Decimal
    policy_debt: Decimal
    surrender_charge: Decimal
    coi_x2: Decimal
    fees_x2: Decimal
    subtotal: Decimal
    premium_load: Decimal
    premium: Decimal
    load_description: str


@dataclass(frozen=True)
class ReinstatementQuote:
    reinstatement_date: date
    deduction: MonthlyDeduction
    premium: ReinstatementPremium
    notes: tuple[str, ...]


@dataclass(frozen=True)
class ValuesAfterReinstatement:
    reinstatement_date: date
    reinstatement_code: str
    terminated_months: int
    net_premium: Decimal
    monthly_deduction: Decimal
    account_value: Decimal
    loan_balance: Decimal
    surrender_charge: Decimal
    surrender_value: Decimal
    snet_expiry_date: date | None
    ccv_cease_date: date | None


def _money(value, label: str) -> Decimal:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReinstatementError(f"{label} is missing or invalid.") from exc
    if not isfinite(number):
        raise ReinstatementError(f"{label} is not finite.")
    amount = Decimal(str(number)).quantize(_CENT, rounding=ROUND_HALF_UP)
    return amount if amount else Decimal("0.00")


def _completed_months(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + end.month - start.month
    return months - (end < start + relativedelta(months=months))


def _counters(policy: IllustrationPolicyData, when: date) -> tuple[int, int, int]:
    """Policy year, policy month and attained age on ``when`` (from original issue)."""
    completed = _completed_months(policy.issue_date, when)
    return completed // 12 + 1, completed % 12 + 1, policy.issue_age + completed // 12


def _surrender_charge(policy, config, rates, when: date, account_value: Decimal) -> Decimal:
    try:
        _rate, total, _rates, _charges = _calculate_surrender_charge(
            policy, rates, _counters(policy, when)[0], when, config,
            account_value=float(account_value))
    except (RatesError, RateLookupError, ValueError, TypeError, ArithmeticError,
            KeyError, IndexError) as exc:
        raise ReinstatementError(f"Surrender charge is unavailable: {exc}") from exc
    return _money(total, "Surrender charge")


def latest_monthliversary(issue_date: date, on_or_before: date) -> date:
    """The issue-day-anchored monthliversary on or before ``on_or_before``."""
    return issue_date + relativedelta(months=max(_completed_months(issue_date, on_or_before), 0))


def reinstatement_date_choices(
    issue_date: date, lapse_date: date, today: date, maturity: date | None = None,
) -> tuple[date, ...]:
    """Monthliversaries from six months before ``today`` through the next month.

    Dates before the lapse (or at/after maturity) cannot be quoted and are left out.
    """
    first = today - relativedelta(months=6)
    last = today + relativedelta(months=1)
    start = _completed_months(issue_date, first)
    choices = []
    for count in range(max(start, 0), _completed_months(issue_date, last) + 2):
        day = issue_date + relativedelta(months=count)
        if (first <= day <= last and day >= lapse_date
                and (maturity is None or day < maturity)):
            choices.append(day)
    return tuple(choices)


def is_ul_policy(policy) -> bool:
    if not bool(policy is not None and getattr(policy, "exists", False)):
        return False
    rules = policy_attr(policy, "product_rules", None)
    if rules is not None:
        return bool(getattr(rules, "supports_reinstatement", False))
    return str(policy_attr(policy, "product_type", "")).strip().upper() in {"UL", "IUL", "SGUL"}


def _terminating_surrender(policy) -> str:
    """Last live surrender transaction code: SI (internal, reinstatable) or SF (full)."""
    surrenders = policy_attr(policy, "get_live_transactions")({FULL_SURRENDER_CODE, INTERNAL_SURRENDER_CODE})
    return surrenders[-1].trans_code if surrenders else ""


def reinstatement_eligibility(policy) -> ReinstatementEligibility:
    """Eligibility: a lapse (Q) or an internal surrender (P ending in SI), never an SF."""
    try:
        code = str(policy_attr(policy, "last_entry_code", "") or "").strip().upper()
        message = ""
        internal = False
        if not is_ul_policy(policy):
            message = "Currently reinstatement quotes are only available for ULs"
        elif code == "P":
            internal = _terminating_surrender(policy) == INTERNAL_SURRENDER_CODE
            if not internal:
                message = ("A full surrender (SF) cannot be reinstated; only a lapse or an "
                           "internal surrender (SI) can.")
        elif code != "Q":
            message = ("Only a lapse (Q) or an internal surrender (P ending in SI) can be "
                       "reinstated; free-look and other terminations are not eligible.")
    except (DB2ConnectionError, RatesError, TypeError) as exc:
        raise ReinstatementError(f"Cannot read reinstatement eligibility: {exc}") from exc
    description = LAST_ENTRY_CODES.get(code, f"Unknown ({code})") if code else "Not available"
    if internal:
        description += " (internal surrender, SI)"
    return ReinstatementEligibility(
        code, description, not message,
        message or ("Internal surrender: eligible for a reinstatement quote." if internal
                    else "Lapsed policy: eligible for a reinstatement quote."))


def find_lapse_date(policy) -> tuple[date | None, Decimal | None]:
    """The latest live TL (lapse) or SI (internal surrender) transaction's date and
    amount, else PLN_TMN_DT."""
    lapses = policy_attr(policy, "get_live_transactions")(
        {LAPSE_TRANSACTION_CODE, INTERNAL_SURRENDER_CODE})
    if lapses:
        # Only a TL amount is the account value; an SI amount is a net surrender value.
        last = lapses[-1]
        return last.trans_date, (last.gross_amount if last.trans_code == LAPSE_TRANSACTION_CODE else None)
    terminated = policy_attr(policy, "terminate_date", None)
    if terminated is not None and terminated.year < 9999:
        return terminated, None
    return None, None


def read_reinstatement_code(policy) -> str:
    """The reinstatement rule on the policy record (segment 66, LH_NON_TRD_POL.REN_RLE_CD)."""
    rows = policy_attr(policy, "fetch_table")("LH_NON_TRD_POL")
    return str(rows[0].get("REN_RLE_CD") or "").strip() if rows else ""


def restore_lapse_benefits(policy: IllustrationPolicyData, raw_benefits, lapse_date: date) -> list[str]:
    """Undo benefit terminations made by the lapse (continuous coverage).

    On lapse CyberLife moves BNF_CEA_DT to the lapse date and keeps the contract
    date in BNF_OGN_CEA_DT. Only benefits whose cease date equals the lapse date
    and whose original cease date is later are restored. Returns explanatory notes.
    """
    notes = []
    for raw in raw_benefits:
        original = getattr(raw, "orig_cease_date", None)
        if raw.cease_date != lapse_date or original is None or original <= lapse_date:
            continue
        key = (raw.cov_pha_nbr, str(raw.benefit_type_cd or "").strip(),
               str(raw.benefit_subtype_cd or "").strip())
        for index, benefit in enumerate(policy.benefits):
            if ((benefit.coverage_phase, benefit.benefit_type.strip(), benefit.benefit_subtype.strip())
                    == key and benefit.cease_date == lapse_date):
                policy.benefits[index] = replace(
                    benefit, cease_date=original, is_active=True,
                    pay_up_date=_charge_end_date(replace(raw, cease_date=original)))
                notes.append(
                    f"Benefit {key[1]}{key[2]} was ceased with the lapse; its original cease "
                    f"date {original:%m/%d/%Y} is restored for continuous coverage.")
                break
    return notes


@dataclass(frozen=True)
class ReinstatementBasis:
    """Loaded lapse values and rates; :meth:`quote` prices any reinstatement date."""

    eligibility: ReinstatementEligibility
    policy: IllustrationPolicyData
    config: PlancodeConfig
    rates: IllustrationRates
    lapse: LapseValues
    default_date: date
    cvat: object | None = None
    notes: tuple[str, ...] = ()
    reinstatement_code: str = ""
    date_choices: tuple[date, ...] = ()

    def quote(self, reinstatement_date: date) -> ReinstatementQuote:
        p = self.policy
        if reinstatement_date < self.lapse.lapse_date:
            raise ReinstatementError(
                f"The reinstatement date cannot be before the lapse date "
                f"({self.lapse.lapse_date:%m/%d/%Y}).")
        maturity = p.issue_date + relativedelta(years=p.maturity_age - p.issue_age)
        if reinstatement_date >= maturity:
            raise ReinstatementError(f"The reinstatement date is at or after maturity ({maturity:%m/%d/%Y}).")
        try:
            return self._quote(reinstatement_date)
        except ReinstatementError:
            raise
        except (RatesError, RateLookupError, ValueError, TypeError, ArithmeticError,
                KeyError, IndexError) as exc:
            raise ReinstatementError(f"Reinstatement charges are unavailable: {exc}") from exc

    def values_after_reinstatement(self, quote: ReinstatementQuote) -> ValuesAfterReinstatement:
        """Skipped-coverage values once the quoted premium is paid (mirrors Values at Lapse).

        The approximate account value is the lapse value plus the net premium (premium less
        load) less one monthly deduction. The reinstatement rule is the policy's segment 66
        code (``REN_RLE_CD``): rule 3 pushes the SNET expiry out by the months the policy
        was terminated and leaves the CCV benefit ceasing at termination. Any other rule
        ends both at the termination date.
        """
        code = self.reinstatement_code
        lapse, p = self.lapse, quote.premium
        terminated = lapse.lapse_date
        months = skipped_monthliversaries(self.policy.issue_date, terminated, quote.reinstatement_date)
        snet = lapse.snet_expiry_date
        if snet is not None:
            snet = snet + relativedelta(months=months) if code == SKIPPED_COVERAGE_CODE else min(snet, terminated)
        net_premium = p.premium - p.premium_load
        deduction = quote.deduction.total
        account_value = lapse.account_value + net_premium - deduction
        return ValuesAfterReinstatement(
            quote.reinstatement_date, code, months, net_premium, deduction,
            account_value, lapse.loan_balance, p.surrender_charge,
            account_value - p.surrender_charge - lapse.loan_balance,
            snet, terminated if lapse.has_ccv else None)

    def _quote(self, when: date) -> ReinstatementQuote:
        p = self.policy
        year, month, age = _counters(p, when)
        ded = calculate_deduction(
            float(self.lapse.account_value), p, self.config, self.rates, year, age,
            p.premiums_paid_to_date, monthly_mtp=truncate_monthly_mtp(p.mtp),
            projection_date=when, bln_round_charge=True,
            corridor_rate=cvat_corridor_rate(self.cvat, when),
        )
        deduction = MonthlyDeduction(
            when, year, month, age,
            base_coi=_money(ded.coi_charge, "Base COI"),
            rider_coi=_money(ded.rider_charges, "Rider COI"),
            benefit_charges=_money(ded.benefit_charges, "Benefit charges"),
            epu=_money(ded.epu_charge, "EPU"),
            monthly_fee=_money(ded.mfee_charge, "Monthly fee"),
            av_charge=_money(ded.av_charge, "Account value charge"),
        )
        if abs(deduction.total - _money(ded.total_deduction, "Monthly deduction")) > _CENT:
            raise ReinstatementError("Monthly deduction components do not reconcile to the total.")
        premium = self._premium(when, year, deduction)
        notes = list(self.notes)
        if when != latest_monthliversary(p.issue_date, when):
            notes.append(
                f"{when:%m/%d/%Y} is not a monthliversary; charges use policy year {year}, "
                f"month {month}.")
        if premium.subtotal <= 0:
            notes.append("The account value covers the requirement; no reinstatement premium is due.")
        return ReinstatementQuote(when, deduction, premium, tuple(notes))

    def _premium(self, when: date, year: int, deduction: MonthlyDeduction) -> ReinstatementPremium:
        p = self.policy
        lapse = self.lapse
        surrender = _surrender_charge(p, self.config, self.rates, when, lapse.account_value)
        coi_x2 = 2 * deduction.coi_total
        fees_x2 = 2 * deduction.fee_total
        subtotal = surrender + lapse.loan_balance + coi_x2 + fees_x2 - lapse.account_value
        tpp, epp = premium_load_rates(self.rates, year)
        flat = self.config.prem_flat_load if self.config.prem_flat_load > 0 else 0.0
        same_year = p.valuation_date is not None and _counters(p, p.valuation_date)[0] == year
        premiums_ytd = p.premiums_ytd if same_year else 0.0
        if subtotal > 0:
            split = gross_up_for_premium_load(
                float(subtotal), premiums_ytd=premiums_ytd, ctp=p.ctp,
                tpp=tpp, epp=epp, flat=flat)
            premium = _money(split.gross, "Reinstatement premium")
        else:
            premium = Decimal("0.00")
        load = premium - subtotal if subtotal > 0 else Decimal("0.00")
        return ReinstatementPremium(
            lapse.account_value, lapse.loan_balance, surrender, coi_x2, fees_x2,
            subtotal, load, premium, _load_description(tpp, epp, flat))


def _load_description(tpp: float, epp: float, flat: float) -> str:
    text = (f"{tpp:.2%}" if abs(tpp - epp) < 1e-12
            else f"{tpp:.2%} to target, {epp:.2%} excess")
    return text + (f" + ${flat:,.2f}" if flat else "")


def build_reinstatement_basis(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    *,
    eligibility: ReinstatementEligibility,
    lapse_date: date,
    today: date,
    lapse_amount: Decimal | None = None,
    cvat=None,
    notes: tuple[str, ...] = (),
    reinstatement_code: str = "",
) -> ReinstatementBasis:
    """Assemble lapse values from a loaded snapshot (pure; no database reads)."""
    if policy.issue_date is None:
        raise ReinstatementError("The policy issue date is not available.")
    if not policy.segments:
        raise ReinstatementError("No base coverage is available to quote.")
    if lapse_date > today:
        raise ReinstatementError(f"The lapse date {lapse_date:%m/%d/%Y} is in the future.")
    for segment in policy.segments:
        phase = segment.coverage_phase
        for name, schedule in (("COI", rates.segment_coi.get(phase, rates.coi)),
                               ("surrender charge", rates.segment_scr.get(phase, rates.scr))):
            if not schedule or len(schedule) < 2:
                raise ReinstatementError(
                    f"The {name} rate schedule for coverage {phase} is missing.")
    account_value = _money(policy.account_value, "Account value")
    loan_balance = sum((
        _money(value, "Loan balance") for value in (
            policy.regular_loan_principal, policy.regular_loan_accrued,
            policy.preferred_loan_principal, policy.preferred_loan_accrued,
            policy.variable_loan_principal, policy.variable_loan_accrued)
    ), Decimal("0.00"))
    ccv = [b for b in policy.benefits if (b.benefit_type or "").strip() == CCV_BENEFIT_TYPE]
    ccv_dates = [b.cease_date for b in ccv if b.cease_date is not None]
    lapse = LapseValues(
        lapse_date, policy.valuation_date, account_value, loan_balance,
        _surrender_charge(policy, config, rates, lapse_date, account_value),
        policy.map_cease_date, bool(ccv), max(ccv_dates) if ccv_dates else None,
    )
    notes = list(notes)
    if policy.valuation_date is not None:
        notes.insert(0,
            f"Lapse values are from the last monthliversary values record "
            f"({policy.valuation_date:%m/%d/%Y}).")
    if lapse_amount is not None and abs(_money(lapse_amount, "Lapse amount") - account_value) > _CENT:
        notes.append(
            f"The TL lapse transaction amount ({lapse_amount:,.2f}) differs from the "
            f"values-record account value ({account_value:,.2f}).")
    for benefit in policy.benefits:
        if benefit.cease_date == lapse_date and not (benefit.benefit_type or "").startswith("#"):
            notes.append(
                f"Benefit {benefit.benefit_type}{benefit.benefit_subtype} ceases on the lapse date, "
                "so its charge is excluded. Confirm whether it is reinstated.")
    default = max(latest_monthliversary(policy.issue_date, today), lapse_date)
    maturity = policy.issue_date + relativedelta(years=policy.maturity_age - policy.issue_age)
    choices = reinstatement_date_choices(policy.issue_date, lapse_date, today, maturity)
    if default not in choices:
        default = choices[0] if choices else default
    return ReinstatementBasis(
        eligibility, policy, config, rates, lapse, default, cvat, tuple(notes),
        str(reinstatement_code or "").strip(), choices or (default,))


def load_reinstatement_basis(policy, today: date | None = None) -> ReinstatementBasis:
    """Read the lapsed policy's canonical illustration basis once (read-only)."""
    today = today or date.today()
    eligibility = reinstatement_eligibility(policy)
    if not eligibility.eligible:
        raise ReinstatementError(eligibility.message)
    try:
        lapse_date, lapse_amount = find_lapse_date(policy)
        if lapse_date is None:
            raise ReinstatementError(
                "The lapse date is not available: no TL (termination - lapse) "
                "transaction or termination date was found.")
        terminated = policy_attr(policy, "terminate_date", None)
        loaded = load_projection_basis(
            policy.policy_number, region=policy.region, company_code=policy.company_code,
            illustration_date=today,
            # Restores coverages CyberLife terminated with the lapse (continuous coverage).
            reinstatement_date=lapse_date if terminated == lapse_date else None,
        )
        cvat = None
        if loaded.policy.is_cvat:
            # The engine's own CVAT corridor tracker, so CVAT COIs match projections.
            cvat = IllustrationEngine()._start_cvat_corridor(loaded.policy, loaded.config)
        restored = restore_lapse_benefits(
            loaded.policy, policy_attr(policy, "get_benefits")(), lapse_date)
        return build_reinstatement_basis(
            loaded.policy, loaded.config, loaded.rates, eligibility=eligibility,
            lapse_date=lapse_date, today=today, lapse_amount=lapse_amount, cvat=cvat,
            notes=tuple(restored), reinstatement_code=read_reinstatement_code(policy),
        )
    except ReinstatementError:
        raise
    except (DB2ConnectionError, RatesError, RateLookupError, OSError, RuntimeError,
            ValueError, TypeError, ArithmeticError, KeyError, IndexError) as exc:
        raise ReinstatementError(f"Reinstatement data is unavailable: {exc}") from exc
