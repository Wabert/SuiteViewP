"""Wrap legacy CyberLife SQL builder calls with criteria collection."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGETS = [ROOT / "tests", ROOT / "tools" / "audit"]


class Rewriter(ast.NodeTransformer):
    def __init__(self) -> None:
        self.changed = False

    def visit_Call(self, node: ast.Call) -> ast.AST:
        node = self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == "build_cyberlife_sql":
            if node.args and isinstance(node.args[0], ast.Call):
                inner = node.args[0]
                if isinstance(inner.func, ast.Name) and inner.func.id == "collect_audit_criteria":
                    return node
            self.changed = True
            return ast.copy_location(
                ast.Call(
                    func=node.func,
                    args=[
                        ast.Call(
                            func=ast.Name(id="collect_audit_criteria", ctx=ast.Load()),
                            args=node.args,
                            keywords=node.keywords,
                        )
                    ],
                    keywords=[],
                ),
                node,
            )
        return node


def _needs_import(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if node.module == "suiteview.audit.cyberlife_criteria":
                return False
    return True


def _add_import(text: str) -> str:
    lines = text.splitlines()
    insert_at = 0
    for index, line in enumerate(lines):
        if line.startswith("import ") or line.startswith("from "):
            insert_at = index + 1
    lines.insert(
        insert_at,
        "from suiteview.audit.cyberlife_criteria import collect_audit_criteria",
    )
    return "\n".join(lines) + "\n"


def rewrite_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    rewriter = Rewriter()
    new_tree = rewriter.visit(tree)
    if not rewriter.changed:
        return False
    ast.fix_missing_locations(new_tree)
    new_text = ast.unparse(new_tree) + "\n"
    if _needs_import(new_tree):
        new_text = _add_import(new_text)
    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> None:
    for root in TARGETS:
        for path in sorted(root.rglob("*.py")):
            if path.name == "wrap_cyberlife_builder_calls.py":
                continue
            if "build_cyberlife_sql" not in path.read_text(encoding="utf-8"):
                continue
            if rewrite_file(path):
                print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
