"""Shell-owned registrations for cross-app launch requests."""

from __future__ import annotations

from suiteview.core.app_launcher import register_app_launcher


def register_default_launchers() -> None:
    """Register app factories that lower layers may request by app id."""

    def open_filenav(*, parent_bar=None):
        from suiteview.taskbar_launcher.file_nav_window import FileNavWindow

        return FileNavWindow(parent_bar=parent_bar)

    def open_rerun():
        from suiteview.illustration import launch_illustration

        return launch_illustration()

    register_app_launcher("FILENAV", open_filenav)
    register_app_launcher("RERUN", open_rerun)
