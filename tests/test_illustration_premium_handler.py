"""apply_premium — TPP/EPP load-rate surfacing and load math."""
from suiteview.illustration.core.premium_handler import apply_premium
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def _rates(tpp: float, epp: float, years: int = 5) -> IllustrationRates:
    rates = IllustrationRates()
    rates.tpp = [tpp] * years
    rates.epp = [epp] * years
    return rates


def _config(premium_load="Table") -> PlancodeConfig:
    return PlancodeConfig(plancode="TESTPLAN", premium_load=premium_load)


def _policy(modal_premium: float = 100.0, ctp: float = 1000.0) -> IllustrationPolicyData:
    return IllustrationPolicyData(modal_premium=modal_premium, ctp=ctp)


def test_tpp_epp_rates_surface_with_a_premium():
    result = apply_premium(
        av_beginning=0.0, policy=_policy(), config=_config(),
        rates=_rates(0.08, 0.04), rate_year=1,
        premiums_ytd=0.0, premiums_to_date=0.0, cost_basis=0.0,
    )
    assert result.tpp_rate == 0.08
    assert result.epp_rate == 0.04
    assert abs(result.target_load - 100.0 * 0.08) < 1e-9


def test_tpp_epp_rates_surface_even_with_no_premium():
    # The rates must be reported for display even in months with no premium.
    result = apply_premium(
        av_beginning=0.0, policy=_policy(), config=_config(),
        rates=_rates(0.08, 0.04), rate_year=1,
        premiums_ytd=0.0, premiums_to_date=0.0, cost_basis=0.0,
        gross_premium_override=0.0,
    )
    assert result.gross_premium == 0.0
    assert result.tpp_rate == 0.08
    assert result.epp_rate == 0.04


def test_flat_percentage_load_reported_as_rate():
    result = apply_premium(
        av_beginning=0.0, policy=_policy(), config=_config(premium_load="0.05"),
        rates=_rates(0.0, 0.0), rate_year=1,
        premiums_ytd=0.0, premiums_to_date=0.0, cost_basis=0.0,
    )
    assert result.tpp_rate == 0.05
    assert result.epp_rate == 0.05
    assert abs(result.target_load - 100.0 * 0.05) < 1e-9
