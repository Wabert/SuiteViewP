"""Launch the standard source entry point from an auditable tools script."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.run_suiteview import main

if __name__ == "__main__":
    main()
