"""Smoke-test the ABR "Explanation of Benefit" builder and renderers.

Builds the explanation document two ways (empty/template and with sample quote
data), renders HTML, and writes a .docx to the temp directory to confirm
python-docx rendering works. Does NOT open Word.

Usage:
    venv\\Scripts\\python.exe tools/abrquote/verify_explanation.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def main() -> int:
    from suiteview.abrquote.models.abr_data import (
        ABRPolicyData, ABRQuoteResult, MedicalAssessment,
    )
    from suiteview.abrquote.core.abr_explanation import (
        build_explanation, explanation_to_html, explanation_to_docx,
    )

    # 1) Template mode (no data) — every value should be a placeholder.
    doc_empty = build_explanation(None, None, None)
    html_empty = explanation_to_html(doc_empty)
    assert "[to be completed]" in html_empty
    assert doc_empty.title

    # 2) Populated mode — sample UL quote with a level annual premium.
    policy = ABRPolicyData(
        policy_number="E0213651", issue_age=45, attained_age=58,
        sex="M", rate_class="N", face_amount=250000.0,
        issue_date=date(2011, 6, 1), issue_state="TX", plan_code="B75TL400",
        product_type="UL", insured_name="JOHN Q SAMPLE",
    )
    result = ABRQuoteResult(
        full_eligible_db=250000.0,
        full_actuarial_discount=41250.0,
        full_admin_fee=250.0,
        full_loan_repayment=0.0,
        full_accel_benefit=208500.0,
        full_accelerated_benefit=208500.0,
        full_benefit_ratio=0.834,
        full_surrender_value=0.0,
        abr_interest_rate=0.0545,
        quote_date=date(2026, 8, 17),
        apv_fb=210000.0,
        apv_fp=1250.0,
    )
    assessment = MedicalAssessment(rider_type="Chronic", computed_le=4.76)

    doc = build_explanation(policy, result, assessment, level_annual_premium=1595.0)
    html = explanation_to_html(doc)
    assert "$250,000.00" in html, "accelerated amount missing"
    assert "$250.00" in html, "admin fee missing"
    assert "5.450%" in html, "interest rate missing"
    assert "75% multiple of the 2008" in html, "chronic base table missing"
    assert "modified mortality table" in html, "modified mortality framing missing"
    assert "PVFB" in html and "PVFP" in html and "PVFDivs" in html, "PV components missing"
    assert "Moody's" in html, "Moody's interest-rate language missing"
    assert "$1,595.00" in html, "UL level annual premium missing"
    assert "level annual premium" in html, "UL premium explanation missing"
    # Letter framing present.
    assert "AMERICAN NATIONAL INSURANCE COMPANY" in html, "letterhead missing"
    assert "Dear JOHN Q SAMPLE:" in html, "salutation missing"
    assert "RE:" in html and "Policy: E0213651" in html, "RE line missing"
    assert "Sincerely," in html, "closing missing"
    # Removed the higher/lower interest-rate sentence.
    assert "a lower interest rate results in a higher" not in html, "higher/lower sentence not removed"
    # No form numbers or filing citations in the customer-facing text.
    assert "ABR14" not in html, "form number leaked into customer text"
    assert "IIPRC" not in html, "filing citation leaked into customer text"

    # Terminal branch should use the terminal table language.
    doc_tm = build_explanation(
        policy, result, MedicalAssessment(rider_type="Terminal", computed_le=1.2),
    )
    html_tm = explanation_to_html(doc_tm)
    assert "500 per 1,000" in html_tm, "terminal table language missing"
    assert "ABR14" not in html_tm, "form number leaked into terminal text"

    # Near-surrender scenario: small mortality impact, payment floored to CSV.
    result_floor = ABRQuoteResult(
        full_eligible_db=250000.0,
        full_admin_fee=250.0,
        full_loan_repayment=0.0,
        full_accelerated_benefit=72000.0,  # floored up to surrender value
        full_surrender_value=72000.0,
        apv_fb=72000.0,     # net PV barely above surrender
        apv_fp=0.0,
        abr_interest_rate=0.0545,
        quote_date=date(2026, 8, 17),
    )
    html_floor = explanation_to_html(build_explanation(
        policy, result_floor, MedicalAssessment(rider_type="Chronic", computed_le=9.0),
    ))
    assert "equal to the policy's cash surrender value" in html_floor, "surrender-floor message missing"

    out_path = os.path.join(tempfile.gettempdir(), "verify_abr_explanation.docx")
    explanation_to_docx(doc, out_path)
    size = os.path.getsize(out_path)

    # Confirm 0.5-inch margins were applied.
    from docx import Document
    from docx.shared import Inches
    saved = Document(out_path)
    sec = saved.sections[0]
    half = Inches(0.5)
    assert sec.top_margin == half and sec.bottom_margin == half, "top/bottom margin not 0.5in"
    assert sec.left_margin == half and sec.right_margin == half, "left/right margin not 0.5in"

    print(json.dumps({
        "ok": True,
        "sections": [s.heading for s in doc.sections],
        "html_len_empty": len(html_empty),
        "html_len_populated": len(html),
        "docx_path": out_path,
        "docx_size": size,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
