"""The base band face folds in riders that band as base coverage (1U144A00)."""

from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
    RiderInfo,
)


def _policy(riders):
    return IllustrationPolicyData(
        plancode="1U144800",  # an IUL08-family base plancode
        segments=[CoverageSegment(face_amount=200_000.0, units=200.0, is_base=True)],
        riders=riders,
    )


def test_band_face_includes_base_banding_rider():
    policy = _policy([
        RiderInfo(plancode="1U144A00", face_amount=100_000.0, is_active=True),
    ])
    # Death-benefit face stays base-only; band face folds the rider in.
    assert policy.total_face == 200_000.0
    assert policy.band_specified_amount == 300_000.0


def test_band_face_ignores_ordinary_rider():
    policy = _policy([
        RiderInfo(plancode="1U999Z00", face_amount=100_000.0, is_active=True),
    ])
    assert policy.band_specified_amount == 200_000.0


def test_band_face_ignores_inactive_base_banding_rider():
    policy = _policy([
        RiderInfo(plancode="1U144A00", face_amount=100_000.0, is_active=False),
    ])
    assert policy.band_specified_amount == 200_000.0


def test_band_face_equals_total_face_without_riders():
    policy = _policy([])
    assert policy.band_specified_amount == policy.total_face == 200_000.0


def test_base_banding_rider_charges_on_policy_band():
    # illustration_policy_service assigns the base-banding rider the policy's
    # combined band; rate_loader must NOT re-derive it from the rider's own face.
    from suiteview.core.rates import Rates
    from suiteview.illustration.core.rate_loader import _load_rider_coi_rates

    rider = RiderInfo(plancode="1U144A00", face_amount=100_000.0, band=3, is_active=True)

    class _FakeRates:
        def get_band(self, _plancode, _face):
            return 2  # what the rider's OWN 100k face would give

        def get_coi(self, _plancode, _age, _sex, _cls, scale=1, band=1):
            assert band == 3  # policy band preserved, not re-derived to 2
            return [None, 0.1]

    _load_rider_coi_rates(_FakeRates(), rider)
    assert rider.band == 3


def test_ordinary_rider_rebands_on_own_face():
    from suiteview.illustration.core.rate_loader import _load_rider_coi_rates

    rider = RiderInfo(plancode="1U999Z00", face_amount=100_000.0, band=3, is_active=True)

    class _FakeRates:
        def get_band(self, _plancode, _face):
            return 2

        def get_coi(self, _plancode, _age, _sex, _cls, scale=1, band=1):
            assert band == 2  # ordinary rider re-derives from its own face
            return [None, 0.1]

    _load_rider_coi_rates(_FakeRates(), rider)
    assert rider.band == 2
