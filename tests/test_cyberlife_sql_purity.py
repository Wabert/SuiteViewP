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
    assert offenders == []
