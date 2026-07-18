"""Guideline-basis charge sourcing (7702 rule): guaranteed COI, statutory
interest, CURRENT expenses.

Pins the expense basis of ``build_guideline_basis`` (and ``load_rates``):

* Expenses (EPU / fee / loads) are ALWAYS the current scale — a current EPU
  schedule that ceases at year N ceases in the guideline too, even though the
  guaranteed-scale schedule persists.
* Rider charge streams (CTR / spouse term) load the guideline with their
  CURRENT COI — the same ``rates.rider_rates`` schedules the deduction uses.
* ADB (benefit type 1) is not a QAB: its charges never enter the guideline.
* The base COI zeroes from the premium-cease age on and the policy fee from
  the maturity age on (RERUN Guideline_Premiums COIR / Fee gates).

Verified against RERUN Guideline_Premiums on U0356726 (DBO B->A @yr31).
"""
from datetime import date

from suiteview.illustration.core import rate_loader
from suiteview.illustration.core.monthly_guideline import build_guideline_basis
from suiteview.illustration.core.rate_loader import IllustrationRates, load_rates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    BenefitInfo,
    CoverageSegment,
    IllustrationPolicyData,
    RiderInfo,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


def _policy(*, benefits=None, riders=None) -> IllustrationPolicyData:
    seg = CoverageSegment(
        coverage_phase=1,
        issue_date=date(2000, 6, 1),
        issue_age=40,
        rate_sex="M",
        rate_class="N",
        face_amount=50_000.0,
        original_face_amount=50_000.0,
        band=1,
        original_band=1,
    )
    policy = IllustrationPolicyData(
        plancode="TEST0001",
        issue_date=date(2000, 6, 1),
        issue_age=40,
        db_option="A",
        mtp=30.0,
        ctp=360.0,
    )
    policy.segments = [seg]
    policy.face_amount = seg.face_amount
    policy.benefits = benefits or []
    policy.riders = riders or []
    return policy


def _config(**overrides) -> PlancodeConfig:
    defaults = dict(
        plancode="TEST0001",
        mfee="3.25",
        epu_code="Table",
        premium_load="0.05",
        premium_cease_age=121,
        maturity_age=121,
        table_rating_factor=0.25,
    )
    defaults.update(overrides)
    return PlancodeConfig(**defaults)


def _rates(*, epu=None, coi=None, rider_rates=None, benefit_coi=None) -> IllustrationRates:
    coi = coi if coi is not None else [None] + [1.0] * 80
    epu = epu if epu is not None else [None] + [0.0] * 80
    return IllustrationRates(
        coi=coi,
        segment_coi={1: coi},
        epu=epu,
        segment_epu={1: epu},
        rider_rates=rider_rates or {},
        benefit_coi=benefit_coi or {},
    )


# ── Expense basis: CURRENT schedules, including duration cessation ─────────


def test_guideline_epu_follows_current_schedule_cessation():
    """Current EPU ceases at year 11 — the guideline must cease with it."""
    # Current-scale EPU: charged years 1-10, zero from year 11 on. (The
    # guaranteed-scale schedule persists — it must never be consulted.)
    current_epu = [None] + [0.3] * 10 + [0.0] * 70
    basis = build_guideline_basis(
        _policy(), _config(), _rates(epu=current_epu),
        attained_age=40, as_of=date(2000, 6, 1),
    )
    # Year 10 (months 108..119) charges; year 11+ (month 120 on) does not.
    per_month = 0.3 * 50_000.0 / 1000.0
    assert abs(basis.months[119].epu - per_month) < 1e-9
    assert basis.months[120].epu == 0.0
    assert all(gm.epu == 0.0 for gm in basis.months[120:])


def test_load_rates_uses_current_scale_for_expenses_with_guaranteed_coi():
    """load_rates(coi_scale=0): COI is scale 0, EPU/MFEE/TPP/EPP stay scale 1."""

    class _FakeRates:
        def __init__(self):
            self.calls = []

        def get_rates(self, rate_type, plancode, issue_age=None, sex=None,
                      rateclass=None, scale=1, band=None, **kwargs):
            self.calls.append((rate_type, scale))
            # Distinct arrays per scale so a wrong-scale read is visible.
            return [None, 100.0 + scale]

        def get_band(self, plancode, face):
            return 1

        def get_mtp(self, *a, **k):
            return 0.0

        def get_ctp(self, *a, **k):
            return 0.0

    fake = _FakeRates()
    monkey_rates = lambda: fake  # noqa: E731

    original = rate_loader.Rates
    rate_loader.Rates = monkey_rates
    try:
        rates = load_rates(_policy(), _config(), coi_scale=0)
    finally:
        rate_loader.Rates = original

    scale_by_type = {}
    for rate_type, scale in fake.calls:
        scale_by_type.setdefault(rate_type, set()).add(scale)
    assert scale_by_type["COI"] == {0}, "guideline COI must be the guaranteed scale"
    for expense in ("EPU", "MFEE", "TPP", "EPP"):
        assert scale_by_type[expense] == {1}, f"{expense} must stay the current scale"
    assert rates.coi[1] == 100.0        # scale 0
    assert rates.epu[1] == 101.0        # scale 1


# ── Benefit scope: ADB out, waiver in ──────────────────────────────────────


def test_guideline_excludes_adb_benefit_charges():
    policy = _policy(benefits=[
        BenefitInfo(benefit_type="1", benefit_subtype="1", units=50.0, is_active=True),
        BenefitInfo(benefit_type="3", benefit_subtype="9", units=50.0, is_active=True),
    ])
    rates = _rates(benefit_coi={
        "11": [None] + [0.09] * 80,   # ADB — must NOT load the guideline
        "39": [None] + [0.10] * 80,   # PW — charges the monthly MTP basis
    })
    basis = build_guideline_basis(
        policy, _config(), rates, attained_age=40, as_of=date(2000, 6, 1))
    gm = basis.months[0]
    assert "Benefit 1 1" not in gm.benefit_charge_detail
    assert "PW (Waiver)" in gm.benefit_charge_detail
    # PW = trunc2(rate x monthly MTP) only — no ADB contribution.
    assert abs(gm.benefit_charges - 3.0) < 1e-9   # 0.10 x 30.00


# ── Rider charges: current COI stream, active-window gated ─────────────────


def test_guideline_includes_rider_current_coi_and_cease():
    rider = RiderInfo(
        coverage_phase=2,
        occurrence=1,
        plancode="TESTCTR1",
        issue_date=date(2000, 6, 1),
        issue_age=40,
        rate_sex="M",
        rate_class="N",
        face_amount=10_000.0,
        units=10.0,
        maturity_date=date(2010, 6, 1),   # ceases at the year-11 anniversary
        is_active=True,
    )
    rates = _rates(rider_rates={rider.export_key: [None] + [0.585] * 80})
    basis = build_guideline_basis(
        _policy(riders=[rider]), _config(), rates,
        attained_age=40, as_of=date(2000, 6, 1),
    )
    # Years 1-10: 10 units x 0.585 = 5.85/month; from the cease anniversary: 0.
    assert abs(basis.months[0].rider_charges - 5.85) < 1e-9
    assert abs(basis.months[119].rider_charges - 5.85) < 1e-9
    assert basis.months[120].rider_charges == 0.0


def test_guideline_excludes_rider_ceased_at_change_row():
    """A rider already ceased at the change date is out of the WHOLE solve."""
    rider = RiderInfo(
        coverage_phase=2,
        occurrence=1,
        plancode="TESTCTR1",
        issue_date=date(2000, 6, 1),
        issue_age=40,
        rate_sex="M",
        rate_class="N",
        face_amount=10_000.0,
        units=10.0,
        maturity_date=date(2010, 6, 1),
        is_active=True,
    )
    rates = _rates(rider_rates={rider.export_key: [None] + [0.585] * 80})
    basis = build_guideline_basis(
        _policy(riders=[rider]), _config(), rates,
        attained_age=55, as_of=date(2015, 6, 1),
        active_as_of=date(2015, 6, 1),
    )
    assert all(gm.rider_charges == 0.0 for gm in basis.months)


# ── Age gates: COI at premium-cease, fee at maturity, EPU persists ─────────


def test_guideline_coi_and_fee_cease_at_config_ages_epu_persists():
    current_epu = [None] + [0.3] * 80
    basis = build_guideline_basis(
        _policy(),
        _config(premium_cease_age=95, maturity_age=95, mfee="3.25"),
        _rates(epu=current_epu),
        attained_age=40, as_of=date(2000, 6, 1),
    )
    by_age = {}
    for gm in basis.months:
        by_age.setdefault(gm.attained_age, gm)
    assert by_age[94].coi_rate > 0.0
    assert by_age[94].fee == 3.25
    assert by_age[95].coi_rate == 0.0     # COIR: IF(age>=sPremiumCeaseAge,0,..)
    assert by_age[95].fee == 0.0          # Fee:  IF(age>=sMaturityAge,0,..)
    assert by_age[99].coi_rate == 0.0
    # EPU has no age gate — it charges to the deemed maturity.
    assert by_age[99].epu > 0.0
