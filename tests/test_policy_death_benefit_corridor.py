"""Total death benefit must respect the 7702 corridor.

CyberLife/VBA rule (frmAudit "CV * CORR% > Specified Amount + OPTDB"):

    corridor DB = ROUND(LH_POL_MVRY_VAL.CSV_AMT * LH_NON_TRD_POL.CDR_PCT / 100, 2)
    total DB    = MAX(face + DB-option amount, corridor DB)
"""
from decimal import Decimal
from types import SimpleNamespace

from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.models.policy_sections.coverages import CoveragesSection


class _StubCoverages(CoveragesSection):
    @property
    def primary_insured_face_amount(self):
        return self.policy._face


class _StubPolicy(PolicyInformation):
    """PolicyInformation with only the death-benefit inputs stubbed out."""

    def __init__(self, face, db_option="1", account_value=None,
                 corridor_pct=None, advanced=True, premiums_paid=Decimal("0")):
        self._face = Decimal(face)
        self._db_option = db_option
        self._account_value = None if account_value is None else Decimal(account_value)
        self._corridor_pct = None if corridor_pct is None else Decimal(corridor_pct)
        self._advanced = advanced
        self._premiums_paid = Decimal(premiums_paid)
        self._sections = {
            "coverages": _StubCoverages(self),
            "product": SimpleNamespace(
                db_option_code=self._db_option,
                is_advanced_product=self._advanced,
                # Mirrors the real property: missing CDR_PCT defaults to 100%.
                corridor_percent=(
                    self._corridor_pct if self._corridor_pct is not None
                    else Decimal("100")
                ),
            ),
            "values": SimpleNamespace(mv_av=self.mv_av, accumulation_value=self._account_value),
            "billing": SimpleNamespace(total_premiums_paid=self._premiums_paid),
        }

    def mv_av(self, index: int = 0):
        return self._account_value


def test_corridor_raises_death_benefit_above_face():
    policy = _StubPolicy(face=100_000, account_value=50_000, corridor_pct=250)

    assert policy.coverages.standard_death_benefit == Decimal("100000")
    assert policy.coverages.corridor_death_benefit == Decimal("125000.00")
    assert policy.coverages.is_in_corridor
    assert policy.coverages.corridor_amount == Decimal("25000.00")
    assert policy.coverages.total_death_benefit == Decimal("125000.00")


def test_face_wins_when_corridor_is_lower():
    policy = _StubPolicy(face=173_373, account_value=20_000, corridor_pct=250)

    assert policy.coverages.corridor_death_benefit == Decimal("50000.00")
    assert not policy.coverages.is_in_corridor
    assert policy.coverages.corridor_amount == Decimal("0")
    assert policy.coverages.total_death_benefit == Decimal("173373")


def test_corridor_compared_against_option_b_death_benefit():
    # Option B already adds the AV, so the corridor must clear face + AV.
    policy = _StubPolicy(face=100_000, db_option="2", account_value=50_000,
                         corridor_pct=250)

    assert policy.coverages.standard_death_benefit == Decimal("150000")
    assert policy.coverages.corridor_death_benefit == Decimal("125000.00")
    assert not policy.coverages.is_in_corridor
    assert policy.coverages.total_death_benefit == Decimal("150000")


def test_corridor_compared_against_option_c_death_benefit():
    policy = _StubPolicy(face=100_000, db_option="3", account_value=50_000,
                         corridor_pct=250, premiums_paid=60_000)

    assert policy.coverages.standard_death_benefit == Decimal("160000")
    assert policy.coverages.total_death_benefit == Decimal("160000")


def test_corridor_percent_is_rounded_to_the_cent():
    policy = _StubPolicy(face=10_000, account_value=Decimal("33333.33"),
                         corridor_pct=Decimal("182.500"))

    # 33333.33 * 1.825 = 60833.32725 -> 60,833.33
    assert policy.coverages.corridor_death_benefit == Decimal("60833.33")
    assert policy.coverages.total_death_benefit == Decimal("60833.33")


def test_traditional_product_has_no_corridor():
    policy = _StubPolicy(face=100_000, account_value=50_000, corridor_pct=250,
                         advanced=False)

    assert policy.coverages.corridor_death_benefit is None
    assert not policy.coverages.is_in_corridor
    assert policy.coverages.total_death_benefit == Decimal("100000")


def test_no_account_value_means_no_corridor():
    policy = _StubPolicy(face=100_000, account_value=None, corridor_pct=250)

    assert policy.coverages.corridor_death_benefit is None
    assert policy.coverages.total_death_benefit == Decimal("100000")
