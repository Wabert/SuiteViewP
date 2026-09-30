"""Par WL service façade: load a policy's snapshot and rates, run and check it."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from suiteview.illustration.core.parwl.engine import ParWLEngine
from suiteview.illustration.core.inforce_check import CheckLine
from suiteview.illustration.core.parwl.inforce_checks import inforce_checks
from suiteview.illustration.core.parwl.policy_loader import build_parwl_policy, is_par_whole_life
from suiteview.illustration.core.parwl.rates import ParWLRates, load_parwl_rates
from suiteview.illustration.models.parwl import ParWLInputs, ParWLPolicy, ParWLResult


@dataclass
class ParWLBasis:
    """A loaded par WL policy with its rates."""

    policy: ParWLPolicy
    rates: ParWLRates

    def engine(self, inputs: Optional[ParWLInputs] = None) -> ParWLEngine:
        return ParWLEngine(self.policy, self.rates, inputs)

    def run(self, inputs: Optional[ParWLInputs] = None) -> ParWLResult:
        return self.engine(inputs).run()

    def checks(self) -> List[CheckLine]:
        return inforce_checks(self.policy, self.rates, ParWLEngine(self.policy, self.rates))


def load_parwl_basis(pi, region: str = "CKPR", repo=None) -> ParWLBasis:
    """Snapshot and rates for a loaded PolicyInformation."""
    policy = build_parwl_policy(pi, region=region)
    return ParWLBasis(policy, load_parwl_rates(policy, repo=repo))


__all__ = ["ParWLBasis", "is_par_whole_life", "load_parwl_basis"]
