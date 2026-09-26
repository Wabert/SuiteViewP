"""Static guard for mixin host contracts.

The split FileNav classes still use mixins, so each mixin must document its
host contract and every non-method ``self.*`` read must be provided somewhere in
the composed host or its builders. Audit query-object-viewer mixins are read
dynamically but skipped here because that area is owned by the parallel audit
refactor.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
OWNED_ROOTS = [
    ROOT / "suiteview" / "taskbar_launcher",
    ROOT / "suiteview" / "file_nav",
]
AUDIT_QUERY_VIEWER = ROOT / "suiteview" / "audit" / "query_object_viewer"


def _python_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.py") if path.name != "__init__.py")


def _class_nodes(paths: list[Path]) -> dict[str, tuple[Path, ast.ClassDef]]:
    classes: dict[str, tuple[Path, ast.ClassDef]] = {}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                classes[node.name] = (path, node)
    return classes


def _self_assigns(node: ast.ClassDef) -> set[str]:
    attrs: set[str] = set()
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Attribute)
            and isinstance(child.value, ast.Name)
            and child.value.id == "self"
            and isinstance(child.ctx, (ast.Store, ast.Del))
        ):
            attrs.add(child.attr)
    return attrs


def _class_attrs(node: ast.ClassDef) -> set[str]:
    attrs: set[str] = set()
    for child in node.body:
        if isinstance(child, (ast.Assign, ast.AnnAssign)):
            targets = child.targets if isinstance(child, ast.Assign) else [child.target]
            attrs.update(target.id for target in targets if isinstance(target, ast.Name))
    return attrs


def _method_names(classes: dict[str, tuple[Path, ast.ClassDef]]) -> set[str]:
    names: set[str] = set()
    for _, node in classes.values():
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(child.name)
    return names


def _parent_map(node: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(node) for child in ast.iter_child_nodes(parent)}


def _self_reads(node: ast.ClassDef, method_names: set[str]) -> set[str]:
    parents = _parent_map(node)
    reads: set[str] = set()
    for child in ast.walk(node):
        if not (
            isinstance(child, ast.Attribute)
            and isinstance(child.value, ast.Name)
            and child.value.id == "self"
            and isinstance(child.ctx, ast.Load)
        ):
            continue
        parent = parents.get(child)
        if isinstance(parent, ast.Call) and parent.func is child:
            continue
        if child.attr in method_names:
            continue
        reads.add(child.attr)
    return reads


def _contracted_mixins() -> list[tuple[Path, ast.ClassDef, bool]]:
    cases: list[tuple[Path, ast.ClassDef, bool]] = []
    for root in OWNED_ROOTS:
        for path, node in _class_nodes(_python_files(root)).values():
            if node.name.endswith("Mixin"):
                cases.append((path, node, False))
    for path, node in _class_nodes(_python_files(AUDIT_QUERY_VIEWER)).values():
        if node.name.endswith("Mixin"):
            cases.append((path, node, True))
    return cases


def test_mixin_requires_provides_contracts_are_documented_and_satisfied():
    paths = [path for root in OWNED_ROOTS for path in _python_files(root)]
    classes = _class_nodes(paths)
    provided = set().union(*(_self_assigns(node) | _class_attrs(node) for _, node in classes.values()))
    methods = _method_names(classes)
    missing: list[str] = []

    for path, node, audit_owned in _contracted_mixins():
        if audit_owned:
            continue
        doc = ast.get_docstring(node) or ""
        assert "Requires:" in doc and "Provides:" in doc, f"{node.name} in {path} needs Requires/Provides"
        reads = _self_reads(node, methods)
        unresolved = sorted(reads - provided)
        if unresolved:
            missing.append(f"{node.name}: {', '.join(unresolved)}")

    if missing:
        pytest.fail("Mixin reads without a provider:\n" + "\n".join(missing))


def _is_collaborator(node: ast.ClassDef) -> bool:
    explicit = {
        "SystemTray",
    }
    suffixes = ("Controller", "Collaborator", "Chrome", "Tabs", "Modes", "Tray", "Launcher")
    return (
        node.name in explicit
        or node.name.endswith(suffixes)
    )


def test_collaborators_do_not_hide_host_state_behind_forwarding():
    paths = [path for root in OWNED_ROOTS for path in _python_files(root)]
    classes = _class_nodes(paths)
    offenders: list[str] = []
    window_writes: list[str] = []
    generated_forwarders: list[str] = []

    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if path.name == "collaborators.py":
            for child in ast.walk(tree):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    if child.func.id in {"property", "setattr"}:
                        generated_forwarders.append(f"{child.func.id}() in {path}:{child.lineno}")
        for child in ast.walk(tree):
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "setattr"
                and child.args
                and isinstance(child.args[0], ast.Name)
                and child.args[0].id.endswith(("Class", "Controller", "Chrome", "Tabs", "Modes", "Tray", "Launcher"))
            ):
                generated_forwarders.append(f"setattr({child.args[0].id}, ...) in {path}:{child.lineno}")

    for path, node in classes.values():
        if not _is_collaborator(node):
            continue
        for child in node.body:
            if isinstance(child, ast.FunctionDef) and child.name in {"__getattr__", "__setattr__"}:
                offenders.append(f"{node.name}.{child.name} in {path}")
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Attribute)
                and isinstance(child.ctx, (ast.Store, ast.Del))
                and isinstance(child.value, ast.Attribute)
                and child.value.attr in {"window", "tab"}
                and isinstance(child.value.value, ast.Name)
                and child.value.value.id == "self"
            ):
                window_writes.append(f"{node.name}.self.{child.value.attr}.{child.attr} in {path}")

    if offenders:
        pytest.fail("Collaborator forwarding methods are forbidden:\n" + "\n".join(offenders))
    if generated_forwarders:
        pytest.fail("Generated collaborator forwarders are forbidden:\n" + "\n".join(generated_forwarders))
    if window_writes:
        pytest.fail("Collaborators must not assign window/tab attributes:\n" + "\n".join(window_writes))
