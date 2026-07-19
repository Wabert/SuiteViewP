"""Withdrawal Net vs Gross basis — compiler routing + handler inversion.

Net (the verified default — RERUN's vINPUT_Withdrawal/AX is a net request):
the client receives the entered amount and the policy is charged that plus
the WD fee (and partial SC when the SA reduces) — RERUN BN = net + PSC + fee.

Gross (SuiteView extension): the entered amount is what leaves the account
value (BN); the handler inverts it to the net request the AX chain consumes.
"""
from __future__ import annotations

from datetime import date

import pytest

from suiteview.illustration.core.input_compiler import (
    CompiledMonthInputs,
    compile_month_inputs,
)
from suiteview.illustration.core.withdrawal_handler import compute_withdrawal
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)

FEE = 25.0


def _policy(dbo: str = "A") -> IllustrationPolicyData:
    return IllustrationPolicyData(
        db_option=dbo,
        segments=[CoverageSegment(coverage_phase=1, face_amount=100_000.0)],
    )


def _config(**overrides) -> PlancodeConfig:
    values = dict(
        withdrawal_fee=FEE,
        md_holdback=0.0,
        partial_surrender_charge=True,
        min_face_after_wd=25_000.0,
    )
    values.update(overrides)
    return PlancodeConfig(**values)


def _compute(policy, config, request=0.0, gross_request=0.0, *,
             av=50_000.0, corridor_rate=2.5, scr=0.0):
    return compute_withdrawal(
        av, policy, config, {1: scr}, request,
        gross_request=gross_request,
        corridor_rate=corridor_rate,
        prior_total_md=0.0,
        policy_debt=0.0,
        cost_basis=20_000.0,
        withdrawals_to_date=0.0,
        withdrawals_ytd=0.0,
        is_anniversary=True,
    )


# ── compiler: basis routing ──────────────────────────────────────────────


def _compile_single_withdrawal(subtype: str):
    policy = IllustrationPolicyData(issue_date=date(2020, 1, 1), duration=12)
    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(
            kind=TransactionKind.WITHDRAWAL,
            effective_date=date(2021, 3, 1),   # duration 15
            amount=1_000.0,
            subtype=subtype,
        ),
    ])
    return compile_month_inputs(policy, inputs, 12)[15]


@pytest.mark.parametrize("subtype", ["", "net", "Net"])
def test_compiler_routes_net_and_blank_basis_to_net_bucket(subtype):
    month = _compile_single_withdrawal(subtype)
    assert month.withdrawal == 1_000.0
    assert month.withdrawal_gross == 0.0


@pytest.mark.parametrize("subtype", ["gross", "Gross", " GROSS "])
def test_compiler_routes_gross_basis_to_gross_bucket(subtype):
    month = _compile_single_withdrawal(subtype)
    assert month.withdrawal == 0.0
    assert month.withdrawal_gross == 1_000.0


def test_compiler_accumulates_mixed_bases_separately():
    policy = IllustrationPolicyData(issue_date=date(2020, 1, 1), duration=12)
    when = date(2021, 3, 1)
    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(kind=TransactionKind.WITHDRAWAL, effective_date=when,
                         amount=400.0, subtype="net"),
        DatedTransaction(kind=TransactionKind.WITHDRAWAL, effective_date=when,
                         amount=600.0, subtype="gross"),
    ])
    month = compile_month_inputs(policy, inputs, 12)[15]
    assert month.withdrawal == 400.0
    assert month.withdrawal_gross == 600.0


def test_compiled_month_inputs_default_has_no_gross_withdrawal():
    assert CompiledMonthInputs().withdrawal_gross == 0.0


# ── handler: net basis (the verified pre-existing behavior) ──────────────


def test_net_basis_charges_fee_on_top_of_client_cash():
    # Below the corridor slice (corridor 2.5*50k - 100k = 25k) — no SA change.
    wd = _compute(_policy(), _config(), request=1_000.0)
    assert wd.applied_net_withdrawal == 1_000.0          # client receives
    assert wd.partial_sc == 0.0
    assert wd.gross_withdrawal == 1_000.0 + FEE          # AV gives up net + fee
    assert wd.av_post_withdrawal == 50_000.0 - 1_025.0
    assert wd.withdrawals_to_date == 1_000.0             # NET accumulates
    assert wd.cost_basis_after_wd == 19_000.0


def test_net_basis_without_gross_keyword_matches_prior_signature():
    # gross_request defaults to 0.0 — legacy call sites are byte-identical.
    policy, config = _policy(), _config()
    baseline = _compute(policy, config, request=1_000.0)
    explicit = _compute(policy, config, request=1_000.0, gross_request=0.0)
    assert explicit == baseline


def test_net_basis_with_psc_adds_charge_into_gross():
    # corridor_rate 1.0 -> corridor amount 0, DBO A -> SA reduces; SCR 20/1000.
    wd = _compute(_policy(), _config(), request=10_000.0,
                  corridor_rate=1.0, scr=20.0)
    assert wd.applied_net_withdrawal == 10_000.0
    assert wd.reduces_sa is True
    assert wd.partial_sc == pytest.approx(200.0)
    assert wd.gross_withdrawal == pytest.approx(10_000.0 + 200.0 + FEE)


# ── handler: gross basis ─────────────────────────────────────────────────


def test_gross_basis_deducts_exactly_the_entered_amount():
    wd = _compute(_policy(), _config(), gross_request=1_000.0)
    assert wd.applied_net_withdrawal == pytest.approx(1_000.0 - FEE)
    assert wd.gross_withdrawal == pytest.approx(1_000.0)
    assert wd.av_post_withdrawal == pytest.approx(49_000.0)


def test_gross_basis_inverts_psc_so_av_drop_matches_request():
    wd = _compute(_policy(), _config(), gross_request=10_000.0,
                  corridor_rate=1.0, scr=20.0)
    # net solves net = 10_000 - 25 - 0.02*net -> 9_975/1.02
    expected_net = 9_975.0 / 1.02
    assert wd.applied_net_withdrawal == pytest.approx(expected_net, abs=1e-6)
    assert wd.partial_sc == pytest.approx(expected_net * 0.02, abs=1e-6)
    assert wd.gross_withdrawal == pytest.approx(10_000.0, abs=1e-6)
    assert wd.av_post_withdrawal == pytest.approx(40_000.0, abs=1e-6)


def test_gross_basis_skips_psc_inversion_when_dbo_b():
    # DBO B never reduces SA, so gross = net + fee only.
    wd = _compute(_policy("B"), _config(), gross_request=10_000.0,
                  corridor_rate=1.0, scr=20.0)
    assert wd.reduces_sa is False
    assert wd.applied_net_withdrawal == pytest.approx(10_000.0 - FEE)
    assert wd.gross_withdrawal == pytest.approx(10_000.0)


def test_gross_request_at_or_below_fee_yields_no_withdrawal():
    wd = _compute(_policy(), _config(), gross_request=FEE)
    assert wd.input_withdrawal == 0.0
    assert wd.applied_net_withdrawal == 0.0
    assert wd.gross_withdrawal == 0.0
    assert wd.av_post_withdrawal == 50_000.0


def test_mixed_bases_charge_the_single_fee_against_the_gross_portion():
    # Net 400 (client cash exact) + gross 600 (AV drop exact) in one month:
    # one fee, attributed to the gross entry.
    wd = _compute(_policy(), _config(), request=400.0, gross_request=600.0)
    assert wd.applied_net_withdrawal == pytest.approx(400.0 + 600.0 - FEE)
    assert wd.gross_withdrawal == pytest.approx(1_000.0)
    assert wd.av_post_withdrawal == pytest.approx(49_000.0)


def test_gross_basis_still_caps_at_max_net_withdrawal():
    # Tiny AV: max net = csv - fee = 500 - 25 = 475 caps the converted request.
    wd = _compute(_policy(), _config(), gross_request=10_000.0, av=500.0)
    assert wd.max_net_withdrawal == pytest.approx(475.0)
    assert wd.applied_net_withdrawal == pytest.approx(475.0)
    assert wd.gross_withdrawal == pytest.approx(500.0)
    assert wd.av_post_withdrawal == pytest.approx(0.0)
