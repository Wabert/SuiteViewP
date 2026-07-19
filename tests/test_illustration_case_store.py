"""Saved illustration cases — store round-trips and UI capture/apply.

The case store persists named input scenarios (one JSON file per case,
atomic writes, loud failures). The UI surface is
IllustrationInputsTab.capture_case_inputs()/apply_case_inputs() — the same
widget state a Run Values consumes — so a saved case can never drift from
what a run actually uses.
"""
import os
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.models import case_store
from suiteview.illustration.models.case_store import (
    CaseExistsError,
    CaseNotFoundError,
    CaseStoreError,
    CorruptCaseError,
    UnknownCaseVersionError,
)
from suiteview.illustration.models.policy_data import (
    BenefitInfo,
    CoverageSegment,
    IllustrationPolicyData,
    RiderInfo,
)
from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


# ── store: save / load / list / delete / rename ──────────────────────


def _inputs(marker: str = "x") -> dict:
    return {
        "grids": {"unscheduled_premiums": [[0, ["06/15/2027", "1,000"]]]},
        "controls": {"exact_days": True, "duration_years": "20"},
        "dynamic": {"lumpsum": marker, "riders": {}, "sections": {}},
    }


def test_save_and_load_round_trip_is_exact(tmp_path):
    inputs = _inputs()
    saved = case_store.save_case(
        "My Case A", policy_number="UL054426", region="CKPR",
        company_code="01", inputs=inputs, directory=tmp_path)
    loaded = case_store.load_case("My Case A", directory=tmp_path)
    assert loaded.inputs == inputs
    assert loaded.name == "My Case A"
    assert loaded.policy_number == "UL054426"
    assert loaded.region == "CKPR"
    assert loaded.company_code == "01"
    assert loaded.schema_version == case_store.CASE_SCHEMA_VERSION
    assert loaded.app_version
    assert loaded == saved
    # Slugged filename, self-describing file, no index.
    assert loaded.path.name == "my_case_a.case.json"


def test_overwrite_requires_flag_and_atomic_write_leaves_no_temp(tmp_path):
    case_store.save_case("A", policy_number="P1", region="CKPR",
                         inputs=_inputs("one"), directory=tmp_path)
    with pytest.raises(CaseExistsError):
        case_store.save_case("A", policy_number="P1", region="CKPR",
                             inputs=_inputs("two"), directory=tmp_path)
    case_store.save_case("A", policy_number="P1", region="CKPR",
                         inputs=_inputs("two"), overwrite=True,
                         directory=tmp_path)
    assert case_store.load_case("A", directory=tmp_path).inputs["dynamic"]["lumpsum"] == "two"
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == ["a.case.json"]          # no .tmp leftovers


def test_atomic_write_preserves_original_when_replace_fails(tmp_path, monkeypatch):
    case_store.save_case("A", policy_number="P1", region="CKPR",
                         inputs=_inputs("original"), directory=tmp_path)

    def _boom(src, dst):
        raise OSError("simulated crash mid-replace")

    monkeypatch.setattr(case_store.os, "replace", _boom)
    with pytest.raises(OSError):
        case_store.save_case("A", policy_number="P1", region="CKPR",
                             inputs=_inputs("clobbered"), overwrite=True,
                             directory=tmp_path)
    monkeypatch.undo()
    assert case_store.load_case("A", directory=tmp_path).inputs["dynamic"]["lumpsum"] == "original"


def test_corrupt_file_raises_loudly(tmp_path):
    path = tmp_path / "bad.case.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CorruptCaseError):
        case_store.load_case("bad", directory=tmp_path)
    with pytest.raises(CorruptCaseError):
        case_store.list_cases(directory=tmp_path)


def test_unknown_schema_version_raises(tmp_path):
    case_store.save_case("A", policy_number="P1", region="CKPR",
                         inputs=_inputs(), directory=tmp_path)
    path = tmp_path / "a.case.json"
    import json
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = 99
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(UnknownCaseVersionError):
        case_store.load_case("A", directory=tmp_path)


def test_missing_required_fields_raise(tmp_path):
    case_store.save_case("A", policy_number="P1", region="CKPR",
                         inputs=_inputs(), directory=tmp_path)
    path = tmp_path / "a.case.json"
    import json
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["inputs"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CorruptCaseError):
        case_store.load_case("A", directory=tmp_path)


def test_list_filters_by_policy_and_sorts_newest_first(tmp_path):
    import json
    case_store.save_case("Old", policy_number="P1", region="CKPR",
                         inputs=_inputs(), directory=tmp_path)
    case_store.save_case("New", policy_number="P1", region="CKPR",
                         inputs=_inputs(), directory=tmp_path)
    case_store.save_case("Other", policy_number="P2", region="CKPR",
                         inputs=_inputs(), directory=tmp_path)
    # Force distinct timestamps (same-second saves).
    old = tmp_path / "old.case.json"
    data = json.loads(old.read_text(encoding="utf-8"))
    data["saved_at"] = "2020-01-01T00:00:00"
    old.write_text(json.dumps(data), encoding="utf-8")

    all_cases = case_store.list_cases(directory=tmp_path)
    assert {c.name for c in all_cases} == {"Old", "New", "Other"}
    p1 = case_store.list_cases("p1", directory=tmp_path)   # case-insensitive
    assert [c.name for c in p1] == ["New", "Old"]          # newest first
    assert case_store.list_cases("P9", directory=tmp_path) == []
    # Missing folder → empty list, not an error.
    assert case_store.list_cases(directory=tmp_path / "nope") == []


def test_delete_and_missing_delete(tmp_path):
    case_store.save_case("A", policy_number="P1", region="CKPR",
                         inputs=_inputs(), directory=tmp_path)
    case_store.delete_case("A", directory=tmp_path)
    assert case_store.list_cases(directory=tmp_path) == []
    with pytest.raises(CaseNotFoundError):
        case_store.delete_case("A", directory=tmp_path)


def test_rename_case(tmp_path):
    case_store.save_case("A", policy_number="P1", region="CKPR",
                         inputs=_inputs("keepme"), directory=tmp_path)
    case_store.save_case("B", policy_number="P1", region="CKPR",
                         inputs=_inputs(), directory=tmp_path)
    renamed = case_store.rename_case("A", "A Prime", directory=tmp_path)
    assert renamed.name == "A Prime"
    assert renamed.inputs["dynamic"]["lumpsum"] == "keepme"
    with pytest.raises(CaseNotFoundError):
        case_store.load_case("A", directory=tmp_path)
    # Renaming onto an existing case refuses without overwrite.
    with pytest.raises(CaseExistsError):
        case_store.rename_case("A Prime", "B", directory=tmp_path)


def test_copy_case_duplicates_with_fresh_stamp(tmp_path):
    source = case_store.save_case(
        "A", policy_number="P1", region="CKPR", inputs=_inputs("keepme"),
        directory=tmp_path)
    case_store.save_case("B", policy_number="P2", region="CKPR",
                         inputs=_inputs(), directory=tmp_path)

    copied = case_store.copy_case("A", "A Copy", directory=tmp_path)
    assert copied.name == "A Copy"
    assert copied.inputs == source.inputs
    assert copied.policy_number == "P1"
    assert copied.saved_at >= source.saved_at        # freshly re-stamped
    # The source survives untouched — both load independently.
    assert case_store.load_case("A", directory=tmp_path).inputs == source.inputs
    assert len(case_store.list_cases(directory=tmp_path)) == 3

    # Copying onto the source itself is refused outright.
    with pytest.raises(CaseStoreError):
        case_store.copy_case("A", "A", directory=tmp_path)
    # Copying onto another existing case refuses without overwrite.
    with pytest.raises(CaseExistsError):
        case_store.copy_case("A", "B", directory=tmp_path)
    overwritten = case_store.copy_case("A", "B", overwrite=True,
                                       directory=tmp_path)
    assert overwritten.policy_number == "P1"


def test_copy_case_preserves_snapshot_and_schema_version(tmp_path):
    snapshot = _full_snapshot()
    case_store.save_case("Frozen", policy_number="P1", region="CKPR",
                         inputs=_inputs(), policy_snapshot=snapshot,
                         directory=tmp_path)
    copied = case_store.copy_case("Frozen", "Frozen Copy", directory=tmp_path)
    assert copied.policy_snapshot == snapshot
    assert copied.schema_version == 2


def test_case_name_must_slug_to_something(tmp_path):
    with pytest.raises(CaseStoreError):
        case_store.save_case("///", policy_number="P1", region="CKPR",
                             inputs=_inputs(), directory=tmp_path)
    # Spaces and slashes slug safely.
    saved = case_store.save_case("Q3 / what-if #2", policy_number="P1",
                                 region="CKPR", inputs=_inputs(),
                                 directory=tmp_path)
    assert saved.path.name == "q3_what-if_2.case.json"


# ── schema v2: frozen policy snapshot ────────────────────────────────


def _full_snapshot() -> IllustrationPolicyData:
    """A fully-populated IllustrationPolicyData exercising every value kind:
    dates (set and None), floats, ints, bools, strings, dicts, plain lists,
    and nested CoverageSegment / BenefitInfo / RiderInfo dataclasses."""
    return IllustrationPolicyData(
        policy_number="UL054426", region="CKPR", company_code="01",
        insured_name="DOE, JANE", plancode="1U135D00", product_type="IUL",
        form_number="ULIUL19", issue_state="TX", company_sub="ANICO",
        issue_date=date(2019, 11, 9), issue_age=50, attained_age=56,
        insured_birth_date=date(1969, 3, 2), rate_sex="F", rate_class="N",
        face_amount=250000.0, units=250.0, db_option="B", band=3,
        account_value=41234.56, cost_basis=39000.0,
        system_coi_charge=101.11, system_expense_charge=12.5,
        system_other_charge=0.35, system_monthly_deduction=113.96,
        modal_premium=310.25, annual_premium=3723.0, billing_frequency=1,
        premiums_paid_to_date=24000.0, premiums_ytd=1861.5,
        guaranteed_interest_rate=0.02, current_interest_rate=0.045,
        fund_values={"SW": 1200.0, "IP1": 40034.56},
        premium_allocations={"SW": 0.25, "IP1": 0.75},
        sweep_account_min=250.0, iul_declared_rate=0.031,
        iul_asset_charge_rate=None,
        policy_year=7, policy_month=8, duration=80,
        valuation_date=date(2026, 6, 9), maturity_age=121,
        def_of_life_ins="GPT", glp=4200.0, gsp=31000.0,
        accumulated_glp=29400.0, corridor_percent=115.0,
        mtp=95.0, accumulated_mtp=7980.0, map_cease_date=date(2029, 11, 9),
        ctp=2400.0,
        is_mec=False, tamra_7pay_level=5100.0,
        tamra_7pay_start_date=date(2019, 11, 9), tamra_7pay_start_av=0.0,
        tamra_7pay_cash_value=0.0, tamra_7year_lowest_db=250000.0,
        tamra_7year_contributions=[3723.0, 3723.0, 3723.0, 0.0, 0.0, 0.0, 0.0],
        regular_loan_principal=5000.0, regular_loan_accrued=123.45,
        preferred_loan_principal=0.0, preferred_loan_accrued=0.0,
        preferred_loans_available=True,
        variable_loan_principal=0.0, variable_loan_accrued=0.0,
        variable_loan_charge_rate=None,
        withdrawals_to_date=1000.0,
        shadow_account_value=39000.0, swam=1.05, ccv_active=True,
        ccv_ceased=False, ccv_units=250.0, ccv_coi_rate=0.012,
        deemed_cash_value=0.0,
        segments=[
            CoverageSegment(
                coverage_phase=1, is_base=True, issue_date=date(2019, 11, 9),
                issue_age=50, rate_sex="F", rate_class="N",
                face_amount=250000.0, original_face_amount=250000.0,
                units=250.0, vpu=1000.0, band=3, original_band=3,
                table_rating=2, table_cease_date=date(2030, 11, 9),
                flat_extra=2.5, flat_cease_date=None, status="A",
                maturity_date=date(2090, 11, 9), months_since_terminated=0,
                coi_renewal_rate=0.123),
        ],
        benefits=[
            BenefitInfo(
                coverage_phase=1, benefit_type="A", benefit_subtype="1",
                benefit_amount=250000.0, units=250.0, vpu=1000.0,
                issue_date=date(2019, 11, 9), issue_age=50,
                cease_date=None, rating_factor=1.0, coi_rate=0.012,
                is_active=True),
        ],
        riders=[
            RiderInfo(
                coverage_phase=2, occurrence=1, plancode="1R100000",
                issue_date=date(2019, 11, 9), issue_age=50, rate_sex="F",
                rate_class="N", face_amount=25000.0, units=25.0, vpu=1000.0,
                band=1, table_rating=0, flat_extra=0.0,
                maturity_date=date(2039, 11, 9), status="A",
                premium_rate=1.23, coi_rate=None, is_active=True,
                on_primary_insured=True, cov_type="CTR",
                cease_age_dur=70, cease_use_code="AGE"),
        ],
        _debug_csv=41111.11,
    )


def test_v2_snapshot_round_trips_exactly(tmp_path):
    snapshot = _full_snapshot()
    saved = case_store.save_case(
        "Frozen", policy_number="UL054426", region="CKPR", company_code="01",
        inputs=_inputs(), policy_snapshot=snapshot, directory=tmp_path)
    assert saved.schema_version == 2

    loaded = case_store.load_case("Frozen", directory=tmp_path)
    assert loaded.policy_snapshot is not None
    assert loaded.policy_snapshot is not snapshot         # rebuilt, not shared
    assert loaded.policy_snapshot == snapshot             # EXACT round trip
    # Type fidelity spot checks — dates stay dates, None stays None, nested
    # dataclasses come back as dataclasses.
    assert loaded.policy_snapshot.issue_date == date(2019, 11, 9)
    assert loaded.policy_snapshot.iul_asset_charge_rate is None
    assert isinstance(loaded.policy_snapshot.segments[0], CoverageSegment)
    assert isinstance(loaded.policy_snapshot.benefits[0], BenefitInfo)
    assert isinstance(loaded.policy_snapshot.riders[0], RiderInfo)
    assert loaded.policy_snapshot.riders[0].maturity_date == date(2039, 11, 9)
    assert loaded.policy_snapshot.fund_values == {"SW": 1200.0, "IP1": 40034.56}
    # list_cases materializes the snapshot too.
    listed = case_store.list_cases("UL054426", directory=tmp_path)
    assert listed[0].policy_snapshot == snapshot


def test_v2_save_without_snapshot_loads_as_none(tmp_path):
    case_store.save_case("NoSnap", policy_number="P1", region="CKPR",
                         inputs=_inputs(), directory=tmp_path)
    loaded = case_store.load_case("NoSnap", directory=tmp_path)
    assert loaded.schema_version == 2
    assert loaded.policy_snapshot is None


def test_v1_files_remain_loadable_without_snapshot(tmp_path):
    import json
    path = tmp_path / "legacy.case.json"
    path.write_text(json.dumps({
        "kind": case_store.CASE_KIND,
        "schema_version": 1,
        "name": "Legacy",
        "policy_number": "P1",
        "region": "CKPR",
        "company_code": "01",
        "saved_at": "2026-06-01T09:30:00",
        "app_version": "2.1",
        "inputs": _inputs("legacy"),
    }), encoding="utf-8")
    loaded = case_store.load_case("Legacy", directory=tmp_path)
    assert loaded.schema_version == 1
    assert loaded.policy_snapshot is None                 # UI must say so
    assert loaded.inputs["dynamic"]["lumpsum"] == "legacy"
    assert case_store.list_cases(directory=tmp_path)[0].name == "Legacy"


def test_corrupt_snapshot_raises_loudly(tmp_path):
    import json
    case_store.save_case("Frozen", policy_number="P1", region="CKPR",
                         inputs=_inputs(), policy_snapshot=_full_snapshot(),
                         directory=tmp_path)
    path = tmp_path / "frozen.case.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["policy_snapshot"]["fields"]["issue_date"] = {
        "__type__": "date", "value": "not-a-date"}
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CorruptCaseError):
        case_store.load_case("Frozen", directory=tmp_path)
    # An unknown nested type marker is corruption too, not a silent skip.
    data["policy_snapshot"]["fields"]["issue_date"] = {
        "__type__": "mystery", "value": 1}
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CorruptCaseError):
        case_store.load_case("Frozen", directory=tmp_path)


def test_snapshot_must_be_policy_data(tmp_path):
    with pytest.raises(CaseStoreError):
        case_store.save_case("Bad", policy_number="P1", region="CKPR",
                             inputs=_inputs(), policy_snapshot={"nope": 1},
                             directory=tmp_path)


def test_rename_preserves_snapshot_and_schema_version(tmp_path):
    import json
    snapshot = _full_snapshot()
    case_store.save_case("Frozen", policy_number="P1", region="CKPR",
                         inputs=_inputs(), policy_snapshot=snapshot,
                         directory=tmp_path)
    renamed = case_store.rename_case("Frozen", "Frozen v2", directory=tmp_path)
    assert renamed.policy_snapshot == snapshot
    assert renamed.schema_version == 2

    # A v1 file renames without gaining a snapshot or a version bump.
    legacy = tmp_path / "legacy.case.json"
    legacy.write_text(json.dumps({
        "kind": case_store.CASE_KIND, "schema_version": 1, "name": "Legacy",
        "policy_number": "P1", "region": "CKPR", "company_code": "",
        "saved_at": "2026-06-01T09:30:00", "app_version": "2.1",
        "inputs": _inputs("legacy"),
    }), encoding="utf-8")
    renamed_legacy = case_store.rename_case("Legacy", "Legacy Prime",
                                            directory=tmp_path)
    assert renamed_legacy.schema_version == 1
    assert renamed_legacy.policy_snapshot is None


# ── UI: capture / apply round trip ───────────────────────────────────


class _FakeCoverage:
    """Rider coverage surface for RiderButtonsPanel.set_policy."""

    is_base = False
    cov_pha_nbr = 2
    form_number = "ULCTR90"
    plancode = "1R100000"
    issue_date = date(2019, 11, 9)
    face_amount = 25000.0
    issue_age = 50
    rate_class = "N"
    cov_status = "Active"
    rate = 1.23            # premium-paying
    cease_date = None
    maturity_date = None
    terminate_date = None


class _FakePolicy:
    """Just enough PolicyInformation surface for the inputs tab."""

    issue_date = date(2019, 11, 9)
    base_issue_age = 50
    attained_age = 56
    valuation_date = date(2026, 5, 9)
    policy_year = 7
    maturity_age = 121
    billing_frequency = 1
    modal_premium = 153.56
    def_of_life_ins = "GPT"
    glp = 1200.0
    accumulated_glp = 5000.0
    premiums_paid_to_date = 10000.0
    withdrawals_to_date = 1000.0
    base_rate_class = "N"
    base_table_rating = 2
    base_plancode = "1U135D00"
    status_code = "0"

    def get_coverages(self):
        return []

    def get_benefits(self):
        return []


class _RiderPolicy(_FakePolicy):
    def get_coverages(self):
        return [_FakeCoverage()]


def _loaded_tab(policy=None, **kwargs) -> IllustrationInputsTab:
    _app()
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(policy or _FakePolicy(), **kwargs)
    return tab


def _fill_everything(tab: IllustrationInputsTab):
    """Populate every input group with non-default values."""
    panel = tab.dynamic_panel
    # Dynamic premium row + a second row.
    row = panel.premium_section.rows()[0]
    row.amount_edit.setText("250.00")
    extra = panel.premium_section.add_row()
    extra.year_edit.set_value(20)
    extra._year_edited()
    extra.amount_edit.setText("100.00")
    # Loans / withdrawals / repayments rows.
    loan_row = panel.loan_section.rows()[0]
    loan_row.year_edit.setText("10")
    loan_row.age_edit.setText("59")
    loan_row.amount_edit.setText("500.00")
    wd_row = panel.withdrawal_section.rows()[0]
    wd_row.year_edit.setText("12")
    wd_row.amount_edit.setText("750.00")
    wd_row.basis_combo.setCurrentText("Gross")
    rp_row = panel.repayment_section.rows()[0]
    rp_row.year_edit.setText("15")
    rp_row.amount_edit.setText("300.00")
    # Policy changes.
    face_row = panel.face_section.rows()[0]
    face_row.year_edit.setText("18")
    face_row.amount_edit.setText("50000")
    dbo_row = panel.dbo_section.rows()[0]
    dbo_row.year_edit.setText("19")
    dbo_row.value_combo.setCurrentIndex(dbo_row.value_combo.findData("B"))
    rc_row = panel.rateclass_section.rows()[0]
    rc_row.year_edit.setText("21")
    rc_row.value_combo.setCurrentIndex(rc_row.value_combo.findData("P"))
    tbl_row = panel.table_section.rows()[0]
    tbl_row.year_edit.setText("22")
    tbl_row.value_combo.setCurrentIndex(tbl_row.value_combo.findData("0"))
    # Header controls on the Input panel.
    panel.lumpsum_edit.setText("2,500.00")
    panel.apply_prem_to_loan_check.setChecked(True)
    panel.tamra_check.setChecked(False)
    panel.excess_apply_radio.setChecked(True)
    panel.illustrated_rate_edit.setText("4.500")
    # Rider decision (set directly — the dialog is interaction-only).
    adj = panel.riders_panel._adjustments["cov:2"]
    adj.action = "change"
    adj.new_amount = 10000.0
    adj.effective_year = 9
    # Grid Inputs tab.
    tab.unscheduled_premium_table.item(0, 0).setText("06/09/2027")
    tab.unscheduled_premium_table.item(0, 1).setText("1,000")
    tab.unscheduled_premium_table.item(5, 0).setText("06/09/2028")
    tab.unscheduled_premium_table.item(5, 1).setText("2,000")
    tab.specific_loan_table.item(0, 0).setText("06/09/2029")
    tab.specific_loan_table.item(0, 1).setText("400")
    tab.loan_repayment_table.item(0, 0).setText("06/09/2030")
    tab.loan_repayment_table.item(0, 1).setText("150")
    tab.withdrawal_table.item(0, 0).setText("06/09/2031")
    tab.withdrawal_table.item(0, 1).setText("600")
    tab.scheduled_premium_table.item(0, 0).setText("8")
    tab.scheduled_premium_table.item(0, 1).setText("1,200")
    tab.face_amount_table.item(0, 0).setText("11/09/2040")
    tab.face_amount_table.item(0, 1).setText("40000")
    tab.db_option_table.item(0, 0).setText("11/09/2041")
    tab.db_option_table.item(0, 1).setText("A")
    tab.variable_loan_toggle.setChecked(True)
    # Illustration Control tab.
    tab.exact_days_check.setChecked(True)
    tab.tefra_check.setChecked(False)
    tab.cap_acceptance_check.setChecked(False)
    tab.levelizing_check.setChecked(False)
    tab.gp_search_check.setChecked(True)
    tab.stop_on_lapse_check.setChecked(False)
    tab.illustration_years_combo.setCurrentText("20")


def test_capture_apply_round_trips_every_input_group(tmp_path):
    source = _loaded_tab(_RiderPolicy())
    _fill_everything(source)
    inputs_before = source.export_input_set()
    options_before = source.export_options()
    overrides_before = source.export_inforce_overrides()
    assert inputs_before.scheduled_transactions          # sanity: non-empty
    assert inputs_before.dated_transactions
    assert inputs_before.policy_changes

    state = source.capture_case_inputs()
    # Persist through the real store — proves the payload is JSON-clean.
    case_store.save_case("Round Trip", policy_number="POLA", region="CKPR",
                         inputs=state, directory=tmp_path)
    loaded = case_store.load_case("Round Trip", directory=tmp_path)
    assert loaded.inputs == state

    target = _loaded_tab(_RiderPolicy())     # fresh tab = "clear"
    warnings = target.apply_case_inputs(loaded.inputs)
    assert warnings == []

    # The exports a run consumes are IDENTICAL — the exactness contract.
    assert target.export_input_set() == inputs_before
    assert target.export_options() == options_before
    assert target.export_inforce_overrides() == overrides_before

    # Spot-check widget state (positions preserved, including the row gap).
    assert target.unscheduled_premium_table.item(5, 1).text() == "2,000"
    assert target.dynamic_panel.premium_section.rows()[0].amount_edit.text() == "250.00"
    assert len(target.dynamic_panel.premium_section.rows()) == 2
    assert target.dynamic_panel.withdrawal_section.rows()[0].basis() == "gross"
    assert target.variable_loan_toggle.isChecked()
    assert target.exact_days_check.isChecked()
    assert target.illustration_years_combo.currentText() == "20"
    adj = target.dynamic_panel.riders_panel._adjustments["cov:2"]
    assert adj.action == "change" and adj.new_amount == 10000.0
    assert adj.effective_year == 9


def test_apply_warns_when_saved_rider_is_missing():
    source = _loaded_tab(_RiderPolicy())
    adj = source.dynamic_panel.riders_panel._adjustments["cov:2"]
    adj.action = "drop"
    adj.effective_year = 9
    state = source.capture_case_inputs()

    target = _loaded_tab(_FakePolicy())      # no riders on this policy
    warnings = target.apply_case_inputs(state)
    assert len(warnings) == 1
    assert "ULCTR90" in warnings[0]
    assert "no matching rider" in warnings[0]
    # Nothing else was silently dropped — the rest of the case still landed.
    assert target.dynamic_panel.riders_panel.capture_adjustments() == {}


def test_apply_warns_when_premium_type_unavailable():
    shadow = _loaded_tab(_FakePolicy(), has_shadow=True)
    row = shadow.dynamic_panel.premium_section.rows()[0]
    row.type_combo.setCurrentText("Prem to Shadow Maturity")
    assert row.premium_type() == "Prem to Shadow Maturity"
    state = shadow.capture_case_inputs()

    plain = _loaded_tab(_FakePolicy())       # no shadow account
    warnings = plain.apply_case_inputs(state)
    assert any("Prem to Shadow Maturity" in w and "not available" in w
               for w in warnings)


def test_apply_warns_when_allocations_hit_a_declared_rate_policy():
    source = _loaded_tab(_FakePolicy())
    state = source.capture_case_inputs()
    state["dynamic"]["allocations"] = {
        "allocations": {"IX": 0.5}, "rates": {"IX": 0.06}, "sweep_min": None}

    target = _loaded_tab(_FakePolicy())      # 1U135D00 is declared-rate
    warnings = target.apply_case_inputs(state)
    assert any("not an IUL plan" in w for w in warnings)


def test_saved_exception_premium_does_not_sneak_past_a_shadow_block():
    source = _loaded_tab(_FakePolicy())
    source.exception_prem_check.setChecked(True)
    state = source.capture_case_inputs()

    blocked = _loaded_tab(_FakePolicy(), has_shadow=True)
    assert not blocked.exception_prem_check.isEnabled()
    warnings = blocked.apply_case_inputs(state)
    assert blocked.exception_prem_check.isChecked() is False
    assert any("Allow GP Exception Premium" in w for w in warnings)


# NOTE: the window-level cross-policy load test moved on when the Cases menu
# (and its CasesController.load_flow) was removed — case activation now goes
# through the Saved Cases panel and restores the case's own policy snapshot.
# See tests/test_illustration_saved_cases_panel.py for the window-level
# activation and Save-button coverage.


def test_save_clear_load_restores_inputs_tab_state(tmp_path):
    # The end-to-end user story: save a case, lose the session (fresh tab),
    # load the case days later — the inputs come back exactly.
    source = _loaded_tab(_RiderPolicy())
    _fill_everything(source)
    exported = source.export_input_set()
    case_store.save_case(
        "Story", policy_number="POLA", region="CKPR", company_code="01",
        inputs=source.capture_case_inputs(), directory=tmp_path)

    fresh = _loaded_tab(_RiderPolicy())      # brand-new session, same policy
    assert fresh.export_input_set() != exported
    loaded = case_store.load_case("Story", directory=tmp_path)
    assert fresh.apply_case_inputs(loaded.inputs) == []
    assert fresh.export_input_set() == exported


# ── Grid Inputs tab visibility (per-case, not global) ─────────────────


def test_grid_inputs_tab_hidden_by_default_on_a_fresh_tab():
    tab = _loaded_tab(_FakePolicy())
    assert tab.grid_inputs_tab_visible() is False
    assert not tab.input_tabs.isTabVisible(tab._grid_inputs_tab_index)


def test_capture_case_inputs_records_grid_inputs_visibility():
    tab = _loaded_tab(_FakePolicy())
    state = tab.capture_case_inputs()
    assert state["ui"]["grid_inputs_tab_visible"] is False

    tab._set_grid_inputs_tab_visible(True)
    state = tab.capture_case_inputs()
    assert state["ui"]["grid_inputs_tab_visible"] is True


def test_apply_case_inputs_restores_grid_inputs_visibility(tmp_path):
    source = _loaded_tab(_FakePolicy())
    source._set_grid_inputs_tab_visible(True)
    state = source.capture_case_inputs()
    case_store.save_case(
        "Grid Visible", policy_number="POLA", region="CKPR",
        inputs=state, directory=tmp_path)

    loaded = case_store.load_case("Grid Visible", directory=tmp_path)
    target = _loaded_tab(_FakePolicy())      # fresh tab: hidden by default
    assert target.grid_inputs_tab_visible() is False
    target.apply_case_inputs(loaded.inputs)
    assert target.grid_inputs_tab_visible() is True


def test_apply_case_inputs_defaults_to_hidden_for_cases_saved_before_the_field_existed():
    # Backward-tolerance: an old saved case's "inputs" dict has no "ui" key.
    tab = _loaded_tab(_FakePolicy())
    tab._set_grid_inputs_tab_visible(True)   # simulate a stray visible state
    legacy_state = tab.capture_case_inputs()
    del legacy_state["ui"]

    tab.apply_case_inputs(legacy_state)
    assert tab.grid_inputs_tab_visible() is False
