import pytest
from datetime import date

from suiteview.illustration.core.monthly_deduction import calculate_deduction
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.models.policy_data import BenefitInfo, CoverageSegment, IllustrationPolicyData, RiderInfo


def test_death_benefit_discount_uses_plancode_dbd_not_policy_interest_rate():
    policy = IllustrationPolicyData(
        plancode="1U135D00",
        db_option="A",
        face_amount=100_000.0,
        account_value=10_000.0,
        guaranteed_interest_rate=0.03,
        current_interest_rate=0.03,
        segments=[CoverageSegment(face_amount=100_000.0, units=100.0)],
    )
    config = PlancodeConfig(
        plancode="1U135D00",
        dbd=0.04,
        gint=0.03,
        corridor_code=None,
        epu_code="0",
        mfee="0",
    )

    result = calculate_deduction(
        10_000.0,
        policy,
        config,
        IllustrationRates(),
        rate_year=1,
        attained_age=45,
        premiums_to_date=0.0,
    )

    expected_discount_factor = round((1.0 + 0.04) ** (1.0 / 12.0), 7)
    expected_discounted_db = 100_000.0 / expected_discount_factor
    assert result.discounted_db_cov1 == pytest.approx(expected_discounted_db)
    assert result.discounted_db_cov1 != pytest.approx(100_000.0 / round((1.0 + 0.03) ** (1.0 / 12.0), 7))


def test_corridor_code_two_uses_alternate_corridor_curve():
    policy = IllustrationPolicyData(
        plancode="1U130N2X",
        db_option="A",
        face_amount=100_000.0,
        account_value=100_000.0,
        segments=[CoverageSegment(face_amount=100_000.0, units=100.0)],
    )
    config = PlancodeConfig(
        plancode="1U130N2X",
        dbd=0.0,
        gint=0.0,
        corridor_code=2,
        epu_code="0",
        mfee="0",
    )

    result = calculate_deduction(
        100_000.0,
        policy,
        config,
        IllustrationRates(),
        rate_year=1,
        attained_age=45,
        premiums_to_date=0.0,
    )

    assert result.corridor_rate == pytest.approx(1.35)
    assert result.gross_db == pytest.approx(135_000.0)
    assert result.corr_amount == pytest.approx(35_000.0)


def test_plancode_loader_reads_corridor_code_from_table():
    config = load_plancode("1U130M29")

    assert config.corridor_code == 2


def _minimal_policy_with_riders_and_benefits(*, riders=None, benefits=None):
    return IllustrationPolicyData(
        plancode="1U135D00",
        db_option="A",
        face_amount=100_000.0,
        account_value=10_000.0,
        segments=[CoverageSegment(face_amount=100_000.0, units=100.0)],
        riders=riders or [],
        benefits=benefits or [],
    )


def _minimal_config_and_rates():
    config = PlancodeConfig(
        plancode="1U135D00",
        dbd=0.04,
        gint=0.03,
        corridor_code=None,
        epu_code="0",
        mfee="0",
        table_rating_factor=0.0,
    )
    rates = IllustrationRates()
    return config, rates


def test_rider_charge_stops_on_rider_maturity_date():
    rider = RiderInfo(
        plancode="LTR",
        occurrence=1,
        face_amount=50_000.0,
        units=50.0,
        maturity_date=date(2041, 9, 1),
        premium_rate=2.0,
        is_active=True,
    )
    policy = _minimal_policy_with_riders_and_benefits(riders=[rider])
    config, rates = _minimal_config_and_rates()

    before_maturity = calculate_deduction(
        10_000.0,
        policy,
        config,
        rates,
        rate_year=1,
        attained_age=45,
        premiums_to_date=0.0,
        projection_date=date(2041, 8, 1),
    )
    at_maturity = calculate_deduction(
        10_000.0,
        policy,
        config,
        rates,
        rate_year=1,
        attained_age=45,
        premiums_to_date=0.0,
        projection_date=date(2041, 9, 1),
    )
    after_maturity = calculate_deduction(
        10_000.0,
        policy,
        config,
        rates,
        rate_year=1,
        attained_age=45,
        premiums_to_date=0.0,
        projection_date=date(2041, 10, 1),
    )

    assert before_maturity.rider_charges == pytest.approx(100.0)
    assert at_maturity.rider_charges == pytest.approx(0.0)
    assert after_maturity.rider_charges == pytest.approx(0.0)


def test_benefit_charge_stops_on_benefit_cease_date():
    benefit = BenefitInfo(
        benefit_type="2",
        benefit_subtype="1",
        benefit_amount=25_000.0,
        units=25.0,
        cease_date=date(2041, 9, 1),
        coi_rate=1.5,
        is_active=True,
    )
    policy = _minimal_policy_with_riders_and_benefits(benefits=[benefit])
    config, rates = _minimal_config_and_rates()

    before_cease = calculate_deduction(
        10_000.0,
        policy,
        config,
        rates,
        rate_year=1,
        attained_age=45,
        premiums_to_date=0.0,
        projection_date=date(2041, 8, 1),
    )
    at_cease = calculate_deduction(
        10_000.0,
        policy,
        config,
        rates,
        rate_year=1,
        attained_age=45,
        premiums_to_date=0.0,
        projection_date=date(2041, 9, 1),
    )

    assert before_cease.benefit_charges == pytest.approx(37.5)
    assert at_cease.benefit_charges == pytest.approx(0.0)


# ── Ratchet banding (RERUN CalcEngine PP-QX) ─────────────────────────────────
# NAR up to the band break is charged at the band-1 COI rate; the excess at the
# band-2 rate (vs. the regular calc, where all NAR uses one band's rate). Only
# the earliest UL plans (~1983, e.g. 1U130N2X) are coded this way.

def _ratchet_config(*, rachet_banding=True):
    # dbd=0 → monthly discount factor is exactly 1.0, so discounted DB == face
    # and the NAR math stays clean and exact for assertions.
    return PlancodeConfig(
        plancode="1U130N2X",
        dbd=0.0,
        gint=0.0,
        corridor_code=None,
        epu_code="0",
        mfee="0",
        table_rating_factor=0.0,
        rachet_banding=rachet_banding,
    )


def test_ratchet_single_segment_splits_nar_at_band_break():
    # One segment, 100k NAR, break at 50k: 50k @ band-1 (10/1000) + 50k @ band-2
    # (4/1000) = 500 + 200 = 700.
    policy = IllustrationPolicyData(
        plancode="1U130N2X",
        db_option="A",
        face_amount=100_000.0,
        account_value=0.0,
        segments=[CoverageSegment(coverage_phase=1, face_amount=100_000.0, units=100.0, band=2)],
    )
    config = _ratchet_config()
    rates = IllustrationRates(
        segment_coi_band1={1: [0.0, 10.0]},
        segment_coi_band2={1: [0.0, 4.0]},
        band_break=50_000.0,
    )

    result = calculate_deduction(
        0.0, policy, config, rates,
        rate_year=1, attained_age=45, premiums_to_date=0.0,
    )

    assert result.ratchet_active is True
    assert result.band_break == 50_000.0
    assert result.coi_band1_nar_by_coverage["cov1"] == pytest.approx(50_000.0)
    assert result.coi_band2_nar_by_coverage["cov1"] == pytest.approx(50_000.0)
    assert result.coi_band1_rates_by_coverage["cov1"] == pytest.approx(10.0)
    assert result.coi_band2_rates_by_coverage["cov1"] == pytest.approx(4.0)
    assert result.coi_charge == pytest.approx(700.0)
    assert result.total_coi_charge == pytest.approx(700.0)


def test_ratchet_fills_band1_across_segments_fifo():
    # Three 30k segments (90k total NAR), break at 50k. Band-1 fills FIFO:
    # seg1 30k (all band 1), seg2 20k band 1 / 10k band 2, seg3 30k (all band 2).
    # Charges: 300 + (200+40) + 120 = 660.
    segs = [
        CoverageSegment(coverage_phase=i, face_amount=30_000.0, units=30.0, band=2)
        for i in (1, 2, 3)
    ]
    policy = IllustrationPolicyData(
        plancode="1U130N2X",
        db_option="A",
        face_amount=90_000.0,
        account_value=0.0,
        segments=segs,
    )
    config = _ratchet_config()
    rates = IllustrationRates(
        segment_coi_band1={1: [0.0, 10.0], 2: [0.0, 10.0], 3: [0.0, 10.0]},
        segment_coi_band2={1: [0.0, 4.0], 2: [0.0, 4.0], 3: [0.0, 4.0]},
        band_break=50_000.0,
    )

    result = calculate_deduction(
        0.0, policy, config, rates,
        rate_year=1, attained_age=45, premiums_to_date=0.0,
    )

    assert result.ratchet_active is True
    assert result.coi_band1_nar_by_coverage == pytest.approx(
        {"cov1": 30_000.0, "cov2": 20_000.0, "cov3": 0.0, "corr": 0.0}
    )
    assert result.coi_band2_nar_by_coverage == pytest.approx(
        {"cov1": 0.0, "cov2": 10_000.0, "cov3": 30_000.0, "corr": 0.0}
    )
    assert result.coi_charges_by_coverage["cov1"] == pytest.approx(300.0)
    assert result.coi_charges_by_coverage["cov2"] == pytest.approx(240.0)
    assert result.coi_charges_by_coverage["cov3"] == pytest.approx(120.0)
    assert result.coi_charge == pytest.approx(660.0)


def test_ratchet_disabled_uses_regular_single_band_coi():
    # Same 100k-NAR policy, but rachet_banding=False: the band schedules are
    # ignored and the regular single-band COI (6/1000 on all 100k = 600) applies.
    policy = IllustrationPolicyData(
        plancode="1U130N2X",
        db_option="A",
        face_amount=100_000.0,
        account_value=0.0,
        segments=[CoverageSegment(coverage_phase=1, face_amount=100_000.0, units=100.0, band=2)],
    )
    config = _ratchet_config(rachet_banding=False)
    rates = IllustrationRates(
        coi=[0.0, 6.0],
        segment_coi={1: [0.0, 6.0]},
        # Band schedules present but must be ignored when the flag is off.
        segment_coi_band1={1: [0.0, 10.0]},
        segment_coi_band2={1: [0.0, 4.0]},
        band_break=50_000.0,
    )

    result = calculate_deduction(
        0.0, policy, config, rates,
        rate_year=1, attained_age=45, premiums_to_date=0.0,
    )

    assert result.ratchet_active is False
    assert result.coi_charge == pytest.approx(600.0)
    assert result.coi_band1_nar_by_coverage == {}


def test_ratchet_inactive_when_no_band_break():
    # Flag on but BANDSPECS gave no band-2 break (band_break=0): fall back to the
    # regular path rather than charging everything at band 1.
    policy = IllustrationPolicyData(
        plancode="1U130N2X",
        db_option="A",
        face_amount=100_000.0,
        account_value=0.0,
        segments=[CoverageSegment(coverage_phase=1, face_amount=100_000.0, units=100.0, band=1)],
    )
    config = _ratchet_config(rachet_banding=True)
    rates = IllustrationRates(
        coi=[0.0, 6.0],
        segment_coi={1: [0.0, 6.0]},
        segment_coi_band1={1: [0.0, 10.0]},
        segment_coi_band2={1: [0.0, 4.0]},
        band_break=0.0,
    )

    result = calculate_deduction(
        0.0, policy, config, rates,
        rate_year=1, attained_age=45, premiums_to_date=0.0,
    )

    assert result.ratchet_active is False
    assert result.coi_charge == pytest.approx(600.0)