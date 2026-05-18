"""Tests for the wire format."""
from __future__ import annotations

import pytest

from dcp.wire import Frame, Kind, WIRE_VERSION, intent_id


def test_intent_id_is_deterministic():
    assert intent_id("set_brightness") == intent_id("set_brightness")
    assert intent_id("set_brightness") != intent_id("read_brightness")
    assert 0 <= intent_id("anything") <= 0xFFFF


def test_frame_round_trip():
    f = Frame(kind=Kind.CALL, seq=42, intent_id=0x1234, payload={"level": 50, "fade": 0})
    raw = f.encode()
    decoded = Frame.decode(raw)
    assert decoded.kind == Kind.CALL
    assert decoded.seq == 42
    assert decoded.intent_id == 0x1234
    assert decoded.payload == {"level": 50, "fade": 0}


def test_empty_payload_round_trip():
    f = Frame(kind=Kind.REPLY, seq=1, intent_id=0, payload={})
    decoded = Frame.decode(f.encode())
    assert decoded.payload == {}


def test_header_layout():
    f = Frame(kind=Kind.CALL, seq=0x1234, intent_id=0xABCD, payload={})
    raw = f.encode()
    assert raw[0] == WIRE_VERSION
    assert raw[1] == 0x01  # CALL
    assert raw[2:4] == b"\x12\x34"
    assert raw[4:6] == b"\xab\xcd"


def test_rejects_short_frame():
    with pytest.raises(ValueError, match="too short"):
        Frame.decode(b"\x01\x01\x00")


def test_rejects_wrong_version():
    bad = bytes([99, 1, 0, 1, 0, 0])
    with pytest.raises(ValueError, match="unsupported wire version"):
        Frame.decode(bad)


def test_rejects_non_map_payload():
    import cbor2

    bad = b"\x01\x01\x00\x01\x00\x00" + cbor2.dumps([1, 2, 3])
    with pytest.raises(ValueError, match="must be a CBOR map"):
        Frame.decode(bad)


def test_dry_run_kind():
    f = Frame(kind=Kind.DRY_RUN, seq=1, intent_id=0, payload={})
    assert f.encode()[1] == 0x81
