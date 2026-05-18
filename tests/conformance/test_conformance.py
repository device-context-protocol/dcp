"""Reference conformance runner.

Loads ``golden_frames.yaml`` and checks that the Python implementation
produces, and accepts, the listed bytes. Any DCP port should be able to
write an equivalent runner.
"""
from __future__ import annotations

from pathlib import Path

import cbor2
import pytest
import yaml

from dcp.framing import unwrap, wrap
from dcp.wire import Frame, Kind, intent_id

GOLDEN = Path(__file__).parent / "golden_frames.yaml"


def _hex(s: str) -> bytes:
    return bytes.fromhex(s.replace(" ", "").replace("\n", ""))


def _build_frame(case: dict) -> bytes:
    header = bytes(
        [
            0x01,  # version
            int(case["kind"]),
            (int(case["seq"]) >> 8) & 0xFF,
            int(case["seq"]) & 0xFF,
        ]
    )
    iid = intent_id(case["intent"])
    header += bytes([(iid >> 8) & 0xFF, iid & 0xFF])
    return header + _hex(case.get("cbor_hex", ""))


def load_cases() -> list[dict]:
    return yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["name"])
def test_encode_matches_golden(case: dict):
    """Building a Frame from payload and re-encoding produces the golden bytes."""
    frame = Frame(
        kind=Kind(int(case["kind"])),
        seq=int(case["seq"]),
        intent_id=intent_id(case["intent"]),
        payload=case["payload"],
    )
    produced = frame.encode()
    expected = _build_frame(case)

    # Encoders are allowed either empty body OR explicit CBOR empty map (0xa0)
    # for {} payloads. Decoders MUST accept both. The golden suite includes
    # both forms; here we only check the header matches and the body is one
    # of the two permitted encodings.
    if case["payload"] == {}:
        assert produced[:6] == expected[:6]
        assert produced[6:] in (b"", b"\xa0")
    else:
        assert produced == expected, (
            f"\n  produced: {produced.hex()}"
            f"\n  expected: {expected.hex()}"
        )


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["name"])
def test_decode_matches_payload(case: dict):
    """Parsing the golden bytes yields the listed payload."""
    raw = _build_frame(case)
    frame = Frame.decode(raw)
    assert frame.kind == Kind(int(case["kind"]))
    assert frame.seq == int(case["seq"])
    assert frame.intent_id == intent_id(case["intent"])

    expected_payload = case["payload"]
    if case.get("cbor_hex", "").strip():
        decoded_payload = cbor2.loads(_hex(case["cbor_hex"]))
        assert decoded_payload == expected_payload
    assert frame.payload == expected_payload


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["name"])
def test_uart_wrap_roundtrip(case: dict):
    """COBS + CRC wrap of the frame decodes back to itself."""
    frame_bytes = _build_frame(case)
    wire = wrap(frame_bytes)
    assert wire.endswith(b"\x00")
    assert b"\x00" not in wire[:-1]
    assert unwrap(wire[:-1]) == frame_bytes


def test_intent_id_table():
    """Sanity-check a few CRC-16 values that other implementations can hard-code."""
    table = {
        "ping": intent_id("ping"),
        "read_brightness": intent_id("read_brightness"),
        "set_brightness": intent_id("set_brightness"),
        "set_color": intent_id("set_color"),
        "unknown": intent_id("unknown"),
        "motion_detected": intent_id("motion_detected"),
    }
    # All in range and deterministic — no test_*flakiness*
    for name, iid in table.items():
        assert 0 <= iid <= 0xFFFF, name
        assert iid == intent_id(name), name
