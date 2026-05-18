"""BLE GATT transport.

The host (central) connects to a device (peripheral) and uses two
characteristics on one DCP service:

- **c2d** (host → device): GATT write-with-response
- **d2c** (device → host): GATT notify

By convention the c2d / d2c UUIDs differ from the service UUID only in their
last byte (``c1`` and ``d1`` respectively). The same convention is documented
in the ESP32 firmware sketch so the two sides agree without configuration.

Requires the ``ble`` extra::

    pip install -e ".[ble]"
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from dcp.transports.base import Transport

log = logging.getLogger("dcp.ble")


def derive_uuids(service_uuid: str) -> tuple[str, str]:
    """Return (c2d_uuid, d2c_uuid) derived from the service UUID by the DCP convention.

    Last byte is replaced with ``c1`` for c2d, ``d1`` for d2c. UUIDs are
    expected in canonical 8-4-4-4-12 form.
    """
    base = service_uuid.lower()
    if len(base) < 2:
        raise ValueError("invalid service UUID")
    return base[:-2] + "c1", base[:-2] + "d1"


class BleTransport(Transport):
    def __init__(
        self,
        address: str,
        *,
        service_uuid: str,
        c2d_uuid: str | None = None,
        d2c_uuid: str | None = None,
    ) -> None:
        if c2d_uuid is None or d2c_uuid is None:
            derived_c2d, derived_d2c = derive_uuids(service_uuid)
            c2d_uuid = c2d_uuid or derived_c2d
            d2c_uuid = d2c_uuid or derived_d2c
        self._address = address
        self._service_uuid = service_uuid
        self._c2d_uuid = c2d_uuid
        self._d2c_uuid = d2c_uuid
        self._client = None
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._closed = False

    async def open(self) -> None:
        try:
            from bleak import BleakClient
        except ImportError as e:
            raise SystemExit(
                "BLE transport needs bleak. Run: pip install -e '.[ble]'"
            ) from e

        self._loop = asyncio.get_running_loop()
        self._client = BleakClient(self._address)
        await self._client.connect()
        await self._client.start_notify(self._d2c_uuid, self._on_notify)
        log.info("BLE connected to %s (service=%s)", self._address, self._service_uuid)

    def _on_notify(self, _sender, data: bytearray) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, bytes(data))

    async def send(self, frame: bytes) -> None:
        if self._closed or self._client is None:
            raise RuntimeError("transport not open")
        await self._client.write_gatt_char(self._c2d_uuid, frame, response=True)

    async def frames(self) -> AsyncIterator[bytes]:
        while not self._closed:
            frame = await self._queue.get()
            if frame == b"":
                return
            yield frame

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._queue.put(b"")
        if self._client is not None:
            try:
                await self._client.stop_notify(self._d2c_uuid)
            except Exception:  # noqa: BLE001
                pass
            try:
                await self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
