"""Guard against double-encoded (UTF-8 read as cp1252) text in app sources.

Such mojibake shows up in the UI, e.g. a group header rendered as "â–£" instead
of "▣". It is typically introduced when a tool reads UTF-8 source as ANSI and
writes it back as UTF-8.
"""
import re
from pathlib import Path

SUITEVIEW = Path(__file__).resolve().parents[1] / "suiteview"
_CONT = "€‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ\u00a0¡¢£¤¥¦§¨©ª«¬\u00ad®¯°±²³´µ¶·¸¹º»¼½¾¿"
MOJIBAKE = re.compile(f"[ÂÃ][{_CONT}]|â[{_CONT}][{_CONT}]|ð[{_CONT}][{_CONT}][{_CONT}]")


def test_app_sources_have_no_mojibake():
    offenders = []
    for path in sorted(SUITEVIEW.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if MOJIBAKE.search(line):
                offenders.append(f"{path.relative_to(SUITEVIEW.parent).as_posix()}:{number}")
    assert offenders == []
