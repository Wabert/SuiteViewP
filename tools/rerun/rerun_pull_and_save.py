"""Pull a policy from Cyberlife (live DB2) into RERUN and save it to a case slot.

Drives the ACTUAL workbook (not a temp copy) so the saved case persists, then
saves the file.  Run ATTENDED (visible=True) so RERUN's DB2 login form (frmLogin)
can be answered if the NEON DSN needs credentials.

Mirrors the manual workflow:
  1. INPUT!sDataSource   = "Production"   (live DB2 path)
  2. INPUT!sQueryRegion  = region          (CKPR for production)
  3. INPUT!sCyberlifePolicyNumber = policy
  4. Run GetPolicyFromCyberlife            (fills INPUT sheet from DB2)
  5. CalculateFull
  6. Run SaveCase(slot)                     (overwrite that Saved Cases column)
  7. wb.Save

Config is read from a JSON FILE (sole arg) to avoid shell-quoting problems with
workbook paths containing spaces/backslashes.

Usage:
    venv\\Scripts\\python.exe tools/rerun/rerun_pull_and_save.py <config.json>
    config.json: {
      "workbook": "<path .xlsm>",
      "policy": "UE000023",
      "region": "CKPR",
      "data_source": "Production",
      "slot": 1,
      "visible": true,
      "save": true          # false = pull only, read back inputs, do NOT persist
    }
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

XL_CALC_MANUAL = -4135

# INPUT named ranges to echo back after the pull, as a sanity check.
ECHO_NAMES = [
    "sCompany", "sStatus", "sPlancode", "sFormNumber", "sINPUT_CaseID",
    "sINPUT_Issue_Age", "sINPUT_Issue_Date", "sINPUT_Rate_Sex",
    "sINPUT_Rateclass", "sINPUT_CurrentSA1", "sINPUT_State", "sStorageNumber",
]


def _open_excel_macros_on(visible: bool):
    import win32com.client

    xl = win32com.client.DispatchEx("Excel.Application")
    xl.Visible = visible
    xl.DisplayAlerts = False
    # Leave EnableEvents at default; the login UserForm needs a normal UI pump.
    # msoAutomationSecurityLow = 1 -> macros run without prompts.
    xl.AutomationSecurity = 1
    try:
        xl.Iteration = True
        xl.MaxIterations = 1000
        xl.MaxChange = 1e-9
    except Exception:
        pass
    return xl


def _name_val(wb, name):
    try:
        return wb.Names(name).RefersToRange.Value
    except Exception as exc:  # noqa: BLE001
        return f"<err: {exc}>"


def main() -> None:
    with open(sys.argv[1], "r", encoding="utf-8-sig") as fh:
        cfg = json.load(fh)

    workbook = str(Path(cfg["workbook"]).resolve())
    policy = str(cfg["policy"]).strip()
    region = str(cfg.get("region", "CKPR")).strip()
    data_source = str(cfg.get("data_source", "Production")).strip()
    slot = int(cfg.get("slot", 1))
    visible = bool(cfg.get("visible", True))
    do_save = bool(cfg.get("save", True))

    report = {
        "workbook": workbook, "policy": policy, "region": region,
        "data_source": data_source, "slot": slot, "saved": False,
    }

    xl = _open_excel_macros_on(visible)
    try:
        wb = xl.Workbooks.Open(workbook, UpdateLinks=0, ReadOnly=False)
        xl.Calculation = XL_CALC_MANUAL

        wb.Names("sDataSource").RefersToRange.Value = data_source
        wb.Names("sQueryRegion").RefersToRange.Value = region
        wb.Names("sCyberlifePolicyNumber").RefersToRange.Value = policy

        xl.Run("GetPolicyFromCyberlife")

        # Confirm the pull actually populated the base plancode.
        pulled_plancode = _name_val(wb, "sPlancode")
        report["pulled_plancode"] = str(pulled_plancode)
        if pulled_plancode in (None, "", "<err"):
            report["error"] = "GetPolicyFromCyberlife did not populate sPlancode"

        xl.CalculateFull()

        report["inputs_after_pull"] = {n: _name_val(wb, n) for n in ECHO_NAMES}

        if do_save:
            xl.Run("SaveCase", slot)
            report["storage_number_after_save"] = _name_val(wb, "sStorageNumber")
            wb.Save()
            report["saved"] = True

        wb.Close(SaveChanges=False)
    finally:
        xl.Quit()

    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
