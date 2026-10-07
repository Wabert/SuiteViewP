"""Supplemental benefits past their cease date are not charged (CyberLife LH_SPM_BNF).

CyberLife moves BNF_CEA_DT to the termination date when a benefit ends before its
pay-up date and keeps the original in BNF_OGN_CEA_DT. Matrix evidence (10/3/2026):
1U143900 U1004448 (CCVR A1 ceased 2020-07-12, pay-up 2082) and S6600857 (PW4 ceased
2022-07-05, pay-up 2027) are charged nothing by CyberLife.
"""
from datetime import date
from types import SimpleNamespace

from suiteview.illustration.core.illustration_policy_service import build_benefits
from suiteview.illustration.core.monthly_deduction import _calculate_policy_benefit_charges
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData

AS_OF = date(2026, 9, 12)


def _raw_benefit(type_cd, subtype_cd, *, cease, pay_up, coi_rate=0.51, units=25.0, renewal="1", original=None):
    return SimpleNamespace(
        cov_pha_nbr=1, form_number="CCVR", benefit_type_cd=type_cd, benefit_subtype_cd=subtype_cd,
        benefit_amount=units * 1000.0, units=units, vpu=1000.0, issue_date=date(2014, 5, 12),
        issue_age=53, pay_up_date=pay_up, cease_date=cease, orig_cease_date=original or pay_up,
        rating_factor=1.0, coi_rate=coi_rate, renewal_indicator=renewal)


def _assembly(*raw):
    return build_benefits(SimpleNamespace(raw_benefits=list(raw), as_of_date=AS_OF))


def test_ccv_ceased_before_pay_up_is_inactive_and_marks_ccv_ceased():
    """U1004448: CCVR cease 2020-07-12 (terminated), pay-up 2082-05-12."""
    assembly = _assembly(_raw_benefit("A", "1", cease=date(2020, 7, 12), pay_up=date(2082, 5, 12)))

    assert len(assembly.benefits) == 1
    assert assembly.benefits[0].is_active is False
    assert assembly.ccv_active is False
    assert assembly.ccv_ceased is True


def test_benefit_in_force_stays_active():
    assembly = _assembly(_raw_benefit("A", "1", cease=date(2082, 5, 12), pay_up=date(2082, 5, 12)))

    assert assembly.benefits[0].is_active is True
    assert assembly.ccv_active is True
    assert assembly.ccv_ceased is False


def test_benefit_ceasing_on_as_of_date_is_still_active():
    assembly = _assembly(_raw_benefit("4", "0", cease=AS_OF, pay_up=date(2027, 7, 5)))

    assert assembly.benefits[0].is_active is True


def test_benefit_past_pay_up_is_still_dropped():
    assembly = _assembly(_raw_benefit("4", "0", cease=date(2026, 7, 5), pay_up=date(2026, 7, 5)))

    assert assembly.benefits == []


def test_cease_extended_past_original_charges_to_the_extended_cease():
    """V8634366: ADB2 pay-up = original cease 2025-10-10, cease extended to 2026-10-10;
    CyberLife still charges it at 2026-09-10."""
    assembly = _assembly(_raw_benefit(
        "1", "2", cease=date(2026, 10, 10), pay_up=date(2025, 10, 10), original=date(2025, 10, 10)))

    assert len(assembly.benefits) == 1
    assert assembly.benefits[0].pay_up_date == date(2026, 10, 10)
    assert assembly.benefits[0].is_active is True


def test_original_cease_after_pay_up_still_stops_at_pay_up():
    """UE124240: ULDW91 pay-up 2026-06-29, original cease 2027-06-29; not charged after pay-up."""
    assembly = _assembly(_raw_benefit(
        "3", "9", cease=date(2027, 6, 29), pay_up=date(2026, 6, 29), original=date(2027, 6, 29)))

    assert assembly.benefits == []


def test_future_cease_before_pay_up_ends_the_charge_in_projection():
    """S4600372: PW4 cease 2026-05-20, pay-up 2031-05-20. CyberLife charged 0.60 on
    2026-04-20 and nothing from the 2026-05-20 monthliversary on."""
    raw = _raw_benefit("4", "0", cease=date(2026, 5, 20), pay_up=date(2031, 5, 20),
                       coi_rate=0.24, units=2.5)
    benefit = build_benefits(SimpleNamespace(raw_benefits=[raw], as_of_date=date(2026, 3, 20))).benefits[0]
    policy = IllustrationPolicyData(plancode="1S133A29", benefits=[benefit])

    assert benefit.is_active is True
    assert benefit.pay_up_date == date(2026, 5, 20)

    def charge(on):
        return _calculate_policy_benefit_charges(
            20.0, 0.0, policy, PlancodeConfig(), IllustrationRates(), 42, 0.0, on).benefit_charges

    assert charge(date(2026, 4, 20)) == 0.6
    assert charge(date(2026, 5, 20)) == 0.0
    assert charge(date(2026, 6, 20)) == 0.0


def test_ceased_benefit_is_not_charged_in_the_monthly_deduction():
    """S6600857: the PW4 (ceased 2022, pay-up 2027) adds nothing; the ADB still charges."""
    assembly = _assembly(
        _raw_benefit("1", "2", cease=date(2032, 7, 5), pay_up=date(2032, 7, 5), coi_rate=0.11),
        _raw_benefit("4", "0", cease=date(2022, 7, 5), pay_up=date(2027, 7, 5), coi_rate=0.29, units=2.5),
    )
    policy = IllustrationPolicyData(plancode="1S133229", benefits=assembly.benefits)

    result = _calculate_policy_benefit_charges(
        30.73, 0.0, policy, PlancodeConfig(), IllustrationRates(), 41, 0.0, AS_OF)

    assert result.benefit_charge_detail == {"12": 2.75}
    assert result.benefit_charges == 2.75


def test_non_renewing_stipulated_waiver_is_charged_past_pay_up_to_cease():
    """26-000321574 (1U1F4M00): WPMP 4M, RNL_RT_IND 0, pay-up 2026-01-12, cease 2031-01-12.
    CyberLife's MD at 2026-09-12 carries 31.140 units x 0.30 = 9.34 for it."""
    assembly = _assembly(_raw_benefit(
        "4", "M", cease=date(2031, 1, 12), pay_up=date(2026, 1, 12), original=date(2031, 1, 12),
        coi_rate=0.30, units=31.14, renewal="0"))
    benefit = assembly.benefits[0]
    policy = IllustrationPolicyData(plancode="1U1F4M00", benefits=assembly.benefits)

    assert benefit.is_active is True
    assert benefit.pay_up_date == date(2031, 1, 12)

    result = _calculate_policy_benefit_charges(
        110.0, 0.0, policy, PlancodeConfig(), IllustrationRates(), 16, 0.0, AS_OF)

    assert result.benefit_charge_detail == {"4M": 9.34}
    assert result.benefit_rates == {"4M": 0.3}


def test_non_renewing_stipulated_waiver_still_stops_at_cease():
    assembly = _assembly(_raw_benefit(
        "4", "M", cease=date(2031, 1, 12), pay_up=date(2026, 1, 12), original=date(2031, 1, 12),
        coi_rate=0.30, units=31.14, renewal="0"))
    policy = IllustrationPolicyData(plancode="1U1F4M00", benefits=assembly.benefits)

    def charge(on):
        return _calculate_policy_benefit_charges(
            110.0, 0.0, policy, PlancodeConfig(), IllustrationRates(), 17, 0.0, on).benefit_charges

    assert charge(date(2030, 12, 12)) == 9.34
    assert charge(date(2031, 1, 12)) == 0.0


def test_renewing_stipulated_waiver_still_stops_at_pay_up():
    """NU1FU200 26-000175165: WPMP 4M RNL_RT_IND 1, pay-up 2026-06-09, cease 2031-06-09;
    CyberLife charges nothing for it at 2026-09-09."""
    assembly = _assembly(_raw_benefit(
        "4", "M", cease=date(2031, 6, 9), pay_up=date(2026, 6, 9), original=date(2031, 6, 9),
        coi_rate=0.12, units=14.5, renewal="1"))

    assert assembly.benefits == []


def test_non_renewing_non_waiver_still_stops_at_pay_up():
    assembly = _assembly(_raw_benefit(
        "2", "4", cease=date(2032, 9, 8), pay_up=date(2026, 6, 8), original=date(2032, 9, 8),
        coi_rate=0.05, units=50.0, renewal="0"))

    assert assembly.benefits == []
