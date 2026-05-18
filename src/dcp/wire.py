"""DCP wire format: a 6-byte header followed by a CBOR payload.

    ┌────────┬────────┬────────┬─────────────┬───────┐
    │ ver:u8 │ kind:u8│ seq:u16│ intent_id:u16│ cbor  │
    └────────┴────────┴────────┴─────────────┴───────┘

All multi-byte integers are network byte order (big-endian).
"""
from __future__ import annotations

import binascii
import hmac
import struct
from dataclasses import dataclass
from enum import IntEnum
from hashlib import sha256

import cbor2

WIRE_VERSION = 1
_HEADER = struct.Struct("!BBHH")  # ver, kind, seq, intent_id
HMAC_BYTES = 16  # truncated HMAC-SHA256 appended after CBOR when wire signing is enabled


class Kind(IntEnum):
    CALL = 0x01
    REPLY = 0x02
    EVENT = 0x03
    ERROR = 0x04
    DRY_RUN = 0x81


def intent_id(name: str) -> int:
    """CRC-16/CCITT of the intent name. Used as the on-wire intent identifier."""
    return binascii.crc_hqx(name.encode("utf-8"), 0xFFFF)


@dataclass(slots=True)
class Frame:
    kind: Kind
    seq: int
    intent_id: int
    payload: dict

    def encode(self, *, wire_secret: bytes | None = None) -> bytes:
        body = cbor2.dumps(self.payload) if self.payload else b""
        frame = _HEADER.pack(WIRE_VERSION, int(self.kind), self.seq, self.intent_id) + body
        if wire_secret is not None:
            frame += hmac.new(wire_secret, frame, sha256).digest()[:HMAC_BYTES]
        return frame

    @classmethod
    def decode(cls, data: bytes, *, wire_secret: bytes | None = None) -> "Frame":
        if wire_secret is not None:
            if len(data) < _HEADER.size + HMAC_BYTES:
                raise ValueError(f"frame too short for HMAC: {len(data)} bytes")
            body, sig = data[:-HMAC_BYTES], data[-HMAC_BYTES:]
            expected = hmac.new(wire_secret, body, sha256).digest()[:HMAC_BYTES]
            if not hmac.compare_digest(sig, expected):
                raise ValueError("wire HMAC verification failed")
            data = body

        if len(data) < _HEADER.size:
            raise ValueError(f"frame too short: {len(data)} bytes")
        ver, kind, seq, iid = _HEADER.unpack_from(data)
        if ver != WIRE_VERSION:
            raise ValueError(f"unsupported wire version: {ver}")
        body = data[_HEADER.size:]
        payload = cbor2.loads(body) if body else {}
        if not isinstance(payload, dict):
            raise ValueError(f"frame payload must be a CBOR map, got {type(payload).__name__}")
        return cls(Kind(kind), seq, iid, payload)
