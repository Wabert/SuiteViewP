"""Render the ABR ResourcesDialog with sample data and grab it to a PNG.

Auditable UI verification helper — builds the dialog with a populated sample
quote, shows it, grabs the widget to an image, and exits. Does not require the
full app to be running.

Usage:
    venv\\Scripts\\python.exe tools/abrquote/screenshot_resources_dialog.py [out.png]
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from suiteview.core.profile_paths import diagnostics_dir

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else str(
        diagnostics_dir() / "resources_dialog.png"
    )
    os.makedirs(os.path.dirname(out), exist_ok=True)

    from suiteview.abrquote.models.abr_data import (
        ABRPolicyData, ABRQuoteResult, MedicalAssessment,
    )
    from suiteview.abrquote.ui.resources_dialog import ResourcesDialog

    policy = ABRPolicyData(
        policy_number="E0213651", issue_age=45, attained_age=58,
        sex="M", rate_class="N", face_amount=250000.0,
        issue_date=date(2011, 6, 1), issue_state="TX", plan_code="B75TL400",
        product_type="UL", insured_name="JOHN Q SAMPLE",
    )
    result = ABRQuoteResult(
        full_eligible_db=250000.0, full_actuarial_discount=41250.0,
        full_admin_fee=250.0, full_loan_repayment=0.0,
        full_accelerated_benefit=208500.0, full_benefit_ratio=0.834,
        abr_interest_rate=0.0545, quote_date=date(2026, 8, 17),
        apv_fb=210000.0, apv_fp=1250.0,
    )
    assessment = MedicalAssessment(rider_type="Chronic", computed_le=4.76)

    app = QApplication(sys.argv)
    dlg = ResourcesDialog(
        policy=policy, result=result, assessment=assessment,
        level_annual_premium=1595.0,
    )
    dlg.resize(900, 640)
    dlg.show()

    def capture():
        pixmap = dlg.grab()
        pixmap.save(out, "PNG")
        print(f"Saved {out}")
        app.quit()

    QTimer.singleShot(300, capture)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
