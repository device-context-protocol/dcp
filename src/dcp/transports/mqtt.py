"""MQTT transport.

Frames are sent as raw bytes on MQTT topics::

    {prefix}/c2d   — host → device (calls, dry-runs)
    {prefix}/d2c   — device → host (replies, events, errors)

Requires the ``mqtt`` extra::

    pip install -e ".[mqtt]"

MQTT itself provides framing and (with QoS≥1) delivery guarantees, so we do
not COBS-encode or CRC; the wire bytes are just the DCP frame.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from dcp.transports.base import Transport

log = logging.getLogger("dcp.mqtt")


class MqttTransport(Transport):
    def __init__(
        self,
        broker: str,
        *,
        port: int = 1883,
        prefix: str = "dcp/default",
        username: str | None = None,
        password: str | None = None,
        client_id: str | None = None,
        host_side: bool = True,
    ) -> None:
        self._broker = broker
        self._port = port
        self._prefix = prefix.rstrip("/")
        self._username = username
        self._password = password
        self._client_id = client_id or f"dcp-{'host' if host_side else 'device'}"
        self._host_side = host_side
        self._tx_topic = f"{self._prefix}/{'c2d' if host_side else 'd2c'}"
        self._rx_topic = f"{self._prefix}/{'d2c' if host_side else 'c2d'}"
        self._client = None
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._closed = False

    async def open(self) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as e:
            raise SystemExit(
                "MQTT transport needs paho-mqtt. Run: pip install -e '.[mqtt]'"
            ) from e

        self._loop = asyncio.get_running_loop()
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=self._client_id
        )
        if self._username:
            self._client.username_pw_set(self._username, self._password)

        ready: asyncio.Future[None] = self._loop.create_future()

        def on_connect(client, _userdata, _flags, rc, _props=None):
            if rc == 0:
                client.subscribe(self._rx_topic, qos=1)
                if not ready.done():
                    self._loop.call_soon_threadsafe(ready.set_result, None)
            else:
                if not ready.done():
                    self._loop.call_soon_threadsafe(
                        ready.set_exception,
                        RuntimeError(f"MQTT connect failed: rc={rc}"),
                    )

        def on_message(_client, _userdata, msg):
            self._loop.call_soon_threadsafe(self._queue.put_nowait, msg.payload)

        self._client.on_connect = on_connect
        self._client.on_message = on_message
        self._client.connect(self._broker, self._port, keepalive=30)
        self._client.loop_start()
        await asyncio.wait_for(ready, timeout=5.0)
        log.info("MQTT connected to %s:%d (rx=%s, tx=%s)",
                 self._broker, self._port, self._rx_topic, self._tx_topic)

    async def send(self, frame: bytes) -> None:
        if self._closed or self._client is None:
            raise RuntimeError("transport not open")
        info = self._client.publish(self._tx_topic, frame, qos=1)
        info.wait_for_publish(timeout=2.0)

    async def frames(self) -> AsyncIterator[bytes]:
        while not self._closed:
            frame = await self._queue.get()
            if frame == b"":  # close sentinel
                return
            yield frame

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._queue.put(b"")
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
