"""Opt-in restoration of coverages explicitly terminated with a policy lapse."""
from copy import copy
from datetime import date


def restore_lapse_coverage(coverage, lapse_date: date | None):
    if lapse_date is None:
        return coverage
    terminated = getattr(coverage, "terminate_date", None)
    changed = getattr(coverage, "nxt_chg_dt", None)
    change_type = str(getattr(coverage, "nxt_chg_typ_cd", "")).strip()
    maturity = getattr(coverage, "maturity_date", None)
    if ((terminated is not None and terminated < lapse_date)
            or (maturity is not None and maturity <= lapse_date)):
        return coverage
    if terminated != lapse_date and not (change_type == "0" and changed == lapse_date):
        return coverage
    restored = copy(coverage)
    restored.cov_status = "1"
    restored.nxt_chg_typ_cd = "1"
    restored.terminate_date = None
    if changed == lapse_date:
        restored.nxt_chg_dt = None
    return restored
