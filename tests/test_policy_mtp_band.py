"""Stored issue MTP bands are not reconstructed from current specified amounts."""
import pytest

from suiteview.polview.models.policy_information import PolicyInformation


def _policy(structure="1", code="B"):
    policy = object.__new__(PolicyInformation)
    tables = {
        "LH_COV_PHA": [{"COV_PHA_NBR": 5, "BAN_STRUCTURE_CD": structure}],
        "LH_COV_INS_RNL_RT": [
            {"COV_PHA_NBR": 1, "PRM_RT_TYP_CD": "M", "JT_INS_IND": "0", "RT_BAN_CD": "A"},
            {"COV_PHA_NBR": 5, "PRM_RT_TYP_CD": "C", "JT_INS_IND": "0", "RT_BAN_CD": "C"},
            {"COV_PHA_NBR": 5, "PRM_RT_TYP_CD": "M", "JT_INS_IND": "1", "RT_BAN_CD": "A"},
            {"COV_PHA_NBR": 5, "PRM_RT_TYP_CD": "M", "JT_INS_IND": "0", "RT_BAN_CD": code},
        ],
    }
    policy.fetch_table = tables.__getitem__
    return policy, tables


@pytest.mark.parametrize("structure,code,expected", [
    ("1", " B ", 2), ("6", "X", 1), ("06", "Y", 2), ("6", "A", 3),
    ("", "", 0), ("00", "", 0),
])
def test_mtp_band_uses_phase_type_primary_person_and_structure(structure, code, expected):
    policy, _ = _policy(structure, code)
    assert policy.rates.cov_mtp_band(5) == expected


@pytest.mark.parametrize("code", [None, "", "AB", "Z"])
def test_invalid_mtp_band_is_not_replaced_with_current_band(code):
    policy, _ = _policy(code=code)
    with pytest.raises(ValueError, match="invalid stored MTP band"):
        policy.rates.cov_mtp_band(5)


def test_missing_or_conflicting_mtp_bands_are_explicit():
    policy, tables = _policy()
    row = tables["LH_COV_INS_RNL_RT"].pop()
    with pytest.raises(ValueError, match="missing or ambiguous stored MTP band"):
        policy.rates.cov_mtp_band(5)
    tables["LH_COV_INS_RNL_RT"].extend([row, {**row, "RT_BAN_CD": "C"}])
    with pytest.raises(ValueError, match="missing or ambiguous stored MTP band"):
        policy.rates.cov_mtp_band(5)


def test_band_lookup_propagates_data_access_errors():
    policy, _ = _policy()

    def failed_fetch(table):
        raise RuntimeError("DB2 unavailable")

    policy.fetch_table = failed_fetch
    with pytest.raises(RuntimeError, match="DB2 unavailable"):
        policy.rates.cov_mtp_band(5)
