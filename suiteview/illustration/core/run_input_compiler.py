"""Compile plain Illustration UI drafts into engine inputs.

Widgets expose :meth:`read_draft` and :meth:`render_draft`; callers use this
module to turn those plain drafts into :class:`IllustrationInputSet`,
:class:`IllustrationOptions` and solve controls.  The draft stores JSON-safe
case input state so Run Values, Compare and saved cases can share one boundary
instead of reaching into live widgets.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Optional

from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    IllustrationOptions,
    IssueOverrideSet,
    RollbackOverrideSet,
)


@dataclass(frozen=True)
class ControlDraft:
    """Compiled run controls read from the inputs widget."""

    options: IllustrationOptions
    stop_on_lapse: bool
    run_from_issue: bool = False
    abr_quote: bool = False
    abr_minimum_face_amount: float | None = None


@dataclass(frozen=True)
class InputDraft:
    """Plain, restorable input state plus compiled engine requests."""

    case_inputs: dict = field(default_factory=dict)
    input_set: IllustrationInputSet = field(default_factory=IllustrationInputSet)
    controls: ControlDraft = field(
        default_factory=lambda: ControlDraft(IllustrationOptions(), True)
    )
    inforce_overrides: object | None = None
    issue_overrides: IssueOverrideSet | None = None
    rollback_overrides: RollbackOverrideSet | None = None
    max_level: Optional[dict] = None
    min_level: Optional[dict] = None
    shadow_level: Optional[dict] = None
    target_premium: Optional[dict] = None
    duration: Optional[dict] = None
    lumpsum_to_next: bool = False
    loan_payoffs: tuple[dict, ...] = ()


def compile_input_set(draft: InputDraft) -> IllustrationInputSet:
    """Return an isolated engine input set for a draft."""

    return copy.deepcopy(draft.input_set)


def compile_options(draft: InputDraft) -> IllustrationOptions:
    """Return an isolated options object for a draft."""

    return copy.deepcopy(draft.controls.options)


def apply_basis_mode(draft: InputDraft, *, run_from_issue: bool | None = None) -> InputDraft:
    """Return ``draft`` with the run-from-issue mode adjusted.

    This intentionally changes only the plain control draft; widget rendering is
    performed by ``render_draft`` at the UI boundary.
    """

    if run_from_issue is None or run_from_issue == draft.controls.run_from_issue:
        return draft
    controls = ControlDraft(
        options=draft.controls.options,
        stop_on_lapse=draft.controls.stop_on_lapse,
        run_from_issue=run_from_issue,
        abr_quote=draft.controls.abr_quote,
        abr_minimum_face_amount=draft.controls.abr_minimum_face_amount,
    )
    return InputDraft(
        case_inputs=copy.deepcopy(draft.case_inputs),
        input_set=copy.deepcopy(draft.input_set),
        controls=controls,
        inforce_overrides=copy.deepcopy(draft.inforce_overrides),
        issue_overrides=copy.deepcopy(draft.issue_overrides),
        rollback_overrides=copy.deepcopy(draft.rollback_overrides),
        max_level=copy.deepcopy(draft.max_level),
        min_level=copy.deepcopy(draft.min_level),
        shadow_level=copy.deepcopy(draft.shadow_level),
        target_premium=copy.deepcopy(draft.target_premium),
        duration=copy.deepcopy(draft.duration),
        lumpsum_to_next=draft.lumpsum_to_next,
        loan_payoffs=copy.deepcopy(draft.loan_payoffs),
    )


def clear_rollback_draft(draft: InputDraft) -> InputDraft:
    """Return ``draft`` with Edit Record assumptions removed.

    If rollback mode saved the prior live inputs, restore those JSON-safe input
    rows so disabling the option behaves like ``set_value_rollback(None)`` on a
    visible widget.
    """

    case_inputs = copy.deepcopy(draft.case_inputs)
    live_inputs = case_inputs.get("rollback_live_inputs")
    if isinstance(live_inputs, dict):
        for key, value in live_inputs.items():
            case_inputs[key] = copy.deepcopy(value)
    case_inputs["value_rollback"] = None
    case_inputs["rollback_live_inputs"] = None
    return replace(
        draft,
        case_inputs=case_inputs,
        rollback_overrides=None,
    )
