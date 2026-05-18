"""UART transport over serial ports (USB-CDC, RS-232, RS-485).

Requires the ``serial`` extra::

    pip install -e ".[serial]"

Frames are wrapped with COBS + CRC-16 (see :mod:`dcp.framing`).
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from dcp.framing import unwrap, wrap
from dcp.transports.base import Transport

log = logging.getLogger("dcp.uart")


class UartTransport(Transport):
    def __init__(self, port: str, baud: int = 115200) -> None:
        self._port = port
        self._baud = baud
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._closed = False

    async def open(self) -> None:
        try:
            import serial_asyncio
        except ImportError as e:
            raise SystemExit(
                "UART transport needs pyserial-asyncio. Run: pip install -e '.[serial]'"
            ) from e
        self._reader, self._writer = await serial_asyncio.open_serial_connection(
            url=self._port, baudrate=self._baud
        )
        log.info("opened %s @ %d baud", self._port, self._baud)

    async def send(self, frame: bytes) -> None:
        if self._closed or self._writer is None:
            raise RuntimeError("transport not open")
        self._writer.write(wrap(frame))
        await self._writer.drain()

    async def frames(self) -> AsyncIterator[bytes]:
        if self._reader is None:
            raise RuntimeError("transport not open")
        buf = bytearray()
        while not self._closed:
            try:
                byte = await self._reader.readexactly(1)
            except (asyncio.IncompleteReadError, ConnectionError):
                return
            if byte == b"\x00":
                if buf:
                    try:
                        yield unwrap(bytes(buf))
                    except ValueError as e:
                        log.warning("dropping malformed UART frame: %s", e)
                    buf.clear()
            else:
                buf.append(byte[0])

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
