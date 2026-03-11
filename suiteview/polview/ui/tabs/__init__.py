"""
Tab widgets for the SuiteView right-panel tabbed interface.

Each tab module contains one QWidget subclass that populates
a single tab in the main window's QTabWidget.
"""

from .coverages_tab import CoveragesTab
from .policy_tab import PolicyTab
from .targets_tab import TargetsAccumulatorsTab
from .persons_tab import PersonsTab
from .adv_prod_tab import AdvProdValuesTab
from .activity_tab import ActivityTab
from .dividends_tab import DividendsTab
from .loans_tab import LoansTab
from .raw_table_tab import RawTableTab
from .policy_list_tab import PolicyListWindow
from .policy_support_tab import PolicySupportTab
from .reinsurance_tab import ReinsuranceTab

__all__ = [
    "CoveragesTab",
    "PolicyTab",
    "TargetsAccumulatorsTab",
    "PersonsTab",
    "AdvProdValuesTab",
    "ActivityTab",
    "DividendsTab",
    "LoansTab",
    "RawTableTab",
    "PolicyListWindow",
    "PolicySupportTab",
    "ReinsuranceTab",
]
