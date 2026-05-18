"""End-to-end test: Bridge talks to an in-process fake device via loopback."""
from __future__ import annotations

import asyncio

import pytest

from dcp.bridge import Bridge
from dcp.manifest import Manifest
from dcp.transports.loopback import LoopbackTransport
from dcp.wire import Frame, Kind

from tests.test_manifest import SAMPLE


class FakeLamp:
    """Tiny device-side handler. Owns its own loopback end."""

    def __init__(self, manifest: Manifest, transport: LoopbackTransport) -> None:
        self._manifest = manifest
        self._transport = transport
        self._brightness = 0.0

    async def run(self) -> None:
        async for raw in self._transport.frames():
            frame = Frame.decode(raw)
            reply = await self._handle(frame)
            await self._transport.send(reply.encode())

    async def _handle(self, frame: Frame) -> Frame:
        intent = self._manifest.intent_by_id(frame.intent_id)
        if intent is None:
            return Frame(Kind.ERROR, frame.seq, frame.intent_id, {"status": "unknown_intent"})

        if frame.kind == Kind.DRY_RUN:
            return Frame(Kind.REPLY, frame.seq, frame.intent_id,
                         {"would_set": frame.payload.get("level")})

        if intent.name == "set_brightness":
            self._brightness = float(frame.payload.get("level", 0))
            return Frame(Kind.REPLY, frame.seq, frame.intent_id, {})

        if intent.name == "read_brightness":
            return Frame(Kind.REPLY, frame.seq, frame.intent_id, {"value": self._brightness})

        return Frame(Kind.ERROR, frame.seq, frame.intent_id, {"status": "denied"})


@pytest.fixture
async def bridge_and_lamp():
    manifest = Manifest.from_dict(SAMPLE)
    host_tr, device_tr = LoopbackTransport.pair()
    lamp = FakeLamp(manifest, device_tr)
    lamp_task = asyncio.create_task(lamp.run())

    bridge = Bridge(
        manifest,
        host_tr,
        granted_capabilities={"lamp.write", "lamp.read"},
        timeout=1.0,
    )
    await bridge.start()
    try:
        yield bridge, lamp
    finally:
        await bridge.stop()
        lamp_task.cancel()
        try:
            await lamp_task
        except (asyncio.CancelledError, Exception):
            pass


async def test_set_brightness_round_trip(bridge_and_lamp):
    bridge, lamp = bridge_and_lamp
    result = await bridge.call("set_brightness", {"level": 75})
    assert result.ok
    assert lamp._brightness == 75.0


async def test_read_after_write(bridge_and_lamp):
    bridge, lamp = bridge_and_lamp
    await bridge.call("set_brightness", {"level": 33})
    result = await bridge.call("read_brightness")
    assert result.ok
    assert result.data["value"] == 33.0


async def test_unknown_intent_rejected_at_bridge(bridge_and_lamp):
    bridge, _ = bridge_and_lamp
    result = await bridge.call("turn_into_pumpkin")
    assert result.status == "unknown_intent"


async def test_out_of_range_rejected_at_bridge(bridge_and_lamp):
    bridge, lamp = bridge_and_lamp
    result = await bridge.call("set_brightness", {"level": 200})
    assert result.status == "range"
    assert lamp._brightness == 0.0  # never reached the device


async def test_missing_capability_rejected(bridge_and_lamp):
    bridge, _ = bridge_and_lamp
    bridge._granted = set()  # revoke
    result = await bridge.call("set_brightness", {"level": 50})
    assert result.status == "capability_required"


async def test_dry_run(bridge_and_lamp):
    bridge, lamp = bridge_and_lamp
    result = await bridge.call("set_brightness", {"level": 50}, dry_run=True)
    assert result.ok
    assert result.data == {"would_set": 50.0}
    assert lamp._brightness == 0.0  # side-effect-free


async def test_dry_run_denied_when_unsupported(bridge_and_lamp):
    bridge, _ = bridge_and_lamp
    result = await bridge.call("read_brightness", dry_run=True)
    assert result.status == "denied"


def test_normalize_status_translates_firmware_ints():
    from dcp.bridge import _normalize_status
    assert _normalize_status(4) == "unknown_intent"
    assert _normalize_status(2) == "range"
    assert _normalize_status(0) == "ok"
    assert _normalize_status("denied") == "denied"
    assert _normalize_status(None) == "denied"
    assert _normalize_status(99) == "denied"   # unknown int falls back
