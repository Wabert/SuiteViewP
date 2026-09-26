from __future__ import annotations

import inspect

from suiteview.audit.query_object_viewer.contracts import MIXIN_CONTRACTS
from suiteview.audit.query_object_viewer_window import QueryObjectViewerWindow


def test_query_object_viewer_mixin_contract_attributes_are_initialized() -> None:
    init_source = inspect.getsource(QueryObjectViewerWindow.__init__)
    for mixin_name, attrs in MIXIN_CONTRACTS.items():
        missing = sorted(
            attr for attr in attrs
            if f"self.{attr}" not in init_source
        )
        assert missing == [], f"{mixin_name} missing {missing}"
    assert "self.browser_services" in init_source
