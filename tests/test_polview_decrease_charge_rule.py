import pytest
from types import SimpleNamespace

from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.ui.tabs.policy_tab import PolicyTab


def _policy_with_rule(raw):
    policy = object.__new__(PolicyInformation)
    calls = []

    def data_item(table, field, *_args):
        calls.append((table, field))
        return raw

    policy.data_item = data_item
    return policy, calls


@pytest.mark.parametrize(
    ("raw", "rule", "allowed"),
    [("1", "1", True), ("0", "0", False), (" ", "", None), ("\x00", "", None),
     (None, "", None), ("7", "7", None)],
)
def test_decrease_charge_rule_reads_th_non_trd_pol(raw, rule, allowed):
    policy, calls = _policy_with_rule(raw)

    assert policy.support.decrease_charge_rule == rule
    assert policy.support.decrease_charge_allowed is allowed
    assert set(calls) == {("TH_NON_TRD_POL", "DECR_CHRG_ALLOW")}


class _FakePolicy:
    company_code = "01"
    policy_number = "U0000001"
    base_plancode = "1U145500"
    product_line_code = "U"
    issue_state_code = ""
    is_advanced_product = True
    grace_period_expiry_date = None
    paid_to_date = None
    last_anniversary = None
    next_bill_date = None

    def __init__(self, rule):
        self.decrease_charge_rule = rule
        self.coverages = SimpleNamespace(base_plancode=self.base_plancode)
        self.product = self
        self.status = self
        self.activity = self
        self.billing = self
        self.support = self

    @staticmethod
    def data_item(*_args):
        return None


@pytest.mark.parametrize(
    ("rule", "shown", "text"),
    [("0", True, "0 - No charge on decrease"),
     ("1", True, "1 - Charge on decrease"),
     ("", False, "")],
)
def test_policy_tab_shows_decrease_charge_rule_only_when_present(qtbot, rule, shown, text):
    tab = PolicyTab()
    qtbot.addWidget(tab)
    tab.show()

    tab._populate_column1_from_policy(_FakePolicy(rule), {})

    assert tab.col1.get_value("decr_chrg_rule") == text
    assert tab.col1._labels["decr_chrg_rule"].isVisible() is shown
    assert tab.col1._fields["decr_chrg_rule"].isVisible() is shown


def test_policy_tab_hides_prior_policy_decrease_charge_rule(qtbot):
    tab = PolicyTab()
    qtbot.addWidget(tab)
    tab.show()

    tab._populate_column1_from_policy(_FakePolicy("0"), {})
    tab._populate_column1_from_policy(_FakePolicy(""), {})

    assert tab.col1.get_value("decr_chrg_rule") == ""
    assert not tab.col1._fields["decr_chrg_rule"].isVisible()
