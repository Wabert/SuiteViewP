"""Indeterminate premium term service façade: load a policy's snapshot and rates, run and check it."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from suiteview.illustration.core.inforce_check import CheckLine
from suiteview.illustration.core.term.engine import TermEngine
from suiteview.illustration.core.term.inforce_checks import inforce_checks
from suiteview.illustration.core.term.policy_loader import build_term_policy, is_indeterminate_term
from suiteview.illustration.core.term.rates import TermRates, load_term_rates
from suiteview.illustration.models.term import TermInputs, TermPolicy, TermResult


@dataclass
class TermBasis:
    """A loaded indeterminate premium term policy with its rates."""

    policy: TermPolicy
    rates: TermRates

    def engine(self, inputs: Optional[TermInputs] = None) -> TermEngine:
        return TermEngine(self.policy, self.rates, inputs)

    def run(self, inputs: Optional[TermInputs] = None) -> TermResult:
        return self.engine(inputs).run()

    def checks(self) -> List[CheckLine]:
        return inforce_checks(self.policy, self.rates, TermEngine(self.policy, self.rates))


def load_term_basis(pi, region: str = "CKPR", repo=None) -> TermBasis:
    """Snapshot and rates for a loaded PolicyInformation."""
    policy = build_term_policy(pi, region=region)
    return TermBasis(policy, load_term_rates(policy, repo=repo))


__all__ = ["TermBasis", "is_indeterminate_term", "load_term_basis"]
