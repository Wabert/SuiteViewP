"""build_target_detail_snapshots exposes every base segment and every rider.

RERUN's MTP/CTP detail historically capped its per-coverage columns at three
slots and rolled all riders into a single hidden sum. A policy with many base
coverage segments (e.g. ten) therefore lost every segment past the third, and
rider targets (CTR/STR) never surfaced. The snapshot now emits one column per
base coverage segment and one column per active rider so the MTP/CTP groups
match the Monthly Deduction group.
"""
from __future__ import annotations

from suiteview.illustration.core.target_premium import (
    TargetPremiumResult,
    build_target_detail_snapshots,
)
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)


def _policy_with_segments(count: int) -> IllustrationPolicyData:
    return IllustrationPolicyData(
        face_amount=10_000.0 * count,
        segments=[
            CoverageSegment(coverage_phase=phase, face_amount=10_000.0)
            for phase in range(1, count + 1)
        ],
    )


def test_snapshot_emits_every_base_segment():
    policy = _policy_with_segments(10)
    result = TargetPremiumResult(
        mtp_by_coverage={phase: float(phase) for phase in range(1, 11)},
        ctp_by_coverage={phase: float(phase) * 1.2 for phase in range(1, 11)},
        mtp_rates_by_coverage={phase: 0.1 for phase in range(1, 11)},
        ctp_rates_by_coverage={phase: 0.12 for phase in range(1, 11)},
    )

    mtp, ctp = build_target_detail_snapshots(policy, result)

    for index in range(1, 11):
        assert f"MTP Cov {index}" in mtp
        assert f"CTP Cov {index}" in ctp
    assert mtp["MTP Cov 10"] == 10.0
    assert ctp["CTP Cov 10"] == 12.0


def test_snapshot_emits_one_column_per_rider():
    policy = _policy_with_segments(2)
    result = TargetPremiumResult(
        mtp_riders={"CTR": 7.8, "STR": 15.6},
        ctp_riders={"CTR": 9.0, "STR": 18.0},
    )

    mtp, ctp = build_target_detail_snapshots(policy, result)

    assert mtp["MTP Rider CTR"] == 7.8
    assert mtp["MTP Rider STR"] == 15.6
    assert ctp["CTP Rider CTR"] == 9.0
    assert ctp["CTP Rider STR"] == 18.0
    # The rolled-up total no longer replaces the per-rider columns.
    assert "Riders MTP" not in mtp
    assert "Riders CTP" not in ctp


def test_snapshot_always_emits_cov_1_without_segments():
    policy = IllustrationPolicyData(face_amount=100_000.0)
    result = TargetPremiumResult()

    mtp, ctp = build_target_detail_snapshots(policy, result)

    assert "MTP Cov 1" in mtp
    assert "CTP Cov 1" in ctp


def test_snapshot_emits_ffl_waiver_intermediates():
    policy = _policy_with_segments(1)
    result = TargetPremiumResult(
        ffl_min_base=120.0,
        ffl_min_base_table=60.0,
        ffl_min_base_flat=5.0,
        ffl_pwoc_basis=185.42,
        ffl_pwot_basis=2012.40,
        ffl_pwot_factor=0.08695,
    )

    mtp, _ctp = build_target_detail_snapshots(policy, result)

    assert mtp["Min_Base"] == 120.0
    assert mtp["Min_Base_Table"] == 60.0
    assert mtp["Min_Base_Flat"] == 5.0
    assert mtp["PWoC_MinBasis"] == 185.42
    assert mtp["PWoT_MinBasis"] == 2012.40


def test_snapshot_omits_ffl_intermediates_for_non_ffl():
    policy = _policy_with_segments(1)
    result = TargetPremiumResult(mtp_by_coverage={1: 100.0})

    mtp, _ctp = build_target_detail_snapshots(policy, result)

    assert "Min_Base" not in mtp
    assert "PWoC_MinBasis" not in mtp
    assert "PWoT_MinBasis" not in mtp

