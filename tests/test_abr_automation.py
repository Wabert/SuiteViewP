"""Synthetic, in-memory ABR cases; no client evidence or live connections."""
from copy import deepcopy
from datetime import date
import json
from types import SimpleNamespace

import pytest

from suiteview.abrquote.automation import (
    QuoteError, QuoteRequest, calculate_quote, quote_abr, _validate_assessment_result,
)
from suiteview.abrquote.models.abr_data import ABRPolicyData
from suiteview.abrquote.models.abr_database import get_abr_database, using_quote_database


class Rates:
    def get_vbt_qx(self, *args): return 10.0
    def get_effective_interest_rate(self, month): return (month, .05)
    def get_term_rate(self, *args): return 2.0
    def get_term_rate_schedule(self, *args): return [2.0] * 82
    def get_band(self, *args): return "A"
    def get_policy_fee(self, *args): return 60.0
    def get_modal_factor(self, *args): return 1.0
    def get_modal_fee_factor(self, *args): return 1.0
    def get_admin_fee(self, *args): return 250.0
    def get_per_diem(self, *args): return (420.0, 153300.0)
    def get_prem_cease_age(self, *args): return 95


@pytest.fixture
def request_data():
    return {
        "policy_number": "SYNTHETIC", "company_code": "01", "region": "CKPR",
        "quote_date": "2026-09-03", "effective_date": "2026-09-03",
        "assessment": {"rider_type": "Terminal"},
        "options": {"min_face_amount": 50000},
        "input_provenance": {"source": "synthetic unit test"},
    }


@pytest.fixture(autouse=True)
def no_ambient_local_mode(monkeypatch):
    monkeypatch.delenv("SUITEVIEW_LOCAL_DATA", raising=False)


@pytest.fixture
def policy():
    return ABRPolicyData(
        policy_number="SYNTHETIC", company="01", region="CKPR",
        product_type="TERM", plan_code="TEST", issue_state="TX",
        issue_date=date(2020, 1, 15), maturity_date=date(2055, 1, 15),
        face_amount=100000, issue_age=40, attained_age=46, maturity_age=75,
        sex="F", rate_sex="F", rate_class="N", policy_year=7, policy_month=8,
        reinsurers="(none)", billing_mode=1,
    )


def run(data, p, db=None):
    return calculate_quote(data, p, database=db or Rates(),
                           policy_provenance={"source": "synthetic"},
                           eligible_riders={"Terminal", "Chronic", "Critical"})


def test_terminal_uses_canonical_calculation_and_clipboard(request_data, policy, monkeypatch):
    from suiteview.abrquote.ui.email_print_dialog import EmailPrintDialog
    from suiteview.abrquote.models.abr_data import ABRQuoteResult, MedicalAssessment
    monkeypatch.setattr(EmailPrintDialog, "__init__", lambda *a, **kw: pytest.fail("No dialogs"))
    original = deepcopy(policy)
    result = run(request_data, policy)
    assert policy == original
    json.dumps(result, allow_nan=False)
    assert result["numbers"]["full_eligible_db"] == 100000
    assert result["numbers"]["full_admin_fee"] == 250
    assert result["numbers"]["quote_date"] == "2026-09-03"
    assert result["numbers"]["full_accel_benefit"] > 0
    assert result["assessment"]["computed_survival_5yr"] == pytest.approx(.5 ** 5)
    numbers = dict(result["numbers"], quote_date=date(2026, 9, 3))
    render = SimpleNamespace(_policy=policy, _result=ABRQuoteResult(**numbers),
                             _assessment=MedicalAssessment(**result["assessment"]),
                             _fmt=EmailPrintDialog._fmt)
    sections = EmailPrintDialog._build_summary_sections(render)
    assert result["html"] == EmailPrintDialog._build_clipboard_html(render, sections)
    assert result["text"] == EmailPrintDialog._build_clipboard_text(render, sections)
    assert result["provenance"]["request"] == request_data
    assert result["provenance"]["rate_lookups"]


@pytest.mark.parametrize("assessment", [
    {"rider_type": "Chronic", "five_year_survival": .5},
    {"rider_type": "Critical", "five_year_survival": .5, "ten_year_survival": .2},
    {"rider_type": "Chronic", "life_expectancy_years": 5},
    {"rider_type": "Chronic", "table": {"value": 2, "start_year": 1, "stop_year": 5}},
    {"rider_type": "Critical", "increased_decrement": {"value": 200, "start_year": 1, "stop_year": 10}},
])
def test_medical_options_run_existing_assessment(request_data, policy, assessment):
    request_data["assessment"] = assessment
    result = run(request_data, policy)
    assert result["assessment"]["rider_type"] == assessment["rider_type"]
    assert 0 < result["assessment"]["computed_le"] < 35


def test_no_missing_interest_fallback(request_data, policy):
    db = Rates()
    db.get_effective_interest_rate = lambda month: None
    with pytest.raises(QuoteError, match="Required rate data missing"):
        run(request_data, policy, db)


def test_no_missing_term_rate_fallback(request_data, policy):
    db = Rates()
    db.get_term_rate = lambda *args: None
    with pytest.raises(QuoteError, match="Required rate data missing"):
        run(request_data, policy, db)


@pytest.mark.parametrize("loan_payoff", [0, 50])
def test_ul_requires_explicit_inputs(request_data, policy, loan_payoff):
    policy.product_type = "UL"
    with pytest.raises(QuoteError, match="UL requires explicit"):
        run(request_data, policy)
    request_data["options"].update(level_annual_premium=1000, loan_payoff=loan_payoff, surrender_value=100)
    result = run(request_data, policy)
    assert result["numbers"]["full_surrender_value"] == 100
    assert result["numbers"]["full_loan_repayment"] == loan_payoff


@pytest.mark.parametrize("mutation,match", [
    ({"effective_date": "2026-09-01"}, "Distinct effective_date"),
    ({"quote_date": "20260903"}, "YYYY-MM-DD"),
    ({"assessment": {"rider_type": "Terminal", "life_expectancy_years": 2}}, "Terminal"),
    ({"assessment": {"rider_type": "Chronic"}}, "requires survival"),
    ({"options": {}}, "min_face_amount"),
    ({"options": {"min_face_amount": float("nan")}}, "finite"),
    ({"company_code": 1}, "string"),
    ({"extra": True}, "unknown fields"),
])
def test_strict_request_validation(request_data, mutation, match):
    request_data.update(mutation)
    with pytest.raises(QuoteError, match=match):
        QuoteRequest.from_dict(request_data)


def test_identity_eligibility_and_product_fail_closed(request_data, policy):
    with pytest.raises(QuoteError, match="not verified active"):
        calculate_quote(request_data, policy, database=Rates(),
                        policy_provenance={}, eligible_riders=set())
    policy.product_type = "WL"
    with pytest.raises(QuoteError, match="Unsupported ABR product"):
        run(request_data, policy)
    policy.company = "02"
    with pytest.raises(QuoteError, match="company"):
        run(request_data, policy)


def test_database_context_is_nested_and_restored():
    a, b = Rates(), Rates()
    with using_quote_database(a):
        assert get_abr_database() is a
        with pytest.raises(RuntimeError):
            with using_quote_database(b):
                assert get_abr_database() is b
                raise RuntimeError()
        assert get_abr_database() is a


def test_minimum_face_uses_actual_assessment_product_rule():
    from suiteview.abrquote.models.abr_data import default_minimum_face
    assert default_minimum_face("TERM") == 50000
    assert default_minimum_face("UL") == 25000
    assert default_minimum_face("IUL") == 25000
    assert default_minimum_face("ISWL") == 25000


def test_cli_validation_only_is_offline(request_data, monkeypatch, capsys):
    from tools.abrquote.quote import main
    from pathlib import Path
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: json.dumps(request_data))
    monkeypatch.setattr("tools.abrquote.quote.quote_abr", lambda *args: pytest.fail("No live read"))
    assert main(["--request", "synthetic.json", "--validate-only"]) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "valid", "live_access": False}


def test_dataclass_request_and_decimal_sources_are_json_safe(request_data, policy):
    from decimal import Decimal
    req = QuoteRequest(
        policy_number="SYNTHETIC", company_code="01", region="CKPR",
        quote_date=date(2026, 9, 3), assessment={"rider_type": "Terminal"},
        options={"min_face_amount": 50000},
    )
    policy.account_value = Decimal("0.00")
    result = run(req, policy)
    assert result["policy"]["account_value"] == 0
    assert result["provenance"]["request"]["input_provenance"] == {}


def test_dates_are_not_replaced_by_today_or_reconstructed(request_data, policy):
    request_data["quote_date"] = request_data["effective_date"] = "2027-01-14"
    result = run(request_data, policy)
    assert result["numbers"]["quote_date"] == "2027-01-14"
    assert result["policy"]["policy_year"] == 7
    assert result["policy"]["policy_month"] == 8
    lookups = [json.loads(key) for key in result["provenance"]["rate_lookups"]]
    assert ["get_effective_interest_rate", ["2027-01"], {}] in lookups
    assert ["get_per_diem", [2027], {}] in lookups
    assert any(call[0] == "get_term_rate" and call[1][-1] == 7 for call in lookups)


def test_read_only_rate_guard_and_fingerprints():
    from suiteview.abrquote.automation_data import _Cursor
    evidence = []
    raw = SimpleNamespace(execute=lambda *args: None, fetchall=lambda: [(250,)])
    cursor = _Cursor(raw, evidence, "TERM")
    with pytest.raises(QuoteError, match="SELECT only"):
        cursor.execute("UPDATE rates SET amount=0")
    assert not evidence
    cursor.execute("SELECT admin_fee FROM [SV_ABR_STATE_VARIATIONS] WHERE state_abbr=?", ("TX",))
    assert cursor.fetchall() == [(250,)]
    assert evidence[0]["parameters"] == ["TX"]
    assert evidence[0]["row_count"] == 1
    assert len(evidence[0]["rows_sha256"]) == 64


@pytest.mark.parametrize("rows", [[], [(None,)]])
def test_missing_admin_fee_never_uses_ui_250_default(rows):
    from suiteview.abrquote.automation_data import _Cursor
    raw = SimpleNamespace(execute=lambda *args: None, fetchall=lambda: rows)
    cursor = _Cursor(raw, [], "UL")
    cursor.execute("SELECT admin_fee FROM [SV_ABR_STATE_VARIATIONS]")
    with pytest.raises(QuoteError):
        cursor.fetchall()


def test_reinsurance_warning_is_not_no_cession():
    import logging
    from suiteview.abrquote.automation_data import reject_lookup_warnings
    with pytest.raises(QuoteError, match="default result rejected"):
        with reject_lookup_warnings("suiteview.core.reinsurance"):
            logging.getLogger("suiteview.core.reinsurance").warning("simulated unavailable data")


def test_goal_seek_fallback_is_not_a_fitted_medical_assessment():
    from suiteview.abrquote.models.abr_data import MedicalAssessment
    with pytest.raises(QuoteError, match="did not fit ten_year_survival"):
        _validate_assessment_result(
            {"rider_type": "Critical", "five_year_survival": .6, "ten_year_survival": .4},
            MedicalAssessment(computed_survival_5yr=.6, computed_survival_10yr=.3),
        )


def test_live_adapter_uses_exact_inputs_and_no_policy_fallback(request_data, monkeypatch):
    calls = []
    def missing_policy(number, region, **kwargs):
        calls.append((number, region, kwargs))
        return ABRPolicyData(policy_number=number), None
    monkeypatch.setattr("suiteview.abrquote.core.abr_policy_service.build_abr_policy", missing_policy)
    with pytest.raises(QuoteError, match="manual/default policy is forbidden"):
        quote_abr(request_data)
    assert calls == [("SYNTHETIC", "CKPR", {"company_code": "01", "use_cache": False})]


def test_live_api_rejects_ambient_local_snapshot(request_data, monkeypatch):
    monkeypatch.setenv("SUITEVIEW_LOCAL_DATA", "1")
    with pytest.raises(QuoteError, match="local-data mode"):
        quote_abr(request_data)


def test_live_adapter_with_injected_external_reads(request_data, policy, monkeypatch):
    benefits = [SimpleNamespace(benefit_type_cd="#", benefit_subtype_cd="1",
                               cov_pha_nbr=1, issue_date=date(2020, 1, 15), cease_date=None)]
    pi = SimpleNamespace(
        is_active=True, status_code="10", base_issue_age=40, base_rate_class="N",
        age_at_maturity=75, billing_frequency=12, policy_year=7, policy_month=8,
        primary_insured_face_amount=100000, issue_date=date(2020, 1, 15),
        primary_insured_db_layers=[(100000, date(2055, 1, 15))],
        get_substandard_ratings=lambda *args: [],
        get_coverages=lambda: [SimpleNamespace(cov_pha_nbr=1, person_code="00")],
        get_benefits=lambda: benefits,
        data_item=lambda *args: "01",
    )
    monkeypatch.setattr("suiteview.abrquote.core.abr_policy_service.build_abr_policy",
                        lambda *a, **kw: (deepcopy(policy), pi))
    reinsurance_calls = []
    def reinsurers(*args):
        reinsurance_calls.append(args)
        return "(none)"
    monkeypatch.setattr("suiteview.core.reinsurance.fetch_reinsurer_list", reinsurers)
    db = Rates()
    closed = []
    db.close = lambda: closed.append(True)
    monkeypatch.setattr("suiteview.abrquote.automation_data.open_rate_database",
                        lambda product: (db, [{"synthetic": True}]))
    result = quote_abr(request_data)
    assert reinsurance_calls == [("SYNTHETIC", "01", date(2026, 9, 3))]
    assert closed == [True]
    assert result["provenance"]["rate_queries"] == [{"synthetic": True}]
    assert result["provenance"]["policy_source"]["policy_status"] == "10"
    benefits[0].cease_date = date(2026, 9, 2)
    with pytest.raises(QuoteError, match="not verified active"):
        quote_abr(request_data)
    assert closed == [True, True]
    pi.is_active = False
    with pytest.raises(QuoteError, match="not active"):
        quote_abr(request_data)


@pytest.mark.parametrize("medical_blocked", [False, True])
def test_resolver_derives_funding_instead_of_substituting_modal_premium(monkeypatch, medical_blocked):
    from tools.abrquote import resolve_inputs as resolver
    from suiteview.illustration.models.policy_data import IllustrationPolicyData
    from suiteview.illustration.models.calc_state import MonthlyState
    source = {"policy_number": "SYNTHETIC", "quote_date": "2026-09-03",
              "survival_5yr": .6, "survival_10yr": .4, "rider": "CT"}
    evidence = {
        "company_code": "01",
        "policy": {"product_type": "UL", "surrender_value": 1234, "valuation_date": "2026-08-19"},
        "source_values": {"is_active": True},
        "canonical_rate_observations": {"interest": ["2026-09", .0575]},
        "medical_assessment_status": "blocked" if medical_blocked else "calculated",
        "calculation_blockers": ["goal seek failed"] if medical_blocked else [],
    }
    monkeypatch.setattr(resolver, "inspect", lambda *args: evidence)
    ill_policy = IllustrationPolicyData(policy_number="SYNTHETIC", annual_premium=999)
    monkeypatch.setattr("suiteview.illustration.core.illustration_policy_service.build_illustration_data",
                        lambda *args, **kwargs: ill_policy)
    called = []
    def fund(policy, minimum_face_amount):
        assert policy.current_interest_rate == .0575
        assert minimum_face_amount == 25000
        return SimpleNamespace(
            premium=4000, regular_premium=4000, shadow_premium=None,
            premium_basis="regular", first_payment_date=date(2027, 6, 19),
            achieved_sv=1000, achieved_shadow=None, illustrated_rate=.0575,
            loan_retired=500, db_option_switched=True, max_partial=None,
            results=[MonthlyState(surrender_value=634, surrender_charge=100)],
        )
    monkeypatch.setattr("suiteview.illustration.core.abr_quote.run_abr_quote", fund)
    monkeypatch.setattr(resolver, "quote_abr",
                        lambda request: called.append(request) or {"status": "calculated", "html": "canonical"})
    result = resolver.resolve_inputs(source)
    assert result["request"]["options"]["level_annual_premium"] == 4000
    assert result["request"]["options"]["loan_payoff"] == 500
    assert result["request"]["options"]["min_face_amount"] == 25000
    assert result["request"]["options"]["surrender_value"] == 634
    assert result["output"]["provenance"]["financial_derivations"]["surrender_value"]["gross_loaded_value"] == 1234
    assert bool(called) is not medical_blocked
    assert result["output"]["status"] == ("blocked" if medical_blocked else "calculated")
    assert result["funding"]["status"] == "funding_input_calculated_not_final_abr_quote"
    assert result["output"]["inputs"] == result["request"]


def test_resolver_cli_rejects_source_tree_output_before_lookup(monkeypatch):
    from tools.abrquote import resolve_inputs as resolver
    import sys
    monkeypatch.setattr(sys, "argv", ["resolve_inputs.py", "--input", "unused.json",
                                     "--output", str(resolver.ROOT)])
    monkeypatch.setattr(resolver, "resolve_inputs",
                        lambda *args: pytest.fail("Source-tree destination must fail before lookup"))
    with pytest.raises(SystemExit) as error:
        resolver.main()
    assert error.value.code == 2


@pytest.mark.parametrize("paying,suspense,expected", [
    ("22", "0", True), ("21", 0, True), ("22", None, False),
    ("22", "2", False), ("99", "0", False), ("54", "0", False),
    ("", "0", False), ("11", "0", False),
])
def test_activity_uses_actual_status_fields_without_fabricated_defaults(paying, suspense, expected):
    from suiteview.abrquote.automation import policy_activity
    fields = {"PRM_PAY_STA_REA_CD": paying, "SUS_CD": suspense}
    pi = SimpleNamespace(status_code="", is_active=False,
                         data_item=lambda table, field: fields.get(field))
    result = policy_activity(pi)
    assert result["verified_active"] is expected
    assert "status_code" not in result


def test_dual_survival_boundary_uses_relative_horizons_and_nonnegative_rating(monkeypatch):
    from suiteview.abrquote.core.mortality_engine import MortalityEngine
    from suiteview.abrquote.models.abr_data import MortalityParams
    engine = MortalityEngine(MortalityParams(
        issue_age=40, policy_month=87, table_rating_2=-1,
        table_2_start_month=147, table_2_last_month=206,
    ))
    assert engine._apply_table_rating(.01, 147)[0] == .01
    engine.params.table_rating_2 = 4
    assert engine._apply_table_rating(.01, 146)[0] == .01
    assert engine._apply_table_rating(.01, 147)[0] == .02
    assert engine._apply_table_rating(.01, 206)[0] == .02
    assert engine._apply_table_rating(.01, 207)[0] == .01
    monkeypatch.setattr(engine, "compute_monthly_rates", lambda: [.01] * 120)
    assert engine.compute_survival_probability(5) == pytest.approx(.99 ** 60)
    assert engine.compute_survival_probability(10) == pytest.approx(.99 ** 120)


@pytest.mark.parametrize("amount", [0, 1234.56])
def test_abr_surrender_reads_existing_monthliversary_without_undefined_table_probe(amount):
    from suiteview.abrquote.core.abr_policy_service import _read_surrender_value
    class Policy:
        def data_item(self, table, field):
            assert (table, field) == ("LH_POL_MVRY_VAL", "CSV_AMT")
            return amount

        @property
        def cash_surrender_value(self):
            pytest.fail("Unnecessary legacy TH_POL_MVRY_VAL probe")
    assert _read_surrender_value(Policy()) == amount


def test_resolver_cli_pins_failure_json_for_review(tmp_path, monkeypatch):
    from tools.abrquote import resolve_inputs as resolver
    import sys
    source = tmp_path / "invalid.json"
    source.write_text("{invalid", encoding="utf-8")
    destination = tmp_path / "WorkOps_Manager" / "workspace" / "albert" / "case"
    monkeypatch.setattr(resolver, "ROOT", tmp_path / "SuiteViewP")
    monkeypatch.setattr(sys, "argv", ["resolve_inputs.py", "--input", str(source),
                                     "--output", str(destination)])
    assert resolver.main() == 1
    output = json.loads((destination / "output.json").read_text())
    assert output["status"] == "error"
    assert output["needs_review"] is True
    assert output["html"] is None
    assert output["quote_issued"] is False
    assert output["error_type"] == "JSONDecodeError"
    assert (destination / "manifest.json").exists()


def test_canonical_ui_proceeds_with_unattainable_target_but_keeps_attained_value(
        request_data, policy, monkeypatch):
    from suiteview.abrquote.automation import _assessment_port
    from suiteview.abrquote.core.assessment_solver import AssessmentInputs, solve_substandard
    request_data["assessment"] = {
        "rider_type": "Critical", "five_year_survival": .9, "ten_year_survival": .899,
    }
    with using_quote_database(Rates()):
        solved = solve_substandard(
            policy,
            AssessmentInputs(
                rider_type="Critical",
                use_five_year=True,
                use_ten_year=True,
                five_year_survival=.9,
                ten_year_survival=.899,
            ),
        )
        with pytest.raises(QuoteError, match="Nonnegative mortality boundary") as error:
            _assessment_port(policy, QuoteRequest.from_dict(request_data))
    assert solved.assessment.ten_year_survival == .899
    assert solved.assessment.derived_table_rating_10yr == 0
    assert solved.assessment.computed_survival_10yr < .899
    assert error.value.details["ui_permits_continuation"] is True
    assert error.value.details["exact_fit"] is False


def test_boundary_guard_prevents_new_quote_without_replacing_source_targets(request_data, policy):
    request_data["assessment"] = {
        "rider_type": "Critical", "five_year_survival": .9, "ten_year_survival": .899,
    }
    original = deepcopy(request_data)
    with pytest.raises(QuoteError, match="Nonnegative mortality boundary") as error:
        run(request_data, policy)
    assert error.value.details["requested_10yr"] == .899
    assert error.value.details["attained_10yr"] < .899
    assert request_data == original
