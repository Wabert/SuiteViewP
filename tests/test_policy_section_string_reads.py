"""Name-based readers see PolicyInformation facts that now live on section objects.

Each case failed after the section split: ``getattr(pi, "product_type", "")``
silently returned the default because the fact moved to ``pi.product``.
"""

from contextlib import nullcontext
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import illustration_policy_service, input_context
from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.services import glp_exception, policy_insights, reinstatement


class _Data:
    exists = True
    policy_number = "U0000001"
    company_code = "01"
    system_code = "I"
    region = "CKPR"
    policy_id = "ID1"

    @staticmethod
    def cached_reads_only():
        return nullcontext()


def _pi(**sections) -> PolicyInformation:
    """A PolicyInformation whose sections are fixed stand-ins (no database)."""
    pi = object.__new__(PolicyInformation)
    pi._data = _Data()
    pi._sections = dict(sections)
    return pi


def _ul_rules(**flags):
    return SimpleNamespace(supports_reinstatement=True, supports_glp_exception=True,
                           is_advanced=True, rate_family="UL", **flags)


def test_reinstatement_sees_ul_rules_and_lapse_entry():
    pi = _pi(
        product=SimpleNamespace(product_rules=_ul_rules(), product_type="UL"),
        status=SimpleNamespace(last_entry_code="Q"),
        activity=SimpleNamespace(terminate_date=date(2024, 7, 15), issue_date=date(2010, 1, 15),
                                 get_live_transactions=lambda codes: []),
    )
    assert reinstatement.is_ul_policy(pi)
    eligibility = reinstatement.reinstatement_eligibility(pi)
    assert eligibility.last_entry_code == "Q" and eligibility.eligible
    assert reinstatement.find_lapse_date(pi) == (date(2024, 7, 15), None)


def test_glp_exception_eligibility_reads_product_section():
    pi = _pi(product=SimpleNamespace(
        product_rules=_ul_rules(), product_type="UL",
        def_of_life_ins_code="2", def_of_life_ins_description="DEFRA Guideline Premium",
    ))
    assert glp_exception.is_glp_exception_eligible(pi)


def test_policy_summary_reader_resolves_section_facts():
    pi = _pi(product=SimpleNamespace(product_type="UL"),
             status=SimpleNamespace(premium_pay_status_code="22"))
    read = policy_insights._Reader(pi)
    assert read.get("product_type") == "UL"
    assert read.get("premium_pay_status_code") == "22"
    assert read.pending == []


def test_illustration_loan_basis_reads_loan_rates():
    loans = SimpleNamespace(
        variable_loan_charge_rate=7.4, fixed_loan_interest_rate=6.0,
        preferred_loan_interest_rate=4.0, total_regular_loan_principal=0,
        total_regular_loan_accrued=0, total_preferred_loan_principal=0,
        total_preferred_loan_accrued=0, preferred_loans_available=False,
        total_variable_loan_principal=0, total_variable_loan_accrued=0,
    )
    basis = illustration_policy_service._loan_basis(_pi(loans=loans))
    assert basis["regular_loan_charge_rate"] == 0.06
    assert basis["preferred_loan_charge_rate"] == 0.04
    assert basis["variable_loan_charge_rate"] == pytest.approx(0.074)


def test_input_context_reads_status_and_timing_from_sections():
    pi = _pi(
        status=SimpleNamespace(status_code="", suspense_code="2", premium_pay_status_code="22"),
        activity=SimpleNamespace(issue_date=date(2010, 1, 15), policy_year=17),
        coverages=SimpleNamespace(base_issue_age=40, age_at_maturity=121, attained_age=56),
        values=SimpleNamespace(valuation_date=date(2026, 8, 15)),
    )
    assert input_context.is_suspended(pi) is True
    timing = input_context._policy_timing(pi)
    assert timing.issue_date == date(2010, 1, 15)
    assert timing.issue_age == 40
    assert timing.valuation_date == date(2026, 8, 15)
    assert timing.attained_age == 56


def test_facade_identity_defaults_and_row_filter_signature():
    class Unresolved(_Data):
        policy_id = None
        company_code = None

        @staticmethod
        def get_rows_where(table_name, filter_field, filter_value):
            return [(table_name, filter_field, filter_value)]

    pi = _pi()
    pi._data = Unresolved()
    assert pi.policy_id == ""
    assert pi.company_code == ""
    assert pi.get_rows_where("LH_COV_PHA", "COV_PHA_NBR", 1) == [("LH_COV_PHA", "COV_PHA_NBR", 1)]
