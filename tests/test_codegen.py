"""Tests for the codegen module."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dcp.codegen import render
from dcp.wire import intent_id


@pytest.fixture
def manifest_file(tmp_path: Path) -> Path:
    path = tmp_path / "manifest.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "dcp": "0.1",
                "device": {"id": "lamp-x", "model": "lx", "vendor": "ex.dev"},
                "intents": [
                    {
                        "name": "set_brightness",
                        "params": {"level": {"type": "float"}},
                        "capability": "lamp.write",
                        "idempotent": True,
                    },
                    {"name": "read_brightness", "returns": {"type": "float"}, "capability": "lamp.read"},
                ],
                "events": [
                    {"name": "motion_detected",
                     "payload": {"confidence": {"type": "float"}},
                     "capability": "lamp.read"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_emits_ids_and_capabilities(manifest_file: Path):
    out = render(manifest_file)
    assert "#ifndef DCP_INTENTS_LAMP_X_H" in out
    assert f"DCP_INTENT_SET_BRIGHTNESS = 0x{intent_id('set_brightness'):04x}" in out
    assert f"DCP_INTENT_READ_BRIGHTNESS = 0x{intent_id('read_brightness'):04x}" in out
    assert f"DCP_EVENT_MOTION_DETECTED = 0x{intent_id('motion_detected'):04x}" in out
    assert '#define DCP_CAP_LAMP_WRITE "lamp.write"' in out
    assert '#define DCP_CAP_LAMP_READ "lamp.read"' in out


def test_includes_manifest_hash(manifest_file: Path):
    out1 = render(manifest_file)
    assert "Manifest SHA-256[:16]: " in out1

    manifest_file.write_text(manifest_file.read_text() + "\n# touched\n", encoding="utf-8")
    out2 = render(manifest_file)
    assert out1 != out2  # hash changed


def test_with_stubs_emits_handler_table(manifest_file: Path):
    out = render(manifest_file, with_stubs=True)
    assert "dcp::Status handle_set_brightness" in out
    assert "dcp::Status handle_read_brightness" in out
    assert "static dcp::IntentBinding DCP_BINDINGS[]" in out
    assert 'DCP_ID("set_brightness")' in out