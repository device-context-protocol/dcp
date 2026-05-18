"""Tests for COBS encoding and the UART wire wrapper."""
from __future__ import annotations

import pytest

from dcp.framing import (
    cobs_decode,
    cobs_encode,
    crc16_ccitt,
    unwrap,
    wrap,
)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\x01",
        b"\x00",
        b"\x11\x22\x33",
        b"\x11\x22\x00\x33",
        b"\x00\x00\x00",
        bytes(range(256)),
        b"\xff" * 254,
        b"\xff" * 255,  # exercises the 0xFF run-length boundary
        b"\xff" * 600,
    ],
)
def test_cobs_round_trip(data: bytes):
    encoded = cobs_encode(data)
    assert 0 not in encoded, "COBS output must never contain 0x00"
    assert cobs_decode(encoded) == data


def test_cobs_decode_rejects_zero_byte():
    with pytest.raises(ValueError):
        cobs_decode(b"\x02\x11\x00")


def test_wrap_unwrap_round_trip():
    frame = b"\x01\x01\x00\x2a\x12\x34hello"
    wire = wrap(frame)
    assert wire.endswith(b"\x00"), "wire frames must end with the 0x00 delimiter"
    assert wire.count(b"\x00") == 1, "no internal zero bytes"
    assert unwrap(wire[:-1]) == frame


def test_unwrap_rejects_corruption():
    frame = b"hello world"
    wire = wrap(frame)
    body = bytearray(wire[:-1])
    body[2] ^= 0x01  # flip a bit
    with pytest.raises(ValueError, match="CRC|COBS"):
        unwrap(bytes(body))


def test_crc16_known_vector():
    # CRC-16/CCITT-FALSE of "123456789" with init 0xFFFF is 0x29B1
    assert crc16_ccitt(b"123456789") == 0x29B1
