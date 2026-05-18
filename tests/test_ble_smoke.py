"""Smoke tests for the BLE transport — no radio required.

Real BLE integration testing requires a peripheral on the air; do it manually.
"""
from __future__ import annotations

import importlib.util

import pytest

from dcp.transports.ble import derive_uuids


def test_derive_uuids_canonical():
    svc = "12345678-1234-5678-1234-567812345678"
    c2d, d2c = derive_uuids(svc)
    assert c2d == "12345678-1234-5678-1234-5678123456c1"
    assert d2c == "12345678-1234-5678-1234-5678123456d1"


def test_derive_uuids_case_insensitive():
    svc = "ABCDEF12-3456-7890-ABCD-EF1234567890"
    c2d, d2c = derive_uuids(svc)
    assert c2d.endswith("c1")
    assert d2c.endswith("d1")
    assert c2d.startswith("abcdef12-")  # normalized to lower


@pytest.mark.skipif(
    importlib.util.find_spec("bleak") is None,
    reason="bleak not installed; install with `pip install -e '.[ble]'`",
)
def test_class_constructs_without_radio():
    from dcp.transports.ble import BleTransport

    t = BleTransport(
        "AA:BB:CC:DD:EE:FF",
        service_uuid="12345678-1234-5678-1234-567812345678",
    )
    assert t._c2d_uuid.endswith("c1")
    assert t._d2c_uuid.endswith("d1")
