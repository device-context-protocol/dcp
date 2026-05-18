"""Transport abstraction. A transport is a bidirectional, framed byte channel.

Real transports (UART, MQTT, BLE, USB-CDC, WebSocket) implement this interface.
``send`` writes one frame; ``frames`` yields one frame at a time.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class Transport(ABC):
    @abstractmethod
    async def send(self, frame: bytes) -> None: ...

    @abstractmethod
    def frames(self) -> AsyncIterator[bytes]: ...

    @abstractmethod
    async def close(self) -> None: ...
