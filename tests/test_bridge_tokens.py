"""Integration test: Bridge accepts a token and grants its capabilities."""
from __future__ import annotations

import asyncio

import pytest

from dcp.bridge import Bridge
from dcp.manifest import Manifest
from dcp.simulator import GenericSimulator
from dcp.tokens import mint
from dcp.transports.loopback import LoopbackTransport

from tests.test_manifest import SAMPLE

SECRET = b"k" * 32


@pytest.fixture
async def with_token():
    manifest = Manifest.from_dict(SAMPLE)
    host_tr, device_tr = LoopbackTransport.pair()
    sim = GenericSimulator(manifest, device_tr)
    sim_task = asyncio.create_task(sim.run())

    token = mint({"lamp.write", "lamp.read"}, secret=SECRET, ttl_seconds=60)
    bridge = Bridge(manifest, host_tr, token=token, secret=SECRET)
    await bridge.start()
    try:
        yield bridge
    finally:
        await bridge.stop()
        sim_task.cancel()
        try:
            await sim_task
        except (asyncio.CancelledError, Exception):
            pass


async def test_token_grants_capabilities(with_token):
    bridge = with_token
    assert (await bridge.call("set_brightness", {"level": 50})).ok


async def test_token_without_capability_is_rejected():
    manifest = Manifest.from_dict(SAMPLE)
    host_tr, device_tr = LoopbackTransport.pair()
    sim = GenericSimulator(manifest, device_tr)
    sim_task = asyncio.create_task(sim.run())

    token = mint({"lamp.read"}, secret=SECRET, ttl_seconds=60)  # write missing
    bridge = Bridge(manifest, host_tr, token=token, secret=SECRET)
    await bridge.start()
    try:
        result = await bridge.call("set_brightness", {"level": 50})
        assert result.status == "capability_required"
    finally:
        await bridge.stop()
        sim_task.cancel()
        try:
            await sim_task
        except (asyncio.CancelledError, Exception):
            pass


def test_bridge_rejects_token_without_secret():
    manifest = Manifest.from_dict(SAMPLE)
    host_tr, _ = LoopbackTransport.pair()
    token = mint({"lamp.read"}, secret=SECRET)
    with pytest.raises(ValueError, match="secret"):
        Bridge(manifest, host_tr, token=token)
