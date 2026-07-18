"""Install the Local/Production data switch into the RERUN local workbook.

Idempotent installer that:
  1. Imports (or re-imports) docs/Illustration_UL/RERUN_VBA_local/mdl_LocalData.bas
     as VBA module ``mdl_LocalData``.
  2. Inserts a local-data branch at the top of ``MainGetRates`` (mdl_GetRates)
     and ``GetPolicyFromCyberlife`` (mdl_GetCyberlifePolicy) — right after their
     "Application.Calculation = xlCalculationManual" line — so the normal
     buttons transparently use the local path when INPUT!sDataSource = Local*.
  3. Adds the ``sDataSource`` dropdown to INPUT!C2 (label in B2) with values
     Production / Local / Local (no benefits), defined name sDataSource.

Requires Excel's "Trust access to the VBA project object model" setting
(File > Options > Trust Center > Trust Center Settings > Macro Settings).
The tool detects and reports when it's off.

Usage (single JSON arg, all keys optional):
    venv\\Scripts\\python.exe tools/rerun_install_local_vba.py '{}'
    {"workbook": "docs/Illustration_UL/RERUN (v20.0) local.xlsm"}
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rerun_com import _open_excel  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK = ROOT / "docs" / "Illustration_UL" / "RERUN (v20.0) local.xlsm"
MODULE_BAS = ROOT / "docs" / "Illustration_UL" / "RERUN_VBA_local" / "mdl_LocalData.bas"

BRANCH_MARK = "LOCAL DATA BRANCH"
BRANCH_LINES = (
    "    '--- {mark} (installed by tools/rerun_install_local_vba.py) ---\n"
    "    If IsLocalData() Then\n"
    "        {call}\n"
    "        Application.Calculation = CalcStatus\n"
    "        Exit Sub\n"
    "    End If\n"
    "    '--- END {mark} ---"
)

PATCHES = [
    # (module, sub name, local call)
    ("mdl_GetRates", "MainGetRates", "GetRatesLocal"),
    ("mdl_GetCyberlifePolicy", "GetPolicyFromCyberlife", "GetPolicyFromLocal"),
]
ANCHOR = "Application.Calculation = xlCalculationManual"


def _patch_module(comp, sub_name: str, local_call: str) -> str:
    cm = comp.CodeModule
    code = cm.Lines(1, cm.CountOfLines) if cm.CountOfLines else ""
    if BRANCH_MARK in code:
        return "already patched"

    # Find the Sub, then the first ANCHOR line inside it.
    sub_line = None
    lines = code.split("\r\n")
    for i, ln in enumerate(lines, start=1):
        if sub_line is None:
            if ln.strip().lower().startswith(("sub " + sub_name.lower(),
                                              "public sub " + sub_name.lower())):
                sub_line = i
        else:
            if ANCHOR in ln:
                block = BRANCH_LINES.format(mark=BRANCH_MARK, call=local_call)
                cm.InsertLines(i + 1, block)
                return f"patched after line {i}"
            if ln.strip().lower().startswith("end sub"):
                break
    return f"ERROR: anchor not found in {sub_name}"


def main():
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    workbook = Path(cmd.get("workbook") or DEFAULT_WORKBOOK).resolve()
    if not workbook.exists():
        print(json.dumps({"ok": False, "error": f"workbook not found: {workbook}"}))
        sys.exit(1)

    backup = workbook.with_suffix(".xlsm.bak")
    shutil.copyfile(workbook, backup)

    xl = _open_excel()
    report = {"ok": True, "workbook": str(workbook), "backup": str(backup)}
    try:
        wb = xl.Workbooks.Open(str(workbook), UpdateLinks=0, ReadOnly=False)
        try:
            vbp = wb.VBProject
            _ = vbp.VBComponents.Count
        except Exception:
            print(json.dumps({"ok": False, "error": (
                "Cannot access the VBA project. Enable: File > Options > Trust Center > "
                "Trust Center Settings > Macro Settings > 'Trust access to the VBA "
                "project object model', then rerun.")}))
            wb.Close(SaveChanges=False)
            return

        # 1) (Re)import mdl_LocalData, baking the absolute repo root into the
        # module so temp copies of the workbook still find venv + tools.
        bas_text = MODULE_BAS.read_text(encoding="utf-8").replace(
            "__REPO_ROOT__", str(ROOT))
        staged = Path(tempfile.gettempdir()) / "mdl_LocalData.bas"
        staged.write_text(bas_text, encoding="utf-8")
        for comp in list(vbp.VBComponents):
            if comp.Name == "mdl_LocalData":
                vbp.VBComponents.Remove(comp)
        vbp.VBComponents.Import(str(staged))
        report["mdl_LocalData"] = "imported"

        # 2) Patch the two production subs
        for mod_name, sub_name, local_call in PATCHES:
            comp = vbp.VBComponents(mod_name)
            report[f"{mod_name}.{sub_name}"] = _patch_module(comp, sub_name, local_call)

        # 3) sDataSource dropdown on INPUT
        ws = wb.Worksheets("INPUT")
        was_protected = bool(ws.ProtectContents)
        if was_protected:
            ws.Unprotect()
        ws.Range("B2").Value = "Data Source"
        ws.Range("B2").Font.Italic = True
        c = ws.Range("C2")
        if str(c.Value or "") not in ("Production", "Local", "Local (no benefits)"):
            c.Value = "Local"
        try:
            c.Validation.Delete()
        except Exception:
            pass
        try:
            # xlValidateList=3, xlValidAlertStop=1, xlBetween=1 (positional — late
            # binding rejects named args here)
            c.Validation.Add(3, 1, 1, "Production,Local,Local (no benefits)")
            report["validation"] = "dropdown added"
        except Exception as exc:
            report["validation"] = f"skipped ({exc}) — cell still works, type the value"
        if was_protected:
            ws.Protect()
        exists = False
        for nm in wb.Names:
            if nm.Name.endswith("sDataSource"):
                exists = True
                break
        if not exists:
            wb.Names.Add(Name="sDataSource", RefersTo="=INPUT!$C$2")
        report["sDataSource"] = f"INPUT!C2 = {c.Value}"

        wb.Save()
        wb.Close(SaveChanges=False)
    finally:
        xl.Quit()

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
