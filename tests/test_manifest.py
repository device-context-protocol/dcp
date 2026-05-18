"""Tests for manifest parsing and the safety layer."""
from __future__ import annotations

import pytest

from dcp.manifest import Manifest
from dcp.safety import SafetyError, check_call


SAMPLE = {
    "dcp": "0.1",
    "device": {"id": "lamp-1", "model": "smart_lamp", "vendor": "example.dev"},
    "intents": [
        {
            "name": "set_brightness",
            "params": {
                "level": {"type": "float", "unit": "percent", "range": [0, 100]},
                "fade": {"type": "duration", "unit": "ms", "default": 0},
            },
            "capability": "lamp.write",
            "idempotent": True,
            "dry_run": True,
        },
        {
            "name": "read_brightness",
            "returns": {"type": "float", "unit": "percent"},
            "capability": "lamp.read",
        },
    ],
    "events": [
        {
            "name": "motion_detected",
            "payload": {"confidence": {"type": "float", "range": [0, 1]}},
            "capability": "lamp.read",
        }
    ],
}


def test_manifest_from_dict():
    m = Manifest.from_dict(SAMPLE)
    assert m.device_id == "lamp-1"
    assert set(m.intents) == {"set_brightness", "read_brightness"}
    assert set(m.events) == {"motion_detected"}

    sb = m.intents["set_brightness"]
    assert sb.capability == "lamp.write"
    assert sb.idempotent is True
    assert sb.dry_run is True
    assert sb.params["level"].range == (0.0, 100.0)
    assert sb.params["fade"].default == 0


def test_safety_passes_valid_call():
    m = Manifest.from_dict(SAMPLE)
    normalized = check_call(
        m.intents["set_brightness"],
        {"level": 50, "fade": 200},
        granted_capabilities={"lamp.write"},
    )
    assert normalized == {"level": 50.0, "fade": 200.0}


def test_safety_applies_default():
    m = Manifest.from_dict(SAMPLE)
    normalized = check_call(
        m.intents["set_brightness"],
        {"level": 50},
        granted_capabilities={"lamp.write"},
    )
    assert normalized["fade"] == 0.0


def test_safety_rejects_out_of_range():
    m = Manifest.from_dict(SAMPLE)
    with pytest.raises(SafetyError) as exc:
        check_call(
            m.intents["set_brightness"],
            {"level": 150},
            granted_capabilities={"lamp.write"},
        )
    assert exc.value.status == "range"


def test_safety_rejects_missing_capability():
    m = Manifest.from_dict(SAMPLE)
    with pytest.raises(SafetyError) as exc:
        check_call(
            m.intents["set_brightness"],
            {"level": 50},
            granted_capabilities=set(),
        )
    assert exc.value.status == "capability_required"


def test_safety_rejects_unknown_param():
    m = Manifest.from_dict(SAMPLE)
    with pytest.raises(SafetyError) as exc:
        check_call(
            m.intents["set_brightness"],
            {"level": 50, "evil": 1},
            granted_capabilities={"lamp.write"},
        )
    assert exc.value.status == "range"


def test_safety_rejects_missing_required():
    m = Manifest.from_dict(SAMPLE)
    with pytest.raises(SafetyError) as exc:
        check_call(
            m.intents["set_brightness"],
            {},
            granted_capabilities={"lamp.write"},
        )
    assert exc.value.status == "range"
