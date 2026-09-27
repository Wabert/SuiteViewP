from unittest.mock import Mock

import pytest

from suiteview.core.data_access.errors import UnknownColumnError
from suiteview.polview.models.policy_data import PolicyData


def _loaded_policy_data(columns=("KNOWN",), rows=(("value",),)):
    data = object.__new__(PolicyData)
    data._policy_number = "STRICT01"
    data._table_cache = {"LH_BAS_POL": {"columns": list(columns), "rows": list(rows)}}
    data._table_errors = {}
    data._exists = True
    return data


def test_data_item_missing_row_returns_none():
    assert _loaded_policy_data().data_item("LH_BAS_POL", "KNOWN", 5) is None


def test_data_item_misspelled_loaded_column_raises_typed_error():
    with pytest.raises(UnknownColumnError, match="LH_BAS_POL.MISSPELLED"):
        _loaded_policy_data().data_item("LH_BAS_POL", "MISSPELLED")


def test_optional_fieldspec_column_absence_returns_none():
    data = _loaded_policy_data(columns=("KNOWN",), rows=(("value",),))
    data._table_cache = {"TH_BAS_POL": {"columns": ["KNOWN"], "rows": [("value",)]}}
    with pytest.raises(UnknownColumnError, match="TH_BAS_POL.FORCED_PREM_IND"):
        data.data_item("TH_BAS_POL", "FORCED_PREM_IND")


def test_optional_fieldspec_column_absence_is_handled_by_policy_information():
    from suiteview.polview.models.policy_information import PolicyInformation

    policy = object.__new__(PolicyInformation)
    policy.data_item = data_item = Mock(side_effect=UnknownColumnError("TH_BAS_POL", "FORCED_PREM_IND"))

    assert policy._field("forced_premium_indicator") == ""
    data_item.assert_called_once_with("TH_BAS_POL", "FORCED_PREM_IND", 0)


# Live CKPR LH_BAS_POL columns (policy UE215622, September 26, 2026). The table
# has no POL_STS_CD, so status_code must stay blank as it was before strict
# column reads, instead of failing every PolView tab that reads status.
_LIVE_LH_BAS_POL_COLUMNS = (
    "TCH_POL_ID CK_CMP_CD CK_SYS_CD CK_POLICY_NBR NON_TRD_POL_IND PRM_PAID_TO_DT "
    "PRM_BILL_TO_DT SUS_CD PRM_PAY_STA_REA_CD PMT_FQY_PER OGN_ETR_CD LST_ETR_CD "
    "POL_ISS_ST_CD NXT_BIL_DT PLN_TMN_DT NXT_MVRY_PRC_DT NXT_YR_END_PRC_DT"
).split()


def test_status_code_is_blank_when_live_table_lacks_pol_sts_cd():
    from suiteview.polview.models.policy_information import PolicyInformation

    row = tuple("22" if name == "PRM_PAY_STA_REA_CD" else "1" for name in _LIVE_LH_BAS_POL_COLUMNS)
    policy = object.__new__(PolicyInformation)
    policy._data = _loaded_policy_data(columns=_LIVE_LH_BAS_POL_COLUMNS, rows=(row,))
    policy._sections = {}

    assert policy.status.status_code == ""
    assert policy.status.is_active is False
    assert policy.status.premium_pay_status_code == "22"
