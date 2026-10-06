"""Development-only IUL segment ("bucket") crediting — core/iul_segments.py.

Hand-built cases follow the IUL14 Series product specification: sweep account
minimum, sweep of the excess by allocation, one-year segments credited only at
maturity, maturity refill of the sweep then renewal, and the Sweep -> Fixed ->
IS -> IC -> IF -> IX deduction hierarchy with LIFO segments.
"""
from datetime import date

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine, ProjectionTiming
from suiteview.illustration.core.iul_segments import (
    IndexSegment,
    SegmentAccounts,
    SegmentCreditingContext,
    SegmentMonth,
    build_segment_context,
    normalized_allocations,
    segment_hierarchy,
)
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.input_set import IllustrationOptions
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    FundSegmentValue,
    IllustrationPolicyData,
)

IUL14_PLANCODE = "1U145500"
_QT_APP = None


def _context(**overrides) -> SegmentCreditingContext:
    kwargs = dict(
        product="IUL14",
        hierarchy=("IS", "IC", "IF", "IX"),
        allocations={"U1": 0.25, "IX": 0.75},
        index_rates={"IS": 0.05, "IC": 0.055, "IF": 0.06, "IX": 0.0623},
        asset_charges={"IS": 0.0, "IC": 0.0, "IF": 0.0, "IX": 0.0},
        declared_rate=0.035,
        guaranteed_basis=False,
    )
    kwargs.update(overrides)
    return SegmentCreditingContext(**kwargs)


def _segment(segment_id, fund, start, value, rate=0.0623, slot=1):
    return IndexSegment(
        segment_id=segment_id, fund_id=fund, start_date=start,
        maturity_date=date(start.year + 1, start.month, start.day),
        value=value, rate=rate, slot=slot)


# ── Pure account mechanics ────────────────────────────────────


def test_iul14_hierarchy_and_unsupported_products():
    assert segment_hierarchy("IUL14") == ("IS", "IC", "IF", "IX")
    assert segment_hierarchy("IUL14U(NY)") == ("IS", "IC", "IF", "IX")
    assert segment_hierarchy("IUL19") is None


def test_allocations_normalize_percent_and_default_to_ix():
    assert normalized_allocations({"U1": 25, "IX": 75, "SW": 0}) == {"U1": 0.25, "IX": 0.75}
    assert normalized_allocations({}) == {"IX": 1.0}


def test_draw_follows_hierarchy_newest_segment_first():
    accounts = SegmentAccounts(
        sweep=100.0, fixed=50.0,
        segments=(
            _segment(1, "IX", date(2026, 1, 1), 300.0),
            _segment(2, "IX", date(2026, 3, 1), 200.0),
            _segment(3, "IS", date(2026, 2, 1), 40.0),
        ),
        next_segment_id=4)
    month = SegmentMonth(_context(), accounts, date(2026, 6, 1), 6)
    month.draw(500.0, "Monthly deduction")
    by_id = {seg.segment_id: seg.value for seg in month.segments}
    # Sweep 100, Fixed 50, IS 40 (ahead of IX), then IX newest (id 2) 200, then id 1 110.
    assert month.sweep == 0.0
    assert month.fixed == 0.0
    assert by_id == {1: pytest.approx(190.0), 2: 0.0, 3: 0.0}
    assert month.total == pytest.approx(190.0)


def test_draw_beyond_accounts_takes_sweep_negative():
    month = SegmentMonth(_context(), SegmentAccounts(sweep=10.0), date(2026, 6, 1), 6)
    month.draw(25.0, "Monthly deduction")
    assert month.sweep == pytest.approx(-15.0)
    month.deposit(40.0, "Premium")
    assert month.sweep == pytest.approx(25.0)


def test_sweep_moves_only_excess_over_minimum_by_allocation():
    month = SegmentMonth(_context(), SegmentAccounts(sweep=1_500.0, sweep_min=600.0),
                         date(2026, 6, 1), 6)
    month.sweep_out()
    assert month.sweep == pytest.approx(600.0)
    assert month.fixed == pytest.approx(225.0)
    [segment] = month.segments
    assert (segment.fund_id, segment.start_date, segment.slot) == ("IX", date(2026, 6, 1), 6)
    assert segment.value == pytest.approx(675.0)
    assert segment.maturity_date == date(2027, 6, 1)
    assert segment.rate == pytest.approx(0.0623)


def test_maturity_refills_sweep_then_renews_with_this_months_sweep():
    accounts = SegmentAccounts(
        sweep=100.0, sweep_min=500.0,
        segments=(
            _segment(1, "IX", date(2025, 6, 1), 1_000.0, rate=0.06),
            _segment(2, "IX", date(2025, 7, 1), 800.0),
        ),
        next_segment_id=3)
    month = SegmentMonth(_context(allocations={"IX": 1.0}), accounts, date(2026, 6, 1), 1)
    interest = month.mature(bonus_rate=0.0)
    assert interest == pytest.approx(60.0)
    # 1,060 matured: 400 refills the sweep to its minimum, 660 renews.
    assert month.sweep == pytest.approx(500.0)
    renewal = [s for s in month.segments if s.start_date == date(2026, 6, 1)]
    assert len(renewal) == 1 and renewal[0].value == pytest.approx(660.0)
    # A premium arrives, then the sweep's excess joins the same new segment.
    month.deposit(300.0, "Premium")
    month.sweep_out()
    renewal = [s for s in month.segments if s.start_date == date(2026, 6, 1)]
    assert len(renewal) == 1 and renewal[0].value == pytest.approx(960.0)
    assert month.maturity_interest == pytest.approx(60.0)


def test_collateral_draws_by_hierarchy_and_releases_to_sweep():
    accounts = SegmentAccounts(sweep=100.0, fixed=0.0,
                               segments=(_segment(1, "IF", date(2026, 1, 1), 500.0),),
                               next_segment_id=2)
    month = SegmentMonth(_context(), accounts, date(2026, 6, 1), 6)
    month.sync_collateral(300.0, "New loan")
    assert month.collateral == pytest.approx(300.0)
    assert month.sweep == pytest.approx(0.0)
    assert month.segments[0].value == pytest.approx(300.0)
    month.sync_collateral(100.0, "Loan repayment")
    assert month.collateral == pytest.approx(100.0)
    assert month.sweep == pytest.approx(200.0)
    assert month.total == pytest.approx(600.0)


def test_interest_only_on_sweep_and_fixed_plus_collateral_interest():
    accounts = SegmentAccounts(sweep=1_000.0, fixed=2_000.0, collateral=500.0,
                               segments=(_segment(1, "IX", date(2026, 1, 1), 5_000.0),))
    month = SegmentMonth(_context(), accounts, date(2026, 6, 1), 6)
    credited = month.credit_interest(0.01, 0.035, collateral_interest=2.5)
    assert credited == pytest.approx(10.0 + 20.0 + 2.5)
    assert month.segments[0].value == 5_000.0
    assert month.collateral == 500.0


# ── Run-level context ─────────────────────────────────────────


def _iul14_policy(**overrides) -> IllustrationPolicyData:
    kwargs = dict(
        plancode=IUL14_PLANCODE,
        issue_date=date(2016, 6, 15),
        valuation_date=date(2026, 6, 15),
        issue_age=45,
        attained_age=55,
        maturity_age=121,
        policy_year=11,
        policy_month=1,
        duration=121,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        account_value=20_000.0,
        current_interest_rate=0.0623,
        guaranteed_interest_rate=0.02,
        iul_declared_rate=0.035,
        premium_allocations={"IX": 1.0},
        index_illustration_rates={"U1": 0.035, "IX": 0.0623, "IS": 0.0556,
                                  "IC": 0.0599, "IF": 0.0623},
        fund_values={"SW": 2_000.0, "IX": 18_000.0},
        fund_segments=[
            FundSegmentValue("IX", date(2025, month, 1) if month >= 7 else date(2026, month, 1),
                             1_500.0)
            for month in range(1, 13)
        ],
        modal_premium=0.0,
        segments=[CoverageSegment(
            coverage_phase=1, issue_date=date(2016, 6, 15),
            face_amount=100_000.0, units=100.0)],
    )
    kwargs.update(overrides)
    return IllustrationPolicyData(**kwargs)


def test_context_requires_option_and_rejects_wair_and_other_products():
    from suiteview.illustration.core.iul_crediting import build_iul_context

    policy = _iul14_policy()
    options = IllustrationOptions()
    iul = build_iul_context(policy, options)
    assert build_segment_context(policy, options, iul) is None
    seg_options = IllustrationOptions(iul_segment_crediting=True)
    ctx = build_segment_context(policy, seg_options, iul)
    assert ctx.hierarchy == ("IS", "IC", "IF", "IX")
    assert ctx.index_rates["IX"] == pytest.approx(0.0623)
    assert ctx.declared_rate == pytest.approx(0.035)
    with pytest.raises(ValueError, match="WAIR"):
        build_segment_context(
            policy, IllustrationOptions(iul_segment_crediting=True, iul_wair_crediting=True), iul)
    guaranteed = build_segment_context(
        policy, IllustrationOptions(iul_segment_crediting=True, guaranteed_assumption=True), iul)
    assert guaranteed.index_rates["IX"] == 0.0


def test_context_is_development_only(monkeypatch):
    from suiteview.core import build_env
    from suiteview.illustration.core.iul_crediting import build_iul_context

    policy = _iul14_policy()
    options = IllustrationOptions(iul_segment_crediting=True)
    monkeypatch.setattr(build_env, "is_distribution_build", lambda: True)
    with pytest.raises(ValueError, match="development mode"):
        build_segment_context(policy, options, build_iul_context(policy, options))


# ── Engine wiring ─────────────────────────────────────────────


def _config(**overrides) -> PlancodeConfig:
    kwargs = dict(
        plancode="TEST", gint=0.02, dbd=0.0, prem_flat_load=0.0,
        lapse_value="SV", interest_method="MonthlyCompounding")
    kwargs.update(overrides)
    return PlancodeConfig(**kwargs)


def _rates() -> IllustrationRates:
    coi = [0.0] + [0.5] * 180
    zero = [0.0] * 181
    return IllustrationRates(
        coi=coi, segment_coi={1: coi}, epu=zero, segment_epu={1: zero},
        scr=zero, segment_scr={1: zero}, mfee=[0.0] + [10.0] * 180,
        tpp=zero, epp=zero)


def _project(monkeypatch, policy, options, months=26,
             timing=ProjectionTiming.ILLUSTRATION, config=None):
    config = config or _config()
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _plancode: config)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_a: BonusConfig())
    monkeypatch.setattr(calc_engine, "compute_target_premiums", lambda *a, **k: None)
    monkeypatch.setattr(
        calc_engine, "build_target_detail_snapshots", lambda *_a, **_k: ({}, {}))
    import suiteview.illustration.core.ul_rates as ul_rates_module

    class _FakeRatesDB:
        def get_band(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(ul_rates_module, "ULRates", lambda *_a, **_k: _FakeRatesDB())
    return IllustrationEngine().project(
        policy, months=months, stop_on_lapse=False, timing=timing,
        rates_override=_rates(), bonus_override=BonusConfig(), options=options)


@pytest.mark.parametrize("timing", list(ProjectionTiming), ids=lambda t: t.value)
def test_engine_accounts_always_equal_engine_av(monkeypatch, timing):
    results = _project(
        monkeypatch, _iul14_policy(), IllustrationOptions(iul_segment_crediting=True),
        timing=timing)
    for state in results:
        accounts = state.iul_segment_detail["accounts"]
        assert accounts.total == pytest.approx(state.av_end_of_month, abs=1e-6)
        assert len([s for s in accounts.segments if s.fund_id == "IX"]) <= 12


def test_engine_inforce_row_seeds_segments_and_credits_only_sweep(monkeypatch):
    results = _project(
        monkeypatch, _iul14_policy(), IllustrationOptions(iul_segment_crediting=True),
        months=1)
    opening = results[0].iul_segment_detail["accounts"]
    assert len(opening.segments) == 12
    assert opening.index_total == pytest.approx(18_000.0)
    expected = 2_000.0 * ((1.035) ** (1.0 / 12.0) - 1.0)
    assert results[0].interest_credited == pytest.approx(expected)
    assert opening.sweep == pytest.approx(2_000.0 + expected)


def test_engine_matures_oldest_segment_and_sweeps_monthly(monkeypatch):
    results = _project(
        monkeypatch, _iul14_policy(), IllustrationOptions(iul_segment_crediting=True),
        months=2)
    m1 = results[1]
    detail = m1.iul_segment_detail
    # The 2025-07-01 segment matures at the 2026-07-15 monthliversary: 1,500 x 6.23%.
    assert detail["summary"]["Maturity Interest"] == pytest.approx(1_500.0 * 0.0623)
    # Sweep minimum is 12 x last month's (the inforce row's) deduction.
    assert detail["summary"]["Sweep Min"] == pytest.approx(12.0 * results[0].total_deduction)
    starts = sorted(s.start_date for s in detail["accounts"].segments)
    assert date(2025, 7, 1) not in starts
    assert date(2026, 7, 15) in starts


@pytest.mark.parametrize("timing", list(ProjectionTiming), ids=lambda t: t.value)
def test_engine_fixed_loan_collateral_tracks_principal_through_capitalization(monkeypatch, timing):
    policy = _iul14_policy(
        account_value=20_000.0, regular_loan_principal=3_000.0, regular_loan_accrued=50.0,
        fund_values={"SW": 2_000.0, "IX": 15_000.0},
        fund_segments=[
            FundSegmentValue("IX", date(2025, m, 1) if m >= 7 else date(2026, m, 1), 1_250.0)
            for m in range(1, 13)
        ])
    config = _config(loan_charge_rate_guar=0.06, loan_charge_rate_curr=0.06)
    results = _project(monkeypatch, policy, IllustrationOptions(iul_segment_crediting=True),
                       months=14, timing=timing, config=config)
    opening = results[0].iul_segment_detail
    assert not [e for e in opening["events"] if e.event == "Seeding difference"]
    for state in results:
        accounts = state.iul_segment_detail["accounts"]
        assert accounts.total == pytest.approx(state.av_end_of_month, abs=1e-6)
        assert accounts.collateral == pytest.approx(
            state.end_rg_loan_princ + state.end_pf_loan_princ, abs=1e-6)
    capitalized = [s for s in results[1:]
                   if s.iul_segment_detail["summary"].get("Collateral In", 0.0) > 0.0]
    assert capitalized and all(s.is_anniversary for s in capitalized)
    assert any(s.iul_segment_detail["summary"].get("Collateral Interest", 0.0) > 0.0
               for s in results[1:])


def test_engine_blended_run_is_unchanged_by_segment_detail(monkeypatch):
    results = _project(monkeypatch, _iul14_policy(), IllustrationOptions(), months=3)
    assert all(state.iul_segment_detail == {} for state in results)
    assert results[1].effective_annual_rate == pytest.approx(0.0623)


def test_engine_segment_method_credits_less_than_blend_with_drawn_segments(monkeypatch):
    blended = _project(monkeypatch, _iul14_policy(), IllustrationOptions(), months=24)
    segment = _project(
        monkeypatch, _iul14_policy(), IllustrationOptions(iul_segment_crediting=True),
        months=24)
    assert segment[-1].av_end_of_month != pytest.approx(blended[-1].av_end_of_month)
    assert segment[-1].av_end_of_month > 0.0


# ── Inforce source and debug views ────────────────────────────


def test_abr_quote_forces_segment_crediting_off():
    from suiteview.illustration.core.abr_quote import abr_quote_options

    options = abr_quote_options(IllustrationOptions(iul_segment_crediting=True))
    assert options.iul_segment_crediting is False


def test_fund_value_edits_replace_record_segments():
    from suiteview.illustration.core.scenario_builder import _apply_fund_edits

    policy = _iul14_policy()
    assumptions = []
    _apply_fund_edits(policy, {"fund_values": {"SW": 1_000.0, "IX": 19_000.0}}, assumptions)
    assert policy.fund_segments == []
    assert policy.fund_values == {"SW": 1_000.0, "IX": 19_000.0}


def test_open_index_segment_reads_phase_start_and_skips_sweep_fixed_and_empty():
    from suiteview.illustration.core.illustration_policy_service import _open_index_segment

    row = {"VAL_STR_DT": "2026-09-01", "IMPAIRED_IND": "0"}
    segment = _open_index_segment("IX", 330.59, row)
    assert segment == FundSegmentValue("IX", date(2026, 9, 1), 330.59)
    assert _open_index_segment("SW", 590.41, row) is None
    assert _open_index_segment("U1", 100.0, row) is None
    assert _open_index_segment("IX", 0.0, row) is None
    assert _open_index_segment("IX", 50.0, {**row, "IMPAIRED_IND": "1"}) is None


def _basis_source(plancode: str, buckets: list):
    from types import SimpleNamespace

    values = SimpleNamespace(
        get_fund_buckets=lambda current_only=True: buckets,
        get_loan_values_dict=lambda: {},
        get_premium_allocation_dict=lambda: {},
    )
    pi = SimpleNamespace(
        values=values, product=SimpleNamespace(prospective_bonus_code=None),
        company_code="01")
    return SimpleNamespace(pi=pi, plancode=plancode, plancode_config=_config())


def _bucket(fund: str, value: float, start: str):
    from types import SimpleNamespace

    return SimpleNamespace(
        fund_id=fund, csv_amount=value,
        raw_data={"VAL_STR_DT": start, "IMPAIRED_IND": "0"})


@pytest.mark.parametrize("plancode, fund", [("1U135200", "GP"), ("1U14I100", "F1")])
def test_declared_rate_ul_buckets_are_not_index_segments(monkeypatch, plancode, fund):
    """A negative GP bucket or the FFL F1 fund on a declared-rate UL is a fund
    value, not an IUL index segment (Save Case failed on such policies)."""
    from suiteview.illustration.core import illustration_policy_service as service

    monkeypatch.setattr(service, "_current_interest_rate", lambda _s: (0.03, "test"))
    monkeypatch.setattr(service, "_legacy_guaranteed_crediting_rate", lambda _s: None)
    source = _basis_source(plancode, [
        _bucket("U1", 1_000.0, "2010-01-01"), _bucket(fund, -270.54, "2018-09-12")])
    basis = service.build_iul_basis(source)
    assert basis["fund_segments"] == []
    assert basis["fund_values"] == {"U1": 1_000.0, fund: -270.54}


def _numeric_states(states):
    import dataclasses

    return [
        {k: v for k, v in dataclasses.asdict(s).items()
         if isinstance(v, (int, float)) and not isinstance(v, bool)}
        for s in states
    ]


@pytest.mark.parametrize("policy_kind, segment_crediting", [
    ("iul", True), ("iul", False), ("passport_select_ii_gp", False),
])
def test_saved_snapshot_projects_identically(monkeypatch, policy_kind, segment_crediting):
    """Save Case round trip (encode -> JSON -> decode) keeps fund segments and fund
    values exactly, so the decoded snapshot projects to the same values (E4).
    Passport Select II 1U135200 carries a negative GP fund row (U0445398: -82.37),
    which is a fund value, never an index segment."""
    import json

    from suiteview.illustration.models.case_store import (
        decode_policy_snapshot,
        encode_policy_snapshot,
    )

    if policy_kind == "iul":
        policy = _iul14_policy()
    else:
        policy = _iul14_policy(
            plancode="1U135200", fund_segments=[], premium_allocations={},
            index_illustration_rates=None,
            fund_values={"U1": 20_082.37, "GP": -82.37})
    decoded = decode_policy_snapshot(json.loads(json.dumps(encode_policy_snapshot(policy))))
    assert decoded == policy
    assert all(isinstance(s, FundSegmentValue) for s in decoded.fund_segments)
    options = IllustrationOptions(iul_segment_crediting=segment_crediting)
    original = _project(monkeypatch, policy, options, months=24)
    restored = _project(monkeypatch, decoded, options, months=24)
    assert _numeric_states(restored) == _numeric_states(original)


def test_segment_views_grid_slots_and_ledger(monkeypatch):
    from suiteview.illustration.ui import iul_segment_views as views

    results = _project(
        monkeypatch, _iul14_policy(), IllustrationOptions(iul_segment_crediting=True),
        months=3)
    funds = views.segment_funds(results)
    assert funds == ["IX"]
    columns = views.grid_columns(funds)
    assert columns[:2] == ["IX M01", "IX M02"] and columns[-1] == "IX Total"
    row = views.month_values(results[2], funds)
    assert row["IX Total"] == pytest.approx(
        results[2].iul_segment_detail["accounts"].fund_total("IX"))
    assert "IUL Sweep Min" in views.accounts_columns(results)
    ledger = views.ledger_frame(results)
    assert {"Maturity", "Sweep", "Interest"} <= set(ledger["Step"])
    assert views.month_values(
        _project(monkeypatch, _iul14_policy(), IllustrationOptions(), months=1)[1], funds) == {}


def test_values_tab_shows_segment_views_only_for_segment_runs(monkeypatch):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    from suiteview.illustration.ui.values_tab import IllustrationValuesTab

    app = QApplication.instance() or QApplication([])
    # Keep the application alive for later Qt tests (local scope would delete it).
    global _QT_APP
    _QT_APP = app
    policy = _iul14_policy()
    tab = IllustrationValuesTab()

    def nav_titles():
        return [tab.nav_tree.topLevelItem(i).text(0)
                for i in range(tab.nav_tree.topLevelItemCount())]

    segment = _project(monkeypatch, policy, IllustrationOptions(iul_segment_crediting=True),
                       months=3)
    tab.display_projection(policy, segment)
    assert {"IUL Accounts", "IUL Segment Grid", "IUL Segment Ledger"} <= set(nav_titles())
    accounts = list(tab._tab_grids["IUL Accounts"].df.columns)
    assert accounts[:4] == ["Date", "Year", "Month", "Attained Age"]
    assert "IUL Sweep Min" in accounts and "IUL Difference" in accounts
    assert "IX M07" in tab._tab_grids["IUL Segment Grid"].df.columns
    assert len(tab.segment_ledger_grid.df) > 0
    tab._drill_down(1, "Interest")
    assert tab.content_stack.currentWidget() is tab._tab_grids["IUL Accounts"]

    blended = _project(monkeypatch, policy, IllustrationOptions(), months=3)
    tab.display_projection(policy, blended)
    assert not {"IUL Accounts", "IUL Segment Grid", "IUL Segment Ledger"} & set(nav_titles())
    assert len(tab.segment_ledger_grid.df) == 0
