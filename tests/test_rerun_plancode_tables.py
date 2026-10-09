"""RERUN's UL_Rates plancode tables: column conversion, DDL and control classification."""
from decimal import Decimal

import pytest

from suiteview.illustration.models.rerun_plancode_tables import (
    ADV_COLUMNS,
    ADV_CREATE_SQL,
    ADV_SELECT_SQL,
    CONTROL_COLUMNS,
    CONTROL_CREATE_SQL,
    PRODUCT_TYPES,
    insert_sql,
    row_from_db,
    row_to_db,
)
from tools.rerun.rerun_plancode_tables import classify

ROW = {
    "Plancode": "1U143800", "LoanType": "Advance", "LapseTarget": "SV", "AgeCalc": "ALB",
    "Interest_Method": "ExactDays", "SA_Basis": "CurrentSA", "TableRatingFactor": 0.3,
    "PoAV_Table": "0", "DynamicBanding": 3, "Rachet_Banding": False, "CompanySub": "ANICO",
    "MinFaceAfterWD": 100000, "MinFaceEvidenced": True, "PremiumAndChargeCeaseAge": 100,
    "SCR_PctOfSurrenderTarget": [1, 1, 0.93, 0], "ShadowAvailability": "Inherent",
    "ShadowCeaseAge": 100, "ShadowMFEE": 5, "ShadowFrozenAfterCease": True,
}


def _as_stored(params):
    """What pyodbc hands back for the INSERT parameters (decimal/bit columns)."""
    return [Decimal(str(v)) if isinstance(v, Decimal) else v for v in params]


def test_rows_round_trip_and_null_columns_stay_unset():
    params = row_to_db(ADV_COLUMNS, ROW)
    assert len(params) == len(ADV_COLUMNS)
    back = row_from_db(ADV_COLUMNS, _as_stored(params))
    assert back == ROW
    assert isinstance(back["PremiumAndChargeCeaseAge"], int)
    assert isinstance(back["TableRatingFactor"], float)
    assert "ShadowLoanImpact" not in back


@pytest.mark.parametrize("key, value", [
    ("LoanType", None), ("DynamicBanding", 3.5), ("Rachet_Banding", 1),
    ("SCR_PctOfSurrenderTarget", "1,1"), ("Unknown", 1),
])
def test_invalid_rows_are_refused(key, value):
    with pytest.raises(ValueError):
        row_to_db(ADV_COLUMNS, {**ROW, key: value})


def test_ddl_and_select_use_every_column():
    for column in ADV_COLUMNS:
        assert f"[{column.name}]" in ADV_CREATE_SQL and f"[{column.name}]" in ADV_SELECT_SQL
    assert "PRIMARY KEY ([Plancode])" in ADV_CREATE_SQL
    assert "[CanIllustrate] bit NOT NULL" in CONTROL_CREATE_SQL
    for product_type in PRODUCT_TYPES:
        assert f"'{product_type}'" in CONTROL_CREATE_SQL
    assert insert_sql("dbo.X", CONTROL_COLUMNS) == (
        "INSERT INTO dbo.X ([Plancode], [ProductType], [CanIllustrate]) VALUES (?, ?, ?)")


@pytest.mark.parametrize("product_type, code, participation, expected", [
    ("Universal Life", "UL", "Non-Participating", "UL"),
    ("Survivorship Universal Life", "UL", "Non-Participating", "UL"),
    ("Universal Life", "IUL", "Non-Participating", "IUL"),
    ("Interest Sensitive Life", "ISWL", "Participating without Dividends", "ISWL"),
    ("Disability Income", "DI", "Non-Participating", "DI"),
    ("Whole Life", "WL_PAR", "Participating", "ParWL"),
    ("Whole Life", "END_PAR", "Participating", "ParWL"),
    ("Whole Life", "WL", "Participating", "ParWL"),        # N11SPB00: registry code WL
    ("Whole Life", "WL", "Non-Participating", "WL"),
    ("Whole Life", "RPU_PLANS", "Non-Participating", "WL"),
    ("Whole Life", "FAMILY", "Non-Participating", "WL"),
    ("Life Rider", "FAMILY", "Non-Participating", "Term"),
    ("Term Life", "TERM_IND", "Participating without Dividends", "Term"),
    ("Term Life", "ETI_PLANS", "Non-Participating", "Term"),
    ("Life Rider", "CHILD", "Non-Participating", "Term"),
    ("Life Rider", "ANNUITY", "Non-Participating", "Other"),
])
def test_control_classification(product_type, code, participation, expected):
    assert classify(product_type, code, participation) == expected
