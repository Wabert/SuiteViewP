r"""Verify the Term reference lookups against the live UL_Rates database.

Usage:
    venv\Scripts\python.exe tools\rates\check_term_reference.py [DSN]
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from suiteview.ratemanager.workup import term_reference


def main() -> None:
    dsn = sys.argv[1] if len(sys.argv) > 1 else term_reference.DEFAULT_DSN
    data = term_reference.load_reference_data(dsn)
    print(json.dumps({
        "available": data.available,
        "error": data.error,
        "modefact_choices": [
            label for label, _index in term_reference.modefact_choices(data)
        ],
        "bandspec_choices": [
            label for label, _index in term_reference.bandspec_choices(data)
        ],
        "next_modefact_index": data.next_index(data.modefact),
        "next_bandspec_index": data.next_index(data.bandspecs),
        "used_base_index_count": len(data.used_base_indexes),
        "highest_base_index": max(data.used_base_indexes, default=0),
        "next_base_index": data.next_base_index(),
    }, indent=2))


if __name__ == "__main__":
    main()
