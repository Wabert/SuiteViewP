"""ISWL RPU service façade: load a policy's snapshot, run and check it."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from suiteview.illustration.core.inforce_check import CheckLine
from suiteview.illustration.core.iswl_rpu.engine import ISWLRPUEngine
from suiteview.illustration.core.iswl_rpu.inforce_checks import inforce_checks
from suiteview.illustration.core.iswl_rpu.policy_loader import build_iswl_rpu_policy, is_iswl_rpu
from suiteview.illustration.models.iswl_rpu import ISWLRPUInputs, ISWLRPUPolicy, ISWLRPUResult


@dataclass
class ISWLRPUBasis:
    """A loaded ISWL reduced paid-up policy (its NSP basis is on the record)."""

    policy: ISWLRPUPolicy

    def engine(self, inputs: Optional[ISWLRPUInputs] = None) -> ISWLRPUEngine:
        return ISWLRPUEngine(self.policy, inputs)

    def run(self, inputs: Optional[ISWLRPUInputs] = None) -> ISWLRPUResult:
        return self.engine(inputs).run()

    def checks(self) -> List[CheckLine]:
        return inforce_checks(self.policy, ISWLRPUEngine(self.policy))


def load_iswl_rpu_basis(pi, region: str = "CKPR") -> ISWLRPUBasis:
    """Snapshot for a loaded PolicyInformation."""
    return ISWLRPUBasis(build_iswl_rpu_policy(pi, region=region))


__all__ = ["ISWLRPUBasis", "is_iswl_rpu", "load_iswl_rpu_basis"]
