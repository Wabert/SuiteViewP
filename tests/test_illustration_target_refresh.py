"""Target refresh in projections: COI-priced CTP follows the COI; the MTP freezes at the MAP end."""
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.target_premium import (
    TargetPremiumResult,
    coi_table_target_signature,
)
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData


class _Convention:
    refresh_targets = True


def _ctx(*, map_end, state_date, signature_years, changes=()):
    policy = IllustrationPolicyData(
        plancode="1S135M0X", issue_date=date(1985, 7, 16), map_cease_date=map_end,
        mtp=13.08, ctp=256.59,
    )
    state = SimpleNamespace(
        date=state_date, mtp_detail={"MTP": 13.08}, ctp_detail={"CTP": 256.59},
        accumulated_mtp=0.0, gp_exception_mode=False,
    )
    ctx = SimpleNamespace(
        state=state, policy=policy, config=SimpleNamespace(safety_net_years=lambda _issue_age: 5),
        policy_changes=list(changes),
    )
    return ctx, policy


def _work(month_date):
    return SimpleNamespace(
        month_date=month_date, wd=SimpleNamespace(face_decrease=0.0), next_year=42,
    )


@pytest.fixture
def stubbed(monkeypatch):
    calls = []

    def compute(policy, _config, as_of=None):
        calls.append(as_of)
        return TargetPremiumResult(mtp_annual=157.0, ctp_annual=270.0)

    monkeypatch.setattr(calc_engine, "compute_target_premiums", compute)
    monkeypatch.setattr(
        calc_engine, "build_target_detail_snapshots",
        lambda _p, r: ({"MTP": r.mtp_annual / 12}, {"CTP": r.ctp_annual}),
    )
    monkeypatch.setattr(
        calc_engine, "coi_table_target_signature",
        lambda _policy, as_of: ((1, 42 if as_of >= date(2026, 7, 16) else 41),),
    )
    monkeypatch.setattr(
        calc_engine, "target_actives_signature", lambda *_a: ("same",))
    return calls


def test_ctp_follows_the_coi_when_a_coverage_year_turns_and_mtp_stays_frozen(stubbed):
    ctx, policy = _ctx(map_end=date(1986, 7, 16), state_date=date(2026, 6, 16), signature_years=None)
    work = _work(date(2026, 7, 16))
    calc_engine.refresh_targets(ctx, _Convention(), work)
    assert policy.ctp == 270.0
    assert policy.mtp == 13.08                  # MAP ended 1986: prior value kept
    assert work.ctp_detail == {"CTP": 270.0}
    assert work.mtp_detail == {"MTP": 13.08}
    assert stubbed == [date(2026, 7, 16)]


def test_mtp_also_refreshes_inside_the_map_period(stubbed):
    ctx, policy = _ctx(map_end=date(2030, 7, 16), state_date=date(2026, 6, 16), signature_years=None)
    work = _work(date(2026, 7, 16))
    calc_engine.refresh_targets(ctx, _Convention(), work)
    assert policy.ctp == 270.0
    assert policy.mtp == pytest.approx(157.0 / 12)
    assert work.mtp_detail == {"MTP": 157.0 / 12}


def test_policy_change_after_the_map_end_still_recomputes_the_mtp(stubbed):
    ctx, policy = _ctx(map_end=date(1986, 7, 16), state_date=date(2026, 6, 16),
                       signature_years=None, changes=[object()])
    work = _work(date(2026, 7, 16))
    calc_engine.refresh_targets(ctx, _Convention(), work)
    assert work.mtp_detail == {"MTP": 157.0 / 12}


def test_no_recompute_inside_a_coverage_year(stubbed):
    ctx, policy = _ctx(map_end=date(1986, 7, 16), state_date=date(2026, 7, 16), signature_years=None)
    work = _work(date(2026, 8, 16))
    calc_engine.refresh_targets(ctx, _Convention(), work)
    assert stubbed == []
    assert policy.ctp == 256.59
    assert work.ctp_detail == {"CTP": 256.59}


def test_signature_is_empty_without_a_table_rated_segment():
    policy = IllustrationPolicyData(
        plancode="X", segments=[CoverageSegment(face_amount=1000, table_rating=0)])
    assert coi_table_target_signature(policy, date(2026, 1, 1)) == ()
