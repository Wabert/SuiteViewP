"""Generate CyberLife SQL golden files from the current builder."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.cyberlife_sql_cases import CASES
from tests.test_cyberlife_sql_golden import GOLDEN_DIR, render_case


def main() -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    expected = {f"{case.name}.sql" for case in CASES}
    for old in GOLDEN_DIR.glob("*.sql"):
        if old.name not in expected:
            old.unlink()
    for case in CASES:
        path = GOLDEN_DIR / f"{case.name}.sql"
        path.write_text(render_case(case))
        print(str(path.relative_to(Path.cwd())))


if __name__ == "__main__":
    main()
