"""Read-only live verification of Administrator identity and table loading."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.administrator.service import AccessRepository, current_network_id
from suiteview.core.build_env import has_developer_access
from suiteview.core.access_control import _load_access


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--menu", action="store_true", help="Also exercise the asynchronous Qt menu check")
    parser.add_argument("--runtime", action="store_true",
                        help="Also verify the packaged runtime query read-only, without the source bypass")
    args = parser.parse_args()
    repository = AccessRepository()
    snapshot = repository.load()
    report = {
        "network_id": current_network_id(),
        "is_admin": repository.is_admin(),
        "developer_access": has_developer_access(),
        "users": len(snapshot.users),
        "roles": len(snapshot.roles),
        "app_grants": sum(len(role.apps) for role in snapshot.roles),
        "enabled_users": sum(user.enabled for user in snapshot.users),
        "read_only_verification": True,
    }
    if not report["is_admin"]:
        raise PermissionError("ADMIN access was revoked during verification.")
    if args.runtime:
        runtime = _load_access()
        report["runtime"] = {
            "network_id": runtime.actor_id,
            "role": runtime.role_code,
            "all_apps": runtime.all_apps,
            "can_update_database": runtime.can_update_database,
            "can_write_support_files": runtime.can_write_support_files,
            "apps": sorted(runtime.apps),
            "administrator": runtime.allows_app("ADMINISTRATOR"),
        }
    if args.menu:
        from PyQt6.QtCore import QEventLoop, QThreadPool, QTimer
        from PyQt6.QtWidgets import QApplication, QMenu
        from suiteview.administrator.launcher import AdministratorMenuAccess

        app = QApplication.instance() or QApplication([])
        menu = QMenu()
        action = menu.addAction("Administrator")
        access = AdministratorMenuAccess(menu, action)
        assert action.isVisible() == has_developer_access()
        loop = QEventLoop()
        deadline = QTimer()
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        access.refresh()
        if access._pending:
            access._probe.signals.completed.connect(loop.quit)
            deadline.start(30000)
            loop.exec()
        QThreadPool.globalInstance().waitForDone()
        app.processEvents()
        if access._pending or not action.isVisible():
            raise RuntimeError("Asynchronous ADMIN menu visibility check failed.")
        report["admin_menu_visible"] = True
        menu.deleteLater()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
