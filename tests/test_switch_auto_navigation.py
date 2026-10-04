"""Switch A/B auto-navigation in the terminal pane, from sign-on to a policy on 62D2.

Screen recognition and navigation decisions belong to the shared
``mainframe_navigator`` package (tested in Dev\\Mainframe_Navigator). These tests
drive ``MainframeTerminalScreen`` with a scripted host through the screens of
Robert's October 1 and 4, 2026 walk-throughs; policy numbers and names are
placeholders.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

LOGIN = {
    0: " Date 10/01/2026     AMERICAN NATIONAL INSURANCE COMPANY    Term: TERM0001",
    16: " User ID              ===> ",
    17: " Password or Phrase   ===> ",
    19: " New Password or Phrase ===> ",
    21: " Password Verification  ===> ",
    23: " Password             ===>            (If phrase is entered above)  SWITCH1A",
}
LOGIN_INPUTS = ((16, 26), (17, 26), (19, 28), (21, 28), (23, 26))
PASSWORD_NOTICE = {
    0: "VTAM/Switch 6.7  User: AB7Y02   Terminal: TERM0001",
    4: "(GSPPRLHF) ** YOUR PASSWORD WILL EXPIRE IN 15  DAYS ON 10/16/2026",
    21: 'PF10-PRINT                 Press "CLEAR" or "PF3" to continue',
}


def _menu(level: int, header: str, options: list[str], message: str = "") -> dict:
    rows = {
        0: "VTAM/Switch 6.7  SWITCH1A Session Selection       User: AB7Y02   Term: TERM0001",
        1: "===>",
        3: f"--------- {header:<40} ---------------- Level:{level} --",
        16: "Commands: HELP   KEYS   ROTATE FOR (Next Session)   OPEN (Start New Session)",
    }
    if message:
        rows[2] = message
    rows.update({4 + index: line for index, line in enumerate(options)})
    return rows


MAIN_MENU = _menu(1, "MENUOPT  SWITCH APPLICATION MAIN MENU", [
    "        1 TSO      TSO APPLICATIONS                              %TSO",
    "        3 CICS     CICS REGIONS                                  %CICS",
])
CICS_MENU = _menu(2, "CICS     CICS REGIONS", [
    "        3 CICSCRD  CICS ANICO CONSOLIDATED REGIONS               %CICSCRD",
    "        4 CICSCYB  CICS CYBERLIFE REGIONS                        %CICSCYB",
])
_CYBERLIFE = [
    "        1 CICSCKAS CICS CYBERLIFE DEV                  CHECKING",
    "        5 CICSCKMO CICS MODEL OFFICE                   CHECKING",
    "        7 CICSCKPR CYBERLIFE PRODUCTION                ACTIVE",
]
CYBERLIFE_MENU = _menu(3, "CICSCYB  CICS CYBERLIFE REGIONS", _CYBERLIFE)
UNAVAILABLE = "(GSLSSOPC) ** APPL CICSCKPR OR LOGICAL TERM LUNAME01 UNAVAILABLE"
CYBERLIFE_MENU_DOWN = _menu(3, "CICSCYB  CICS CYBERLIFE REGIONS", _CYBERLIFE, UNAVAILABLE)

PRESS_ENTER = {22: "          *** PRESS ENTER TO CONTINUE ***"}
WELCOME = {
    0: " MENU",
    1: "       Welcome to American National Ins CYBERLIFE PROD, CICS/TS 5.6",
    22: "    THIS WORKSTATION TERM0001 / T001 IS SIGNED ON FOR DOE, JANE",
}
TERMINAL_CONFIG = {
    3: "! - - - - - - - - -  SELECT TERMINAL CONFIGURATION - - - - - - - - - - - - - - !",
    6: "!                     PF1 - TERMINALS WITH 12 PF KEYS                          !",
    8: "!                     PF2 - TERMINALS WITH 24 PF KEYS                          !",
}
SYSTEM_MENU = {
    3: "!- - - - - - - - - - - SELECT REQUIRED FUNCTION - - - - - - - - - - - - - -   !",
    5: "!              PF1 - ISSUE SUBSYSTEM                                           !",
    7: "!              PF2 - CYBERLIFE INFORCE SUBSYSTEM                               !",
}
INFORCE_KEYS = {
    4: "! - - - - - - - - - CURRENT FUNCTION KEY DEFINITIONS - - - - - - - - - - - - - !",
    7: "! PF1  - 62D1,*. DISPLAY BASIC INFO     PF13 - U101,*. PAYMENT/REINSTATEMENT  !",
    8: "! PF2  - 62D2,*. DISPLAY COVERAGE       PF14 - U102,*. POLICY LOAN            !",
}
_BANNER = "CKPR-ANICO"


def _transaction(command: str, message: str, banner: str = _BANNER) -> dict:
    return {0: f" {command}", 23: f"{message:<68}{banner}"}


READY = _transaction("62D2,*.", "!  16 RECORD DOES NOT EXIST          !")
POLICY_A = _transaction("62D2,A1234567   ; .   ASOF LAST MVP", "CK620 DISPLAY COMPLETE")
POLICY_B = _transaction("62D2,B7654321   ; .   ASOF LAST MVP", "CK620 DISPLAY COMPLETE")
POLICY_A_MISSING = _transaction("62D2,A1234567   ;newco=01;.", "!  16 RECORD DOES NOT EXIST          !")

_QT_APP = None
_COMMAND_FIELD = ((0, 1),)


def _screen(rows: dict, inputs=((1, 4),), width: int = 30):
    from suiteview.mainframe_nav.tn3270 import Screen
    lines = []
    for row in range(24):
        line = rows.get(row, "")
        assert len(line) <= 80, f"row {row} is wider than 80 columns"
        lines.append(line.ljust(80))
    screen = Screen()
    screen.buffer = list("".join(lines))
    if not inputs or inputs[0] != (0, 1):
        screen.add_field(0, 0x20)
    for row, col in inputs:
        address = row * 80 + col
        screen.add_field(address, 0x00)
        screen.add_field(min(address + width + 1, 1919), 0x20)
    return screen


class _FakeClient:
    port = 992

    def __init__(self, pane, replies):
        self.pane = pane
        self.replies = list(replies)
        self.sent = []
        self.connected = True

    def _reply(self):
        from PyQt6.QtCore import QTimer
        if self.replies:
            screen = self.replies.pop(0)
            QTimer.singleShot(5, lambda: self.pane.on_screen_update(screen))

    def send_aid(self, aid, modified_fields=None):
        self.sent.append(("ENTER", [text for _, text in modified_fields or []]))
        self._reply()

    def send_pf_key(self, pf_num):
        self.sent.append((f"PF{pf_num}", []))
        self._reply()

    def disconnect(self):
        self.connected = False


@pytest.fixture
def pane(monkeypatch):
    global _QT_APP
    from PyQt6.QtWidgets import QApplication

    from suiteview.core import access_control
    from suiteview.data import mainframe_credentials as creds
    from suiteview.mainframe_nav import mainframe_terminal_screen as terminal_module

    monkeypatch.setattr(access_control, "guard_app_access", lambda _code: None)
    _QT_APP = QApplication.instance() or QApplication([])
    creds.save_mainframe_credentials("AB7Y02", "secret-pw")
    widget = terminal_module.MainframeTerminalScreen("A")
    monkeypatch.setattr(widget, "connect_to_mainframe",
                        lambda: pytest.fail("must continue on the open session"))
    yield widget
    widget.close()


def _start(pane, replies, start=LOGIN, start_inputs=LOGIN_INPUTS, policy="",
           region="CKPR", width=30, cics_region=None):
    client = pane.client = _FakeClient(pane, replies)
    pane.terminal.display_screen(_screen(start, start_inputs, width))
    pane._cics_region = cics_region
    pane.policy_input.setText(policy)
    pane.company_combo.setCurrentText("01")
    pane.start_cics_sequence(region, "7")
    return client.sent


_TO_TRANSACTION_SCREEN = [
    _screen(PRESS_ENTER, ()), _screen(WELCOME, _COMMAND_FIELD), _screen(TERMINAL_CONFIG, ()),
    _screen(SYSTEM_MENU, ()), _screen(INFORCE_KEYS, ()), _screen(READY, _COMMAND_FIELD),
]
_TO_TRANSACTION_KEYS = [("ENTER", []), ("ENTER", ["0000"]), ("PF2", []), ("PF2", []), ("PF2", [])]


def test_switch_a_signs_on_and_stops_with_the_host_message_when_the_region_is_down(pane):
    sent = _start(pane, [
        _screen(PASSWORD_NOTICE, ()), _screen(MAIN_MENU), _screen(CICS_MENU),
        _screen(CYBERLIFE_MENU), _screen(CYBERLIFE_MENU_DOWN),
    ], policy="A1234567")
    assert sent == [("ENTER", ["AB7Y02", "secret-pw"]), ("PF3", []),
                    ("ENTER", ["3"]), ("ENTER", ["4"]), ("ENTER", ["7"])]
    assert pane.automation_status.text() == f"❌ CKPR: {UNAVAILABLE}"


def test_switch_a_goes_from_the_region_menu_to_the_policy_on_62d2(pane):
    sent = _start(pane, [*_TO_TRANSACTION_SCREEN, _screen(POLICY_A, _COMMAND_FIELD)],
                  start=CYBERLIFE_MENU, start_inputs=((1, 4),), policy="a1234567")
    assert sent == [("ENTER", ["7"]), *_TO_TRANSACTION_KEYS,
                    ("ENTER", ["62D2,A1234567  ;newco=01;."])]
    assert pane.automation_status.text().startswith("✅ CKPR A1234567 (01) ")
    assert pane._cics_region == "CKPR"


def test_without_a_policy_the_pane_stops_ready_at_the_transaction_screen(pane):
    sent = _start(pane, list(_TO_TRANSACTION_SCREEN), start=CYBERLIFE_MENU,
                  start_inputs=((1, 4),))
    assert sent == [("ENTER", ["7"]), *_TO_TRANSACTION_KEYS]
    assert pane.automation_status.text().startswith("✅ CKPR ready ")


def test_a_missing_policy_shows_the_host_message(pane):
    sent = _start(pane, [_screen(POLICY_A_MISSING, _COMMAND_FIELD)],
                  start=READY, start_inputs=_COMMAND_FIELD, policy="A1234567")
    assert sent == [("ENTER", ["62D2,A1234567  ;newco=01;."])]
    assert pane.automation_status.text() == "❌ CKPR: A1234567: 16 RECORD DOES NOT EXIST"


def test_next_policy_reuses_the_signed_on_session(pane):
    pane.company_combo.addItem("04")
    pane.client = _FakeClient(pane, [_screen(POLICY_B, _COMMAND_FIELD)])
    pane.terminal.display_screen(_screen(POLICY_A, _COMMAND_FIELD))
    pane.policy_input.setText("B7654321")
    pane.company_combo.setCurrentText("04")
    pane.start_cics_sequence("CKPR", "7")
    assert pane.client.sent == [("ENTER", ["62D2,B7654321  ;newco=04;."])]
    assert pane.automation_status.text().startswith("✅ CKPR B7654321 (04) ")


def test_a_command_that_does_not_fit_is_never_sent_truncated(pane):
    sent = _start(pane, [], start=READY, start_inputs=_COMMAND_FIELD, policy="A1234567", width=10)
    assert sent == []
    assert "does not fit the 10-character input field" in pane.automation_status.text()


def test_a_session_in_another_region_is_replaced_by_a_fresh_connection(pane, monkeypatch):
    connects = []

    def _fresh_connection():
        connects.append(pane.terminal.last_screen)

    monkeypatch.setattr(pane, "connect_to_mainframe", _fresh_connection)
    sent = _start(pane, [], start=POLICY_A, start_inputs=_COMMAND_FIELD, region="CKMO",
                  cics_region="CKPR")
    assert sent == []
    assert connects == [None]
    assert pane._cics_region is None
    assert "Could not connect" in pane.automation_status.text()


def test_cics_screens_of_an_unknown_region_are_not_reused(pane, monkeypatch):
    connects = []
    monkeypatch.setattr(pane, "connect_to_mainframe", lambda: connects.append(True))
    _start(pane, [], start=INFORCE_KEYS, start_inputs=(), cics_region=None)
    assert connects == [True]


def test_switch_a_reports_a_silent_host(pane, monkeypatch):
    from suiteview.mainframe_nav import mainframe_terminal_screen as terminal_module
    monkeypatch.setattr(terminal_module, "SWITCH_REPLY_TIMEOUT_MS", 50)
    sent = _start(pane, [])
    assert sent == [("ENTER", ["AB7Y02", "secret-pw"])]
    assert "No reply" in pane.automation_status.text()


def test_an_unrecognised_open_session_is_replaced_by_a_fresh_connection(pane, monkeypatch):
    connects = []

    def _fresh_connection():
        connects.append(pane.terminal.last_screen)
        pane.client = _FakeClient(pane, [])
        pane.client.connected = False

    monkeypatch.setattr(pane, "connect_to_mainframe", _fresh_connection)
    old = _FakeClient(pane, [])
    pane.client = old
    pane.terminal.display_screen(_screen({0: "DFHAC2206 Transaction AB12 failed."}, ()))
    pane.start_cics_sequence("CKPR", "7")
    assert old.connected is False
    # The previous session's screen is never navigated against.
    assert connects == [None]
    assert "Could not connect" in pane.automation_status.text()
