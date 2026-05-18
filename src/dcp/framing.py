"""Byte-level framing helpers for raw transports (UART, RS-485, USB-CDC).

A wire-framed DCP frame looks like::

    [ COBS( dcp_frame || crc16_be ) ] 0x00

- ``cobs_encode`` / ``cobs_decode``: Consistent Overhead Byte Stuffing so the
  encoded payload contains no zero bytes; 0x00 then unambiguously delimits frames.
- ``crc16_ccitt``: same CRC-16/CCITT (poly 0x1021, init 0xFFFF) used elsewhere
  in DCP; here it guards against bit flips on the line.
- ``wrap`` / ``unwrap``: convenience helpers that combine the two.
"""
from __future__ import annotations

import binascii


def cobs_encode(data: bytes) -> bytes:
    """Encode bytes with COBS. Output never contains 0x00."""
    encoded = bytearray(b"\x00")  # placeholder for first code byte
    code_idx = 0
    code = 1
    for byte in data:
        if byte == 0:
            encoded[code_idx] = code
            code_idx = len(encoded)
            encoded.append(0)
            code = 1
        else:
            encoded.append(byte)
            code += 1
            if code == 0xFF:
                encoded[code_idx] = code
                code_idx = len(encoded)
                encoded.append(0)
                code = 1
    encoded[code_idx] = code
    return bytes(encoded)


def cobs_decode(encoded: bytes) -> bytes:
    """Decode a COBS-encoded buffer. Raises ValueError on malformed input."""
    if not encoded:
        return b""
    decoded = bytearray()
    i = 0
    while i < len(encoded):
        code = encoded[i]
        if code == 0:
            raise ValueError("zero byte inside COBS-encoded buffer")
        if i + code > len(encoded):
            raise ValueError("COBS code points past end of buffer")
        decoded += encoded[i + 1 : i + code]
        i += code
        if i < len(encoded) and code != 0xFF:
            decoded.append(0)
    return bytes(decoded)


def crc16_ccitt(data: bytes) -> int:
    """CRC-16/CCITT (poly 0x1021, init 0xFFFF)."""
    return binascii.crc_hqx(data, 0xFFFF)


def wrap(frame: bytes) -> bytes:
    """Build the on-wire representation of a DCP frame: COBS(frame || crc) + 0x00."""
    crc = crc16_ccitt(frame).to_bytes(2, "big")
    return cobs_encode(frame + crc) + b"\x00"


def unwrap(wire: bytes) -> bytes:
    """Decode one wire-framed DCP frame (delimiter 0x00 already stripped)."""
    decoded = cobs_decode(wire)
    if len(decoded) < 2:
        raise ValueError("frame too short to carry CRC")
    body, crc_bytes = decoded[:-2], decoded[-2:]
    expected = crc16_ccitt(body).to_bytes(2, "big")
    if crc_bytes != expected:
        raise ValueError("CRC mismatch")
    return body
