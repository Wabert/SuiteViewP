"""Reinstatement eligibility and real-engine projections without database access."""
import copy
from dataclasses import replace
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from suiteview.polview.services import reinstatement as rein


def source(**changes):
    values = dict(
        exists=True, product_type="UL", last_entry_code="Q",
        issue_date=date(2000, 1, 15), terminate_date=date(2025, 1, 15),
    )
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("product", ["UL", "IUL", "SGUL"])
def test_ul_family_is_eligible(product):
    assert rein.is_ul_policy(source(product_type=product))


@pytest.mark.parametrize("product", ["VUL", "ISWL", "WL", "TERM", "UNKNOWN"])
def test_non_ul_family_is_not_eligible(product):
    summary = rein.reinstatement_summary(source(product_type=product), date(2026, 9, 14))
    assert not summary.eligible
    assert "only available for ULs" in summary.message


@pytest.mark.parametrize("code", ["P", "X", "A", "M", ""])
def test_only_lapse_not_surrender(code):
    summary = rein.reinstatement_summary(source(last_entry_code=code), date(2026, 9, 14))
    assert not summary.eligible
    assert summary.termination_date == date(2025, 1, 15)
    assert (summary.terminated_years, summary.terminated_months) == (1, 7)


def test_summary_uses_effective_date_not_last_entry_date():
    summary = rein.reinstatement_summary(
        source(last_entry_date=date(2026, 8, 20)), date(2026, 9, 14))
    assert summary.last_entry_description == "Termination - Lapse"
    assert summary.termination_date == date(2025, 1, 15)
    assert summary.quote_pay_to_date == date(2026, 8, 15)
    assert summary.next_monthliversary == date(2026, 9, 15)


@pytest.mark.parametrize("today,pay_to,next_date", [
    (date(2024, 2, 28), date(2024, 1, 31), date(2024, 2, 29)),
    (date(2024, 2, 29), date(2024, 2, 29), date(2024, 3, 31)),
    (date(2024, 3, 30), date(2024, 2, 29), date(2024, 3, 31)),
    (date(2024, 3, 31), date(2024, 3, 31), date(2024, 4, 30)),
])
def test_month_end_stays_issue_day_anchored(today, pay_to, next_date):
    summary = rein.reinstatement_summary(
        source(issue_date=date(2000, 1, 31), terminate_date=date(2023, 1, 31)), today)
    assert (summary.quote_pay_to_date, summary.next_monthliversary) == (pay_to, next_date)


@pytest.mark.parametrize("termination", [None, date(9999, 12, 31), date(2027, 1, 15)])
def test_missing_future_termination_not_eligible(termination):
    assert not rein.reinstatement_summary(
        source(terminate_date=termination), date(2026, 9, 14)).eligible


@pytest.fixture
def projection(monkeypatch):
    p = IllustrationPolicyData(
        policy_number="SYNTHETIC", plancode="REINTEST", product_type="UL",
        issue_date=date(2000, 1, 15), valuation_date=date(2026, 1, 15),
        issue_age=30, attained_age=56, maturity_age=121,
        policy_year=27, policy_month=1, duration=313,
        face_amount=100000.0, units=100.0, account_value=10.0,
        modal_premium=999.0, billing_frequency=1,
        def_of_life_ins="GPT", glp=100000.0, gsp=100000.0,
        accumulated_glp=100000.0, premiums_paid_to_date=1000.0,
        cost_basis=1000.0, premiums_ytd=0.0, mtp=10.0,
        accumulated_mtp=1000.0,
        segments=[CoverageSegment(
            issue_date=date(2000, 1, 15), issue_age=30,
            face_amount=100000.0, original_face_amount=100000.0, units=100.0,
            rate_sex="M", rate_class="N",
        )],
    )
    config = PlancodeConfig(
        plancode="REINTEST", gint=0.0, dbd=0.0, corridor_code=None,
        epu_code="0", mfee="10", premium_load="0", snet_period=0,
        lapse_value="SV", shadow_int_rate_code="0", shadow_dbd_rate="0",
        shadow_mfee=10.0,
    )
    rates = IllustrationRates(
        coi=[0.0, 0.0], segment_coi={1: [0.0, 0.0]}, scr=[0.0, 0.0],
        shadow_coi=[0.0, 0.0],
    )
    monkeypatch.setattr(rein, "load_plancode", lambda _: config)
    monkeypatch.setattr(rein, "load_rates", lambda *_: rates)
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _: config)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_: BonusConfig())
    summary = rein.reinstatement_summary(source(), date(2026, 2, 15))

    def run(**kwargs):
        return rein.project_home_office_reinstatement(p, summary, rates=rates, **kwargs)

    return p, config, rates, summary, run


def test_surrender_value_funds_next_deduction_and_exact_cent(projection):
    p, _, _, _, run = projection
    before = copy.deepcopy(p)
    result = run()
    assert result.basis == "Surrender value"
    assert result.premium == Decimal("10.01")
    assert result.states[-1].date == date(2026, 3, 15)
    assert result.states[-1].av_after_deduction == pytest.approx(0.01)
    assert result.states[0].av_after_deduction == 10.0
    assert [s.gross_premium for s in result.states] == [0.0, 10.01, 0.0]
    assert p == before


def test_zero_is_not_replaced_by_policy_billing(projection):
    p, _, _, _, run = projection
    p.account_value = 100.0
    result = run()
    assert result.premium == Decimal("0")
    assert all(s.gross_premium == 0 for s in result.states)


def test_safety_net_requires_next_accumulation_not_current(projection):
    _, config, _, _, run = projection
    config.snet_period = 30
    result = run()
    assert result.basis == "Safety net"
    assert result.premium == Decimal("20.00")
    assert result.states[-1].accumulated_mtp == 1020.0


def test_safety_net_breakdown_exposes_each_term_and_reconciles(projection):
    p, config, _, _, run = projection
    config.snet_period = 30
    p.withdrawals_to_date = 200.0
    p.regular_loan_principal = 100.0
    config.loan_charge_rate_curr = config.loan_charge_rate_guar = 0.12
    result = run()
    end = result.states[-1]
    rows = dict(result.breakdown)
    assert rows["Starting premiums paid"] == "1,000.00"
    assert rows["Starting accumulated withdrawals"] == "200.00"
    assert rows["Starting accumulated minimum target premium"] == "1,000.00"
    assert rows["Next accumulated withdrawals"] == "200.00"
    assert rows["Next premiums paid (including quote)"] == f"{1000 + result.premium:,.2f}"
    margin = (end.premiums_to_date_after_exception - end.withdrawals_to_date
              - rein._debt_at_deduction(end) - end.accumulated_mtp)
    assert 0 <= margin < 0.01
    assert "must cover accumulated MTP" in result.explanation


def test_safety_net_ceasing_before_target_switches_basis(projection):
    p, config, _, _, run = projection
    config.snet_period = 30
    p.map_cease_date = date(2026, 2, 15)
    result = run()
    assert result.basis == "Surrender value"
    assert result.premium == Decimal("10.01")


def test_active_shadow_not_positive_value_alone(projection):
    p, _, _, _, run = projection
    p.account_value = 1000.0
    p.ccv_active = True
    p.shadow_account_value = 10.0
    result = run()
    assert result.basis == "Shadow account"
    assert result.premium == Decimal("10.01")
    p.ccv_active = False
    assert run().premium == 0


def test_expired_shadow_uses_surrender(projection):
    p, config, _, _, run = projection
    p.ccv_active = True
    p.shadow_account_value = 10000.0
    config.shadow_cease_age = 56
    assert run().basis == "Surrender value"


def test_surrender_charges_and_loads_reconcile(projection):
    p, config, rates, _, run = projection
    config.premium_load = "0.1"
    rates.scr = [0.0, 1.0]
    result = run()
    assert result.premium > Decimal("110")
    end = result.states[-1]
    assert end.surrender_charge == 100.0
    assert end.surrender_value > 0
    assert p.account_value + float(result.premium) - sum(
        s.total_premium_load + s.total_deduction for s in result.states[1:]
    ) == pytest.approx(end.av_after_deduction)


def test_debt_accrues_only_through_next_deduction(projection):
    p, config, _, _, run = projection
    p.regular_loan_principal = 100.0
    config.loan_charge_rate_curr = config.loan_charge_rate_guar = 0.12
    result = run()
    target = result.states[-1]
    assert rein._debt_at_deduction(target) > 100
    assert target.policy_debt > rein._debt_at_deduction(target)
    assert target.surrender_value > 0


def test_regulatory_caps_fail_loudly_without_bypass(projection):
    p, _, _, _, run = projection
    p.glp = 0.0
    p.gsp = p.accumulated_glp = p.premiums_paid_to_date
    with pytest.raises(rein.ReinstatementError, match="Regulatory"):
        run(max_premium=Decimal("1000"))


def test_missing_rates_are_not_zero(projection):
    _, _, rates, _, run = projection
    rates.scr = []
    with pytest.raises(rein.ReinstatementError, match="SCR"):
        run()


@pytest.mark.parametrize("change,match", [
    ({"valuation_date": date(2026, 1, 14)}, "inconsistent"),
    ({"duration": 1}, "inconsistent"),
    ({"maturity_age": 56}, "maturity"),
    ({"account_value": None}, "missing"),
    ({"account_value": float("nan")}, "finite"),
    ({"segments": []}, "intact"),
])
def test_invalid_snapshot_fails_safely(projection, change, match):
    p, _, _, _, run = projection
    for name, value in change.items():
        setattr(p, name, value)
    with pytest.raises(rein.ReinstatementError, match=match):
        run()


def test_premium_never_backdated_for_midmonth_date(projection):
    p, _, rates, summary, _ = projection
    summary = replace(summary, current_date=date(2026, 2, 16))
    result = rein.project_home_office_reinstatement(p, summary, rates=rates)
    assert result.premium == Decimal("10.01")
    assert all(s.gross_premium == 0 for s in result.states)
    assert result.states[0].av_after_deduction == p.account_value
    assert result.states[1].av_after_deduction == 0
    assert "2026-02-16" in result.explanation
    assert result.states[-1].surrender_value == pytest.approx(0.01)


def test_receipt_on_snapshot_day_is_after_opening_deduction(projection):
    p, _, rates, summary, _ = projection
    p.valuation_date = summary.current_date
    p.policy_month = 2
    p.duration += 1
    result = rein.project_home_office_reinstatement(p, summary, rates=rates)
    assert result.premium == Decimal("0.01")
    assert result.states[0].av_after_deduction == p.account_value
    assert result.states[0].gross_premium == 0
    assert result.states[-1].surrender_value == pytest.approx(0.01)


def live_source():
    return source(
        policy_number="SYNTHETIC", company_code="01", region="CKPR",
        valuation_date=date(2026, 1, 15), mv_date=lambda _: date(2026, 1, 15),
        mv_av=lambda _: Decimal("10"), premium_td=Decimal("1000"),
        premium_ytd=Decimal("0"), total_withdrawals=Decimal("0"),
        cost_basis=Decimal("1000"), mtp=Decimal("10"),
        accumulated_mtp_target=Decimal("1000"),
        glp=Decimal("100000"), gsp=Decimal("100000"),
        accumulated_glp_target=Decimal("100000"), get_transactions=lambda: [],
        data_item=lambda *args: Decimal("0"), data_item_count=lambda _: 1,
        fetch_table=lambda _: [],
        get_riders=lambda: [], get_benefits=lambda: [], get_substandard_ratings=lambda: [],
        get_base_coverages=lambda: [SimpleNamespace(
            cov_status="1", terminate_date=None, cease_date=None,
            face_amount=100000.0, units=100.0, issue_age=30,
            issue_date=date(2000, 1, 15), sex_code="1", rate_class="N")],
    )


def test_live_missing_av_is_not_zero(monkeypatch):
    policy = live_source()
    policy.mv_av = lambda _: None
    with pytest.raises(rein.ReinstatementError, match="Opening account value"):
        rein.calculate_home_office_reinstatement(policy, date(2026, 2, 15))


def test_live_derived_valuation_date_is_not_snapshot():
    policy = live_source()
    policy.mv_date = lambda _: None
    with pytest.raises(rein.ReinstatementError, match="actual monthliversary"):
        rein.calculate_home_office_reinstatement(policy, date(2026, 2, 15))


def test_live_terminated_coverage_is_not_silently_removed():
    policy = live_source()
    policy.get_base_coverages = lambda: [SimpleNamespace(
        cov_status="0", terminate_date=None, cease_date=None)]
    with pytest.raises(rein.ReinstatementError, match="pre-lapse coverage"):
        rein.calculate_home_office_reinstatement(policy, date(2026, 2, 15))


def test_canonical_loader_quotes_without_blanket_lapse_block(projection, monkeypatch):
    p, _, _, _, _ = projection
    calls = []
    def load(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(policy=p)
    monkeypatch.setattr(rein, "load_projection_basis", load)
    result = rein.calculate_home_office_reinstatement(live_source(), date(2026, 2, 16))
    assert result.premium == Decimal("10.01")
    assert calls[0]["reinstatement_date"] == date(2025, 1, 15)
    assert "Canonical illustration crediting basis" in result.explanation


@pytest.mark.parametrize("exception_type", [rein.DB2ConnectionError, rein.RatesError, rein.RateLookupError])
def test_known_data_failures_use_domain_error(monkeypatch, exception_type):
    def fail(*args, **kwargs):
        raise exception_type("Unavailable source")
    monkeypatch.setattr(rein, "load_projection_basis", fail)
    with pytest.raises(rein.ReinstatementError, match="Unavailable source"):
        rein.calculate_home_office_reinstatement(live_source(), date(2026, 2, 15))


def test_shadow_test_always_deducts_debt(projection):
    p, config, _, _, run = projection
    p.ccv_active = True
    p.shadow_account_value = 10.0
    p.regular_loan_principal = 100.0
    config.shadow_loan_impact = "None"
    result = run()
    assert result.basis == "Shadow account"
    assert result.premium == Decimal("110.01")
    end = result.states[-1]
    assert end.shadow_av - rein._debt_at_deduction(end) == pytest.approx(0.01)


def test_no_next_period_interest_used_to_fund_target_deduction(projection):
    p, _, _, _, run = projection
    p.current_interest_rate = 0.12
    result = run()
    end = result.states[-1]
    assert end.surrender_value > 0
    assert end.av_end_of_month >= end.av_after_deduction
    rows = dict(result.breakdown)
    assert float(rows["Interest before next deduction"].replace(",", "")) == pytest.approx(
        sum(s.interest_credited for s in result.states[:-1]), abs=0.005)


def test_snapshot_premium_history_is_not_backdated(projection):
    p, _, _, _, run = projection
    p.premium_transactions = [SimpleNamespace(
        effective_date=date(2026, 2, 1), amount=1000.0)]
    with pytest.raises(rein.ReinstatementError, match="Historical receipts"):
        run()


@pytest.mark.parametrize("basis", ["Safety net", "Shadow account", "Surrender value"])
def test_midmonth_receipt_supports_all_funding_branches(projection, basis):
    p, config, rates, summary, _ = projection
    if basis == "Safety net":
        config.snet_period = 30
    elif basis == "Shadow account":
        p.ccv_active = True
        p.shadow_account_value = 10.0
    summary = replace(summary, current_date=date(2026, 2, 20))
    result = rein.project_home_office_reinstatement(p, summary, rates=rates)
    assert result.basis == basis
    assert result.premium == (Decimal("20") if basis == "Safety net" else Decimal("10.01"))
    assert result.states[-1].date == date(2026, 3, 15)


def test_receipt_later_in_month_does_not_earn_earlier_interest(projection):
    p, _, rates, summary, _ = projection
    p.current_interest_rate = 0.12
    early = rein.project_home_office_reinstatement(
        p, replace(summary, current_date=date(2026, 2, 16)), rates=rates)
    late = rein.project_home_office_reinstatement(
        p, replace(summary, current_date=date(2026, 3, 14)), rates=rates)
    assert early.premium < late.premium
    assert early.states[0].av_after_deduction == late.states[0].av_after_deduction == 10


def test_midmonth_receipt_preserves_regulatory_caps(projection):
    p, _, rates, summary, _ = projection
    p.glp = 0.0
    p.gsp = p.accumulated_glp = p.premiums_paid_to_date
    with pytest.raises(rein.ReinstatementError, match="Regulatory"):
        rein.project_home_office_reinstatement(
            p, replace(summary, current_date=date(2026, 2, 20)),
            rates=rates, max_premium=Decimal("1000"))


def test_midmonth_zero_premium_does_not_change_existing_interest(projection):
    p, config, rates, summary, _ = projection
    p.account_value = 1000
    p.current_interest_rate = 0.08
    p.regular_loan_principal = 10
    result = rein.project_home_office_reinstatement(
        p, replace(summary, current_date=date(2026, 2, 20)), rates=rates)
    q = copy.deepcopy(p)
    q.modal_premium = 0
    ordinary = rein.IllustrationEngine().project(
        q, months=2, rates_override=rates, bonus_override=BonusConfig(),
        options=rein.IllustrationOptions(no_lapse=True))
    assert result.premium == 0
    assert result.states[-1].av_after_deduction == ordinary[-1].av_after_deduction
    assert result.states[-1].policy_debt == ordinary[-1].policy_debt


def test_raw_missing_accumulators_are_not_silently_zero():
    policy = live_source()
    policy.data_item = lambda *args: None
    with pytest.raises(rein.ReinstatementError, match="LH_POL_TOTALS"):
        rein.calculate_home_office_reinstatement(policy, date(2026, 2, 20))


def test_history_after_snapshot_is_not_merged(projection, monkeypatch):
    p, _, _, _, _ = projection
    monkeypatch.setattr(rein, "load_projection_basis", lambda *a, **kw: SimpleNamespace(policy=p))
    policy = live_source()
    policy.get_transactions = lambda: [SimpleNamespace(trans_date=date(2026, 2, 1))]
    with pytest.raises(rein.ReinstatementError, match="Financial history extends"):
        rein.calculate_home_office_reinstatement(policy, date(2026, 2, 20))


def test_restore_only_explicit_lapse_termination_without_mutating_source():
    original = SimpleNamespace(
        terminate_date=date(2025, 1, 15), maturity_date=date(2091, 1, 15),
        nxt_chg_dt=date(2025, 1, 15), nxt_chg_typ_cd="0", cov_status="0")
    restored = rein.restore_lapse_coverage(original, date(2025, 1, 15))
    assert restored is not original
    assert original.terminate_date == date(2025, 1, 15)
    assert restored.terminate_date is None
    assert not rein._coverage_is_terminated(restored, date(2026, 1, 15))
    assert rein.restore_lapse_coverage(original, date(2025, 2, 15)) is original
    assert rein.restore_lapse_coverage(original, None) is original


def test_contractual_maturity_is_never_restored():
    original = SimpleNamespace(
        terminate_date=date(2025, 1, 15), maturity_date=date(2025, 1, 15),
        nxt_chg_dt=date(2025, 1, 15), nxt_chg_typ_cd="0", cov_status="0")
    assert rein.restore_lapse_coverage(original, date(2025, 1, 15)) is original
