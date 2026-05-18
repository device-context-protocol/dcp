"""Tests for the GenericSimulator."""
from __future__ import annotations

import asyncio

import pytest

from dcp.bridge import Bridge
from dcp.manifest import Manifest
from dcp.simulator import GenericSimulator
from dcp.transports.loopback import LoopbackTransport

from tests.test_manifest import SAMPLE


@pytest.fixture
async def simulated():
    manifest = Manifest.from_dict(SAMPLE)
    host_tr, device_tr = LoopbackTransport.pair()
    sim = GenericSimulator(manifest, device_tr)
    sim_task = asyncio.create_task(sim.run())
    bridge = Bridge(manifest, host_tr, granted_capabilities={"lamp.write", "lamp.read"})
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


async def test_set_then_read_paired(simulated):
    bridge = simulated
    assert (await bridge.call("set_brightness", {"level": 42})).ok
    result = await bridge.call("read_brightness")
    assert result.ok
    assert result.data == {"value": 42.0}


async def test_read_before_write_returns_default(simulated):
    bridge = simulated
    result = await bridge.call("read_brightness")
    assert result.ok
    assert result.data == {"value": 0.0}


async def test_dry_run_does_not_persist(simulated):
    bridge = simulated
    assert (await bridge.call("set_brightness", {"level": 99}, dry_run=True)).ok
    result = await bridge.call("read_brightness")
    assert result.data == {"value": 0.0}
