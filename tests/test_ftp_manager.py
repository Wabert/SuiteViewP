from suiteview.core.ftp_manager import MainframeFTPManager


def _parse(line: str):
    manager = MainframeFTPManager("", "", "")
    return manager._parse_mvs_listing(line)


def test_parse_mvs_listing_skips_headers_and_dataset_attributes():
    assert _parse("NAME     VV.MM CREATED    CHANGED    TIME  SIZE INIT MOD ID") is None
    assert _parse("A8C201 3390   2025/12/29  1  45  FB  80  6160  PO  D03.AA0139.RESTART.SMOPRT") is None


def test_parse_mvs_listing_unix_directory():
    assert _parse("drwxr-xr-x   2 user     group        0     Oct 01 2008 SUBDIR") == {
        "name": "SUBDIR",
        "type": "directory",
        "size": 0,
        "modified": "Oct 01 2008",
        "vv_mm": "",
    }


def test_parse_mvs_listing_unix_member():
    assert _parse("-rw-r--r--   1 user     group       10 Jan 01 2007 AC") == {
        "name": "AC",
        "type": "member",
        "size": 10,
        "modified": "Jan 01 2007",
        "vv_mm": "",
    }


def test_parse_mvs_listing_ispf_member_with_stats():
    assert _parse("EXECULC3  01.00 2025/12/02 2025/12/02 10:12 28990 28990     0 AD9G44") == {
        "name": "EXECULC3",
        "type": "member",
        "size": 28990,
        "modified": "2025/12/02 10:12",
        "created": "2025/12/02",
        "vv_mm": "01.00",
    }


def test_parse_mvs_listing_simple_member_without_stats():
    assert _parse("CLTG1                                         604 40604     0 AD9G44") == {
        "name": "CLTG1",
        "type": "member",
        "size": 604,
        "modified": "",
        "created": "",
        "vv_mm": "",
    }


def test_parse_mvs_listing_rejects_invalid_member_names():
    assert _parse("TOO_LONG_NAME 01.00 2025/12/02") is None
    assert _parse("1BAD 01.00 2025/12/02") is None
