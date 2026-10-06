"""Run the canonical build and verify the versioned distribution before handoff."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PyInstaller.archive.readers import CArchiveReader

from suiteview import __version__


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.verify_only:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_distribution.py")],
            cwd=ROOT, check=True,
        )
    folder = ROOT / "dist" / "SuiteView"
    exe = folder / "SuiteView.exe"
    archive_path = ROOT / "dist" / f"SuiteView-{__version__}.zip"
    executable_archive = CArchiveReader(str(exe))
    pyz_names = [
        name for name, entry in executable_archive.toc.items() if entry[-1] == "z"
    ]
    if len(pyz_names) != 1:
        raise RuntimeError("Expected exactly one embedded Python archive.")
    pyz = executable_archive.open_embedded_archive(pyz_names[0])
    code = pyz.extract("suiteview")
    if __version__ not in code.co_consts:
        raise RuntimeError("Embedded SuiteView version does not match the release.")
    for module in (
        "suiteview.core.profile_paths", "suiteview.core.profile_maintenance",
        "suiteview.core.access_control", "suiteview.taskbar_launcher.albert_launcher",
    ):
        if module not in pyz.toc:
            raise RuntimeError(f"Required module missing from EXE: {module}")
    with zipfile.ZipFile(archive_path) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise RuntimeError(f"Corrupt ZIP member: {bad_member}")
        members = {item.filename for item in archive.infolist() if not item.is_dir()}
        files = {path.relative_to(folder).as_posix(): path
                 for path in folder.rglob("*") if path.is_file()}
        if members != set(files):
            raise RuntimeError("ZIP contents do not match the distribution folder.")
        for name, path in files.items():
            with path.open("rb") as local, archive.open(name) as packed:
                if hashlib.file_digest(local, "sha256").digest() != hashlib.file_digest(
                    packed, "sha256"
                ).digest():
                    raise RuntimeError(f"ZIP content mismatch: {name}")
        private_names = {
            ".key", "suiteview.db", "sp_token_cache.bin", "bookmarks.json", "layout.json",
        }
        if any(Path(name).name in private_names for name in members):
            raise RuntimeError("Personal profile content found in distribution.")
    with archive_path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    sha_file = folder / "_internal" / "suiteview" / "BUILD_SHA"
    build_sha = sha_file.read_text(encoding="utf-8").strip() if sha_file.is_file() else ""
    report = {
        "all_ok": True, "version": __version__, "build_sha": build_sha, "exe": str(exe),
        "zip": str(archive_path), "zip_bytes": archive_path.stat().st_size,
        "zip_sha256": digest, "verified_files": len(files),
        "embedded_version_verified": True, "personal_profile_bundled": False,
        "interactive_exe_test": "pending user testing",
    }
    receipt = ROOT / "dist" / f"SuiteView-{__version__}-verification.json"
    receipt.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
