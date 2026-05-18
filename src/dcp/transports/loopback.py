"""In-memory loopback transport. Useful for tests and simulators."""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from dcp.transports.base import Transport

_CLOSE = b""  # empty frame is invalid on the wire (header is 6 bytes), reused as a sentinel


class LoopbackTransport(Transport):
    """One end of a bidirectional in-memory channel.

    Use :meth:`pair` to obtain the matched pair.
    """

    def __init__(self, rx: asyncio.Queue[bytes], tx: asyncio.Queue[bytes]) -> None:
        self._rx = rx
        self._tx = tx
        self._closed = False

    @classmethod
    def pair(cls) -> tuple["LoopbackTransport", "LoopbackTransport"]:
        a: asyncio.Queue[bytes] = asyncio.Queue()
        b: asyncio.Queue[bytes] = asyncio.Queue()
        return cls(rx=a, tx=b), cls(rx=b, tx=a)

    async def send(self, frame: bytes) -> None:
        if self._closed:
            raise RuntimeError("transport closed")
        await self._tx.put(frame)

    async def frames(self) -> AsyncIterator[bytes]:
        while not self._closed:
            frame = await self._rx.get()
            if frame == _CLOSE:
                return
            yield frame

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # Signal the peer, and also wake our own frames() loop if it's blocked on get().
        await self._tx.put(_CLOSE)
        await self._rx.put(_CLOSE)
