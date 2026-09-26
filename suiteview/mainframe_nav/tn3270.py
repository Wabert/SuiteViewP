"""TN3270 Terminal Emulator Core.

The byte pipeline is intentionally split into four small stages:

``TelnetFrameDecoder``
    Walks telnet IAC framing, emits negotiation frames, and yields complete
    3270 records when an EOR is reached.
``TN3270CommandDecoder``
    Classifies a 3270 record into Write, Erase/Write, Erase/Write Alternate,
    Read Buffer, Read Modified, Write Structured Field, or raw write payload.
``ScreenApplier``
    Parses write-order dataclasses and mutates the screen buffer through a
    handler table keyed by 3270 order byte.
``TN3270Client``
    Owns sockets, replies to telnet negotiation, and sends outbound AID/read
    modified records.

Supported inbound commands are W, EW, EWA, RB, RM and WSF. Supported write
orders are SBA, SF, SFE, SA, MF, IC, PT, RA, EUA and GE. Known gaps are listed
in ``docs/TN3270.md``.
"""

import socket
import ssl
import logging
from typing import Optional, Tuple, List, Callable, Dict
from enum import IntEnum
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# Telnet commands
class TelnetCmd(IntEnum):
    IAC = 255   # Interpret As Command
    DONT = 254
    DO = 253
    WONT = 252
    WILL = 251
    SB = 250    # Sub-negotiation Begin
    SE = 240    # Sub-negotiation End
    EOR = 239   # End of Record
    

# Telnet options
class TelnetOpt(IntEnum):
    BINARY = 0
    ECHO = 1
    TERMINAL_TYPE = 24
    EOR = 25
    TN3270E = 40


# 3270 Orders
class Order3270(IntEnum):
    SF = 0x1D     # Start Field
    SFE = 0x29    # Start Field Extended
    SBA = 0x11    # Set Buffer Address
    SA = 0x28     # Set Attribute
    MF = 0x2C     # Modify Field
    IC = 0x13     # Insert Cursor
    PT = 0x05     # Program Tab
    RA = 0x3C     # Repeat to Address
    EUA = 0x12    # Erase Unprotected to Address
    GE = 0x08     # Graphic Escape


# 3270 AID codes (Attention Identifier)
class AID(IntEnum):
    NONE = 0x60
    ENTER = 0x7D
    PF1 = 0xF1
    PF2 = 0xF2
    PF3 = 0xF3
    PF4 = 0xF4
    PF5 = 0xF5
    PF6 = 0xF6
    PF7 = 0xF7
    PF8 = 0xF8
    PF9 = 0xF9
    PF10 = 0x7A
    PF11 = 0x7B
    PF12 = 0x7C
    PF13 = 0xC1
    PF14 = 0xC2
    PF15 = 0xC3
    PF16 = 0xC4
    PF17 = 0xC5
    PF18 = 0xC6
    PF19 = 0xC7
    PF20 = 0xC8
    PF21 = 0xC9
    PF22 = 0x4A
    PF23 = 0x4B
    PF24 = 0x4C
    PA1 = 0x6C
    PA2 = 0x6E
    PA3 = 0x6B
    CLEAR = 0x6D
    SYSREQ = 0xF0


# EBCDIC to ASCII translation table
EBCDIC_TO_ASCII = {
    0x40: ' ', 0x4B: '.', 0x4C: '<', 0x4D: '(', 0x4E: '+', 0x4F: '|',
    0x50: '&', 0x5A: '!', 0x5B: '$', 0x5C: '*', 0x5D: ')', 0x5E: ';',
    0x5F: '^', 0x60: '-', 0x61: '/', 0x6A: '¦', 0x6B: ',', 0x6C: '%',
    0x6D: '_', 0x6E: '>', 0x6F: '?', 0x79: '`', 0x7A: ':', 0x7B: '#',
    0x7C: '@', 0x7D: "'", 0x7E: '=', 0x7F: '"',
    0x81: 'a', 0x82: 'b', 0x83: 'c', 0x84: 'd', 0x85: 'e', 0x86: 'f',
    0x87: 'g', 0x88: 'h', 0x89: 'i', 0x91: 'j', 0x92: 'k', 0x93: 'l',
    0x94: 'm', 0x95: 'n', 0x96: 'o', 0x97: 'p', 0x98: 'q', 0x99: 'r',
    0xA1: '~', 0xA2: 's', 0xA3: 't', 0xA4: 'u', 0xA5: 'v', 0xA6: 'w',
    0xA7: 'x', 0xA8: 'y', 0xA9: 'z', 0xAD: '[', 0xBD: ']',
    0xC0: '{', 0xC1: 'A', 0xC2: 'B', 0xC3: 'C', 0xC4: 'D', 0xC5: 'E',
    0xC6: 'F', 0xC7: 'G', 0xC8: 'H', 0xC9: 'I', 0xD0: '}', 0xD1: 'J',
    0xD2: 'K', 0xD3: 'L', 0xD4: 'M', 0xD5: 'N', 0xD6: 'O', 0xD7: 'P',
    0xD8: 'Q', 0xD9: 'R', 0xE0: '\\', 0xE2: 'S', 0xE3: 'T', 0xE4: 'U',
    0xE5: 'V', 0xE6: 'W', 0xE7: 'X', 0xE8: 'Y', 0xE9: 'Z',
    0xF0: '0', 0xF1: '1', 0xF2: '2', 0xF3: '3', 0xF4: '4', 0xF5: '5',
    0xF6: '6', 0xF7: '7', 0xF8: '8', 0xF9: '9',
}

# ASCII to EBCDIC translation table (reverse of above)
ASCII_TO_EBCDIC = {v: k for k, v in EBCDIC_TO_ASCII.items()}
# Add uppercase mappings for consistency
for c in 'abcdefghijklmnopqrstuvwxyz':
    ASCII_TO_EBCDIC[c.upper()] = ASCII_TO_EBCDIC.get(c.upper(), 0x40)


def ebcdic_to_ascii(byte_val: int) -> str:
    """Convert EBCDIC byte to ASCII character"""
    return EBCDIC_TO_ASCII.get(byte_val, ' ')


def ascii_to_ebcdic(char: str) -> int:
    """Convert ASCII character to EBCDIC byte"""
    return ASCII_TO_EBCDIC.get(char, 0x40)


def decode_buffer_address(b1: int, b2: int, max_address: int = 1920) -> int:
    """Decode 3270 buffer address from two bytes
    
    Args:
        b1: First byte
        b2: Second byte  
        max_address: Maximum valid address (default 1920 for 24x80 screen)
    
    Returns:
        Decoded address, clamped to valid range
    """
    # 12-bit address encoding
    if b1 & 0xC0 == 0x00:
        # 14-bit address
        addr = ((b1 & 0x3F) << 8) | b2
    else:
        # 12-bit address
        addr = ((b1 & 0x3F) << 6) | (b2 & 0x3F)
    
    # Clamp to valid range to prevent index errors
    if addr < 0:
        addr = 0
    elif addr >= max_address:
        addr = addr % max_address  # Wrap around
    
    return addr


def encode_buffer_address(addr: int) -> bytes:
    """Encode buffer address to 3270 format"""
    # Use 12-bit encoding
    table = [
        0x40, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7,
        0xC8, 0xC9, 0x4A, 0x4B, 0x4C, 0x4D, 0x4E, 0x4F,
        0x50, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7,
        0xD8, 0xD9, 0x5A, 0x5B, 0x5C, 0x5D, 0x5E, 0x5F,
        0x60, 0x61, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7,
        0xE8, 0xE9, 0x6A, 0x6B, 0x6C, 0x6D, 0x6E, 0x6F,
        0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7,
        0xF8, 0xF9, 0x7A, 0x7B, 0x7C, 0x7D, 0x7E, 0x7F,
    ]
    return bytes([table[(addr >> 6) & 0x3F], table[addr & 0x3F]])


@dataclass(frozen=True)
class TelnetFrame:
    """A telnet negotiation frame extracted from an IAC stream."""

    command: int
    option: Optional[int] = None
    payload: bytes = b""


@dataclass(frozen=True)
class TelnetDecodeBatch:
    """Frames and complete 3270 records decoded from one byte chunk."""

    frames: Tuple[TelnetFrame, ...]
    records: Tuple[bytes, ...]


class TelnetFrameDecoder:
    """Decode telnet IAC frames while preserving 3270 record bytes."""

    def __init__(self):
        self._record = bytearray()

    def decode(self, data: bytes) -> TelnetDecodeBatch:
        """Decode one chunk into negotiation frames and EOR-delimited records."""
        frames: List[TelnetFrame] = []
        records: List[bytes] = []
        i = 0

        while i < len(data):
            if data[i] != TelnetCmd.IAC:
                self._record.append(data[i])
                i += 1
                continue

            if i + 1 >= len(data):
                break

            cmd = data[i + 1]
            if cmd in (TelnetCmd.DO, TelnetCmd.DONT, TelnetCmd.WILL, TelnetCmd.WONT):
                if i + 2 >= len(data):
                    break
                frames.append(TelnetFrame(command=cmd, option=data[i + 2]))
                i += 3
            elif cmd == TelnetCmd.SB:
                se_pos = data.find(bytes([TelnetCmd.IAC, TelnetCmd.SE]), i)
                if se_pos > 0:
                    frames.append(
                        TelnetFrame(
                            command=cmd,
                            payload=data[i + 2:se_pos],
                        )
                    )
                    i = se_pos + 2
                else:
                    i += 2
            elif cmd == TelnetCmd.EOR:
                records.append(bytes(self._record))
                self._record.clear()
                i += 2
            elif cmd == TelnetCmd.IAC:
                self._record.append(TelnetCmd.IAC)
                i += 2
            else:
                frames.append(TelnetFrame(command=cmd))
                i += 2

        return TelnetDecodeBatch(frames=tuple(frames), records=tuple(records))

    def flush_record(self) -> bytes:
        """Return and clear any data received without a final EOR."""
        record = bytes(self._record)
        self._record.clear()
        return record

    @staticmethod
    def extract_payload(data: bytes) -> bytes:
        """Strip telnet commands from one already-buffered record."""
        decoder = TelnetFrameDecoder()
        batch = decoder.decode(data)
        payload = decoder.flush_record()
        if batch.records:
            payload = b"".join(batch.records) + payload
        return payload


@dataclass(frozen=True)
class TN3270Command:
    """A decoded 3270 command and the payload relevant to the command."""

    name: str
    command_byte: int
    payload: bytes
    wcc: Optional[int] = None
    clear_screen: bool = False
    is_write: bool = False
    is_structured_field: bool = False
    is_read: bool = False
    is_raw_write: bool = False


class TN3270CommandDecoder:
    """Classify 3270 records into command objects."""

    WRITE_COMMANDS: Dict[int, Tuple[str, bool]] = {
        0x01: ("Write", False),
        0xF1: ("Write", False),
        0x05: ("Erase/Write", True),
        0xF5: ("Erase/Write", True),
        0x0D: ("Erase/Write Alternate", True),
        0x7E: ("Erase/Write Alternate", True),
    }
    STRUCTURED_FIELD_COMMANDS = {0x11, 0xF3}
    READ_MODIFIED_COMMANDS = {0x06, 0xF6}
    READ_BUFFER_COMMANDS = {0x02, 0xF2}

    def decode(self, data: bytes) -> Optional[TN3270Command]:
        """Decode a record; returns ``None`` for empty input."""
        if not data:
            return None

        command_byte = data[0]
        if command_byte in self.WRITE_COMMANDS:
            name, clear_screen = self.WRITE_COMMANDS[command_byte]
            wcc = data[1] if len(data) > 1 else None
            payload = data[2:] if len(data) > 1 else b""
            return TN3270Command(
                name=name,
                command_byte=command_byte,
                payload=payload,
                wcc=wcc,
                clear_screen=clear_screen,
                is_write=True,
            )
        if command_byte in self.STRUCTURED_FIELD_COMMANDS:
            return TN3270Command(
                name="Write Structured Field",
                command_byte=command_byte,
                payload=data[1:],
                is_structured_field=True,
            )
        if command_byte in self.READ_MODIFIED_COMMANDS:
            return TN3270Command(
                name="Read Modified",
                command_byte=command_byte,
                payload=data[1:],
                is_read=True,
            )
        if command_byte in self.READ_BUFFER_COMMANDS:
            return TN3270Command(
                name="Read Buffer",
                command_byte=command_byte,
                payload=data[1:],
                is_read=True,
            )
        return TN3270Command(
            name=f"Raw Write ({hex(command_byte)})",
            command_byte=command_byte,
            payload=data,
            is_write=True,
            is_raw_write=True,
        )


@dataclass(frozen=True)
class WriteOrder:
    """One decoded write-order or data-character operation."""

    code: Optional[int]
    name: str
    raw: bytes
    address: Optional[int] = None
    end_address: Optional[int] = None
    attribute: Optional[int] = None
    attribute_pairs: Tuple[Tuple[int, int], ...] = ()
    char: Optional[str] = None
    count: int = 0


@dataclass(frozen=True)
class WriteApplyStats:
    """Summary of write-order application for logging and tests."""

    chars_written: int = 0
    orders_processed: int = 0


@dataclass
class Field:
    """Represents a 3270 field"""
    address: int
    attribute: int
    length: int = 0
    protected: bool = False
    numeric: bool = False
    display: bool = True
    intensified: bool = False
    modified: bool = False
    content: str = ""


@dataclass 
class Screen:
    """Represents the 3270 screen buffer"""
    rows: int = 24
    cols: int = 80
    buffer: List[str] = field(default_factory=list)
    attributes: List[int] = field(default_factory=list)
    fields: List[Field] = field(default_factory=list)
    cursor_address: int = 0
    
    def __post_init__(self):
        size = self.rows * self.cols
        if not self.buffer:
            self.buffer = [' '] * size
        if not self.attributes:
            self.attributes = [0] * size
    
    def clear(self):
        """Clear the screen"""
        size = self.rows * self.cols
        self.buffer = [' '] * size
        self.attributes = [0] * size
        self.fields = []
        self.cursor_address = 0
    
    def get_text(self) -> str:
        """Get screen as text"""
        lines = []
        for row in range(self.rows):
            start = row * self.cols
            end = start + self.cols
            line = ''.join(self.buffer[start:end])
            lines.append(line)
        return '\n'.join(lines)
    
    def get_string_at(self, row: int, col: int, length: int) -> str:
        """Get string at specific coordinates"""
        start_addr = row * self.cols + col
        end_addr = start_addr + length
        if start_addr < 0:
            start_addr = 0
        if end_addr > len(self.buffer):
            end_addr = len(self.buffer)
            
        return ''.join(self.buffer[start_addr:end_addr])

    def find_text(self, text: str) -> Optional[Tuple[int, int]]:
        """Find text on screen and return (row, col)"""
        full_buffer = ''.join(self.buffer)
        pos = full_buffer.find(text)
        if pos != -1:
            return (pos // self.cols, pos % self.cols)
        return None
    
    def add_field(self, address: int, attribute: int):
        """Add a field at the given address with attribute byte"""
        # Parse attribute byte
        # Bit 5 (0x20): Protected
        # Bit 4 (0x10): Numeric
        # Bits 2-3: Display/Selector pen detect
        #   00 = Normal, non-pen-detectable
        #   01 = Normal, pen-detectable  
        #   10 = Intensified display, pen-detectable
        #   11 = Non-display, non-pen-detectable (password fields!)
        # Bit 0 (0x01): Modified Data Tag
        
        protected = bool(attribute & 0x20)
        numeric = bool(attribute & 0x10)
        display_bits = (attribute >> 2) & 0x03
        hidden = (display_bits == 0x03)  # Non-display field (password)
        intensified = (display_bits == 0x02)
        modified = bool(attribute & 0x01)
        
        row = address // 80
        col = address % 80
        field_type = "protected" if protected else "INPUT"
        logger.info(f"add_field: addr={address} (row={row}, col={col}) {field_type} hidden={hidden}")
        
        field_obj = Field(
            address=address,
            attribute=attribute,
            protected=protected,
            numeric=numeric,
            display=not hidden,
            intensified=intensified,
            modified=modified
        )
        self.fields.append(field_obj)
    
    def get_input_fields(self) -> List[Field]:
        """Get list of unprotected (input) fields"""
        return [f for f in self.fields if not f.protected]
    
    def get_next_input_field(self, current_addr: int) -> Optional[int]:
        """Get address of next unprotected field after current position"""
        input_fields = self.get_input_fields()
        if not input_fields:
            return None
        
        # Sort by address
        input_fields.sort(key=lambda f: f.address)
        
        # First, find which field we're currently in (if any)
        current_field_addr = None
        for f in input_fields:
            if f.address < current_addr:
                # We might be in this field - check if we're before the next field
                current_field_addr = f.address
            elif f.address >= current_addr:
                break
        
        # Find next field after the current field (not just after current position)
        for f in input_fields:
            if current_field_addr is not None:
                # Skip the field we're currently in
                if f.address > current_field_addr:
                    return f.address + 1
            else:
                # Not in any field, find first field after current position
                if f.address >= current_addr:
                    return f.address + 1
        
        # Wrap around to first field
        if input_fields:
            return input_fields[0].address + 1
        
        return None
    
    def get_prev_input_field(self, current_addr: int) -> Optional[int]:
        """Get address of previous unprotected field before current position"""
        input_fields = self.get_input_fields()
        if not input_fields:
            return None
        
        # Sort by address ascending first to find current field
        input_fields.sort(key=lambda f: f.address)
        
        # Find which field we're currently in (if any)
        current_field_addr = None
        for f in input_fields:
            if f.address < current_addr:
                current_field_addr = f.address
            elif f.address >= current_addr:
                break
        
        # Sort by address descending to find previous
        input_fields.sort(key=lambda f: f.address, reverse=True)
        
        # Find previous field before the current field
        for f in input_fields:
            if current_field_addr is not None:
                # Skip the field we're currently in, find field before it
                if f.address < current_field_addr:
                    return f.address + 1
            else:
                # Not in any field, find first field before current position
                if f.address < current_addr:
                    return f.address + 1
        
        # Wrap around to last field
        if input_fields:
            return input_fields[0].address + 1
        
        return None
    
    def is_password_field(self, address: int) -> bool:
        """Check if the given address is in a non-display (password) field"""
        for f in self.fields:
            if not f.display:  # Non-display field
                # Check if address is within this field
                # Field extends from f.address to next field or end of screen
                if address > f.address:
                    # Find next field to determine end of this field
                    next_field_addr = self.rows * self.cols  # Default to end of screen
                    for other in self.fields:
                        if other.address > f.address and other.address < next_field_addr:
                            next_field_addr = other.address
                    if address < next_field_addr:
                        return True
        return False
    
    def set_char(self, address: int, char: str):
        """Set character at address"""
        if 0 <= address < len(self.buffer):
            self.buffer[address] = char
    
    def get_char(self, address: int) -> str:
        """Get character at address"""
        if 0 <= address < len(self.buffer):
            return self.buffer[address]
        return ' '


class ScreenApplier:
    """Apply 3270 write orders to a :class:`Screen` through order handlers."""

    def __init__(self, screen: Screen):
        self.screen = screen
        self._size = screen.rows * screen.cols
        self._handlers = {
            Order3270.SBA: self._handle_sba,
            Order3270.SF: self._handle_sf,
            Order3270.SFE: self._handle_sfe,
            Order3270.SA: self._handle_noop,
            Order3270.MF: self._handle_noop,
            Order3270.IC: self._handle_ic,
            Order3270.PT: self._handle_noop,
            Order3270.RA: self._handle_ra,
            Order3270.EUA: self._handle_eua,
            Order3270.GE: self._handle_ge,
        }

    def apply(self, data: bytes) -> WriteApplyStats:
        """Parse and apply write data, preserving the historical cursor rule."""
        index = 0
        current_address = self.screen.cursor_address
        chars_written = 0
        orders_processed = 0

        while index < len(data):
            order, index = self._read_order(data, index)
            if order.code is None:
                current_address = self._handle_text(order, current_address)
                chars_written += 1
                continue

            handler = self._handlers.get(Order3270(order.code), self._handle_noop)
            current_address, processed = handler(order, current_address)
            orders_processed += processed

        self.screen.cursor_address = current_address
        return WriteApplyStats(chars_written=chars_written, orders_processed=orders_processed)

    def _read_order(self, data: bytes, index: int) -> Tuple[WriteOrder, int]:
        byte = data[index]
        if byte == Order3270.SBA:
            return self._read_sba(data, index)
        if byte == Order3270.SF:
            return self._read_sf(data, index)
        if byte == Order3270.SFE:
            return self._read_sfe(data, index)
        if byte == Order3270.SA:
            next_index = index + 3 if index + 2 < len(data) else index + 1
            return WriteOrder(code=byte, name="SA", raw=data[index:next_index]), next_index
        if byte == Order3270.MF:
            if index + 1 < len(data):
                count = data[index + 1]
                next_index = index + 2 + (count * 2)
                return (
                    WriteOrder(code=byte, name="MF", raw=data[index:next_index], count=count),
                    next_index,
                )
            return WriteOrder(code=byte, name="MF", raw=data[index:index + 1]), index + 1
        if byte == Order3270.IC:
            return WriteOrder(code=byte, name="IC", raw=data[index:index + 1]), index + 1
        if byte == Order3270.PT:
            return WriteOrder(code=byte, name="PT", raw=data[index:index + 1]), index + 1
        if byte == Order3270.RA:
            return self._read_ra(data, index)
        if byte == Order3270.EUA:
            return self._read_eua(data, index)
        if byte == Order3270.GE:
            return self._read_ge(data, index)
        return (
            WriteOrder(
                code=None,
                name="DATA",
                raw=data[index:index + 1],
                char=ebcdic_to_ascii(byte),
            ),
            index + 1,
        )

    def _read_sba(self, data: bytes, index: int) -> Tuple[WriteOrder, int]:
        if index + 2 < len(data):
            address = decode_buffer_address(data[index + 1], data[index + 2])
            return (
                WriteOrder(
                    code=Order3270.SBA,
                    name="SBA",
                    raw=data[index:index + 3],
                    address=address,
                ),
                index + 3,
            )
        return WriteOrder(code=Order3270.SBA, name="SBA", raw=data[index:index + 1]), index + 1

    def _read_sf(self, data: bytes, index: int) -> Tuple[WriteOrder, int]:
        if index + 1 < len(data):
            attr = data[index + 1]
            return (
                WriteOrder(
                    code=Order3270.SF,
                    name="SF",
                    raw=data[index:index + 2],
                    attribute=attr,
                ),
                index + 2,
            )
        return WriteOrder(code=Order3270.SF, name="SF", raw=data[index:index + 1]), index + 1

    def _read_sfe(self, data: bytes, index: int) -> Tuple[WriteOrder, int]:
        if index + 1 >= len(data):
            return WriteOrder(code=Order3270.SFE, name="SFE", raw=data[index:index + 1]), index + 1

        count = data[index + 1]
        pairs = []
        for pair_index in range(count):
            pair_offset = index + 2 + (pair_index * 2)
            if pair_offset + 1 < len(data):
                pairs.append((data[pair_offset], data[pair_offset + 1]))
        next_index = index + 2 + (count * 2)
        return (
            WriteOrder(
                code=Order3270.SFE,
                name="SFE",
                raw=data[index:next_index],
                attribute_pairs=tuple(pairs),
                count=count,
            ),
            next_index,
        )

    def _read_ra(self, data: bytes, index: int) -> Tuple[WriteOrder, int]:
        if index + 3 < len(data):
            end_address = decode_buffer_address(data[index + 1], data[index + 2])
            return (
                WriteOrder(
                    code=Order3270.RA,
                    name="RA",
                    raw=data[index:index + 4],
                    end_address=end_address,
                    char=ebcdic_to_ascii(data[index + 3]),
                ),
                index + 4,
            )
        return WriteOrder(code=Order3270.RA, name="RA", raw=data[index:index + 1]), index + 1

    def _read_eua(self, data: bytes, index: int) -> Tuple[WriteOrder, int]:
        if index + 2 < len(data):
            end_address = decode_buffer_address(data[index + 1], data[index + 2])
            return (
                WriteOrder(
                    code=Order3270.EUA,
                    name="EUA",
                    raw=data[index:index + 3],
                    end_address=end_address,
                ),
                index + 3,
            )
        return WriteOrder(code=Order3270.EUA, name="EUA", raw=data[index:index + 1]), index + 1

    def _read_ge(self, data: bytes, index: int) -> Tuple[WriteOrder, int]:
        if index + 1 < len(data):
            return (
                WriteOrder(
                    code=Order3270.GE,
                    name="GE",
                    raw=data[index:index + 2],
                    char=ebcdic_to_ascii(data[index + 1]),
                ),
                index + 2,
            )
        return WriteOrder(code=Order3270.GE, name="GE", raw=data[index:index + 1]), index + 1

    def _handle_sba(self, order: WriteOrder, current_address: int) -> Tuple[int, int]:
        if order.address is None:
            return current_address, 0
        return order.address, 1

    def _handle_sf(self, order: WriteOrder, current_address: int) -> Tuple[int, int]:
        if order.attribute is None:
            return current_address, 0
        self._start_field(current_address, order.attribute)
        return (current_address + 1) % self._size, 1

    def _handle_sfe(self, order: WriteOrder, current_address: int) -> Tuple[int, int]:
        attr = 0x00
        for attr_type, attr_value in order.attribute_pairs:
            if attr_type == 0xC0:
                attr = attr_value
        self._start_field(current_address, attr)
        return (current_address + 1) % self._size, 1

    def _handle_ic(self, _order: WriteOrder, current_address: int) -> Tuple[int, int]:
        self.screen.cursor_address = current_address
        logger.info(
            "IC order: cursor_address set to %s (row=%s, col=%s)",
            current_address,
            current_address // 80,
            current_address % 80,
        )
        return current_address, 0

    def _handle_ra(self, order: WriteOrder, current_address: int) -> Tuple[int, int]:
        if order.end_address is None or order.char is None:
            return current_address, 0
        while current_address != order.end_address:
            self.screen.set_char(current_address, order.char)
            current_address = (current_address + 1) % self._size
        return current_address, 0

    def _handle_eua(self, order: WriteOrder, current_address: int) -> Tuple[int, int]:
        if order.end_address is None:
            return current_address, 0
        while current_address != order.end_address:
            self.screen.set_char(current_address, ' ')
            current_address = (current_address + 1) % self._size
        return current_address, 0

    def _handle_ge(self, order: WriteOrder, current_address: int) -> Tuple[int, int]:
        if order.char is None:
            return current_address, 0
        self.screen.set_char(current_address, order.char)
        return (current_address + 1) % self._size, 0

    def _handle_text(self, order: WriteOrder, current_address: int) -> int:
        if order.char is not None:
            self.screen.set_char(current_address, order.char)
            return (current_address + 1) % self._size
        return current_address

    def _handle_noop(self, _order: WriteOrder, current_address: int) -> Tuple[int, int]:
        return current_address, 0

    def _start_field(self, address: int, attribute: int):
        self.screen.set_char(address, ' ')
        if 0 <= address < len(self.screen.attributes):
            self.screen.attributes[address] = attribute
        self.screen.add_field(address, attribute)


class TN3270Client:
    """TN3270 Terminal Client"""
    
    def __init__(self, host: str, port: int = 23, use_ssl: bool = False, lu_name: str = None):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.lu_name = lu_name  # Optional: request specific LU name
        self.socket: Optional[socket.socket] = None
        self.ssl_socket: Optional[ssl.SSLSocket] = None
        self.connected = False
        self.screen = Screen()
        self.tn3270e_mode = False
        self.tn3270e_negotiated = False
        self.binary_mode = False
        self.terminal_type = "IBM-3278-2-E"
        self.assigned_lu_name = ""  # LU name assigned by server via TN3270E CONNECT
        self._on_screen_update: Optional[Callable] = None
        self._receive_buffer = b''
        self._command_decoder = TN3270CommandDecoder()
        
    def set_screen_update_callback(self, callback: Callable):
        """Set callback for screen updates"""
        self._on_screen_update = callback
    
    def _get_socket(self):
        """Get the active socket (SSL or plain)"""
        return self.ssl_socket if self.ssl_socket else self.socket
        
    def connect(self) -> bool:
        """Connect to the mainframe"""
        try:
            logger.info(f"Attempting connection to {self.host}:{self.port} (SSL={self.use_ssl})")
            
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(30)
            
            logger.debug(f"Connecting socket to {self.host}:{self.port}...")
            self.socket.connect((self.host, self.port))
            logger.debug("Socket connected successfully")
            
            if self.use_ssl:
                # Wrap socket with SSL
                logger.debug("Wrapping socket with SSL...")
                # Use a less restrictive context for older mainframe SSL
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                # Allow self-signed certificates (common in enterprise)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                # Allow weaker DH keys (mainframes often use older crypto)
                context.set_ciphers('DEFAULT:@SECLEVEL=1')
                # Set minimum TLS version for compatibility with older systems
                context.minimum_version = ssl.TLSVersion.TLSv1
                self.ssl_socket = context.wrap_socket(self.socket, server_hostname=self.host)
                logger.info(f"SSL connection established to {self.host}:{self.port}")
                logger.debug(f"SSL version: {self.ssl_socket.version()}")
            
            self.connected = True
            logger.info(f"Connected to {self.host}:{self.port} (SSL={self.use_ssl})")
            
            # Handle initial telnet negotiation
            self._negotiate()
            
            return True
        except ssl.SSLError as e:
            logger.error(f"SSL error: {e}")
            self.connected = False
            return False
        except socket.timeout as e:
            logger.error(f"Connection timeout: {e}")
            self.connected = False
            return False
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from mainframe"""
        if self.ssl_socket:
            try:
                self.ssl_socket.close()
            except OSError:
                logger.debug("Ignoring SSL socket close failure during TN3270 disconnect", exc_info=True)
            self.ssl_socket = None
        if self.socket:
            try:
                self.socket.close()
            except OSError:
                logger.debug("Ignoring socket close failure during TN3270 disconnect", exc_info=True)
        self.socket = None
        self.connected = False
        logger.info("Disconnected")
    
    def _send(self, data: bytes):
        """Send data to server"""
        sock = self._get_socket()
        if sock and self.connected:
            sock.sendall(data)
            logger.debug(f"Sent {len(data)} bytes: {data.hex()}")
    
    def _recv(self, timeout: float = 5.0) -> bytes:
        """Receive data from server"""
        sock = self._get_socket()
        if not sock or not self.connected:
            logger.debug("_recv: no socket or not connected")
            return b''
        
        try:
            sock.settimeout(timeout)
            data = sock.recv(4096)
            if data:
                logger.debug(f"Received {len(data)} bytes: {data[:100].hex()}...")
            else:
                # Empty data means connection closed
                logger.warning("Received empty data - connection may be closed")
                self.connected = False
            return data
        except socket.timeout:
            logger.debug("Socket timeout - no data available")
            return b''
        except OSError as e:
            # Socket errors (including WinError 10038)
            logger.error(f"Socket error in _recv: {e}")
            self.connected = False
            return b''
        except Exception as e:
            logger.error(f"Receive error: {e}")
            self.connected = False
            return b''
    
    def _negotiate(self):
        """Handle telnet negotiation"""
        logger.info("Starting telnet negotiation")
        decoder = TelnetFrameDecoder()
        data = self._recv(timeout=10)
        negotiation_rounds = 0

        while data:
            negotiation_rounds += 1
            logger.info(f"Negotiation round {negotiation_rounds}: received {len(data)} bytes")
            logger.debug(f"Raw data: {data[:100].hex()}...")

            batch = decoder.decode(data)
            for frame in batch.frames:
                self._handle_telnet_frame(frame)
            for record in batch.records:
                logger.info(f"EOR received - processing {len(record)} bytes of screen data")
                if record:
                    self._process_3270_data(record)

            data = self._recv(timeout=2)

        remaining = decoder.flush_record()
        if remaining:
            logger.info(f"Processing remaining {len(remaining)} bytes of screen data")
            self._process_3270_data(remaining)

        logger.info(f"Telnet negotiation complete after {negotiation_rounds} rounds")
        logger.info(f"Screen buffer sample: '{self.screen.get_text()[:200]}'")
        
        # If TN3270E negotiation completed but we haven't received the main screen yet,
        # wait a bit longer for it
        if self.tn3270e_negotiated and not self.screen.get_text().strip():
            logger.info("Waiting for initial screen after TN3270E negotiation...")
            for _ in range(10):  # Increased from 5 to 10 retries
                data = self._recv(timeout=3)
                if data:
                    logger.info(f"Received delayed screen data: {len(data)} bytes")
                    screen_data = self._extract_3270_data(data)
                    if screen_data:
                        self._process_3270_data(screen_data)
                        if self.screen.get_text().strip():
                            logger.info("Initial screen received successfully")
                            break
                else:
                    # If we timed out but are still connected, keep trying
                    if not self.connected:
                        break

    def _handle_telnet_frame(self, frame: TelnetFrame):
        """Route one decoded telnet frame to the existing negotiation handlers."""
        if frame.command == TelnetCmd.DO and frame.option is not None:
            self._handle_do(frame.option)
        elif frame.command == TelnetCmd.WILL and frame.option is not None:
            self._handle_will(frame.option)
        elif frame.command == TelnetCmd.SB:
            self._handle_subnegotiation(frame.payload)
        else:
            logger.debug(f"Unknown telnet cmd: {frame.command}")

    
    def _handle_do(self, opt: int):
        """Handle DO request"""
        logger.info(f"DO {opt} ({self._opt_name(opt)})")
        if opt == TelnetOpt.TERMINAL_TYPE:
            # Will send terminal type
            self._send(bytes([TelnetCmd.IAC, TelnetCmd.WILL, opt]))
        elif opt == TelnetOpt.EOR:
            # Will use EOR
            self._send(bytes([TelnetCmd.IAC, TelnetCmd.WILL, opt]))
        elif opt == TelnetOpt.BINARY:
            # Will use binary
            self._send(bytes([TelnetCmd.IAC, TelnetCmd.WILL, opt]))
            self.binary_mode = True
        elif opt == TelnetOpt.TN3270E:
            # Support TN3270E for better compatibility
            self._send(bytes([TelnetCmd.IAC, TelnetCmd.WILL, opt]))
            self.tn3270e_mode = True
            logger.info("Accepting TN3270E mode")
        else:
            self._send(bytes([TelnetCmd.IAC, TelnetCmd.WONT, opt]))
    
    def _opt_name(self, opt: int) -> str:
        """Get option name for logging"""
        names = {0: "BINARY", 1: "ECHO", 24: "TERMINAL_TYPE", 25: "EOR", 40: "TN3270E"}
        return names.get(opt, f"OPT-{opt}")
    
    def _handle_will(self, opt: int):
        """Handle WILL offer"""
        logger.debug(f"WILL {opt}")
        if opt == TelnetOpt.EOR:
            self._send(bytes([TelnetCmd.IAC, TelnetCmd.DO, opt]))
        elif opt == TelnetOpt.BINARY:
            self._send(bytes([TelnetCmd.IAC, TelnetCmd.DO, opt]))
            self.binary_mode = True
        else:
            self._send(bytes([TelnetCmd.IAC, TelnetCmd.DONT, opt]))
    
    def _handle_subnegotiation(self, data: bytes):
        """Handle subnegotiation"""
        if len(data) < 1:
            return
        
        opt = data[0]
        logger.info(f"Subnegotiation for option {opt} ({self._opt_name(opt)})")
        logger.debug(f"Subneg data: {data.hex()}")
        
        if opt == TelnetOpt.TERMINAL_TYPE:
            if len(data) >= 2 and data[1] == 1:  # SEND
                # Send terminal type
                term_type = self.terminal_type.encode('ascii')
                response = bytes([TelnetCmd.IAC, TelnetCmd.SB, TelnetOpt.TERMINAL_TYPE, 0]) + term_type + bytes([TelnetCmd.IAC, TelnetCmd.SE])
                self._send(response)
                logger.info(f"Sent terminal type: {self.terminal_type}")
        
        elif opt == TelnetOpt.TN3270E:
            # TN3270E subnegotiation
            self._handle_tn3270e_subneg(data[1:])
    
    def _handle_tn3270e_subneg(self, data: bytes):
        """Handle TN3270E subnegotiation"""
        if len(data) < 1:
            return
        
        # TN3270E subnegotiation codes
        TN3270E_SEND = 0x08
        TN3270E_DEVICE_TYPE = 0x02
        TN3270E_FUNCTIONS = 0x03
        TN3270E_IS = 0x04
        TN3270E_REQUEST = 0x07
        TN3270E_REJECT = 0x06
        TN3270E_CONNECT = 0x01
        
        cmd = data[0]
        logger.info(f"TN3270E subneg cmd: {hex(cmd)}, data: {data.hex()}")
        
        if cmd == TN3270E_SEND:
            if len(data) >= 2:
                what = data[1]
                if what == TN3270E_DEVICE_TYPE:
                    # Send device type REQUEST with optional LU name or CONNECT
                    # Format options:
                    # 1. DEVICE-TYPE REQUEST <term_type> CONNECT - get LU from pool
                    # 2. DEVICE-TYPE REQUEST <term_type> CONNECT <lu_name> - request specific LU
                    term_type = self.terminal_type.encode('ascii')
                    
                    if self.lu_name:
                        # Request a specific LU name - this might route to a different application
                        lu_bytes = self.lu_name.encode('ascii')
                        response = bytes([TelnetCmd.IAC, TelnetCmd.SB, TelnetOpt.TN3270E, 
                                          TN3270E_DEVICE_TYPE, TN3270E_REQUEST]) + term_type + \
                                   bytes([TN3270E_CONNECT]) + lu_bytes + \
                                   bytes([TelnetCmd.IAC, TelnetCmd.SE])
                        logger.info(f"Sent TN3270E device type REQUEST with specific LU: {self.lu_name}")
                    else:
                        # Let server assign an LU from its pool
                        response = bytes([TelnetCmd.IAC, TelnetCmd.SB, TelnetOpt.TN3270E, 
                                          TN3270E_DEVICE_TYPE, TN3270E_REQUEST]) + term_type + \
                                   bytes([TN3270E_CONNECT]) + \
                                   bytes([TelnetCmd.IAC, TelnetCmd.SE])
                        logger.info(f"Sent TN3270E device type REQUEST with CONNECT: {self.terminal_type}")
                    self._send(response)
        
        elif cmd == TN3270E_DEVICE_TYPE:
            if len(data) >= 2 and data[1] == TN3270E_IS:
                # Server accepted our device type - extract assigned LU name if present
                # Format: DEVICE-TYPE IS <term_type> CONNECT <lu_name>
                rest = data[2:]
                # Try to extract the assigned LU name
                if TN3270E_CONNECT in rest:
                    connect_pos = rest.index(TN3270E_CONNECT)
                    term_type_bytes = rest[:connect_pos]
                    lu_name_bytes = rest[connect_pos + 1:]
                    # Filter out non-printable bytes
                    lu_name = bytes(b for b in lu_name_bytes if 32 <= b < 127).decode('ascii', errors='ignore')
                    if lu_name:
                        self.assigned_lu_name = lu_name
                        logger.info(f"TN3270E assigned LU name: {lu_name}")
                    else:
                        logger.info("TN3270E device type IS received (no LU name)")
                else:
                    logger.info("TN3270E device type IS received (no CONNECT response)")
                
                # Now send functions request
                logger.info("Sending TN3270E functions request")
                # Request no special functions (basic 3270 mode)
                response = bytes([TelnetCmd.IAC, TelnetCmd.SB, TelnetOpt.TN3270E,
                                  TN3270E_FUNCTIONS, TN3270E_REQUEST,
                                  TelnetCmd.IAC, TelnetCmd.SE])
                self._send(response)
                logger.info("Sent TN3270E functions REQUEST (basic)")
        
        elif cmd == TN3270E_REJECT:
            # Server rejected our request (likely the LU name)
            logger.warning("TN3270E request rejected by server")
            if len(data) >= 2:
                reason = data[1]
                logger.warning(f"Rejection reason code: {hex(reason)}")
            
            # If we requested an LU name and got rejected, try falling back to default
            if self.lu_name:
                logger.info("Falling back to default LU assignment (no specific LU)")
                self.lu_name = None
                # We can't easily restart negotiation from here without a new SEND from server,
                # but usually server will send another SEND or close connection.
                # However, some servers might expect us to send a new REQUEST immediately.
                
                term_type = self.terminal_type.encode('ascii')
                response = bytes([TelnetCmd.IAC, TelnetCmd.SB, TelnetOpt.TN3270E, 
                                  TN3270E_DEVICE_TYPE, TN3270E_REQUEST]) + term_type + \
                           bytes([TN3270E_CONNECT]) + \
                           bytes([TelnetCmd.IAC, TelnetCmd.SE])
                self._send(response)
                logger.info("Sent fallback TN3270E device type REQUEST (no LU)")

        elif cmd == TN3270E_FUNCTIONS:
            if len(data) >= 2 and data[1] == TN3270E_IS:
                # Server accepted functions
                logger.info("TN3270E functions negotiation complete")
                self.tn3270e_negotiated = True

    def receive_screen(self) -> bool:
        """Receive and process screen data"""
        # Check if we already have a complete record in the buffer
        eor_seq = bytes([TelnetCmd.IAC, TelnetCmd.EOR])
        eor_pos = self._receive_buffer.find(eor_seq)
        
        if eor_pos < 0:
            # No complete record, try to read more
            data = self._recv(timeout=1.0)
            if data:
                self._receive_buffer += data
                eor_pos = self._receive_buffer.find(eor_seq)
        
        if eor_pos >= 0:
            # We have a complete record
            record_data = self._receive_buffer[:eor_pos]
            # Remove record + EOR from buffer
            self._receive_buffer = self._receive_buffer[eor_pos + 2:]
            
            logger.debug(f"Processing record of {len(record_data)} bytes")
            
            # Extract 3270 data (handle escaped IACs etc)
            try:
                screen_data = self._extract_3270_data(record_data)
                
                if screen_data:
                    self._process_3270_data(screen_data)
                    logger.info(f"Screen updated. Buffer length: {len(self.screen.buffer)}. Fields: {len(self.screen.fields)}")
                    if self._on_screen_update:
                        self._on_screen_update(self.screen)
                    return True
            except Exception as e:
                logger.error(f"Error processing 3270 data: {e}", exc_info=True)
                # We consumed the buffer, so return True to keep loop going? 
                # Or False? If we return True, the thread emits 'None' screen?
                # No, we only emit if _on_screen_update is called.
                return True
        
        return False
    
    def _extract_3270_data(self, data: bytes) -> bytes:
        """Extract 3270 data from telnet stream"""
        return TelnetFrameDecoder.extract_payload(data)

    def _extract_3270_payload(self, data: bytes) -> bytes:
        """Strip TN3270E header if in TN3270E mode"""
        if self.tn3270e_mode and len(data) >= 5:
            # TN3270E header: data-type (1), request-flag (1), response-flag (1), seq-number (2)
            data_type = data[0]
            logger.debug(f"TN3270E header: type={data_type}, data={data[:5].hex()}")
            if data_type == 0x00:  # 3270-DATA
                data = data[5:]
                logger.debug(f"Stripped TN3270E header, {len(data)} bytes remaining")
        return data

    def _process_3270_data(self, data: bytes):
        """Process 3270 data stream"""
        if len(data) < 1:
            logger.debug("No 3270 data to process")
            return
        
        # Strip TN3270E header if present
        data = self._extract_3270_payload(data)
        if len(data) < 1:
            logger.debug("No 3270 data after stripping header")
            return
        
        # Log the first few bytes for debugging
        logger.info(f"Processing 3270 data: {len(data)} bytes, first 20: {data[:20].hex()}")
        
        command = self._command_decoder.decode(data)
        if command is None:
            return

        logger.info(f"3270 command byte: {hex(command.command_byte)}")
        logger.info(f"{command.name} command")
        if command.wcc is not None:
            logger.debug(f"WCC: {hex(command.wcc)}")

        if command.clear_screen:
            self.screen.clear()
        if command.is_structured_field:
            self._process_wsf(command.payload)
        elif command.is_read:
            logger.debug(f"{command.name} command - no screen update")
        elif command.is_write:
            if command.is_raw_write:
                logger.info(
                    "Unknown cmd %s - processing as raw write data",
                    hex(command.command_byte),
                )
            self._process_write_data(command.payload)
    
    def _process_write_data(self, data: bytes):
        """Process write data (orders and characters)"""
        logger.debug(f"Processing write data: {len(data)} bytes")
        stats = ScreenApplier(self.screen).apply(data)
        logger.info(
            "Write data complete: %s chars written, %s orders processed",
            stats.chars_written,
            stats.orders_processed,
        )
    
    def _process_wsf(self, data: bytes):
        """Process Write Structured Field command"""
        # WSF contains structured fields with length prefix
        i = 0
        while i < len(data):
            if i + 2 > len(data):
                break
            # Each SF has a 2-byte length (big-endian)
            length = (data[i] << 8) | data[i + 1]
            if length < 3 or i + length > len(data):
                break
            sf_id = data[i + 2]
            logger.info(f"WSF: SF ID={hex(sf_id)}, length={length}")
            
            # Handle Read Partition (Query)
            if sf_id == 0x01:  # Read Partition
                if i + 3 < len(data):
                    partition_id = data[i + 3]
                    if i + 4 < len(data):
                        op_type = data[i + 4]
                        logger.info(f"Read Partition: pid={partition_id}, op={hex(op_type)}")
                        if op_type == 0x02 or op_type == 0xFF:  # Query or Query List
                            # Send Query Reply
                            self._send_query_reply()
            
            i += length
    
    def _send_query_reply(self):
        """Send Query Reply structured field"""
        logger.info("Sending Query Reply")
        
        # Build Query Reply response
        response = bytearray()
        
        # TN3270E header if needed
        if self.tn3270e_mode:
            response.extend([0x00, 0x00, 0x00, 0x00, 0x00])
        
        # AID for structured field
        response.append(0x88)  # AID_SF (Structured Field)
        
        # Query Reply - Usable Area
        qr_ua = self._build_qr_usable_area()
        response.extend(qr_ua)
        
        # Query Reply - Summary (list what we support)
        qr_summary = self._build_qr_summary()
        response.extend(qr_summary)
        
        # Add EOR
        response.extend([TelnetCmd.IAC, TelnetCmd.EOR])
        
        self._send(bytes(response))
        logger.info(f"Sent Query Reply ({len(response)} bytes)")
    
    def _build_qr_usable_area(self) -> bytes:
        """Build Query Reply - Usable Area"""
        qr = bytearray()
        # Length (to be filled)
        qr.extend([0x00, 0x00])
        # QCODE for Usable Area
        qr.append(0x81)  # Query Reply
        qr.append(0x81)  # Usable Area
        # Flags
        qr.append(0x01)  # 12/14 bit addressing
        # Width/height cells
        qr.append(0x00)  # Reserved
        qr.append(0x00)  # Reserved  
        qr.append(0x50)  # 80 cols
        qr.append(0x00)  
        qr.append(0x18)  # 24 rows
        # Units
        qr.append(0x00)  # Inches
        # X/Y units  
        qr.extend([0x00, 0x00, 0x00, 0x00])  # Xr numerator/denominator
        qr.extend([0x00, 0x00, 0x00, 0x00])  # Yr numerator/denominator
        qr.append(0x09)  # AW (character cell width)
        qr.append(0x0C)  # AH (character cell height)
        qr.extend([0x07, 0x80])  # Buffer size (1920)
        
        # Set length
        length = len(qr)
        qr[0] = (length >> 8) & 0xFF
        qr[1] = length & 0xFF
        return bytes(qr)
    
    def _build_qr_summary(self) -> bytes:
        """Build Query Reply - Summary"""
        qr = bytearray()
        # Length (to be filled)
        qr.extend([0x00, 0x00])
        # QCODE
        qr.append(0x81)  # Query Reply
        qr.append(0x80)  # Summary
        # List of supported Query Reply types
        qr.append(0x81)  # Usable Area
        qr.append(0x87)  # Highlighting
        qr.append(0x88)  # Reply Modes
        
        # Set length
        length = len(qr)
        qr[0] = (length >> 8) & 0xFF
        qr[1] = length & 0xFF
        return bytes(qr)
    
    def send_aid(self, aid: int, modified_fields: List[Tuple[int, str]] = None):
        """Send an AID (Attention Identifier) key"""
        if not self.connected:
            return
        
        data = bytearray()
        
        # In TN3270E mode, add the 5-byte header
        if self.tn3270e_mode:
            # TN3270E header: data-type (0x00=3270-DATA), request-flag, response-flag, seq-number (2 bytes)
            data.extend([0x00, 0x00, 0x00, 0x00, 0x00])
        
        data.append(aid)
        
        # Short Read AIDs (CLEAR, PA1-PA3) do not send cursor address or data
        is_short_read = aid in (AID.CLEAR, AID.PA1, AID.PA2, AID.PA3)
        
        if not is_short_read:
            data.extend(encode_buffer_address(self.screen.cursor_address))
            
            # Add modified field data if any
            if modified_fields:
                for addr, content in modified_fields:
                    data.append(Order3270.SBA)
                    data.extend(encode_buffer_address(addr))
                    for char in content:
                        data.append(ascii_to_ebcdic(char))
        
        # Wrap in telnet with EOR
        telnet_data = bytes(data) + bytes([TelnetCmd.IAC, TelnetCmd.EOR])
        self._send(telnet_data)
        logger.debug(f"Sent AID {hex(aid)} with {len(modified_fields) if modified_fields else 0} modified fields (Short Read={is_short_read})")
    
    def send_enter(self, input_text: str = "", field_address: int = 0):
        """Send ENTER key with optional input"""
        modified = []
        if input_text:
            modified.append((field_address, input_text))
        self.send_aid(AID.ENTER, modified)
    
    def send_pf_key(self, pf_num: int):
        """Send PF key (1-24)"""
        pf_aids = {
            1: AID.PF1, 2: AID.PF2, 3: AID.PF3, 4: AID.PF4, 5: AID.PF5,
            6: AID.PF6, 7: AID.PF7, 8: AID.PF8, 9: AID.PF9, 10: AID.PF10,
            11: AID.PF11, 12: AID.PF12, 13: AID.PF13, 14: AID.PF14, 15: AID.PF15,
            16: AID.PF16, 17: AID.PF17, 18: AID.PF18, 19: AID.PF19, 20: AID.PF20,
            21: AID.PF21, 22: AID.PF22, 23: AID.PF23, 24: AID.PF24,
        }
        if pf_num in pf_aids:
            self.send_aid(pf_aids[pf_num])
    
    def send_clear(self):
        """Send CLEAR key"""
        self.send_aid(AID.CLEAR)
    
    def send_pa_key(self, pa_num: int):
        """Send PA key (1-3)"""
        pa_aids = {1: AID.PA1, 2: AID.PA2, 3: AID.PA3}
        if pa_num in pa_aids:
            self.send_aid(pa_aids[pa_num])
