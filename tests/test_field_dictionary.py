"""Tests for suiteview.core.field_dictionary — friendly DB2 column labels."""
from __future__ import annotations

import pytest

from suiteview.core import field_dictionary as fd


# ── Curated labels ───────────────────────────────────────────────────

def test_curated_label():
    assert fd.friendly_label("CK_POLICY_NBR") == "Policy Number"
    assert fd.friendly_label("XTR_PER_1000_AMT") == "Flat Extra per $1,000"
    assert fd.friendly_label("RT_SEX_CD") == "Sex (rate)"


def test_curated_description():
    desc = fd.friendly_description("TCH_POL_ID")
    assert "NOT the policy number" in desc


def test_unknown_has_empty_description():
    assert fd.friendly_description("ZZ_TOTALLY_MADE_UP_AMT") == ""


def test_is_known():
    assert fd.is_known("NON_TRD_POL_IND") is True
    assert fd.is_known("ZZ_TOTALLY_MADE_UP_AMT") is False


# ── Qualifier / alias stripping ──────────────────────────────────────

@pytest.mark.parametrize("ref", [
    "DB2TAB.LH_BAS_POL.CK_POLICY_NBR",
    "LH_BAS_POL.CK_POLICY_NBR",
    "pol.CK_POLICY_NBR",
    "CK_POLICY_NBR AS pol_num",
    "  CK_POLICY_NBR  ",
    "[CK_POLICY_NBR]",
])
def test_strips_qualifiers(ref):
    assert fd.friendly_label(ref) == "Policy Number"


def test_case_insensitive():
    assert fd.friendly_label("ck_policy_nbr") == "Policy Number"
    assert fd.friendly_label("Ck_Policy_Nbr") == "Policy Number"


# ── Humanizer fallback ───────────────────────────────────────────────

def test_humanize_expands_abbreviations():
    # Bypass curated entries — exercise the mechanical expander directly.
    assert fd.humanize("COV_UNT_QTY") == "Coverage Unit Quantity"
    assert fd.humanize("ANN_PRM_AMT") == "Annual Premium Amount"


def test_humanize_drops_ck_prefix():
    assert fd.humanize("CK_SYS_CD") == "System Code"


def test_humanize_keeps_digits():
    assert fd.humanize("XTR_PER_1000_AMT") == "Extra Period 1000 Amount"


def test_humanize_keeps_known_acronyms():
    assert fd.humanize("GAV_BAL_AMT") == "Guaranteed Account Value Balance Amount"


def test_humanize_lone_ck_not_dropped():
    # When CK is the entire name there is nothing else, so keep it.
    assert fd.humanize("CK") == "Ck"


def test_unknown_falls_back_to_humanize():
    assert fd.friendly_label("FOO_BAR_AMT") == "Foo Bar Amount"


def test_label_and_description_pair():
    label, desc = fd.label_and_description("CK_CMP_CD")
    assert label == "Company Code"
    assert "ANICO" in desc


# ── Runtime overrides ────────────────────────────────────────────────

def test_register_label_string(tmp_path):
    fd.register_labels({"WIDGET_CNT": "Widget Count"})
    assert fd.friendly_label("WIDGET_CNT") == "Widget Count"
    assert fd.friendly_description("WIDGET_CNT") == ""


def test_register_label_tuple_overrides_curated():
    fd.register_labels({"CK_POLICY_NBR": ("Contract #", "Custom label")})
    try:
        assert fd.friendly_label("CK_POLICY_NBR") == "Contract #"
        assert fd.friendly_description("CK_POLICY_NBR") == "Custom label"
    finally:
        # Restore so other tests see the curated value regardless of order.
        fd._OVERRIDES.pop("CK_POLICY_NBR", None)


def test_register_strips_qualifier_in_key():
    fd.register_labels({"some_table.GIZMO_DT": "Gizmo Date"})
    assert fd.friendly_label("GIZMO_DT") == "Gizmo Date"


# ── Robustness ───────────────────────────────────────────────────────

def test_empty_input():
    assert fd.friendly_label("") == ""
    assert fd.humanize("") == ""
