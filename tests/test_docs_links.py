from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DOC_FILES = [ROOT / "Agent.md", *sorted((ROOT / "docs").rglob("*.md"))]

MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]\n]+\]\(([^)\n]+)\)")
BACKTICKED_SUITEVIEW_PY_RE = re.compile(r"`(suiteview/[^`\s]+?\.py)`")


def _target_path(raw_target: str) -> str | None:
    target = raw_target.strip()
    if not target:
        return None
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if " " in target and not target.startswith((".", "/", "\\")):
        target = target.split()[0]
    target = unquote(target)
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return None
    if target.startswith("#"):
        return None
    path_part = target.split("#", 1)[0]
    if not path_part:
        return None
    if re.match(r"^[A-Za-z]:", path_part):
        return None
    return path_part


def test_relative_markdown_links_resolve() -> None:
    missing: list[str] = []
    for doc in DOC_FILES:
        text = doc.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK_RE.finditer(text):
            path_part = _target_path(match.group(1))
            if path_part is None:
                continue
            target = (doc.parent / path_part).resolve()
            if not target.exists():
                rel_doc = doc.relative_to(ROOT).as_posix()
                missing.append(f"{rel_doc}: {match.group(1)} -> {target}")
    assert not missing, "Missing Markdown link targets:\n" + "\n".join(missing)


def test_backticked_suiteview_python_paths_resolve() -> None:
    missing: list[str] = []
    for doc in DOC_FILES:
        text = doc.read_text(encoding="utf-8")
        for match in BACKTICKED_SUITEVIEW_PY_RE.finditer(text):
            target = ROOT / match.group(1).replace("/", "\\")
            if not target.exists():
                rel_doc = doc.relative_to(ROOT).as_posix()
                missing.append(f"{rel_doc}: `{match.group(1)}`")
    assert not missing, "Missing backticked suiteview/*.py paths:\n" + "\n".join(missing)
