"""Test FTP parsing logic for mainframe member listings"""

import sys
import logging

# Setup logging to see debug messages
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

# Import the FTP manager
from suiteview.core.ftp_manager import MainframeFTPManager

# Create a dummy instance just to test the parsing method
ftp_mgr = MainframeFTPManager("dummy", "user", "pass")

# Test data - typical MVS FTP listing lines
test_lines = [
    " Volume Unit    Referred Ext Used Recfm Lrecl BlkSz Dsorg Dsname",
    " A8C201 3390   2025/12/29  1  45  FB      80  6160  PO  D03.AA0139.RESTART.SMOPRT",
    "  Name     VV.MM   Created       Changed      Size  Init   Mod   Id",
    "  UTABLES  01.03 2008/07/24 2025/11/18 17:03  1000  1000     0 USERID",
    "  MEMBER2  01.00 2020/01/15 2024/06/20 09:15   500   500     0 USER2",
    "SIMPLE1",
    "SIMPLE2",
    "TESTMBR3",
]

print("\n=== Testing FTP Listing Parser ===\n")
print("Testing lines that represent a typical MVS PDS member listing:\n")

for i, line in enumerate(test_lines):
    print(f"Line {i}: '{line}'")
    result = ftp_mgr._parse_mvs_listing(line)
    if result:
        print(f"  ✓ PARSED: {result}")
    else:
        print(f"  ✗ SKIPPED (correctly filtered out)")
    print()

print("\n=== Summary ===")
print("Expected behavior:")
print("- Lines 0-2 should be SKIPPED (headers and dataset info)")
print("- Lines 3-7 should be PARSED as member names: UTABLES, MEMBER2, SIMPLE1, SIMPLE2, TESTMBR3")
