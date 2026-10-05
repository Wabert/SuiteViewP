"""Single-premium ISWL (premium pay status 42): no premium is due after issue.

The 46 single-premium ISWL plans (B11S*, B71S*, F*2S*, M*2S*, N61SB*, NA1SP900, NB1S*)
carry PLAN_DEF premium load rules 000 or 300 and, for most, no PLAN_MODEFACT, PREM or
PREMLOAD_PCT rows. Their policies paid one premium at issue, which CyberLife stores as
the modal premium (e.g. B11SB200 26/000317196: 12,080.71, mode 12).
"""
from datetime import date

import pytest

from suiteview.illustration.core.calc_engine import _split_requested_premium
from suiteview.illustration.core.iswl_rates import load_iswl_rates, split_iswl_premium
from suiteview.illustration.core.premium_handler import apply_premium
from suiteview.illustration.core.rate_loader import IllustrationRates, RateLookupError
from tests.test_illustration_iswl import _config, _FakeSchema, _policy


class _SinglePremiumSchema(_FakeSchema):
    """A single-premium plan: load rules 000, no PREM/PREMLOAD_PCT cells, no mode factors."""

    def __init__(self, **kwargs):
        super().__init__(rules="000", **kwargs)
        self.cells = [c for c in self.cells if c.rate_type not in ("PREM", "PREMLOAD_PCT")]

    def modal_factors(self, company, plancode):
        return []


def _single_premium_policy(**changes):
    values = dict(premium_pay_status_code="42", modal_premium=12080.71, billing_frequency=12)
    values.update(changes)
    return _policy(**values)


def test_status_42_is_single_premium():
    assert _single_premium_policy().is_single_premium
    assert not _policy(premium_pay_status_code="22").is_single_premium


def test_single_premium_plan_loads_without_premium_load_prem_or_mode_factors():
    rates = load_iswl_rates(_single_premium_policy(), _config(), repo=_SinglePremiumSchema())
    basis = rates.iswl
    assert basis.single_premium
    assert basis.billed_premium == 0.0 and basis.policy_fee_annual == 0.0
    assert rates.coi[39] == pytest.approx(2.55 / 12)
    assert basis.cash_value_per_unit[1] == 10.0
    assert any("Single premium (premium pay status 42)" in note for note in basis.notes)


def test_premium_paying_policy_on_a_single_premium_plan_still_fails_loudly():
    with pytest.raises(RateLookupError, match="premium load rules 000"):
        load_iswl_rates(_policy(), _config(), repo=_SinglePremiumSchema())


def test_single_premium_iswl_bills_nothing_by_default():
    policy = _single_premium_policy()
    assert _split_requested_premium(policy, _config(), None, 40, policy_month=1) == (0.0, 0.0)


def test_requested_premium_on_a_single_premium_iswl_raises():
    basis = load_iswl_rates(_single_premium_policy(), _config(), repo=_SinglePremiumSchema()).iswl
    assert split_iswl_premium(basis, 0.0, 12080.71, 40, None).payments == 0
    with pytest.raises(ValueError, match="Single-premium ISWL"):
        split_iswl_premium(basis, 12080.71, 12080.71, 40, None)


def test_apply_premium_with_no_premium_leaves_the_account_value():
    rates = load_iswl_rates(_single_premium_policy(), _config(), repo=_SinglePremiumSchema())
    result = apply_premium(20000.0, _single_premium_policy(), _config(), IllustrationRates(iswl=rates.iswl),
                           40, 0.0, 0.0, 0.0, gross_premium_override=0.0,
                           projection_date=date(2026, 10, 7))
    assert (result.gross_premium, result.net_premium, result.av_after_premium) == (0.0, 0.0, 20000.0)


def _bucket_source(rows):
    from types import SimpleNamespace

    buckets = [SimpleNamespace(csv_amount=row[1], interest_rate=row[2], raw_data={"IMPAIRED_IND": row[0]},
                               fund_id=row[3] if len(row) > 3 else "F1")
               for row in rows]
    pi = SimpleNamespace(company_code="26",
                         values=SimpleNamespace(get_fund_buckets=lambda current_only=True: buckets))
    return SimpleNamespace(plancode_config=_config(gint=0.04), pi=pi, plancode="B11SB200",
                           illustration_date=date(2026, 10, 3))


def test_iswl_interest_falls_back_to_impaired_flag_buckets(monkeypatch):
    """B11SB200 26/000321893: the only current bucket is F1 with IMPAIRED_IND 1 at 4.000%
    (its unloaned value; the collateral is in LH_FND_VAL_LOAN)."""
    from suiteview.illustration.core import iswl_rates
    from suiteview.illustration.core.illustration_policy_service import _current_interest_rate

    monkeypatch.setattr(iswl_rates, "iswl_current_credited_rate", lambda *a, **k: None)
    rate, source = _current_interest_rate(_bucket_source([("1", 12752.46, 4.5)]))
    assert rate == pytest.approx(0.045)
    assert "LH_POL_FND_VAL_TOT" in source
    rate, _ = _current_interest_rate(_bucket_source([("1", 100.0, 6.0), ("0", 900.0, 4.5)]))
    assert rate == pytest.approx(0.045)


def test_iswl_interest_skips_the_negative_gp_holding_fund(monkeypatch):
    """B71SP600 16867267: GP holds the -325.06 AV at 0%; I1 credits new money at 2%."""
    from suiteview.illustration.core import iswl_rates
    from suiteview.illustration.core.illustration_policy_service import _current_interest_rate

    monkeypatch.setattr(iswl_rates, "iswl_current_credited_rate", lambda *a, **k: None)
    rate, _ = _current_interest_rate(_bucket_source([("0", 0.0, 2.0, "I1"), ("0", -325.06, 0.0, "GP")]))
    assert rate == pytest.approx(0.04)  # floored at the test config's GINT 4%
    with pytest.raises(RateLookupError, match="hold no value"):
        _current_interest_rate(_bucket_source([("0", 0.0, 2.0, "I1"), ("0", -325.06, 0.0, "F2")]))

def test_rule_5_table_58_loads_flat_for_company_01_and_graded_for_company_26():
    fake = _SinglePremiumSchema(scr_rules="50", scr_table="58", scr_cells=("SCR_PCT",))
    basis = load_iswl_rates(_single_premium_policy(), _config(), repo=fake).iswl
    assert basis.surrender_charge_is_pct_of_av and not basis.surrender_charge_graded
    graded = load_iswl_rates(_single_premium_policy(company_code="26"), _config(), repo=fake).iswl
    assert graded.surrender_charge_is_pct_of_av and graded.surrender_charge_graded

def test_non_cvat_iswl_without_corridor_factors_fails_loudly():
    with pytest.raises(RateLookupError, match="no CORR corridor factors"):
        load_iswl_rates(_single_premium_policy(), _config(corridor_by_age=None), repo=_SinglePremiumSchema())


def test_monthly_coi_rate_basis_is_not_divided_by_12():
    """B11SP400 (DULCVCRU 2): CyberLife MD = 12 x the annual-basis result (E0080318 4.14 vs 0.35)."""
    annual = load_iswl_rates(_single_premium_policy(), _config(), repo=_SinglePremiumSchema())
    monthly = load_iswl_rates(_single_premium_policy(), _config(coi_rate_basis="Monthly"),
                              repo=_SinglePremiumSchema())
    assert monthly.coi[39] == pytest.approx(2.55)
    assert monthly.coi[39] == pytest.approx(12 * annual.coi[39])