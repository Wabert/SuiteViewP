from decimal import Decimal
from types import SimpleNamespace

import pytest

from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.models.policy_sections.targets import TargetsSection


def test_shadow_account_value_uses_segment_58_xp_premium_amount():
    policy = object.__new__(PolicyInformation)
    calls = []

    def data_item_where(table, return_field, filter_field, filter_value):
        calls.append((table, return_field, filter_field, filter_value))
        return "4872.53"

    policy.data_item_where = data_item_where

    assert policy.targets.shadow_account_value == Decimal("4872.53")
    assert calls == [
        ("LH_COV_TARGET", "TAR_PRM_AMT", "TAR_TYP_CD", "XP")
    ]


def test_shadow_account_value_preserves_zero():
    policy = object.__new__(PolicyInformation)
    policy.data_item_where = lambda *_args: 0

    assert policy.targets.shadow_account_value == Decimal("0")


# A GLP zapped to 0 can be stored blank (NULL) on the segment 67 'A' row.
# UL054808 (CKPR, 10/29/2026): GPT, GSP -3,046.23, Accum GLP 54,512.33 and an
# 'A' row whose GDL_PRM_AMT is NULL; it must read as 0 so GEP is recognized.

class _GuidelinePolicy:
    def __init__(self, gdl_rows, targets, gpt_cvat="GPT"):
        self.tables = {"LH_COV_INS_GDL_PRM": gdl_rows, "LH_POL_TARGET": targets}
        self.product = SimpleNamespace(gpt_cvat=gpt_cvat)

    def find_row_index(self, table, field, value):
        for idx, row in enumerate(self.tables[table]):
            if str(row[field]) == str(value):
                return idx
        return -1

    def data_item_where(self, table, return_field, field, value, default=None):
        idx = self.find_row_index(table, field, value)
        return self.tables[table][idx][return_field] if idx >= 0 else default


_ACCUM_GLP = [{"TAR_TYP_CD": "TA", "TAR_PRM_AMT": 54512.33}]


def _gdl(glp="missing", gsp=-3046.23):
    rows = []
    if glp != "missing":
        rows.append({"PRM_RT_TYP_CD": "A", "GDL_PRM_AMT": glp})
    if gsp is not None:
        rows.append({"PRM_RT_TYP_CD": "S", "GDL_PRM_AMT": gsp})
    return rows


def _glp(gdl_rows, targets=_ACCUM_GLP, gpt_cvat="GPT"):
    return TargetsSection(_GuidelinePolicy(gdl_rows, targets, gpt_cvat)).glp


def test_blank_glp_reads_zero_on_gpt_policy_with_gsp_and_accum_glp():
    assert _glp(_gdl(glp=None)) == Decimal("0")


def test_recorded_glp_is_unchanged():
    assert _glp(_gdl(glp=1200)) == Decimal("1200")
    assert _glp(_gdl(glp=0)) == Decimal("0")


@pytest.mark.parametrize("gdl_rows, targets, gpt_cvat", [
    (_gdl(glp="missing"), _ACCUM_GLP, "GPT"),  # no 'A' row at all
    (_gdl(glp=None), _ACCUM_GLP, "CVAT"),
    (_gdl(glp=None), _ACCUM_GLP, ""),
    (_gdl(glp=None, gsp=None), _ACCUM_GLP, "GPT"),
    (_gdl(glp=None), [], "GPT"),
])
def test_blank_glp_stays_unknown_outside_those_conditions(gdl_rows, targets, gpt_cvat):
    assert _glp(gdl_rows, targets, gpt_cvat) is None
