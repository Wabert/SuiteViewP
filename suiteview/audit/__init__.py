"""
SuiteView Audit Tool (v2) — faithful VBA replica.
"""

__version__ = "2.0.0"

from suiteview.core.db2_constants import DEFAULT_REGION


def launch_audit(region: str = DEFAULT_REGION):
    """Launch the Audit Tool GUI."""
    from .main import create_audit_window
    return create_audit_window(region)


__all__ = ["launch_audit"]
