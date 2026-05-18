# Device Context Protocol — Specification v0.3

**Status:** Draft. The wire format is stable for v0.x; the manifest schema may
gain backward-compatible fields. Any breaking change bumps `wire_version`.

This document is the normative reference. The reference implementations
(Python Bridge, ESP32 firmware) and the conformance suite at
`tests/conformance/golden_frames.yaml` are tied to this version.

## 1. Goals and scope

DCP is the wire format and architecture for **LLM agents controlling
physical devices** at the cost class of single-dollar microcontrollers.
It is deliberately complementary to MCP: a host-side Bridge translates
between MCP (host ⇄ LLM) and DCP (Bridge ⇄ device).

DCP is **not** a smart-home standard, a robotics middleware, or a
sensor-network protocol. It does not specify mesh routing, OTA, or
device discovery beyond a single point-to-point manifest.

## 2. Architecture

```
┌──────┐    MCP     ┌────────────────┐   DCP    ┌────────┐
│ LLM  │ ─────────▶ │ Bridge         │ wire ──▶ │ Device │
│      │ ◀───────── │ (trust         │ ◀──────  │ (MCU)  │
└──────┘            │  boundary)     │          └────────┘
                    └────────────────┘
```

The **Bridge** is the sole trust boundary. It:

- Authenticates LLM sessions (capability tokens, §6)
- Validates every call against the manifest (range, type, capability)
- Translates intent calls into wire frames (§4) over a transport (§5)
- Optionally signs frames end-to-end with HMAC-SHA256 (§7)

Devices are not required to enforce capability scoping themselves.
They MAY verify per-frame HMAC.

## 3. Manifest

A YAML document declaring the device's intent and event surface.

```yaml
dcp: 0.3                       # spec major.minor
device:
  id:     lamp-kitchen-01      # unique within deployment
  model:  smart_lamp_v1
  vendor: example.dev

intents:
  - name: set_brightness
    params:
      level: { type: float, unit: percent, range: [0, 100] }
      fade:  { type: duration, unit: ms, default: 0 }
    capability: lamp.write
    idempotent: true
    dry_run:    true

  - name: read_brightness
    returns: { type: float, unit: percent }
    capability: lamp.read

events:
  - name: motion_detected
    payload:
      confidence: { type: float, unit: ratio, range: [0, 1] }
    capability: lamp.read
```

### 3.1 Intent fields

| Field         | Required | Meaning |
|---|---|---|
| `name`        | yes | Stable identifier. `intent_id = crc16_ccitt(name)`. |
| `params`      | no  | Map of param name → spec. Absent means no parameters. |
| `returns`     | no  | If present, the intent is a read; absent intents are writes. |
| `capability`  | no  | A dotted scope string the caller must hold. |
| `idempotent`  | no, default `false` | Hint that retry is safe. |
| `dry_run`     | no, default `false` | The device accepts kind `0x81` and reports a predicted result. |

### 3.2 Param spec

```yaml
{ type: <type>, unit?: <unit>, range?: [lo, hi], default?: <value> }
```

`type` is one of:

| Type        | Meaning |
|---|---|
| `int`       | Signed integer; CBOR uint/sint major type. |
| `float`     | IEEE-754 double; CBOR float64. |
| `duration`  | Float, must declare a `unit` (typically `ms` or `s`). |
| `bool`      | CBOR true/false. |
| `string`    | UTF-8, ≤23 bytes in the v0.3 firmware CBOR subset. |

`unit` is a free-form string; recommended values:
`percent`, `ratio`, `ms`, `s`, `celsius`, `lux`, `degree`, `meter`.
Implementations MAY surface units to the LLM in the tool schema.

### 3.3 Intent IDs

```
intent_id = CRC-16/CCITT(name)      # poly 0x1021, init 0xFFFF
```

The same byte sequence in manifest and firmware produces the same id;
no separate registration is required.

## 4. Wire format

Every frame is six header bytes followed by an optional CBOR payload,
followed by an optional 16-byte truncated HMAC.

```
┌────────┬────────┬─────────┬──────────────┬────────────────┬──────────────┐
│ ver:u8 │ kind:u8│ seq:u16 │ intent_id:u16│ cbor map (opt) │ hmac16 (opt) │
└────────┴────────┴─────────┴──────────────┴────────────────┴──────────────┘
   ^                ^^^ big-endian ^^^                          16 bytes
```

| Field        | Encoding | Notes |
|---|---|---|
| `ver`        | u8       | MUST be `0x01` in v0.x. |
| `kind`       | u8       | See §4.1. |
| `seq`        | u16 BE   | Caller-chosen; echoed in the reply. |
| `intent_id`  | u16 BE   | CRC-16/CCITT of intent or event name. |
| CBOR payload | CBOR map | Absent body MUST be treated as an empty map `{}`. |
| HMAC         | 16 bytes | Truncated HMAC-SHA256 over `header || cbor`; presence is a deployment-wide configuration (§7). |

### 4.1 Kind

| Value  | Name         | Direction       | Carries |
|---|---|---|---|
| `0x01` | `call`       | host → device   | params |
| `0x02` | `reply`      | device → host   | return value or `{}` for write ack |
| `0x03` | `event`      | device → host   | payload, unsolicited |
| `0x04` | `error`      | device → host   | `{ "status": <int> }` per §4.2 |
| `0x81` | `dry-run`    | host → device   | identical layout to call; device MUST NOT cause side effects |

### 4.2 Status codes (in error replies)

The firmware sends errors with payload `{"status": <int>}` where `<int>` is
one of the numeric codes below. The Bridge translates the integer to the
canonical string before exposing it to MCP callers.

| Int | String                  | Meaning |
|---|---|---|
| 0   | `ok`                    | Reserved; never appears in an error frame. |
| 1   | `denied`                | Generic refusal (malformed body, unsupported kind). |
| 2   | `range`                 | Parameter outside declared range. |
| 3   | `busy`                  | Device cannot handle the call right now. |
| 4   | `unknown_intent`        | No handler registered for this `intent_id`. |
| 5   | `capability_required`   | Caller lacks the required capability. |

### 4.3 CBOR subset

Implementations MAY restrict to the subset DCP uses on-wire:

- Map (major 5) with ≤ 23 entries
- String key (major 3) ≤ 23 bytes
- uint / sint (major 0/1), float64 (`0xfb` + 8 B), bool (`0xf4`/`0xf5`)
- Short text string value (major 3) ≤ 23 bytes

The Python reference Bridge uses full `cbor2` and accepts arbitrary CBOR;
the firmware subset is enough for every example in `examples/`.

## 5. Transports

The same frame format runs over multiple byte channels.

| Transport       | Framing |
|---|---|
| UART / RS-485   | COBS + CRC-16/CCITT over the wire bytes, `0x00` as delimiter. Order: `COBS(frame || crc16) || 0x00`. |
| USB-CDC         | Identical to UART. |
| MQTT            | Topic prefix `dcp/<prefix>/c2d` (host→device) and `dcp/<prefix>/d2c` (device→host). Message payload IS the DCP frame. QoS 1 recommended. |
| BLE GATT        | One service, two characteristics. The c2d UUID and d2c UUID are derived from the service UUID by replacing the last byte with `0xc1` and `0xd1` respectively. Host writes c2d (write-with-response); device notifies d2c. |
| WebSocket       | One binary message per frame. |
| Loopback        | In-memory queue pair; for tests and simulators. |

The wire frame is identical across all transports; only the framing layer
changes.

## 6. Capability tokens

A token authorizes an LLM session to call intents that declare a matching
capability. Wire form (base64url, no padding):

```
<hdr_b64>.<sig_b64>

hdr = JSON({"caps": ["lamp.write", ...], "exp": <unix-ts>, "sub": "<session>"})
sig = HMAC-SHA256(secret, hdr_b64)[:16]
```

- Secrets MUST be ≥ 16 bytes of randomness; 32 bytes recommended.
- Tokens MUST carry an expiry.
- The Bridge verifies on every call; expired or invalid tokens are rejected
  with `capability_required`.

Token verification is **Bridge-side only** in v0.x. Devices trust their
Bridge.

## 7. Wire-level integrity (optional)

When the channel is shared physical media (RS-485 multidrop, public MQTT
broker), Bridge and device MAY share a *wire secret* and append/verify a
16-byte truncated HMAC-SHA256 over `header || cbor` on every frame.

There is no in-band marker indicating signing status. Both ends must agree
out of band. This is deliberate: an in-band downgrade bit would defeat the
purpose.

## 8. Conformance

An implementation conforms to v0.3 if and only if:

1. It can encode and decode every case in
   `tests/conformance/golden_frames.yaml`, modulo the documented
   encoding flexibility for empty bodies (either `0xa0` or absent).
2. It computes intent ids as CRC-16/CCITT(name) with init `0xFFFF`.
3. It treats absent body as empty map on decode.
4. It rejects frames with `ver ≠ 0x01`.
5. It enforces declared `range` and `capability` either at the Bridge,
   the device, or both.

The reference Python suite is `pytest tests/conformance/`. Any language
port should ship an equivalent.

## 9. Versioning

- `ver` (wire byte): incremented on incompatible frame-level change.
- `dcp:` (manifest field): semver-style; minor bumps are
  backward-compatible additions, major bumps may rename or remove fields.
- Implementations SHOULD reject frames with `ver` they do not understand.

## 10. Out of scope

The following are explicitly NOT part of v0.x:

- Mesh routing or multi-hop addressing (use Thread/Zigbee underneath)
- Multi-device atomic transactions
- Firmware over-the-air update
- Device discovery / commissioning beyond manifest distribution
- Mutual authentication of LLM ↔ Bridge (delegated to MCP host's session auth)
