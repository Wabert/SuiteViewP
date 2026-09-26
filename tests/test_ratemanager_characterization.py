"""Golden-output safety nets for Rate Manager refactors."""

from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import date
from decimal import Decimal

from suiteview.ratemanager.ckultb01_parser import iter_records as iter_ckultb01
from suiteview.ratemanager.database_loader import (
    LoadAction,
    TABLE_SPECS,
    WorkupPackage,
    analyze_package,
    coerce_row,
    create_execution_plan,
)
from suiteview.ratemanager.mpf_parser import group_by_combo, iter_records as iter_mpf
from suiteview.ratemanager.parser import IAFParser, ParseResult, ProductInfo, RateRecord
from suiteview.ratemanager.rate_reformatter import RateReformatter
from suiteview.ratemanager.whole_life.parsers import (
    parse_cvf,
    parse_iaf,
    parse_nsp,
    parse_pui,
)


def _fixed(fields: list[tuple[int, str]], width: int = 133) -> str:
    chars = [" "] * width
    for start, text in fields:
        chars[start:start + len(text)] = text
    return "".join(chars).rstrip() + "\n"


def _write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _iaf_product_line(plan: str = "WLTEST00") -> str:
    return _fixed([
        (2, plan), (13, "1"), (16, "01011900"), (25, "010"), (29, "012"),
        (34, "1"), (41, "100"), (46, "1"), (53, "121"), (58, "1"),
        (60, "1,000.00".rjust(14)), (75, ".00".rjust(14)), (91, "0"),
        (100, "0"), (102, "NONE"), (118, "1"), (120, "01"), (123, "00"),
    ])


def _iaf_alias_line() -> str:
    return (
        " *** PLAN SEARCH KEYS".ljust(31)
        + "WLTEST00    1 01011900  WLALIAS0      02011900\n"
    )


def _iaf_rate_line(rate_type: str = "C") -> str:
    return _fixed([
        (19, rate_type), (23, "01011900"),
        (43, "011NA**"), (51, "0.12345".rjust(12)),
        (65, "992SA3A"), (73, "9.87654".rjust(12)),
    ])


def test_iaf_parser_current_output_golden(tmp_path):
    source = (
        "   PLAN CODE  V  EFFDATE FST LST USE PAY-AGE USE  ME-AGE USE  VAL PER UNIT  "
        "PROD CRED AMT USE MDRT DEF SPEC BENEFITS  R LV DUR       \n"
        + _iaf_product_line("ULTEST00")
        + _iaf_rate_line("C")
    )
    result = IAFParser().parse(str(_write(tmp_path, "iaf.txt", source)))

    assert result.error is None
    assert [asdict(product) for product in result.products] == [{
        "ref": 1, "plancode": "ULTEST00", "version": "1",
        "eff_date": "01/01/1900", "first": 10, "last": 12, "iar_use": 1,
        "pay_age": 100, "pay_age_use": 1, "me_age": 121, "me_age_use": 1,
        "val_per_unit": 1000.0, "prod_cred_amt": 0.0, "prod_cred_use": 0,
        "mdrt": " ", "deficient": 0, "spec_benefits": "NONE", "r": "1",
        "lv": "01", "dur": "00",
    }]
    assert [asdict(rate) for rate in result.rates] == [
        {
            "product_ref": 1, "rate_type": "C", "scale_start": "01/01/1900",
            "scale_stop": "12/31/9999", "attained_age": 10, "duration": 1,
            "issue_age": 9, "gender": "1", "rate_class": "N", "band": "A",
            "plan_option": "**", "rate": 0.12345,
        },
        {
            "product_ref": 1, "rate_type": "C", "scale_start": "01/01/1900",
            "scale_stop": "12/31/9999", "attained_age": 10, "duration": 99,
            "issue_age": -89, "gender": "2", "rate_class": "S", "band": "A",
            "plan_option": "3A", "rate": 9.87654,
        },
    ]


def test_whole_life_parsers_current_output_goldens(tmp_path):
    cv_text = (
        "1CKCVDVPC RUN DATE = 01/02/26 CASH VALUE RATES PAGE 1\n"
        "0USER ID CLASS-BASE-SUB USER DEFINED AGE PREM YEARS BENF YEARS "
        "FIRST DUR LAST DUR DURATION ZERO VALUE\n"
        "    06  1-ABC-01  A B      25  00  00  00  02  37.40-\n"
        " -----\n DURATION ( 1) ( 2) ( 3) ( 4) ( 5) ( 6) ( 7) ( 8) ( 9) (10)\n"
        " -----\n 000-009  37.40 100.00 105.25 0.00 0.00 0.00 0.00 0.00 0.00 0.00\n"
    )
    assert parse_cvf(_write(tmp_path, "cvf.txt", cv_text)) == [
        {
            "USER_CODE": "06", "RATE_KEY": "1ABC01", "CLASS": "1",
            "BASE_SERIES": "ABC", "SUBSERIES": "01", "USER_DEFINED": "A B",
            "ISSUE_AGE": 25, "PREMIUM_YEARS": 0, "BENEFIT_YEARS": 0,
            "FIRST_DURATION": 0, "LAST_DURATION": 2,
            "DURATION_ZERO_VALUE": Decimal("0.00"), "DURATION": 0,
            "RATE": Decimal("0.00"),
        },
        {
            "USER_CODE": "06", "RATE_KEY": "1ABC01", "CLASS": "1",
            "BASE_SERIES": "ABC", "SUBSERIES": "01", "USER_DEFINED": "A B",
            "ISSUE_AGE": 25, "PREMIUM_YEARS": 0, "BENEFIT_YEARS": 0,
            "FIRST_DURATION": 0, "LAST_DURATION": 2,
            "DURATION_ZERO_VALUE": Decimal("0.00"), "DURATION": 1,
            "RATE": Decimal("100.00"),
        },
        {
            "USER_CODE": "06", "RATE_KEY": "1ABC01", "CLASS": "1",
            "BASE_SERIES": "ABC", "SUBSERIES": "01", "USER_DEFINED": "A B",
            "ISSUE_AGE": 25, "PREMIUM_YEARS": 0, "BENEFIT_YEARS": 0,
            "FIRST_DURATION": 0, "LAST_DURATION": 2,
            "DURATION_ZERO_VALUE": Decimal("0.00"), "DURATION": 2,
            "RATE": Decimal("105.25"),
        },
    ]

    pui_text = (
        "1DATE 01/02/26 CYBERLIFE ONLINE TABLES LIST PAGE 1\n"
        "0TABLE: CJUDTPUI PROCESSING OPTIONS: USERID = ALL AUDIT# = ALL DELETED RECORDS = OMIT\n"
        "0 ENTRIES FOR USER 01\n"
        "0 PLAN CD SEX CLASS ATT AGE TAB RATE PUI RATE AUDIT# CHANGED\n"
        + _fixed([
            (11, "WLTEST00"), (23, "1"), (32, "N"), (41, "35".rjust(8)),
            (50, "0"), (59, "123.456789".rjust(14)), (74, "A00001"),
            (81, "01/02/2026"),
        ])
    )
    assert parse_pui(_write(tmp_path, "pui.txt", pui_text)) == [{
        "USER_CODE": "01", "PLANCODE": "WLTEST00", "SEX": "1",
        "RATECLASS": "N", "ATTAINED_AGE": 35, "TABLE_RATING": "0",
        "RATE": Decimal("123.456789"), "AUDIT_NUMBER": "A00001",
        "CHANGED_DATE": date(2026, 1, 2),
    }]

    iaf_text = (
        _iaf_product_line()
        + _iaf_alias_line()
        + " **PREMIUM RATES- TYP START STOP IDENT RATE IDENT RATE IDENT RATE IDENT RATE\n"
        + _iaf_rate_line("Y")
    )
    rows = parse_iaf(_write(tmp_path, "wl_iaf.txt", iaf_text), "06")
    assert len(rows) == 4
    assert rows[0]["SOURCE_PLANCODE"] == "WLTEST00"
    assert rows[1]["PLANCODE"] == "WLTEST00"
    assert rows[2]["PLANCODE"] == "WLALIAS0"
    assert rows[3]["PREMIUM_IDENTIFIER"] == "992SA3A"
    assert {row["RATE"] for row in rows} == {Decimal("0.12345"), Decimal("9.87654")}

    nsp_text = (
        "USER_CODE,RATE_KEY,BASIS_ID,BASIS_DESCRIPTION,SEX,RATECLASS,"
        "ISSUE_AGE,DURATION,EFFECTIVE_DATE,RATE_PER,RATE\n"
        "06,1ABC01,1980CSO,Verified source,1,N,35,1,2026-01-01,1000,1.23456789\n"
    )
    assert parse_nsp(_write(tmp_path, "nsp.csv", nsp_text))[0] == {
        "USER_CODE": "06", "RATE_KEY": "1ABC01", "BASIS_ID": "1980CSO",
        "BASIS_DESCRIPTION": "Verified source", "SEX": "1", "RATECLASS": "N",
        "ISSUE_AGE": 35, "DURATION": 1, "EFFECTIVE_DATE": date(2026, 1, 1),
        "RATE_PER": Decimal("1000"), "RATE": Decimal("1.23456789"),
    }


def test_online_table_and_mpf_parser_output_goldens(tmp_path):
    ckultb01 = (
        "1DATE  04/20/26 CYBERLIFE ONLINE TABLES LIST PAGE    1\n"
        "           C1       M        1        **       *        *        A        "
        "01/01/1900   99,999      999           5.00000  9,999,999.0\n"
        "                     0           5.00000  9,999,999.00 T02416 08/01/2019\n"
    )
    assert list(iter_ckultb01(str(_write(tmp_path, "ckultb01.txt", ckultb01)))) == [{
        "PLAN_CODE": "C1", "FREQ_TYPE": "M", "RULE_CODE": "1",
        "STATE_CODE": "**", "SEX_CODE": "*", "RATE_CLASS": "*", "BAND_CODE": "A",
        "EFFECTIVE_DATE": "01/01/1900", "MONTH_DUR": 99999, "HIGH_AGE": 999,
        "CHARGE": 5.0, "MAXIMUM": 9999999.0, "GUAR_CHARGE": 5.0,
        "GUAR_MAX": 9999999.0, "AUDIT_NUM": "T02416",
        "CHANGED_DATE": "08/01/2019",
    }]

    mpf_key = "M0023#1NA312000"
    mpf_text = (
        _fixed([(0, "0"), (9, mpf_key), (31, "20 5.64% 21 6.00%")])
        + _fixed([(0, "0"), (31, "22 6.50 23 7.25")])
    )
    records = list(iter_mpf(str(_write(tmp_path, "mpf.txt", mpf_text))))
    assert [(record.key.combo, record.cont, record.pairs) for record in records] == [
        (("3#", "1", "N", "A", "312"), "", [
            (20, "5.64%", 5.64, True), (21, "6.00%", 6.0, True),
            (22, "6.50", 6.5, False), (23, "7.25", 7.25, False),
        ]),
    ]
    grouped = group_by_combo(iter(records))
    assert grouped[("00", "3#", "1", "N", "A", "312")][20] == (5.64, "5.64%", True)


def test_rate_reformatter_and_execution_plan_goldens(tmp_path):
    result = ParseResult(
        products=[ProductInfo(ref=1, plancode="PLAN1", version="1", pay_age=25)],
        rates=[
            *[
                RateRecord(1, "C", "01/01/1900", "12/31/9999", age, 99, -79, "1", "N", "A", "**", 0.10)
                for age in range(20, 25)
            ],
            RateRecord(1, "G", "01/01/1900", "12/31/9999", 20, 99, -79, "1", "N", "0", "**", 0.20),
            RateRecord(1, "M", "01/01/1900", "12/31/9999", 20, 0, 20, "1", "N", "A", "**", 1.10),
            RateRecord(1, "T", "01/01/1900", "12/31/9999", 20, 0, 20, "1", "N", "0", "**", 1.00),
            RateRecord(1, "M", "01/01/1900", "12/31/9999", 20, 0, 20, "1", "N", "0", "E*", 0.92),
            RateRecord(1, "T", "01/01/1900", "12/31/9999", 20, 0, 20, "1", "N", "0", "E*", 0.92),
        ],
    )
    reformatter = RateReformatter(result, starting_index=100)
    computed = reformatter.compute()
    assert computed["coi_reps"] == [(100, ("1", "N", "A"))]
    assert list(reformatter.current_coi_rows([(100, ("1", "N", "A"))], 0, 20, 20)) == [
        (100, 1, 20, 1, 0.10),
        (100, 1, 20, 2, 0.10),
        (100, 1, 20, 3, 0.10),
        (100, 1, 20, 4, 0.10),
        (100, 1, 20, 5, 0.10),
    ]
    assert list(reformatter.target_rows([(100, ("1", "N", "A"))], 20, 20)) == [
        (100, 20, 1.0, 0.23, 1.1, 0.23, 0.92),
    ]

    for table_name, rows in {
        "POINT_PVSRB": [[
            "PLAN1", 1, "M", "N", 1, "AA",
            None, None, None, None, 10, None, None, None, None, None,
        ]],
        "RATE_COI": [[10, 1, 20, 1, "0.125000"]],
        "RATE_TRGPREM": [],
        "RATE_SCR": [],
        "RATE_EPU": [],
    }.items():
        path = tmp_path / f"{table_name}.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(TABLE_SPECS[table_name].columns)
            writer.writerows(rows)

    package = WorkupPackage.load(tmp_path)

    class Repository:
        def validate_schema(self):
            return None

        def fetch_pointer_rows(self, table_name, plancode):
            return []

        def fetch_existing_indexes(self, table_name, indexes):
            return set()

        def fetch_rate_rows(self, table_name, indexes):
            return []

        def fetch_index_references(self, table_name, indexes):
            return {}

    analysis = analyze_package(package, Repository())
    plan = create_execution_plan(
        package, analysis, {name: LoadAction.INSERT for name in TABLE_SPECS},
    )
    assert plan.is_safe
    assert {
        table: len(rows)
        for table, rows in plan.insert_rows.items()
        if rows
    } == {"POINT_PVSRB": 1, "RATE_COI": 1}
    assert plan.delete_indexes == {}
    assert plan.delete_pointer_scopes == {}


def test_execution_plan_replace_golden(tmp_path):
    for table_name, rows in {
        "POINT_PVSRB": [[
            "PLAN1", 1, "M", "N", 1, "AA",
            None, None, None, None, 10, None, None, None, None, None,
        ]],
        "RATE_COI": [[10, 1, 20, 1, "0.125000"]],
        "RATE_TRGPREM": [],
        "RATE_SCR": [],
        "RATE_EPU": [],
    }.items():
        path = tmp_path / f"{table_name}.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(TABLE_SPECS[table_name].columns)
            writer.writerows(rows)
    package = WorkupPackage.load(tmp_path)

    class Repository:
        def __init__(self):
            self.pointer = [
                coerce_row(TABLE_SPECS["POINT_PVSRB"], [
                    "PLAN1", 1, "M", "N", 1, "AA",
                    None, None, None, None, 10, None, None, None, None, None,
                ], source="db")
            ]
            self.rate = [
                coerce_row(TABLE_SPECS["RATE_COI"], [10, 1, 20, 1, "0.999000"], source="db")
            ]

        def validate_schema(self):
            return None

        def fetch_pointer_rows(self, table_name, plancode):
            return self.pointer if table_name == "POINT_PVSRB" else []

        def fetch_existing_indexes(self, table_name, indexes):
            return {10} if table_name == "RATE_COI" and 10 in indexes else set()

        def fetch_rate_rows(self, table_name, indexes):
            return self.rate if table_name == "RATE_COI" and 10 in indexes else []

        def fetch_index_references(self, table_name, indexes):
            return {10: {"PLAN1"}} if table_name == "RATE_COI" and 10 in indexes else {}

    analysis = analyze_package(package, Repository())
    plan = create_execution_plan(
        package,
        analysis,
        {"POINT_PVSRB": LoadAction.REPLACE, "RATE_COI": LoadAction.REPLACE},
    )
    assert plan.is_safe
    assert plan.delete_pointer_scopes["POINT_PVSRB"] == (("PLAN1",),)
    assert plan.delete_indexes["RATE_COI"] == frozenset({10})
    assert len(plan.backup_rows["POINT_PVSRB"]) == 1
    assert len(plan.backup_rows["RATE_COI"]) == 1
