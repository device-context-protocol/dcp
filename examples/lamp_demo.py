"""End-to-end demo: a fake lamp device + a Bridge, talking over a loopback transport.

Run with::

    python examples/lamp_demo.py

You should see the Bridge issue a few calls and the lamp respond. This is the
same shape as a real deployment, only the loopback transport would be swapped
for UART / MQTT / BLE.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from dcp.bridge import Bridge
from dcp.manifest import Manifest
from dcp.transports.loopback import LoopbackTransport
from dcp.wire import Frame, Kind

HERE = Path(__file__).parent


class LampDevice:
    """In-process simulation of a smart lamp."""

    def __init__(self, manifest: Manifest, transport: LoopbackTransport) -> None:
        self._manifest = manifest
        self._transport = transport
        self.brightness = 0.0
        self.color = (255, 255, 255)

    async def run(self) -> None:
        async for raw in self._transport.frames():
            try:
                frame = Frame.decode(raw)
            except Exception as e:  # noqa: BLE001
                print(f"[lamp] dropping malformed frame: {e}")
                continue
            reply = await self._handle(frame)
            await self._transport.send(reply.encode())

    async def _handle(self, frame: Frame) -> Frame:
        intent = self._manifest.intent_by_id(frame.intent_id)
        if intent is None:
            return Frame(Kind.ERROR, frame.seq, frame.intent_id, {"status": "unknown_intent"})

        if frame.kind == Kind.DRY_RUN:
            return Frame(Kind.REPLY, frame.seq, frame.intent_id,
                         {"would_apply": frame.payload})

        if intent.name == "set_brightness":
            self.brightness = float(frame.payload["level"])
            print(f"[lamp] brightness -> {self.brightness:.0f}%")
            return Frame(Kind.REPLY, frame.seq, frame.intent_id, {})

        if intent.name == "set_color":
            p = frame.payload
            self.color = (int(p["r"]), int(p["g"]), int(p["b"]))
            print(f"[lamp] color -> rgb{self.color}")
            return Frame(Kind.REPLY, frame.seq, frame.intent_id, {})

        if intent.name == "read_brightness":
            return Frame(Kind.REPLY, frame.seq, frame.intent_id, {"value": self.brightness})

        return Frame(Kind.ERROR, frame.seq, frame.intent_id, {"status": "denied"})


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")

    manifest = Manifest.load(HERE / "lamp_manifest.yaml")
    host_tr, device_tr = LoopbackTransport.pair()
    lamp = LampDevice(manifest, device_tr)
    lamp_task = asyncio.create_task(lamp.run(), name="lamp")

    bridge = Bridge(
        manifest,
        host_tr,
        granted_capabilities={"lamp.write", "lamp.read"},
    )
    await bridge.start()

    print("\n=== valid call ===")
    print(await bridge.call("set_brightness", {"level": 60, "fade": 200}))

    print("\n=== read it back ===")
    print(await bridge.call("read_brightness"))

    print("\n=== dry-run ===")
    print(await bridge.call("set_color", {"r": 255, "g": 100, "b": 0}, dry_run=True))
    print(f"[host] lamp.color still {lamp.color}  (dry-run had no side effect)")

    print("\n=== out-of-range — rejected at Bridge, never hits device ===")
    print(await bridge.call("set_brightness", {"level": 9000}))

    print("\n=== unknown intent ===")
    print(await bridge.call("self_destruct"))

    print("\n=== missing capability ===")
    bridge._granted.discard("lamp.write")
    print(await bridge.call("set_brightness", {"level": 10}))

    await bridge.stop()
    lamp_task.cancel()
    try:
        await lamp_task
    except (asyncio.CancelledError, Exception):
        pass


if __name__ == "__main__":
    asyncio.run(main())
