"""Launch the FULL SuiteView taskbar in LOCAL DATA mode (offline dev/testing).

Identical to ``run_suiteview.py`` but sets ``SUITEVIEW_LOCAL_DATA=1`` so EVERY
policy/rate lookup (PolView, Illustration, ABR, …) reads the bundled SQLite
fixtures (``bundled_data/dev/policy_records.sqlite`` + ``rates.sqlite``) instead
of live DB2 / SQL-Server.  Uses a separate single-instance mutex and the window
title "SuiteView (LOCAL DATA)" so it stays independent of any live instance.

Local policies available offline: UE000576, U0688012, U0492070, U0656998.

⚠️ Dev/testing only — never the default launcher (live data is the real source).
"""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
for _p in (str(ROOT), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from run_suiteview import main  # noqa: E402  (reuse the one launcher implementation)


if __name__ == "__main__":
    main(local_data=True)
