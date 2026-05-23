"""DCP manifest parser: YAML in, structured dataclasses out."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from dcp.wire import intent_id


@dataclass(slots=True)
class Param:
    name: str
    type: str
    unit: str | None = None
    range: tuple[float, float] | None = None
    default: Any = None
    # Optional constraints for string-typed params. Both are advisory
    # at the wire layer and enforced at the Bridge in dcp.safety.
    pattern: str | None = None      # regex (re.fullmatch)
    max_length: int | None = None   # in characters


@dataclass(slots=True)
class Intent:
    name: str
    params: dict[str, Param]
    returns: Param | None
    capability: str
    idempotent: bool
    dry_run: bool

    @property
    def id(self) -> int:
        return intent_id(self.name)


@dataclass(slots=True)
class Event:
    name: str
    payload: dict[str, Param]
    capability: str

    @property
    def id(self) -> int:
        return intent_id(self.name)


@dataclass(slots=True)
class Manifest:
    version: str
    device_id: str
    model: str
    vendor: str
    intents: dict[str, Intent]
    events: dict[str, Event]

    @classmethod
    def load(cls, path: str | Path) -> "Manifest":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "Manifest":
        device = data.get("device", {})
        intents = {i["name"]: _parse_intent(i) for i in data.get("intents", [])}
        events = {e["name"]: _parse_event(e) for e in data.get("events", [])}
        return cls(
            version=str(data.get("dcp", "0.1")),
            device_id=device.get("id", "unknown"),
            model=device.get("model", "unknown"),
            vendor=device.get("vendor", "unknown"),
            intents=intents,
            events=events,
        )

    def intent_by_id(self, iid: int) -> Intent | None:
        return next((i for i in self.intents.values() if i.id == iid), None)

    def event_by_id(self, iid: int) -> Event | None:
        return next((e for e in self.events.values() if e.id == iid), None)


def _parse_param(name: str, spec: dict) -> Param:
    rng = spec.get("range")
    if rng is not None:
        rng = (float(rng[0]), float(rng[1]))
    return Param(
        name=name,
        type=spec["type"],
        unit=spec.get("unit"),
        range=rng,
        default=spec.get("default"),
        pattern=spec.get("pattern"),
        max_length=spec.get("max_length") or spec.get("maxLength"),
    )


def _parse_intent(spec: dict) -> Intent:
    params = {n: _parse_param(n, p) for n, p in (spec.get("params") or {}).items()}
    returns_spec = spec.get("returns")
    returns = _parse_param("__return__", returns_spec) if returns_spec else None
    return Intent(
        name=spec["name"],
        params=params,
        returns=returns,
        capability=spec.get("capability", ""),
        idempotent=spec.get("idempotent", False),
        dry_run=spec.get("dry_run", False),
    )


def _parse_event(spec: dict) -> Event:
    payload = {n: _parse_param(n, p) for n, p in (spec.get("payload") or {}).items()}
    return Event(
        name=spec["name"],
        payload=payload,
        capability=spec.get("capability", ""),
    )
