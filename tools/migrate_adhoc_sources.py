"""Migrate legacy adhoc_source QueryObjects into FileDataSources.

The old model stored a flat file as a QueryObject (kind="adhoc_source"); File
Sources are now their own entity. This converts each adhoc QueryObject into a
FileDataSource (one member file) and — when applied — removes the legacy object.

Dry-run by default; pass apply=true to write.

Usage:
    venv\\Scripts\\python.exe tools/migrate_adhoc_sources.py            # dry run
    venv\\Scripts\\python.exe tools/migrate_adhoc_sources.py '{"apply": true}'

Outputs a JSON summary to stdout.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from suiteview.audit import file_source_store, query_object_store  # noqa: E402
from suiteview.audit.file_source_intake import migrate_adhoc_to_file_source  # noqa: E402
from suiteview.audit.query_object import OBJECT_KIND_ADHOC_SOURCE  # noqa: E402


def main():
    apply = False
    if len(sys.argv) > 1 and sys.argv[1].strip():
        try:
            apply = bool(json.loads(sys.argv[1]).get("apply", False))
        except (ValueError, AttributeError):
            apply = False

    migrated, errors = [], []
    for obj in query_object_store.list_objects():
        if obj.kind != OBJECT_KIND_ADHOC_SOURCE:
            continue
        try:
            fds = migrate_adhoc_to_file_source(obj)
            entry = {
                "name": obj.name,
                "query_object_id": obj.id,
                "file_source_id": fds.id,
                "files": len(fds.members),
                "columns": len(fds.columns),
            }
            if apply:
                file_source_store.save_file_source(fds)
                query_object_store.delete_object_by_id(obj.id)
            migrated.append(entry)
        except Exception as exc:
            errors.append({"name": obj.name, "id": obj.id, "error": str(exc)})

    print(json.dumps({
        "apply": apply,
        "migrated_count": len(migrated),
        "migrated": migrated,
        "errors": errors,
    }, indent=2))


if __name__ == "__main__":
    main()
