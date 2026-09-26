"""Static contracts for explicit taskbar collaborators.

Collaborators must keep their dependencies explicit.  A ``self.foo`` read is
valid only when ``foo`` is owned by that collaborator (assigned on ``self``) or
is a method/property on the collaborator class or one of its bases.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TASKBAR_ROOT = ROOT / "suiteview" / "taskbar_launcher"
BASE_CLASS_NAMES = {"TaskbarCollaborator", "FileExplorerController"}


def _python_files() -> list[Path]:
    return sorted(path for path in TASKBAR_ROOT.rglob("*.py") if path.name != "__init__.py")


def _class_nodes() -> dict[str, tuple[Path, ast.ClassDef]]:
    classes: dict[str, tuple[Path, ast.ClassDef]] = {}
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                classes[node.name] = (path, node)
    return classes


def _base_names(node: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
    return names


def _inherits_contract_base(
    node: ast.ClassDef,
    classes: dict[str, tuple[Path, ast.ClassDef]],
    seen: set[str] | None = None,
) -> bool:
    seen = seen or set()
    for base_name in _base_names(node):
        if base_name in BASE_CLASS_NAMES:
            return True
        if base_name in seen or base_name not in classes:
            continue
        seen.add(base_name)
        if _inherits_contract_base(classes[base_name][1], classes, seen):
            return True
    return False


def _contract_classes() -> dict[str, tuple[Path, ast.ClassDef]]:
    classes = _class_nodes()
    return {
        name: case
        for name, case in classes.items()
        if name not in BASE_CLASS_NAMES and _inherits_contract_base(case[1], classes)
    }


def _walk_class_scope(node: ast.ClassDef):
    """Walk a class body without descending into nested class definitions."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            continue
        yield child
        yield from _walk_without_nested_classes(child)


def _walk_without_nested_classes(node: ast.AST):
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            continue
        yield child
        yield from _walk_without_nested_classes(child)


def _self_assigns(node: ast.ClassDef) -> set[str]:
    attrs: set[str] = set()
    for child in _walk_class_scope(node):
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
        if isinstance(child, ast.Assign):
            attrs.update(target.id for target in child.targets if isinstance(target, ast.Name))
        elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            attrs.add(child.target.id)
    return attrs


def _method_names(node: ast.ClassDef) -> set[str]:
    return {
        child.name
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _chain_nodes(
    node: ast.ClassDef,
    classes: dict[str, tuple[Path, ast.ClassDef]],
) -> list[ast.ClassDef]:
    chain = [node]
    for base_name in _base_names(node):
        if base_name in classes:
            chain.extend(_chain_nodes(classes[base_name][1], classes))
    return chain


def _provided_names(
    node: ast.ClassDef,
    classes: dict[str, tuple[Path, ast.ClassDef]],
) -> set[str]:
    provided: set[str] = set()
    for chain_node in _chain_nodes(node, classes):
        provided.update(_self_assigns(chain_node))
        provided.update(_class_attrs(chain_node))
        provided.update(_method_names(chain_node))
    return provided


def _self_reads(node: ast.ClassDef) -> list[tuple[str, int]]:
    reads: list[tuple[str, int]] = []
    for child in _walk_class_scope(node):
        if (
            isinstance(child, ast.Attribute)
            and isinstance(child.value, ast.Name)
            and child.value.id == "self"
            and isinstance(child.ctx, ast.Load)
            and child.attr != "__class__"
        ):
            reads.append((child.attr, child.lineno))
            continue
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "getattr"
            and len(child.args) >= 2
            and isinstance(child.args[0], ast.Name)
            and child.args[0].id == "self"
            and isinstance(child.args[1], ast.Constant)
            and isinstance(child.args[1].value, str)
        ):
            reads.append((child.args[1].value, child.lineno))
            continue
    return reads


def test_collaborator_self_reads_are_owned_by_the_contract_class():
    classes = _class_nodes()
    missing: list[str] = []

    for name, (path, node) in _contract_classes().items():
        provided = _provided_names(node, classes)
        for attr, line in _self_reads(node):
            if attr not in provided:
                missing.append(f"{path.relative_to(ROOT)}:{line}: {name}.self.{attr}")

    if missing:
        pytest.fail(
            "Collaborator/controller self reads must be assigned or declared methods:\n"
            + "\n".join(sorted(set(missing)))
        )


def test_collaborators_do_not_guard_tab_or_window_state_with_hasattr_self():
    offenders: list[str] = []
    for name, (path, node) in _contract_classes().items():
        for child in _walk_class_scope(node):
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "hasattr"
                and child.args
                and isinstance(child.args[0], ast.Name)
                and child.args[0].id == "self"
            ):
                offenders.append(f"{path.relative_to(ROOT)}:{child.lineno}: {name}")

    if offenders:
        pytest.fail("Use explicit collaborator state/window/tab references, not hasattr(self, ...):\n"
                    + "\n".join(offenders))
