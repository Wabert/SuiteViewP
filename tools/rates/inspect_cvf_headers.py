"""Summarize CVF header variants without materializing millions of rate cells."""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.json_store import write_json
from suiteview.ratemanager.whole_life.parsers import _CV_HEADER, _CV_LABELS, _lines


def main():
    arg = sys.argv[1]
    config = json.loads(Path(arg[1:]).read_text(encoding="utf-8")) if arg.startswith("@") else json.loads(arg)
    reports = []
    for path in config["paths"]:
        counts, rate_cells, examples = Counter(), Counter(), {}
        pending = False
        for number, line in _lines(path, null_padding=True):
            if pending:
                match = _CV_HEADER.fullmatch(line)
                if match is None:
                    raise ValueError(f"{path}:{number}: Unrecognized CVF header: {line!r}")
                fields = match.groupdict()
                first, last = int(fields["first"]), int(fields["last"])
                if first > last:
                    raise ValueError(f"{path}:{number}: FIRST exceeds LAST")
                key = (fields["user"], fields["class"], fields["first"],
                       "absent" if fields["zero"] == "NO ZERO DUR" else "present")
                counts[key] += 1
                rate_cells[key] += last - first + 1
                examples.setdefault(key, {"line": number, **fields})
                pending = False
            elif " ".join(line.strip().removeprefix("0").split()) == _CV_LABELS:
                pending = True
        if pending or not counts:
            raise ValueError(f"{path}: Missing or truncated CVF headers")
        reports.append({
            "path": path,
            "headers": sum(counts.values()),
            "rate_cells": sum(rate_cells.values()),
            "variants": [
                {"user": key[0], "class": key[1], "first_duration": int(key[2]),
                 "zero": key[3], "records": count, "rate_cells": rate_cells[key],
                 "example": examples[key]}
                for key, count in sorted(counts.items())
            ],
        })
    result = {"sources": reports}
    if config.get("output"):
        write_json(config["output"], result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
