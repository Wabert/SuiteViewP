"""Offline smoke test — validates the full pipeline with mock rates."""
from datetime import date

from suiteview.illustration import IllustrationPolicyData, CoverageSegment
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.plancode_config import load_plancode


def main():
    policy = IllustrationPolicyData(
        policy_number="TEST001",
        plancode="1U143900",
        issue_date=date(2016, 10, 27),
        issue_age=50,
        attained_age=59,
        rate_sex="M",
        rate_class="N",
        face_amount=90000.0,
        units=90.0,
        db_option="A",
        band=2,
        account_value=11936.84,
        modal_premium=150.0,
        annual_premium=1800.0,
        billing_frequency=1,
        premiums_paid_to_date=10800.0,
        premiums_ytd=900.0,
        guaranteed_interest_rate=0.03,
        current_interest_rate=0.0425,
        policy_year=10,
        policy_month=6,
        duration=114,
        valuation_date=date(2025, 4, 14),
        maturity_age=121,
        def_of_life_ins="GPT",
        ctp=1242.0,
        segments=[CoverageSegment(
            coverage_phase=1, is_base=True,
            issue_date=date(2016, 10, 27),
            issue_age=50, rate_sex="M", rate_class="N",
            face_amount=90000.0, original_face_amount=90000.0,
            units=90.0, band=2,
        )],
    )

    config = load_plancode("1U143900")

    # Mock rates: 1-indexed, 200 durations
    mock_rates = IllustrationRates(
        coi=[None] + [0.50] * 200,
        epu=[None] + [0.10] * 200,
        scr=[None] + [28.76] * 200,
        mfee=[None] + [5.0] * 200,
        gint=[None] + [0.03] * 200,
        tpp=[None] + [0.06] * 200,
        epp=[None] + [0.02] * 200,
        bonus_dur=[None] + [0.005] * 200,
        bonus_av=[None] + [0.0025] * 200,
        corridor=[0.0] * 60 + [1.34] * 100,
        mtp=10.0,
        ctp=13.80,
    )

    engine = IllustrationEngine()

    state = MonthlyState(
        date=policy.valuation_date,
        policy_year=10, policy_month=6, duration=114,
        attained_age=59,
        av_end_of_month=11936.84,
        premiums_ytd=900.0,
        premiums_to_date=10800.0,
        cost_basis=10800.0,
    )

    result = engine.process_month(state, policy, config, mock_rates)

    print(f"Duration:   {result.duration}")
    print(f"Yr/Mo:      {result.policy_year}/{result.policy_month}")
    print(f"Age:        {result.attained_age}")
    print(f"Date:       {result.date}")
    print(f"Gross Prem: ${result.gross_premium:,.2f}")
    print(f"Under Tgt:  ${result.prem_under_target:,.2f}")
    print(f"Over Tgt:   ${result.prem_over_target:,.2f}")
    print(f"Tgt Load:   ${result.target_load:,.2f}")
    print(f"Excess Ld:  ${result.excess_load:,.2f}")
    print(f"Net Prem:   ${result.net_premium:,.2f}")
    print(f"AV aft Prm: ${result.av_after_premium:,.2f}")
    print(f"NAR AV:     ${result.nar_av:,.2f}")
    print(f"Std DB:     ${result.standard_db:,.2f}")
    print(f"Gross DB:   ${result.gross_db:,.2f}")
    print(f"Disc DB:    ${result.discounted_db:,.2f}")
    print(f"NAR:        ${result.nar:,.2f}")
    print(f"COI Rate:   {result.coi_rate:.5f}")
    print(f"COI:        ${result.coi_charge:,.2f}")
    print(f"EPU:        ${result.epu_charge:,.2f}")
    print(f"MFEE:       ${result.mfee_charge:,.2f}")
    print(f"Tot Ded:    ${result.total_deduction:,.2f}")
    print(f"AV aft Ded: ${result.av_after_deduction:,.2f}")
    print(f"Eff Rate:   {result.effective_annual_rate:.4f}")
    print(f"Mo Rate:    {result.monthly_interest_rate:.7f}")
    print(f"Interest:   ${result.interest_credited:,.2f}")
    print(f"End AV:     ${result.av_end_of_month:,.2f}")
    print(f"SCR:        ${result.surrender_charge:,.2f}")
    print(f"Surr Val:   ${result.surrender_value:,.2f}")
    print(f"End DB:     ${result.ending_db:,.2f}")
    print(f"Lapsed:     {result.lapsed}")
    print()

    # Verify key values
    assert result.duration == 115
    assert result.policy_year == 10
    assert result.policy_month == 7
    assert result.gross_premium == 150.0
    assert result.standard_db == 90000.0
    assert not result.lapsed
    assert result.av_end_of_month > 0

    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
