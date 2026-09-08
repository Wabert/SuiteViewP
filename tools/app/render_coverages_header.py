"""Render the PolView Coverages tab Policy Info header to a PNG.

Feeds the header a stub policy so the death-benefit / corridor display can be
inspected without a live DB2 connection.

Usage:
    venv\\Scripts\\python.exe tools/app/render_coverages_header.py '{"account_value": 90000, "corridor_pct": 250, "out": "C:/tmp/header.png"}'

JSON keys (all optional):
    face            base face amount                (default 173373)
    account_value   monthliversary account value    (default 90000)
    corridor_pct    LH_NON_TRD_POL.CDR_PCT          (default 250)
    db_option       "1" | "2" | "3"                 (default "1")
    advanced        advanced (UL) product           (default true)
    out             output PNG path                 (default ~/.suiteview/coverages_header.png)
"""

import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from suiteview.polview.ui.tabs.coverages_tab import CoveragesTab  # noqa: E402


class _StubPolicy:
    """Minimal stand-in for PolicyInformation's Policy Info header inputs."""

    def __init__(self, opts):
        self._face = Decimal(str(opts.get("face", 173373)))
        av = opts.get("account_value", 90000)
        self._av = None if av is None else Decimal(str(av))
        pct = opts.get("corridor_pct", 250)
        self._pct = None if pct is None else Decimal(str(pct))
        self._db_option = str(opts.get("db_option", "1"))
        self._advanced = bool(opts.get("advanced", True))

        self.exists = True
        self.policy_number = "S1366894"
        self.company_code = "01"
        self.servicing_market_org = "MLM"
        self.issue_state = "TX"
        self.gpt_cvat = "GPT"
        self.billing_mode = "Monthly"
        self.modal_premium = Decimal("300")
        self.region = "CKPR"
        self.system_code = "I"
        self.suspense_code = "0"
        self.suspense_description = "Active"
        self.in_grace = False
        self.valuation_date = date(2026, 7, 1)
        self.policy_year = 39
        self.attained_age = 86
        self.premium_pay_status_code = "9"
        self.premium_pay_status_description = "Terminated"
        self.reins_partner = "R"
        self.is_advanced_product = self._advanced
        self.db_option_code = self._db_option
        self.corridor_percent = self._pct if self._pct is not None else Decimal("100")
        self.accumulation_value = self._av
        self.total_premiums_paid = Decimal("0")
        self.primary_insured_face_amount = self._face

    def get_coverages(self):
        return []

    def get_benefits(self):
        return []

    def mv_av(self, index=0):
        return self._av

    # ── death-benefit properties mirrored from PolicyInformation ────────
    @property
    def current_account_value(self):
        return self._av if self._av is not None else self.accumulation_value

    @property
    def standard_death_benefit(self):
        total = self._face
        if self._db_option in ("2", "B") and self.current_account_value:
            total += self.current_account_value
        elif self._db_option in ("3", "C") and self.total_premiums_paid:
            total += self.total_premiums_paid
        return total

    @property
    def corridor_death_benefit(self):
        if not self._advanced:
            return None
        av = self.current_account_value
        if not av or av <= 0 or not self.corridor_percent:
            return None
        return (av * self.corridor_percent / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def corridor_amount(self):
        corr = self.corridor_death_benefit
        if corr is None:
            return Decimal("0")
        excess = corr - self.standard_death_benefit
        return excess if excess > 0 else Decimal("0")

    @property
    def total_death_benefit(self):
        corr = self.corridor_death_benefit
        standard = self.standard_death_benefit
        return corr if corr is not None and corr > standard else standard


def main():
    opts = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    out = opts.get("out") or str(Path.home() / ".suiteview" / "coverages_header.png")
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv[:1])
    tab = CoveragesTab()
    tab.resize(1060, 220)
    tab.load_data_from_policy(_StubPolicy(opts))
    tab.info_group.adjustSize()
    tab.show()
    app.processEvents()
    tab.info_group.grab().save(out, "PNG")
    tab.close()

    print(json.dumps({
        "output": out,
        "total_death_benefit": tab.total_death_benefit_label.text(),
        "corridor": tab.corridor_label.text(),
        "tooltip": tab.total_death_benefit_label.toolTip(),
    }, indent=2))


if __name__ == "__main__":
    main()
