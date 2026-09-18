"""Native Administrator screenshots; synthetic by default, read-only live via --live.

Usage: venv\\Scripts\\python.exe tools\\app\\verify_administrator.py --output-dir artifacts\\administrator
Add --live to authorize/load the actual tables. Live writes are explicitly blocked.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from suiteview.administrator.service import AccessRepository, AccessRole, AccessSnapshot, AccessUser


class SyntheticRepository:
    """Isolated, in-memory fixture shared by UI regression and screenshot checks."""

    def __init__(self):
        self.snapshot = AccessSnapshot(
            users=(
                AccessUser("ADMIN01", "Morgan Administrator", True, "ADMIN"),
                AccessUser("ANALYST01", "Alex Analyst", True, "ANALYST"),
                AccessUser("REVIEWER01", "Jamie Reviewer", False, "REVIEWER"),
            ),
            roles=(
                AccessRole("ADMIN", "Suite administrators", True, True, True),
                AccessRole("ANALYST", "Policy analysis", False, False, True,
                           frozenset({"POLVIEW", "QUERY", "RERUN", "FUTURE_APP"})),
                AccessRole("REVIEWER", "Read-only review", False, False, False,
                           frozenset({"POLVIEW", "ABR"})),
                AccessRole("UNASSIGNED", "Available for assignment", False, False, False),
            ),
            actor_id="ADMIN01",
        )
        self.mutations = []

    def load(self):
        return self.snapshot

    def _save(self, collection, value, original):
        records = getattr(self.snapshot, collection)
        key = value.network_id if collection == "users" else value.role_code
        found = next((r for r in records if (
            r.network_id if collection == "users" else r.role_code
        ) == key), None)
        if found != original:
            raise ValueError("Record changed by another administrator. Refresh and review.")
        if not key:
            raise ValueError("A stable identifier is required.")
        if collection == "users" and (
            not value.name or value.role_code not in {r.role_code for r in self.snapshot.roles}
        ):
            raise ValueError("Name and one existing role are required.")
        if collection == "roles" and "ADMIN" in value.apps:
            raise ValueError("ADMIN is not a whitelist application.")
        records = tuple(value if r == original else r for r in records)
        if original is None:
            records += (value,)
        self.snapshot = replace(self.snapshot, **{collection: records})
        self.mutations.append(("save", collection, value, original))

    def _delete(self, collection, original):
        records = getattr(self.snapshot, collection)
        if original not in records:
            raise ValueError("Record changed by another administrator. Refresh and review.")
        if collection == "roles" and any(
            u.role_code == original.role_code for u in self.snapshot.users
        ):
            raise ValueError("Role is assigned to users.")
        self.snapshot = replace(
            self.snapshot, **{collection: tuple(r for r in records if r != original)}
        )
        self.mutations.append(("delete", collection, original))

    def save_user(self, user, *, original):
        self._save("users", user, original)

    def save_role(self, role, *, original):
        self._save("roles", role, original)

    def delete_user(self, original):
        self._delete("users", original)

    def delete_role(self, original):
        self._delete("roles", original)


class ReadOnlyCaptureRepository:
    """Expose only the real repository's read path, even if a UI button is clicked."""

    def __init__(self, repository):
        self._repository = repository
        self.mutations = []

    def load(self):
        return self._repository.load()

    def _deny(self, action):
        self.mutations.append(action)
        raise PermissionError("Live screenshot verification is read-only; writes are blocked.")

    def save_user(self, user, *, original):
        self._deny("save_user")

    def save_role(self, role, *, original):
        self._deny("save_role")

    def delete_user(self, original):
        self._deny("delete_user")

    def delete_role(self, original):
        self._deny("delete_role")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--live", action="store_true",
                        help="Read-only real ADMIN lookup and screenshots; never save/delete.")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    from PyQt6.QtTest import QTest
    from PyQt6.QtGui import QFontMetrics
    from PyQt6.QtWidgets import QApplication
    from suiteview.administrator.window import AdministratorWindow
    from suiteview.core.build_env import has_developer_access

    app = QApplication.instance() or QApplication([])
    repository = ReadOnlyCaptureRepository(AccessRepository()) if args.live else SyntheticRepository()
    window = AdministratorWindow(repository=repository)
    screenshots = []
    checks = {}
    try:
        window.show()
        app.processEvents()
        QTest.qWait(150)
        checks["native_platform"] = app.platformName() == "windows"
        checks["administrator_access"] = has_developer_access() or any(
            user.network_id == window.snapshot.actor_id and user.enabled and user.role_code == "ADMIN"
            for user in window.snapshot.users
        )
        checks["access_label"] = (
            "Developer access (source)" if has_developer_access() else "ADMIN"
        ) in window.status.text()
        whitelist_role = next((r for r in window.snapshot.roles if not r.all_apps),
                              window.snapshot.roles[0])
        all_apps_role = next((r for r in window.snapshot.roles if r.all_apps), None)
        captures = [("users.png", 0, None), ("roles.png", 1, whitelist_role.role_code)]
        if all_apps_role:
            captures.append(("all_apps.png", 1, all_apps_role.role_code))
        for filename, index, role in captures:
            window.tabs.setCurrentIndex(index)
            if role:
                table = window.tables[1]
                for row in range(table.model.rowCount()):
                    if table.model.index(row, 0).data() == role:
                        table.table_view.setCurrentIndex(table.model.index(row, 0))
                        break
            app.processEvents()
            QTest.qWait(100)
            checks[f"scope_notice_{filename}"] = (
                window.enforcement_notice.isVisible()
                and "Runtime permissions" in window.enforcement_notice.text()
            )
            checks[f"editor_fit_{filename}"] = all(
                window.editors[index].rect().contains(
                    widget.mapTo(window.editors[index], widget.rect().bottomRight())
                )
                for widget in (
                    (window.user_id, window.user_name, window.user_role)
                    if index == 0 else
                    (window.role_code, window.role_description, window.app_scroll)
                )
            )
            checks[f"no_horizontal_table_scroll_{filename}"] = (
                window.tables[index].table_view.horizontalScrollBar().maximum() == 0
            )
            table = window.tables[index]
            metrics = QFontMetrics(table.header.wrap_font())
            checks[f"single_line_headers_{filename}"] = all(
                metrics.horizontalAdvance(str(label)) + table.header.sort_icon_width + 8
                <= table.table_view.columnWidth(column)
                for column, label in enumerate(table.df.columns)
            )
            path = (args.output_dir / filename).resolve()
            if not window.grab().save(str(path)):
                raise RuntimeError(f"Cannot save screenshot to {path}")
            screenshots.append(str(path))
        checks["picker_matches_all_apps"] = (
            window.app_picker.isEnabled() != window.role_all_apps.isChecked()
        )
        checks["admin_not_grantable"] = "ADMIN" not in window.app_checks
        checks["compact_rows"] = all(
            t.table_view.verticalHeader().defaultSectionSize() == 16
            and t.header.height() == 18 for t in window.tables
        )
        window.close()
        window.show()
        app.processEvents()
        checks["reopens"] = window.isVisible()
        checks["no_mutations"] = not repository.mutations
        checks["snapshot_unchanged"] = repository.load() == window.snapshot
        result = {
            "all_ok": all(checks.values()), "mode": "live-read-only" if args.live else "synthetic",
            "checks": checks, "screenshots": screenshots,
        }
        (args.output_dir / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0 if result["all_ok"] else 1
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
