from dcp.transports.base import Transport
from dcp.transports.loopback import LoopbackTransport

__all__ = ["Transport", "LoopbackTransport"]

# Optional-dep transports are imported lazily.
def __getattr__(name: str):
    if name == "UartTransport":
        from dcp.transports.uart import UartTransport
        return UartTransport
    if name == "MqttTransport":
        from dcp.transports.mqtt import MqttTransport
        return MqttTransport
    if name == "BleTransport":
        from dcp.transports.ble import BleTransport
        return BleTransport
    raise AttributeError(name)
