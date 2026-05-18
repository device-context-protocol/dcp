"""Smoke tests for the MQTT transport — no broker required.

Real integration tests need a live broker; run those manually against
``mosquitto -v`` on localhost.
"""
from __future__ import annotations

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("paho") is None,
    reason="paho-mqtt not installed; install with `pip install -e '.[mqtt]'`",
)


def test_topic_naming_host_side():
    from dcp.transports.mqtt import MqttTransport

    t = MqttTransport("broker.invalid", prefix="dcp/lamp", host_side=True)
    assert t._rx_topic == "dcp/lamp/d2c"
    assert t._tx_topic == "dcp/lamp/c2d"


def test_topic_naming_device_side():
    from dcp.transports.mqtt import MqttTransport

    t = MqttTransport("broker.invalid", prefix="dcp/lamp", host_side=False)
    assert t._rx_topic == "dcp/lamp/c2d"
    assert t._tx_topic == "dcp/lamp/d2c"


def test_prefix_normalization():
    from dcp.transports.mqtt import MqttTransport

    t = MqttTransport("broker.invalid", prefix="dcp/lamp/")
    assert t._tx_topic == "dcp/lamp/c2d"  # trailing slash stripped
