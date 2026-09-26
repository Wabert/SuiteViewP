"""Branch verification gate: structural checks to run before merging a refactor.

Usage (from any directory, with the project venv interpreter):
  venv\\Scripts\\python.exe tools\\app\\verify_branch.py <worktree> <base_commit>

Checks:
  1. pyflakes/pycodestyle (via flake8) F403/F405/F811/F821/E722 in suiteview/
     must be zero; F401 (unused import) must be zero in suiteview files changed
     since <base_commit>.
  2. Decorator drift: a method present at <base> and HEAD (same class+name,
     or a unique name) must keep the same decorators (a lost @staticmethod once
     emptied the FileNav details panel).
  3. pyqtSignal declared inside a *Mixin class (signals only work on QObject subclasses).
  4. Every `from suiteview.x import y` resolves (module exists, y bound or submodule).
  5. No UTF-8-read-as-cp1252 mojibake in suiteview/*.py, docs/*.md, root *.md.
Prints a report and "RESULT: PASS" / "RESULT: FAIL"; exits 1 on failure.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
BASE = sys.argv[2]
failures: list[str] = []


def git(*args: str) -> str:
    return subprocess.run(["git", "--no-pager", "-C", str(ROOT), *args], capture_output=True,
                          stdin=subprocess.DEVNULL).stdout.decode("utf-8", "replace")


def flake8(select: str, targets: list[str]) -> list[str]:
    out = subprocess.run([sys.executable, "-m", "flake8", "--isolated", f"--select={select}",
                          *targets], cwd=ROOT, capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if re.search(r":\d+:\d+: [A-Z]\d+", line)]


# 1. lint -----------------------------------------------------------------
hard = flake8("F403,F405,F811,F821,E722", ["suiteview"])
print(f"[1] lint F403/F405/F811/F821/E722 in suiteview: {len(hard)}")
for l in hard[:40]:
    print("    ", l)
if hard:
    failures.append("lint hard errors")
changed = [p for p in git("diff", "--name-only", BASE, "HEAD", "--", "suiteview").split()
           if p.endswith(".py") and (ROOT / p).exists()]
changed += [p for p in git("ls-files", "--others", "--exclude-standard", "suiteview").split()
            if p.endswith(".py")]
changed += [p for p in git("diff", "--name-only", "--", "suiteview").split()
            if p.endswith(".py") and (ROOT / p).exists()]
changed = sorted(set(changed))
f401 = flake8("F401", changed) if changed else []
print(f"[1] F401 unused imports in {len(changed)} changed suiteview files: {len(f401)}")
for l in f401[:30]:
    print("    ", l)
if f401:
    failures.append("unused imports in changed files")


# 2/3. decorators and mixin signals ---------------------------------------
def methods_from_source(src: str, rel: str, out: dict, mixin_signals: list):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        for f in cls.body:
            if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decs = tuple(sorted(ast.unparse(d) for d in f.decorator_list))
                out.setdefault(("C", cls.name, f.name), set()).add(decs)
                out.setdefault(("N", f.name), set()).add((decs, rel, cls.name))
            elif cls.name.endswith("Mixin") and isinstance(f, (ast.Assign, ast.AnnAssign)):
                value = getattr(f, "value", None)
                if value is not None and "pyqtSignal" in ast.unparse(value):
                    mixin_signals.append(f"{rel}:{f.lineno} {cls.name}")


base_map: dict = {}
head_map: dict = {}
mixin_signals: list[str] = []
_base_files = [r for r in git("ls-tree", "-r", "--name-only", BASE, "suiteview").split() if r.endswith(".py")]
_batch = subprocess.run(["git", "-C", str(ROOT), "cat-file", "--batch"], capture_output=True,
                        input="".join(f"{BASE}:{r}\n" for r in _base_files).encode("utf-8")).stdout
_pos = 0
for rel in _base_files:
    header_end = _batch.index(b"\n", _pos)
    size = int(_batch[_pos:header_end].split()[2])
    body = _batch[header_end + 1:header_end + 1 + size]
    _pos = header_end + 1 + size + 1
    methods_from_source(body.decode("utf-8-sig", "replace"), rel, base_map, [])
for p in (ROOT / "suiteview").rglob("*.py"):
    rel = p.relative_to(ROOT).as_posix()
    methods_from_source(p.read_text(encoding="utf-8-sig"), rel, head_map, mixin_signals)

drift = []
for key, decs in base_map.items():
    if key[0] == "C" and key in head_map and head_map[key] != decs:
        drift.append(f"{key[1]}.{key[2]}: base={sorted(decs)} head={sorted(head_map[key])}")
for key, entries in base_map.items():
    if key[0] != "N" or len(entries) != 1 or key not in head_map or len(head_map[key]) != 1:
        continue
    (bd, brel, bcls), = entries
    (hd, hrel, hcls), = head_map[key]
    if bd != hd and ("C", hcls, key[1]) not in base_map:
        drift.append(f"{key[1]} ({brel}:{bcls} -> {hrel}:{hcls}): base={bd} head={hd}")
print(f"[2] decorator drift: {len(drift)}")
for d in drift[:40]:
    print("    ", d)
if drift:
    failures.append("decorator drift (verify each is intentional)")
print(f"[3] pyqtSignal declared in *Mixin classes: {len(mixin_signals)}")
for m in mixin_signals:
    print("    ", m)
if mixin_signals:
    failures.append("signals in mixins")


# 4. import resolution ------------------------------------------------------
def mod_path(name: str):
    p = ROOT.joinpath(*name.split("."))
    if p.with_suffix(".py").exists():
        return p.with_suffix(".py")
    if (p / "__init__.py").exists():
        return p / "__init__.py"
    if p.is_dir():
        return p  # namespace package
    return None


_bind_cache: dict = {}


def bindings(mod: str) -> set:
    if mod in _bind_cache:
        return _bind_cache[mod]
    path = mod_path(mod)
    names: set = set()
    _bind_cache[mod] = names
    if path is None or path.is_dir():
        return names
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                if a.name == "*" and isinstance(n, ast.ImportFrom) and n.module:
                    names |= bindings(n.module)
                else:
                    names.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            names.add(n.id)
    return names


unresolved = []
for d in ("suiteview", "tests", "tools", "scripts"):
    for p in (ROOT / d).rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8-sig"))
        except SyntaxError as e:
            unresolved.append(f"{p.relative_to(ROOT)}: SyntaxError {e}")
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.ImportFrom) or n.level or not n.module or not n.module.startswith("suiteview"):
                continue
            if mod_path(n.module) is None:
                unresolved.append(f"{p.relative_to(ROOT)}:{n.lineno} missing module {n.module}")
                continue
            for a in n.names:
                if a.name != "*" and a.name not in bindings(n.module) and mod_path(f"{n.module}.{a.name}") is None:
                    unresolved.append(f"{p.relative_to(ROOT)}:{n.lineno} {n.module} has no {a.name}")
KNOWN = {  # pre-existing at 281deef (stale tools / dynamic)
    "suiteview.audit.dynamic_query has no execute_odbc_query",
    "missing module suiteview.ui.email_attachment_manager",
    "missing module suiteview.abrquote.models.vbt_2008",
    "suiteview.abrquote.models.abr_database has no ABRDatabase",
}
new_unresolved = [u for u in unresolved if not any(k in u for k in KNOWN)]
print(f"[4] unresolved suiteview imports (new): {len(new_unresolved)} (known pre-existing: {len(unresolved) - len(new_unresolved)})")
for u in new_unresolved[:40]:
    print("    ", u)
if new_unresolved:
    failures.append("unresolved imports")

# 5. mojibake ---------------------------------------------------------------
CONT = "€‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ\u00a0¡¢£¤¥¦§¨©ª«¬\u00ad®¯°±²³´µ¶·¸¹º»¼½¾¿"
MOJI = re.compile(f"[ÂÃ][{CONT}]|â[{CONT}][{CONT}]|ð[{CONT}][{CONT}][{CONT}]")
files = [*(ROOT / "suiteview").rglob("*.py"), *(ROOT / "docs").rglob("*.md"), *ROOT.glob("*.md")]
moji = []
for p in files:
    for i, line in enumerate(p.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
        if MOJI.search(line):
            moji.append(f"{p.relative_to(ROOT)}:{i}")
print(f"[5] mojibake lines: {len(moji)}")
for m in moji[:20]:
    print("    ", m)
if moji:
    failures.append("mojibake")

print("RESULT:", "PASS" if not failures else "FAIL (" + "; ".join(failures) + ")")
sys.exit(1 if failures else 0)
