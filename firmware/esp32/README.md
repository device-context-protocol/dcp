# DCP — ESP32 reference firmware

Arduino-compatible C++ library implementing the device side of DCP v0.1.

- COBS-framed, CRC-16 protected DCP frames over `Stream` (Serial, Serial1, ...)
- BLE GATT peripheral via NimBLE-Arduino (`DCPBle.h`)
- Tiny inline CBOR encoder/decoder restricted to the subset DCP actually uses
- Optional wire-level HMAC-SHA256 with a self-contained SHA-256 implementation
- Compact: the DCP layer measures 27.6 KB flash and 0.6 KB RAM over a
  baseline empty sketch (measured — see `docs/paper/figures/measure_footprint.py`)

## Install

Drop this folder into `~/Arduino/libraries/DCP` (or use PlatformIO's
`lib_extra_dirs`), then open `examples/lamp/lamp.ino` in the Arduino IDE.

## Usage sketch

```cpp
#include "DCP.h"

static dcp::Status handle_set_brightness(uint8_t kind,
                                         dcp::CborReader& params,
                                         dcp::CborMap& reply,
                                         void*) {
    // read "level" from params, drive PWM, return STATUS_OK
}

static dcp::IntentBinding bindings[] = {
    { 0, handle_set_brightness, nullptr },
};

void setup() {
    Serial.begin(115200);
    bindings[0].id = dcp::intent_id("set_brightness");
    static dcp::DCP dcp(Serial, bindings, 1);
    /* keep a pointer for loop() */
}

void loop() {
    /* dcp.poll() */;
}
```

## Wire-level HMAC

Optional per-frame HMAC-SHA256. Enable on the device with:

```cpp
static const uint8_t WIRE_SECRET[32] = { /* 32 random bytes */ };
dcp.set_wire_secret(WIRE_SECRET, sizeof(WIRE_SECRET));
```

And on the host:

```python
Bridge(manifest, transport, wire_secret=bytes.fromhex("..."))
```

Both sides must agree — there is no in-band marker (preventing downgrade
attacks). The added cost is 16 bytes per frame and ~50 µs of SHA-256 work
on an ESP32 core.

## BLE peripheral

The `DCPBle` class needs [NimBLE-Arduino](https://github.com/h2zero/NimBLE-Arduino)
1.x. Install via Arduino Library Manager, then see
[examples/lamp_ble/lamp_ble.ino](examples/lamp_ble/lamp_ble.ino).

The c2d / d2c characteristic UUIDs are derived from the service UUID by the
DCP convention (last byte → `0xC1` / `0xD1`), matching the Python
`BleTransport` so no extra configuration is needed on the host.

## Constraints in v0.1

- **CBOR subset only.** Maps with ≤23 entries, short ASCII keys (<24 chars),
  values restricted to int / double / bool / short string. This covers
  everything our manifest schema can express today.
- **MAX_FRAME_BYTES = 256** (configurable in `DCP.h`).
- **No capability enforcement on-device.** Tokens are validated by the Bridge.
- **Single Stream.** No mesh, no multi-link.

## Pairing with the Python Bridge

```bash
# On the host
dcp serve examples/lamp_manifest.yaml --serial COM3
```

Then drive it from any MCP-compatible LLM (Claude Desktop, etc.) by adding
the `dcp` command to its server config.
