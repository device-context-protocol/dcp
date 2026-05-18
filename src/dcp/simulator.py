"""Generic in-process device simulator.

A reflective device that accepts any intent from a manifest and replies sensibly:

- **Write intent** (no ``returns``): payload is stored under the intent name, ack.
- **Read intent** (with ``returns``): if the manifest has a matching ``set_X``
  for ``read_X`` / ``get_X``, return the last written value. Otherwise return a
  type-appropriate default.
- **Dry-run frame**: echoes the payload as ``{"would_apply": ...}`` without state change.

For demos and tests only — not a real device.
"""
from __future__ import annotations

import logging

from dcp.manifest import Manifest
from dcp.transports.base import Transport
from dcp.wire import Frame, Kind

log = logging.getLogger("dcp.simulator")

_DEFAULTS = {
    "float": 0.0,
    "int": 0,
    "duration": 0.0,
    "bool": False,
    "string": "",
}


class GenericSimulator:
    def __init__(self, manifest: Manifest, transport: Transport) -> None:
        self._manifest = manifest
        self._transport = transport
        self._state: dict[str, dict] = {}

    async def run(self) -> None:
        async for raw in self._transport.frames():
            try:
                frame = Frame.decode(raw)
            except Exception as e:  # noqa: BLE001
                log.warning("malformed frame: %s", e)
                continue
            reply = self._handle(frame)
            await self._transport.send(reply.encode())

    def _handle(self, frame: Frame) -> Frame:
        intent = self._manifest.intent_by_id(frame.intent_id)
        if intent is None:
            return Frame(Kind.ERROR, frame.seq, frame.intent_id, {"status": "unknown_intent"})

        if frame.kind == Kind.DRY_RUN:
            return Frame(Kind.REPLY, frame.seq, frame.intent_id, {"would_apply": frame.payload})

        if intent.returns is not None:
            return Frame(Kind.REPLY, frame.seq, frame.intent_id, self._read_value(intent.name))

        self._state[intent.name] = frame.payload
        log.info("%s <- %s", intent.name, frame.payload)
        return Frame(Kind.REPLY, frame.seq, frame.intent_id, {})

    def _read_value(self, intent_name: str) -> dict:
        """Resolve a read intent against any prior set_X write.

        Always returns a ``{"value": ...}`` shape so the LLM gets a
        predictable payload. For paired writes with multiple params we
        return the first param's value (typically the "primary" one — e.g.
        ``level`` for ``set_brightness(level, fade)``).
        """
        write_name = _paired_write(intent_name)
        if write_name and write_name in self._state:
            stored = self._state[write_name]
            if stored:
                return {"value": next(iter(stored.values()))}

        intent = self._manifest.intents.get(intent_name)
        ret_type = intent.returns.type if intent and intent.returns else None
        return {"value": _DEFAULTS.get(ret_type)}


def _paired_write(read_name: str) -> str | None:
    for prefix in ("read_", "get_"):
        if read_name.startswith(prefix):
            return "set_" + read_name[len(prefix):]
    return None
