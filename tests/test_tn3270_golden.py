"""Golden byte-stream coverage for the mainframe TN3270 parser.

The fixtures are hand-built from the parser's behavior at commit 281deef.
They intentionally pin private decoder behavior before the protocol pipeline is
split into smaller pieces.
"""

from __future__ import annotations

from suiteview.mainframe_nav.tn3270 import (
    AID,
    Order3270,
    TN3270Client,
    TelnetCmd,
    TelnetOpt,
    ascii_to_ebcdic,
    encode_buffer_address,
)


class FakeSocket:
    """Small socket double for deterministic negotiation and send captures."""

    def __init__(self, chunks: list[bytes] | None = None):
        self._chunks = list(chunks or [])
        self.sent: list[bytes] = []
        self.timeouts: list[float] = []

    def settimeout(self, timeout: float):
        self.timeouts.append(timeout)

    def recv(self, _size: int) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        return b""

    def sendall(self, data: bytes):
        self.sent.append(data)


def _client_with_socket(sock: FakeSocket) -> TN3270Client:
    client = TN3270Client("host.example")
    client.socket = sock
    client.connected = True
    return client


def _ebcdic(text: str) -> bytes:
    return bytes(ascii_to_ebcdic(char) for char in text)


def _order_stream_covering_supported_orders() -> bytes:
    return b"".join(
        [
            bytes([Order3270.SBA]),
            encode_buffer_address(5),
            bytes([Order3270.SF, 0x20]),
            _ebcdic("ABC"),
            bytes([Order3270.SBA]),
            encode_buffer_address(20),
            bytes([Order3270.SFE, 2, 0x41, 0xF1, 0xC0, 0x11]),
            bytes([Order3270.SA, 0x41, 0xF2]),
            bytes([Order3270.MF, 1, 0xC0, 0x20]),
            bytes([Order3270.GE, ascii_to_ebcdic("D")]),
            bytes([Order3270.PT, Order3270.IC, Order3270.RA]),
            encode_buffer_address(25),
            bytes([ascii_to_ebcdic("E"), Order3270.EUA]),
            encode_buffer_address(28),
            _ebcdic("F"),
        ]
    )


def test_telnet_negotiation_replies_and_processes_eor_record():
    screen_record = (
        bytes([0x05, 0x00, Order3270.SBA])
        + encode_buffer_address(0)
        + _ebcdic("HI")
    )
    negotiation = b"".join(
        [
            bytes([TelnetCmd.IAC, TelnetCmd.DO, TelnetOpt.TERMINAL_TYPE]),
            bytes([TelnetCmd.IAC, TelnetCmd.DO, TelnetOpt.BINARY]),
            bytes([TelnetCmd.IAC, TelnetCmd.DO, TelnetOpt.EOR]),
            bytes([TelnetCmd.IAC, TelnetCmd.WILL, TelnetOpt.BINARY]),
            bytes([TelnetCmd.IAC, TelnetCmd.WILL, TelnetOpt.EOR]),
            bytes(
                [
                    TelnetCmd.IAC,
                    TelnetCmd.SB,
                    TelnetOpt.TERMINAL_TYPE,
                    1,
                    TelnetCmd.IAC,
                    TelnetCmd.SE,
                ]
            ),
            screen_record,
            bytes([TelnetCmd.IAC, TelnetCmd.EOR]),
        ]
    )
    sock = FakeSocket([negotiation, b""])
    client = _client_with_socket(sock)

    client._negotiate()

    assert sock.sent == [
        bytes([TelnetCmd.IAC, TelnetCmd.WILL, TelnetOpt.TERMINAL_TYPE]),
        bytes([TelnetCmd.IAC, TelnetCmd.WILL, TelnetOpt.BINARY]),
        bytes([TelnetCmd.IAC, TelnetCmd.WILL, TelnetOpt.EOR]),
        bytes([TelnetCmd.IAC, TelnetCmd.DO, TelnetOpt.BINARY]),
        bytes([TelnetCmd.IAC, TelnetCmd.DO, TelnetOpt.EOR]),
        bytes([TelnetCmd.IAC, TelnetCmd.SB, TelnetOpt.TERMINAL_TYPE, 0])
        + b"IBM-3278-2-E"
        + bytes([TelnetCmd.IAC, TelnetCmd.SE]),
    ]
    assert client.binary_mode is True
    assert client.screen.get_string_at(0, 0, 2) == "HI"


def test_write_orders_apply_current_buffer_fields_attributes_and_cursor():
    client = TN3270Client("host.example")

    client._process_write_data(_order_stream_covering_supported_orders())

    assert client.screen.get_string_at(0, 0, 30) == "      ABC            DEEE   F "
    assert [(field.address, field.attribute) for field in client.screen.fields] == [
        (5, 0x20),
        (20, 0x11),
    ]
    assert client.screen.fields[0].protected is True
    assert client.screen.fields[1].numeric is True
    assert client.screen.fields[1].modified is True
    assert client.screen.attributes[5] == 0x20
    assert client.screen.attributes[20] == 0x11
    assert client.screen.cursor_address == 29


def test_write_erase_write_and_alternate_commands_preserve_current_behavior():
    command_cases = [
        (0x01, "Write", False),
        (0xF1, "SNA Write", False),
        (0x05, "Erase/Write", True),
        (0xF5, "SNA Erase/Write", True),
        (0x0D, "Erase/Write Alternate", True),
        (0x7E, "SNA Erase/Write Alternate", True),
    ]

    for command, _label, clears_first in command_cases:
        client = TN3270Client("host.example")
        client.screen.set_char(0, "Z")
        data = bytes([command, 0x00, Order3270.SBA]) + encode_buffer_address(10) + _ebcdic("OK")

        client._process_3270_data(data)

        assert client.screen.get_char(0) == (" " if clears_first else "Z")
        assert client.screen.get_string_at(0, 10, 2) == "OK"


def test_read_buffer_and_read_modified_commands_do_not_update_screen():
    for command in (0x02, 0xF2, 0x06, 0xF6):
        client = TN3270Client("host.example")
        client.screen.set_char(0, "Z")
        client.screen.cursor_address = 77

        client._process_3270_data(bytes([command, 0x00]) + _ebcdic("IGNORED"))

        assert client.screen.get_char(0) == "Z"
        assert client.screen.cursor_address == 77


def test_write_structured_field_query_reply_is_encoded_with_eor():
    sock = FakeSocket()
    client = _client_with_socket(sock)
    read_partition_query = bytes([0x00, 0x05, 0x01, 0xFF, 0x02])

    client._process_3270_data(bytes([0x11]) + read_partition_query)

    assert len(sock.sent) == 1
    reply = sock.sent[0]
    assert reply[0] == 0x88
    assert reply.endswith(bytes([TelnetCmd.IAC, TelnetCmd.EOR]))
    assert bytes([0x81, 0x81]) in reply
    assert bytes([0x81, 0x80]) in reply


def test_aid_read_modified_outbound_encoding_for_enter_and_clear():
    sock = FakeSocket()
    client = _client_with_socket(sock)
    client.screen.cursor_address = 5

    client.send_aid(AID.ENTER, [(10, "A1")])
    client.send_aid(AID.CLEAR)

    assert sock.sent[0] == (
        bytes([AID.ENTER])
        + encode_buffer_address(5)
        + bytes([Order3270.SBA])
        + encode_buffer_address(10)
        + _ebcdic("A1")
        + bytes([TelnetCmd.IAC, TelnetCmd.EOR])
    )
    assert sock.sent[1] == bytes([AID.CLEAR, TelnetCmd.IAC, TelnetCmd.EOR])


def test_tn3270e_aid_encoding_prepends_header():
    sock = FakeSocket()
    client = _client_with_socket(sock)
    client.tn3270e_mode = True
    client.screen.cursor_address = 1

    client.send_aid(AID.PF1)

    assert sock.sent[0] == (
        b"\x00\x00\x00\x00\x00"
        + bytes([AID.PF1])
        + encode_buffer_address(1)
        + bytes([TelnetCmd.IAC, TelnetCmd.EOR])
    )
