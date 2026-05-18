"""Tests for wire-level HMAC signing."""
from __future__ import annotations

import pytest

from dcp.wire import Frame, Kind

SECRET = b"w" * 32


def test_round_trip_with_secret():
    f = Frame(kind=Kind.CALL, seq=1, intent_id=0x1234, payload={"level": 50})
    raw = f.encode(wire_secret=SECRET)
    decoded = Frame.decode(raw, wire_secret=SECRET)
    assert decoded.payload == {"level": 50}


def test_signed_frame_is_longer():
    f = Frame(kind=Kind.CALL, seq=1, intent_id=0, payload={"x": 1})
    assert len(f.encode(wire_secret=SECRET)) == len(f.encode()) + 16


def test_wrong_secret_rejected():
    f = Frame(kind=Kind.CALL, seq=1, intent_id=0, payload={"x": 1})
    raw = f.encode(wire_secret=SECRET)
    with pytest.raises(ValueError, match="HMAC"):
        Frame.decode(raw, wire_secret=b"x" * 32)


def test_tampered_payload_rejected():
    f = Frame(kind=Kind.CALL, seq=1, intent_id=0, payload={"x": 1})
    raw = bytearray(f.encode(wire_secret=SECRET))
    raw[-17] ^= 0x01  # flip a bit in the last byte before the HMAC
    with pytest.raises(ValueError, match="HMAC"):
        Frame.decode(bytes(raw), wire_secret=SECRET)


def test_signing_is_out_of_band_config():
    """Wire signing has no in-band marker — both sides must agree out of band.

    An attacker can strip the HMAC bytes; an unsigning recipient will then
    parse the underlying frame as if no HMAC existed. This is deliberate:
    an in-band "is signed" bit would enable a downgrade attack. The defense
    is that recipients which require signing simply refuse unsigned frames
    (the absence of the HMAC tail leaves data shorter than expected and
    verification fails).
    """
    payload = {"x": 1}
    f = Frame(kind=Kind.CALL, seq=1, intent_id=0, payload=payload)
    signed = f.encode(wire_secret=SECRET)
    unsigned = f.encode()
    assert len(signed) == len(unsigned) + 16

    # Decoding the signed frame WITH the secret succeeds and yields the payload.
    assert Frame.decode(signed, wire_secret=SECRET).payload == payload

    # Decoding an unsigned frame WITH a secret expectation fails: the last
    # 16 bytes (here, the last 16 of the CBOR/header) won't satisfy the HMAC.
    with pytest.raises(ValueError, match="HMAC"):
        Frame.decode(unsigned, wire_secret=SECRET)
