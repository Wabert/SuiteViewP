"""Read-only, continuous-coverage Home Office reinstatement projections.

PLN_TMN_DT is the termination effective date, not a financial-history entry
date. Opening illustration values are post-deduction. They must not be rolled
back, topped up with later receipts, or substituted for missing lapse values.

The receipt helper posts between deductions without rewriting the opening
snapshot. Skipped-coverage reinstatement is not implemented.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import isfinite

from dateutil.relativedelta import relativedelta

from suiteview.core.db2_connection import DB2ConnectionError
from suiteview.core.rates import RatesError
from suiteview.illustration.api import project_policy
from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.illustration_policy_service import (
    _coverage_is_terminated, build_illustration_data,
)
from suiteview.illustration.core.rate_loader import IllustrationRates, RateLookupError, load_rates
from suiteview.illustration.core.reinstatement_basis import restore_lapse_coverage
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    DatedTransaction, IllustrationInputSet, IllustrationOptions,
    ScheduledTransaction, TransactionKind,
)
from suiteview.illustration.models.plancode_config import load_plancode
from suiteview.illustration.models.policy_data import IllustrationPolicyData, benefit_rate_keys
from suiteview.polview.models.cl_polrec.policy_translations import LAST_ENTRY_CODES
from .reinstatement_receipt import project_receipt


class ReinstatementError(ValueError):
    """A safe reinstatement quote cannot be produced from the supplied basis."""


@dataclass(frozen=True)
class ReinstatementSummary:
    last_entry_code: str
    last_entry_description: str
    termination_date: date | None
    current_date: date
    terminated_years: int | None
    terminated_months: int | None
    eligible: bool
    message: str
    quote_pay_to_date: date | None
    next_monthliversary: date | None


@dataclass(frozen=True)
class ReinstatementResult:
    summary: ReinstatementSummary
    premium: Decimal
    basis: str
    breakdown: tuple[tuple[str, str], ...]
    explanation: str
    states: tuple[MonthlyState, ...]


def is_ul_policy(policy) -> bool:
    return bool(policy is not None and getattr(policy, "exists", False)
                and str(getattr(policy, "product_type", "")).strip().upper()
                in {"UL", "IUL", "SGUL"})


def _months(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + end.month - start.month
    return months - (end < start + relativedelta(months=months))


def reinstatement_summary(policy, today: date | None = None) -> ReinstatementSummary:
    today = today or date.today()
    try:
        code = str(getattr(policy, "last_entry_code", "") or "").strip().upper()
        termination = getattr(policy, "terminate_date", None)
        issue = getattr(policy, "issue_date", None)
        years = months = None
        if termination is not None and termination <= today:
            years, months = divmod(_months(termination, today), 12)
        pay_to = next_date = None
        if issue is not None and issue <= today:
            elapsed = _months(issue, today)
            pay_to = issue + relativedelta(months=elapsed)
            next_date = issue + relativedelta(months=elapsed + 1)
        message = ""
        if not is_ul_policy(policy):
            message = "Currently reinstatement quotes are only available for ULs"
        elif code != "Q":
            message = "Only termination by lapse is eligible; surrender and free-look are not reinstatements."
        elif termination is None or termination.year >= 9999:
            message = "Termination effective date is not available."
        elif termination > today:
            message = "Termination effective date is in the future."
        elif issue is None or issue > termination:
            message = "Issue and termination effective dates are missing or inconsistent."
        return ReinstatementSummary(
            code, LAST_ENTRY_CODES.get(code, f"Unknown ({code})"), termination,
            today, years, months, not message, message or "Eligible lapse termination.",
            pay_to, next_date,
        )
    except (DB2ConnectionError, RatesError, TypeError, OverflowError) as exc:
        raise ReinstatementError(f"Cannot read reinstatement summary: {exc}") from exc


def _number(value, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReinstatementError(f"{label} is missing or invalid.") from exc
    if not isfinite(result):
        raise ReinstatementError(f"{label} is not finite.")
    return result


def _debt_at_deduction(state: MonthlyState) -> float:
    return sum((state.rg_loan_princ, state.rg_loan_accrued,
                state.pf_loan_princ, state.pf_loan_accrued,
                state.vbl_loan_princ, state.vbl_loan_accrued))


def _validate_rates(policy, config, rates):
    required = {}
    for segment in policy.segments:
        phase = segment.coverage_phase
        required[f"COI coverage {phase}"] = rates.segment_coi.get(phase)
        required[f"SCR coverage {phase}"] = rates.segment_scr.get(phase, rates.scr)
        if config.epu_code == "Table":
            required[f"EPU coverage {phase}"] = rates.segment_epu.get(phase)
    for setting, name in (
        (config.mfee, "mfee"), (config.premium_load, "tpp"),
        (config.premium_load, "epp"), (config.poav_code, "poav"),
    ):
        if setting == "Table":
            required[name] = getattr(rates, name)
    if policy.has_shadow_account:
        required["shadow COI"] = rates.shadow_coi
        for setting, names in (
            (config.shadow_epu_code, ("shadow_epu",)),
            (config.shadow_int_rate_code, ("shadow_int",)),
            (config.shadow_dbd_rate, ("shadow_dbd",)),
            (config.shadow_prem_load_code, ("shadow_tpp", "shadow_epp")),
            (config.shadow_target, ("shadow_tpr",)),
        ):
            if setting == "Table":
                for name in names:
                    required[name] = getattr(rates, name)
    for name, schedule in required.items():
        if not schedule or len(schedule) < 2:
            raise ReinstatementError(f"Required {name} rate schedule is missing.")
        for value in schedule[1:]:
            _number(value, f"{name} rate")
    for rider in policy.riders:
        if rider.is_active and not rates.rider_rates.get(rider.export_key):
            raise ReinstatementError(f"Required rider rates are missing: {rider.export_key}.")
    keys = benefit_rate_keys(policy.benefits)
    for benefit in policy.benefits:
        if (benefit.is_active and not benefit.benefit_type.startswith("#")
                and not rates.benefit_coi.get(keys[id(benefit)])):
            raise ReinstatementError(f"Required benefit rates are missing: {keys[id(benefit)]}.")


def project_home_office_reinstatement(
    policy: IllustrationPolicyData,
    summary: ReinstatementSummary,
    *,
    rates: IllustrationRates | None = None,
    max_premium: Decimal = Decimal("10000000.00"),
) -> ReinstatementResult:
    """Solve a verified snapshot with the real engine, in integer cents.

    Pure with respect to the supplied model. Inject explicit rate schedules in
    offline tests; normal callers load the canonical schedules. Continuous
    coverage disables only the absorbing lapse flag, not premium limits,
    deductions, interest, forceouts, or maturity. No historical cash is inserted.
    """
    if not summary.eligible:
        raise ReinstatementError(summary.message)
    p = copy.deepcopy(policy)
    target = summary.next_monthliversary
    if not p.issue_date or not p.valuation_date or target is None:
        raise ReinstatementError("A dated post-deduction snapshot and target are required.")
    if summary.quote_pay_to_date is None or p.valuation_date > summary.quote_pay_to_date:
        raise ReinstatementError(
            "The opening snapshot is after the quote pay-to date.")
    elapsed = _months(p.issue_date, p.valuation_date)
    if (p.issue_date + relativedelta(months=elapsed) != p.valuation_date
            or p.duration != elapsed + 1
            or (p.policy_year, p.policy_month) != (elapsed // 12 + 1, elapsed % 12 + 1)):
        raise ReinstatementError("Snapshot date and policy duration are inconsistent.")
    months = _months(p.issue_date, target) - elapsed
    if months < 1 or months > 1200:
        raise ReinstatementError("Reinstatement projection horizon is invalid or exceeds 100 years.")
    if target >= p.issue_date + relativedelta(years=p.maturity_age - p.issue_age):
        raise ReinstatementError("The next deduction is at or beyond policy maturity.")
    if p.run_from_issue or not p.segments or p.total_face <= 0:
        raise ReinstatementError("An intact inforce coverage basis is required.")
    for name in ("account_value", "shadow_account_value", "premiums_paid_to_date",
                 "withdrawals_to_date", "accumulated_mtp", "mtp", "current_interest_rate",
                 "cost_basis", "premiums_ytd", "glp", "gsp", "accumulated_glp",
                 "regular_loan_principal", "regular_loan_accrued",
                 "preferred_loan_principal", "preferred_loan_accrued",
                 "variable_loan_principal", "variable_loan_accrued"):
        _number(getattr(p, name), name)
    if p.def_of_life_ins not in {"GPT", "CVAT"}:
        raise ReinstatementError("A verified regulatory definition of life insurance is required.")
    if p.current_interest_rate < 0:
        raise ReinstatementError("The current interest basis must be nonnegative.")
    if any(tx.effective_date > p.valuation_date for tx in p.premium_transactions):
        raise ReinstatementError(
            "Historical receipts require snapshot-date reconciliation before reinstatement projection.")
    config = load_plancode(p.plancode)
    if config.int_calc_method != "Declared":
        raise ReinstatementError("Indexed crediting during reinstatement is not yet supported.")
    rates = rates if rates is not None else load_rates(p, config)
    _validate_rates(p, config, rates)
    in_safety_net = (
        target <= p.map_cease_date if p.map_cease_date is not None
        else _months(p.issue_date, target) // 12 + 1 <= config.snet_period
    )
    shadow_active = (p.has_shadow_account
                     and p.issue_age + _months(p.issue_date, target) // 12 < config.shadow_cease_age)
    ccv_benefits = [b for b in p.benefits if b.benefit_type == "A"]
    if ccv_benefits:
        shadow_active = shadow_active and any(
            b.is_active and (b.cease_date is None or b.cease_date >= target)
            for b in ccv_benefits)
    basis = "Safety net" if in_safety_net else "Shadow account" if shadow_active else "Surrender value"
    options = IllustrationOptions(no_lapse=True)
    bonus = calc_engine.load_bonus_config(p.plancode, p.valuation_date)
    receipts = {}

    def project(cents):
        inputs = IllustrationInputSet(
            scheduled_transactions=[ScheduledTransaction(
                TransactionKind.PREMIUM, p.policy_year, 0.0, "M")],
            dated_transactions=[DatedTransaction(
                TransactionKind.PREMIUM, summary.current_date, cents / 100.0)],
        )
        # An explicit zero schedule is mandatory: empty inputs restore billing.
        p.modal_premium = p.annual_premium = 0.0
        receipt = None
        if summary.current_date != summary.quote_pay_to_date or p.valuation_date == summary.current_date:
            states, receipt = project_receipt(
                p, config, rates, bonus, options, summary.current_date,
                summary.quote_pay_to_date, target, months - 1, cents / 100.0,
            )
        else:
            states = project_policy(
                copy.deepcopy(p), months=months, inputs=inputs,
                options=options, rates=rates, config=config,
                bonus_override=bonus, stop_on_lapse=False,
            ).states
        receipts[cents] = receipt
        if len(states) != months + 1 or states[-1].date != target:
            raise ReinstatementError("Projection did not reach the next monthly deduction.")
        end = states[-1]
        debt = _debt_at_deduction(end)
        if basis == "Safety net":
            margin = (end.premiums_to_date_after_exception - end.withdrawals_to_date
                      - debt - end.accumulated_mtp)
        elif basis == "Shadow account":
            margin = end.shadow_av - debt
        else:
            margin = end.av_after_deduction - end.surrender_charge - debt
        _number(margin, "Reinstatement funding margin")
        success = margin >= -1e-8 if in_safety_net else margin > 1e-8
        accepted = sum(row.gross_premium for row in states[1:]) + (receipt.gross if receipt else 0.0)
        if any(row.gp_exception_prem for row in states):
            raise ReinstatementError("An unquoted exception premium was generated.")
        return success, states, accepted

    limit_amount = _number(max_premium, "Premium search bound")
    if limit_amount <= 0 or limit_amount > 10000000:
        raise ReinstatementError("The premium search bound must be positive and at most 10,000,000.")
    limit = int(Decimal(str(max_premium)) * 100)
    if limit < 1:
        raise ReinstatementError("The premium search bound must be positive.")
    zero_ok, states, accepted = project(0)
    low = high = 0
    if not zero_ok:
        high = min(10000, limit)
        while True:
            ok, states, accepted = project(high)
            if ok:
                break
            if high == limit:
                raise ReinstatementError(
                    "No fundable premium within the bounded search. "
                    "Regulatory acceptance caps or the supplied coverage basis prevent this quote.")
            low, high = high, min(high * 2, limit)
        while high - low > 1:
            middle = (low + high) // 2
            ok, _, _ = project(middle)
            if ok:
                high = middle
            else:
                low = middle
        ok, states, accepted = project(high)
        if not ok or project(high - 1)[0]:
            raise ReinstatementError("Exact-cent minimum could not be verified.")
    premium = Decimal(high) / 100
    if abs(accepted - float(premium)) > 0.005:
        raise ReinstatementError("Requested premium was not fully accepted under regulatory limits.")
    end = states[-1]
    receipt = receipts[high]
    deductions = sum(row.total_deduction for row in states[1:])
    loads = sum(row.total_premium_load for row in states[1:]) + (receipt.loads if receipt else 0.0)
    interest = sum(row.interest_credited for row in states[:-1])
    forceouts = sum(row.guideline_forceout for row in states[1:])
    reconciliation = p.account_value + accepted - loads + interest - deductions - forceouts
    if abs(reconciliation - end.av_after_deduction) > 0.02:
        raise ReinstatementError("Projected account-value movements do not reconcile.")
    if shadow_active:
        shadow_reconciled = (
            p.shadow_account_value + accepted
            - sum(s.shadow_prem_load + s.shadow_md for s in states[1:])
            - (receipt.shadow_loads if receipt else 0.0)
            + sum(s.shadow_interest for s in states[:-1])
        )
        if abs(shadow_reconciled - end.shadow_av) > 0.02:
            raise ReinstatementError("Projected shadow-account movements do not reconcile.")
    rows = (
        ("Starting account value (post-deduction)", p.account_value),
        ("Starting shadow account value", p.shadow_account_value),
        ("Starting premiums paid", p.premiums_paid_to_date),
        ("Starting accumulated withdrawals", p.withdrawals_to_date),
        ("Starting accumulated minimum target premium", p.accumulated_mtp),
        ("Required gross premium", premium),
        ("Premium loads", loads),
        ("Interest before next deduction", interest),
        ("Total monthly deductions (including next)", deductions),
        ("Guideline forceouts", forceouts),
        ("Next monthliversary debt (at deduction)", _debt_at_deduction(end)),
        ("Next accumulated minimum target premium", end.accumulated_mtp),
        ("Next premiums paid (including quote)", end.premiums_to_date_after_exception),
        ("Next accumulated withdrawals", end.withdrawals_to_date),
        ("Next premiums paid less withdrawals and debt",
         end.premiums_to_date_after_exception - end.withdrawals_to_date - _debt_at_deduction(end)),
        ("Next surrender charge", end.surrender_charge),
        ("Next account value after deduction", end.av_after_deduction),
        ("Next surrender value after deduction", end.surrender_value),
        ("Shadow premium loads", sum(s.shadow_prem_load for s in states[1:])
         + (receipt.shadow_loads if receipt else 0.0)),
        ("Shadow deductions", sum(s.shadow_md for s in states[1:])),
        ("Shadow interest before next deduction", sum(s.shadow_interest for s in states[:-1])),
        ("Next shadow value after deduction", end.shadow_av),
        ("Next shadow value less debt", end.shadow_av - _debt_at_deduction(end)),
    )
    equation = {
        "Safety net": (
            "Safety net: premiums paid (including this premium) - accumulated withdrawals "
            "- debt at the next deduction must cover accumulated MTP through that deduction. "
            "A zero premium means that requirement is already satisfied."
        ),
        "Shadow account": (
            "Shadow account: starting shadow value + accepted premium - shadow premium loads "
            "+ shadow interest - all shadow deductions - debt at the next deduction "
            "must be strictly positive."
        ),
        "Surrender value": (
            "Surrender value: starting account value + accepted premium - premium loads "
            "+ interest - all monthly deductions - forceouts - surrender charge "
            "- debt at the next deduction must be strictly positive."
        ),
    }[basis]
    return ReinstatementResult(
        summary, premium, basis, tuple((label, f"{value:,.2f}") for label, value in rows),
        f"{equation}\n"
        f"Continuous coverage from the verified post-deduction snapshot {p.valuation_date:%Y-%m-%d}. "
        f"One premium is posted on {summary.current_date:%Y-%m-%d}; no historical receipts are backdated. "
        f"Canonical illustration crediting basis: {p.current_interest_rate:.4%}, "
        f"{config.interest_method}; a between-deduction receipt earns only its remaining-period interest. "
        "The next monthliversary deduction is included; interest after that deduction is excluded. "
        "TEFRA/TAMRA caps and guideline forceouts remain enabled; no automatic exception premium. "
        "Skipped coverage and reinstatement-specific regulatory resets are not modeled.",
        tuple(states),
    )


def calculate_home_office_reinstatement(policy, today: date | None = None) -> ReinstatementResult:
    """Validate canonical data before any normal-loader defaults can hide gaps."""
    try:
        summary = reinstatement_summary(policy, today)
        if not summary.eligible:
            raise ReinstatementError(summary.message)
        snapshot = policy.mv_date(0)
        if snapshot is None or snapshot != policy.valuation_date:
            raise ReinstatementError("An actual monthliversary snapshot is required; derived dates are not sufficient.")
        # These accessors normally default missing database values to zero.
        # Validate their canonical source fields before calling the loader.
        for table, fields, index in (
            ("LH_POL_TOTALS", ("TOT_REG_PRM_AMT", "TOT_ADD_PRM_AMT",
                              "TOT_WTD_AMT", "POL_CST_BSS_AMT"), 0),
            ("LH_POL_MVRY_VAL", ("CINS_AMT", "EXP_CRG_AMT", "OTH_PRM_AMT"), 0),
        ):
            for field in fields:
                _number(policy.data_item(table, field, index), f"{table}.{field}")
        ytd_count = policy.data_item_count("LH_POL_YR_TOT")
        if ytd_count < 1:
            raise ReinstatementError("Premium year-to-date snapshot is missing.")
        for field in ("YTD_TOT_PMT_AMT", "YTD_ADD_PRM_AMT"):
            _number(policy.data_item("LH_POL_YR_TOT", field, ytd_count - 1), field)
        for row in policy.fetch_table("LH_FND_VAL_LOAN"):
            for field in ("LN_PRI_AMT", "POL_LN_ITS_AMT"):
                _number(row.get(field), f"Loan {field}")
        for name, value in (
            ("Opening account value", policy.mv_av(0)),
            ("Premiums paid", policy.premium_td), ("Premiums YTD", policy.premium_ytd),
            ("Withdrawals", policy.total_withdrawals), ("Cost basis", policy.cost_basis),
            ("MTP", policy.mtp), ("Accumulated MTP", policy.accumulated_mtp_target),
        ):
            _number(value, name)
        coverages = policy.get_base_coverages()
        restored = [restore_lapse_coverage(c, summary.termination_date) for c in coverages]
        selected = [c for c in restored if not _coverage_is_terminated(c, snapshot)]
        if not selected:
            raise ReinstatementError(
                "The pre-lapse coverage basis cannot be established. "
                "Undated or unrelated terminations cannot be restored.")
        selected_riders = [
            restore_lapse_coverage(r, summary.termination_date) for r in policy.get_riders()
        ]
        selected_riders = [r for r in selected_riders if not _coverage_is_terminated(r, snapshot)]
        for c in selected + selected_riders:
            for attr in ("face_amount", "units", "issue_age"):
                _number(getattr(c, attr, None), f"Coverage {attr}")
            if (getattr(c, "issue_date", None) is None
                    or not getattr(c, "sex_code", None) or not getattr(c, "rate_class", None)):
                raise ReinstatementError("Coverage issue date or underwriting is missing.")
        policy.get_substandard_ratings()
        for benefit in policy.get_benefits():
            if (benefit.benefit_type_cd != "#"
                    and benefit.cease_date == summary.termination_date):
                raise ReinstatementError(
                    "A benefit ceases on the lapse date without a separate termination indicator. "
                    "Confirm its contractual continuation before quoting.")
        ill_policy = build_illustration_data(
            policy.policy_number, region=policy.region, company_code=policy.company_code,
            illustration_date=summary.current_date,
            reinstatement_date=summary.termination_date,
        )
        if len(ill_policy.segments) != len(selected) or ill_policy.valuation_date != snapshot:
            raise ReinstatementError("The loaded coverage basis is incomplete.")
        if ill_policy.has_shadow_account:
            _number(policy.shadow_account_value, "Starting shadow account value")
        if ill_policy.is_gpt:
            for name in ("glp", "gsp", "accumulated_glp_target"):
                _number(getattr(policy, name, None), name)
        if any(t.trans_date is None or t.trans_date > snapshot for t in policy.get_transactions()):
            raise ReinstatementError(
                "Financial history extends beyond the opening snapshot or has undated entries. "
                "Reconcile accumulator, loan and shadow balances before quoting; no receipts were backdated.")
        return project_home_office_reinstatement(ill_policy, summary)
    except ReinstatementError:
        raise
    except (DB2ConnectionError, RatesError, RateLookupError, OSError, ValueError,
            TypeError, ArithmeticError) as exc:
        raise ReinstatementError(f"Reinstatement data or projection is unavailable: {exc}") from exc
