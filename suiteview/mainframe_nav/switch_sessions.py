"""Switch A / Switch B terminal endpoints.

The mainframe "Switch" front end is reached through two TN3270 endpoints:
Switch A drives the left terminal pane and Switch B the right one, so two
policies (or regions) can be signed on at the same time. Each side keeps its
own host/port/SSL/terminal type in ``terminal_settings.json``; the sign-on
itself is never stored here -- it comes from the shared Passwords store.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, fields

from suiteview.core.json_store import read_json, write_json
from suiteview.core.profile_paths import profile_path
from suiteview.data.mainframe_credentials import (
    load_mainframe_credentials, save_mainframe_credentials,
)

logger = logging.getLogger(__name__)

SWITCH_SIDES = ("A", "B")
_PLAINTEXT_CREDENTIAL_KEYS = ("userid", "password")


@dataclass(frozen=True)
class TerminalEndpoint:
    """Where one terminal pane connects."""

    host: str = "PRODESA"
    port: int = 992
    ssl: bool = True
    term_type: str = "IBM-3278-2-E"


def switch_label(side: str) -> str:
    return f"Switch {side.upper()}"


def _side_key(side: str) -> str:
    side = side.upper()
    if side not in SWITCH_SIDES:
        raise ValueError(f"Unknown Switch side {side!r}; expected one of {SWITCH_SIDES}.")
    return f"switch_{side.lower()}"


def _settings_file():
    return profile_path("terminal_settings.json")


def _read() -> dict:
    data = read_json(_settings_file(), default={})
    return data if isinstance(data, dict) else {}


def _endpoint_from(values: dict, fallback: TerminalEndpoint) -> TerminalEndpoint:
    known = {f.name for f in fields(TerminalEndpoint)}
    merged = asdict(fallback)
    merged.update({key: value for key, value in values.items() if key in known})
    return TerminalEndpoint(
        host=str(merged["host"]),
        port=int(merged["port"]),
        ssl=bool(merged["ssl"]),
        term_type=str(merged["term_type"]),
    )


def load_endpoint(side: str) -> TerminalEndpoint:
    """Return the saved endpoint for *side*.

    A side that was never saved uses the single pre-Switch terminal settings
    (flat keys) when present, else the defaults.
    """
    data = _read()
    shared = _endpoint_from(data, TerminalEndpoint())
    saved = data.get(_side_key(side))
    return _endpoint_from(saved, shared) if isinstance(saved, dict) else shared


def save_endpoint(side: str, endpoint: TerminalEndpoint) -> None:
    """Persist *endpoint* for *side*; every side is written explicitly."""
    data = {_side_key(other): asdict(load_endpoint(other)) for other in SWITCH_SIDES}
    data[_side_key(side)] = asdict(endpoint)
    write_json(_settings_file(), data)


def retire_plaintext_credentials() -> None:
    """Move a sign-on saved in clear text by older builds into the shared store.

    Older terminal settings wrote ``userid``/``password`` into
    ``terminal_settings.json`` in plain text. If the shared store has no
    complete sign-on yet, adopt that one; then rewrite the file without them.
    When the shared store cannot be read, the file is left untouched so the
    only readable copy is not lost.
    """
    data = _read()
    if not any(key in data for key in _PLAINTEXT_CREDENTIAL_KEYS):
        return
    try:
        saved = load_mainframe_credentials()
        userid = str(data.get("userid") or "").strip()
        password = str(data.get("password") or "")
        if not saved.complete and userid and password:
            save_mainframe_credentials(userid, password)
            logger.info("Moved the terminal sign-on into the shared Passwords store")
    except Exception as exc:  # noqa: BLE001 - keep the file; the user can re-enter
        logger.error("Could not move the terminal sign-on into the Passwords store: %s", exc)
        return
    write_json(_settings_file(),
               {_side_key(side): asdict(load_endpoint(side)) for side in SWITCH_SIDES})
    logger.info("Removed the plain-text sign-on from terminal_settings.json")
