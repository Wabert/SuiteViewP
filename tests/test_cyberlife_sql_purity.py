from __future__ import annotations

import ast
from pathlib import Path


SQL_DIR = Path(__file__).parents[1] / "suiteview" / "audit" / "cyberlife_sql"


def test_section_builders_do_not_assign_to_ctx_outside_context() -> None:
    offenders: list[str] = []
    for path in SQL_DIR.glob("*.py"):
        if path.name == "context.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = [node.target] if hasattr(node, "target") else list(node.targets)
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "ctx"
                ):
                    offenders.append(f"{path.name}:{node.lineno}:{target.attr}")
            if _calls_name(node, "setattr") and _first_arg_is_ctx(node):
                offenders.append(f"{path.name}:{node.lineno}:setattr")
            if _calls_name(node, "ctx_set"):
                offenders.append(f"{path.name}:{node.lineno}:ctx_set")
            if _calls_object_setattr(node):
                offenders.append(f"{path.name}:{node.lineno}:object.__setattr__")
    assert offenders == []


def test_cyberlife_sql_uses_typed_criteria_not_widget_facades() -> None:
    banned = (".isChecked(", ".selectedItems(", ".currentText(", ".text(", ".value(")
    offenders = []
    for path in SQL_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            if token in text:
                offenders.append(f"{path.name}:{token}")
    assert offenders == []


def _calls_name(node: ast.AST, name: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
    )


def _first_arg_is_ctx(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and bool(node.args)
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "ctx"
    )


def _calls_object_setattr(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "__setattr__"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "object"
    )
