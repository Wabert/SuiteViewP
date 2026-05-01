"""
Seed default Common Tables — creates starter translation tables
if they don't already exist.

Call ``seed_defaults()`` at startup or on first use.
"""
from __future__ import annotations

from suiteview.audit.common_table import CommonTable
from suiteview.audit import common_table_store


def _seed_state_code_map():
    """State number → 2-char abbreviation."""
    if common_table_store.table_exists("StateCodeMap"):
        return
    rows = [
        ["01", "AL"], ["02", "AZ"], ["03", "AR"], ["04", "CA"],
        ["05", "CO"], ["06", "CT"], ["07", "DE"], ["08", "DC"],
        ["09", "FL"], ["10", "GA"], ["11", "ID"], ["12", "IL"],
        ["13", "IN"], ["14", "IA"], ["15", "KS"], ["16", "KY"],
        ["17", "LA"], ["18", "ME"], ["19", "MD"], ["20", "MA"],
        ["21", "MI"], ["22", "MN"], ["23", "MS"], ["24", "MO"],
        ["25", "MT"], ["26", "NE"], ["27", "NV"], ["28", "NH"],
        ["29", "NJ"], ["30", "NM"], ["31", "NY"], ["32", "NC"],
        ["33", "ND"], ["34", "OH"], ["35", "OK"], ["36", "OR"],
        ["37", "PA"], ["38", "RI"], ["39", "SC"], ["40", "SD"],
        ["41", "TN"], ["42", "TX"], ["43", "UT"], ["44", "VT"],
        ["45", "VA"], ["46", "WA"], ["47", "WV"], ["48", "WI"],
        ["49", "WY"], ["50", "AK"], ["51", "HI"], ["52", "PR"],
    ]
    ct = CommonTable(
        name="StateCodeMap",
        description="Maps CyberLife numeric state code to 2-character abbreviation",
        columns=[
            {"name": "state_num", "type": "TEXT"},
            {"name": "state_abbr", "type": "TEXT"},
        ],
        rows=rows,
    )
    common_table_store.save_table(ct)


def _seed_company_code_map():
    """CyberLife company code ↔ TAI company code."""
    if common_table_store.table_exists("CompanyCodeMap"):
        return
    rows = [
        ["01", "101", "Company 01"],
        ["04", "104", "Company 04"],
        ["06", "106", "Company 06"],
        ["08", "108", "Company 08"],
        ["26", "130", "Company 26"],
    ]
    ct = CommonTable(
        name="CompanyCodeMap",
        description="Maps CyberLife company codes to TAI company codes",
        columns=[
            {"name": "cl_code", "type": "TEXT"},
            {"name": "tai_code", "type": "TEXT"},
            {"name": "description", "type": "TEXT"},
        ],
        rows=rows,
    )
    common_table_store.save_table(ct)


def _seed_bill_mode_map():
    """Bill mode names to DB2 column values."""
    if common_table_store.table_exists("BillModeMap"):
        return
    rows = [
        ["Monthly", "1", ""],
        ["Quarterly", "3", ""],
        ["Semiannual", "6", ""],
        ["Annual", "12", ""],
        ["BiWeekly", "1", "2"],
        ["SemiMonthly", "1", "S"],
        ["9thly", "1", "9"],
        ["10thly", "1", "A"],
    ]
    ct = CommonTable(
        name="BillModeMap",
        description="Maps bill mode names to PMT_FQY_PER and NSD_MD_CD values",
        columns=[
            {"name": "mode_name", "type": "TEXT"},
            {"name": "pmt_fqy_per", "type": "TEXT"},
            {"name": "nsd_md_cd", "type": "TEXT"},
        ],
        rows=rows,
    )
    common_table_store.save_table(ct)


def seed_defaults():
    """Create all default common tables (skips any that already exist)."""
    _seed_state_code_map()
    _seed_company_code_map()
    _seed_bill_mode_map()
