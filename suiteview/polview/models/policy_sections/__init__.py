"""PolicyInformation section objects."""

from .identity import IdentitySection
from .status import StatusSection
from .product import ProductSection
from .billing import BillingSection
from .coverages import CoveragesSection
from .benefits import BenefitsSection
from .loans import LoansSection
from .values import ValuesSection
from .targets import TargetsSection
from .dividends import DividendsSection
from .persons import PersonsSection
from .agents import AgentsSection
from .activity import ActivitySection
from .rates import RatesSection
from .support import SupportSection

__all__ = [
    'IdentitySection',
    'StatusSection',
    'ProductSection',
    'BillingSection',
    'CoveragesSection',
    'BenefitsSection',
    'LoansSection',
    'ValuesSection',
    'TargetsSection',
    'DividendsSection',
    'PersonsSection',
    'AgentsSection',
    'ActivitySection',
    'RatesSection',
    'SupportSection',
]
