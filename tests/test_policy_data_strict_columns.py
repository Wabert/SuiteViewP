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
