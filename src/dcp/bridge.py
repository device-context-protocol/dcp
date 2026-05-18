"""Bridge: host-side orchestrator that links a manifest, a transport, and an LLM.

For v0.1 the LLM-facing API is just :meth:`Bridge.call`. An MCP server wrapper
(``dcp serve --mcp``) is on the roadmap.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from dcp.manifest import Manifest
from dcp.safety import SafetyError, check_call
from dcp.tokens import Token, verify as verify_token
from dcp.transports.base import Transport
from dcp.wire import Frame, Kind

log = logging.getLogger("dcp.bridge")

EventListener = Callable[[int, dict], Awaitable[None] | None]

# Firmware-side `Status` enum values, matching firmware/esp32/src/DCP.h.
# Frames from a device carry the numeric form; we map back to canonical strings
# here so the LLM sees readable statuses rather than opaque integers.
_FIRMWARE_STATUS = {
    0: "ok",
    1: "denied",
    2: "range",
    3: "busy",
    4: "unknown_intent",
    5: "capability_required",
}


def _normalize_status(raw, fallback: str = "denied") -> str:
    if isinstance(raw, int):
        return _FIRMWARE_STATUS.get(raw, fallback)
    if isinstance(raw, str) and raw:
        return raw
    return fallback


@dataclass(slots=True)
class CallResult:
    status: str  # ok | denied | range | busy | unknown_intent | capability_required
    data: dict[str, Any]

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class Bridge:
    """Host-side bridge to one device transport.

    Example::

        manifest = Manifest.load("lamp.yaml")
        host_tr, _ = LoopbackTransport.pair()
        bridge = Bridge(manifest, host_tr, granted_capabilities={"lamp.write"})
        await bridge.start()
        result = await bridge.call("set_brightness", {"level": 50})
        await bridge.stop()
    """

    def __init__(
        self,
        manifest: Manifest,
        transport: Transport,
        *,
        granted_capabilities: set[str] | None = None,
        token: str | None = None,
        secret: bytes | None = None,
        wire_secret: bytes | None = None,
        timeout: float = 2.0,
    ) -> None:
        self._token: Token | None = None
        if token is not None:
            if secret is None:
                raise ValueError("a secret is required to verify a token")
            self._token = verify_token(token, secret=secret)
            granted_capabilities = set(self._token.caps)

        self._manifest = manifest
        self._transport = transport
        self._granted = granted_capabilities or set()
        self._secret = secret
        self._wire_secret = wire_secret
        self._timeout = timeout
        self._next_seq = 1
        self._pending: dict[int, asyncio.Future[Frame]] = {}
        self._reader_task: asyncio.Task | None = None
        self._event_listeners: list[EventListener] = []

    async def start(self) -> None:
        if self._reader_task is None:
            self._reader_task = asyncio.create_task(
                self._reader_loop(), name="dcp.bridge.reader"
            )

    async def stop(self) -> None:
        await self._transport.close()
        if self._reader_task is not None:
            try:
                await asyncio.wait_for(self._reader_task, timeout=1.0)
            except asyncio.TimeoutError:
                self._reader_task.cancel()
            self._reader_task = None
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

    def on_event(self, callback: EventListener) -> None:
        self._event_listeners.append(callback)

    async def call(
        self,
        intent_name: str,
        params: dict | None = None,
        *,
        dry_run: bool = False,
    ) -> CallResult:
        if self._token is not None and self._token.expired():
            return CallResult("capability_required", {"message": "session token expired"})

        intent = self._manifest.intents.get(intent_name)
        if intent is None:
            return CallResult("unknown_intent", {"intent": intent_name})

        if dry_run and not intent.dry_run:
            return CallResult("denied", {"reason": "dry_run not supported"})

        try:
            normalized = check_call(intent, params or {}, granted_capabilities=self._granted)
        except SafetyError as e:
            return CallResult(e.status, {"message": e.message})

        seq = self._next_seq
        self._next_seq = (self._next_seq + 1) & 0xFFFF or 1
        frame = Frame(
            kind=Kind.DRY_RUN if dry_run else Kind.CALL,
            seq=seq,
            intent_id=intent.id,
            payload=normalized,
        )

        future: asyncio.Future[Frame] = asyncio.get_running_loop().create_future()
        self._pending[seq] = future
        await self._transport.send(frame.encode(wire_secret=self._wire_secret))

        try:
            reply = await asyncio.wait_for(future, timeout=self._timeout)
        except asyncio.TimeoutError:
            self._pending.pop(seq, None)
            return CallResult("busy", {"message": "timeout waiting for reply"})

        if reply.kind == Kind.ERROR:
            status = _normalize_status(reply.payload.get("status"))
            return CallResult(status, reply.payload)
        return CallResult("ok", reply.payload)

    async def _reader_loop(self) -> None:
        try:
            async for raw in self._transport.frames():
                try:
                    frame = Frame.decode(raw, wire_secret=self._wire_secret)
                except Exception as e:
                    log.warning("dropping malformed frame: %s", e)
                    continue

                if frame.kind in (Kind.REPLY, Kind.ERROR):
                    future = self._pending.pop(frame.seq, None)
                    if future is not None and not future.done():
                        future.set_result(frame)
                    else:
                        log.warning("reply for unknown seq=%d", frame.seq)
                elif frame.kind == Kind.EVENT:
                    await self._dispatch_event(frame)
                else:
                    log.warning("unexpected frame kind 0x%02x on host side", int(frame.kind))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("reader loop crashed")

    async def _dispatch_event(self, frame: Frame) -> None:
        for cb in self._event_listeners:
            try:
                result = cb(frame.intent_id, frame.payload)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                log.exception("event listener raised")
