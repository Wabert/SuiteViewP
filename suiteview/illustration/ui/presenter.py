"""Plain presenter state for the Illustration window.

The window remains the Qt boundary.  It stores only drafts and render snapshots
per policy; live widgets are created/rendered as needed and are never the source
of truth in ``_session_states``.
"""

from __future__ import annotations

from dataclasses import dataclass

from suiteview.illustration.core.run_input_compiler import InputDraft


@dataclass
class IllustrationSessionState:
    """Session-only policy state without live widget references."""

    input_draft: InputDraft | None = None
    values: dict | None = None
    report: dict | None = None
    status: str | None = None
    scenario: object | None = None
    policy_data: object | None = None


class IllustrationPresenter:
    """Typed UI-routing decisions that previously depended on ``sender()``."""

    @staticmethod
    def is_active_inputs_event(active_tab, source_tab) -> bool:
        return source_tab is None or source_tab is active_tab
