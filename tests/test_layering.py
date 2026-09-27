"""Import-layer guard for SuiteView package boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "suiteview"

LAYERS: tuple[tuple[str, int, str], ...] = (
    ("suiteview.core", 0, "core/utils infrastructure"),
    ("suiteview.data", 1, "profile and local storage"),
    ("suiteview.polview.models", 2, "domain models"),
    ("suiteview.illustration.models", 2, "domain models"),
    ("suiteview.abrquote.models", 2, "domain models"),
    ("suiteview.audit.query_object", 2, "domain models"),
    ("suiteview.audit.qdefinition", 2, "domain models"),
    ("suiteview.polview.services", 3, "engines and services"),
    ("suiteview.illustration.core", 3, "engines and services"),
    ("suiteview.abrquote.core", 3, "engines and services"),
    ("suiteview.ui", 4, "shared UI library"),
    ("suiteview.audit", 5, "app UI"),
    ("suiteview.polview.ui", 5, "app UI"),
    ("suiteview.illustration.ui", 5, "app UI"),
    ("suiteview.abrquote.ui", 5, "app UI"),
    ("suiteview.ratemanager", 5, "app UI"),
    ("suiteview.mainframe_nav", 5, "app UI"),
    ("suiteview.administrator", 5, "app UI"),
    ("suiteview.agent_chat", 5, "app UI"),
    ("suiteview.scratchpad", 5, "app UI"),
    ("suiteview.screenshot_manager", 5, "app UI"),
    ("suiteview.file_nav", 5, "app UI"),
    ("suiteview.taskbar_launcher", 6, "shell"),
    ("suiteview.startup", 6, "shell"),
    ("suiteview.main", 6, "shell"),
)

# Existing violations are recorded with a concrete removal plan. This list may
# shrink only; add entries only with a review/report item explaining why the
# current wave cannot remove the dependency.
ALLOWLIST: dict[tuple[str, str], str] = {
    (
        "suiteview.core.connection_manager",
        "suiteview.data.repositories",
    ): "Wave R1 will move connection ownership into core/data_access and break core<->data coupling.",
    (
        "suiteview.illustration.models.regression_suite",
        "suiteview.illustration.core.summary_results",
    ): "Regression snapshots still format through engine summary exports; move snapshot formatting out of models.",
}


def _module_name(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _layer(module: str) -> tuple[int, str] | None:
    for prefix, order, label in sorted(LAYERS, key=lambda item: len(item[0]), reverse=True):
        if module == prefix or module.startswith(prefix + "."):
            return order, label
    return None


def _resolve_relative(source: str, level: int, module: str | None) -> str | None:
    package = source if (ROOT / Path(*source.split("."))).is_dir() else source.rsplit(".", 1)[0]
    parts = package.split(".")
    if level > len(parts):
        return None
    base = parts[: len(parts) - level + 1]
    if module:
        base.extend(module.split("."))
    return ".".join(base)


def _suiteview_imports(source: str, tree: ast.AST) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "suiteview" or alias.name.startswith("suiteview."):
                    imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            target = (
                _resolve_relative(source, node.level, node.module)
                if node.level
                else node.module
            )
            if target and (target == "suiteview" or target.startswith("suiteview.")):
                imports.add(target)
    return imports


def _upward_edges() -> set[tuple[str, str, str]]:
    edges: set[tuple[str, str, str]] = set()
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        source = _module_name(path)
        source_layer = _layer(source)
        if source_layer is None:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for target in sorted(_suiteview_imports(source, tree)):
            target_layer = _layer(target)
            if target_layer is None or target_layer[0] <= source_layer[0]:
                continue
            edges.add((source, target,
                       f"{source} ({source_layer[1]}) imports {target} ({target_layer[1]})"))
    return edges


def test_suiteview_imports_do_not_point_upward():
    violations = [text for source, target, text in sorted(_upward_edges())
                  if (source, target) not in ALLOWLIST]
    assert not violations, "\n".join(violations)


def test_allowlist_has_no_stale_entries():
    """The allowlist may only shrink: drop an entry as soon as its import is gone."""
    live = {(source, target) for source, target, _ in _upward_edges()}
    stale = sorted(set(ALLOWLIST) - live)
    assert not stale, "Remove stale ALLOWLIST entries: " + ", ".join(f"{s} -> {t}" for s, t in stale)
