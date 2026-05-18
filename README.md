# DCP — Device Context Protocol

[![tests](https://github.com/device-context-protocol/dcp/actions/workflows/test.yml/badge.svg)](https://github.com/device-context-protocol/dcp/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![spec: v0.3 draft](https://img.shields.io/badge/spec-v0.3%20draft-orange)](SPEC.md)

**Status:** Draft v0.3 — May 2026 · Hardware-validated on ESP32-WROOM-32

> A protocol that lets LLM agents safely control physical devices,
> down to dollar-class microcontrollers.
>
> Intent-level, transport-agnostic, capability-scoped. Compact wire format
> (sub-50-byte frames). Self-contained firmware under 16 KB.
>
> Complementary to [MCP](https://modelcontextprotocol.io) — a reference
> Bridge translates DCP ↔ MCP so any MCP host (Claude Desktop, Claude Code,
> IDE assistants) works zero-config.

## Contents

- [Why DCP?](#why-dcp)
- [Design principles](#design-principles)
- [Architecture](#architecture)
- [Quickstart](#quickstart)
- [Add a feature in 5 steps](docs/ADDING_FEATURES.md)
- [Wire format](#wire-format) · full [SPEC.md](SPEC.md)
- [Manifest](#manifest)
- [Roadmap](#roadmap)
- **Design rationale:** [docs/RATIONALE.md](docs/RATIONALE.md) — why
  not MCP-on-MCU, why not WoT, why not Matter.

## Why DCP?

MCP is excellent for SaaS tools, but assumes JSON-RPC over WebSocket and runtime
tool discovery. On an MCU with 32 KB of RAM, that's a non-starter.

DCP keeps MCP's mental model (manifest + tool calls) but:

- compiles to a compact CBOR wire format
- uses a static intent table (no runtime negotiation)
- moves safety enforcement to a Bridge process

A reference Bridge translates **DCP ↔ MCP**, so any MCP-compatible LLM works
out of the box. DCP is the last mile to physical hardware.

## Design principles

1. **Intent, not register.** `set_brightness(50%)`, not `write_pwm(pin=5, duty=128)`.
2. **Units in the protocol.** Every number declares a unit. No ambiguity.
3. **Static intent table.** Manifest known at compile time; runtime is pure binary.
4. **Safety lives in the Bridge.** Devices trust the Bridge; LLMs never see raw GPIO.
5. **Idempotent by default.** Non-idempotent intents must declare themselves.
6. **Transport-agnostic.** UART, BLE, MQTT, USB-CDC, WebSocket — one frame.

## Architecture

![DCP architecture](docs/paper/figures/arch.png)

```
LLM ── MCP ──▶ Bridge ── DCP wire ──▶ Device(s)
                 │
                 ├─ issues capability tokens
                 ├─ enforces rate limits, ranges
                 └─ logs, dry-runs, undo
```

The Bridge is the sole trust boundary. Devices remain simple enough to
fit on commodity microcontrollers; everything the LLM is allowed to do
is enforced before any byte traverses the device boundary.

## Validated on real hardware

As of v0.3 the reference firmware is **measured-validated on an
ESP32-WROOM-32 dev board** over CH340 USB-Serial at 115 200 baud:

- 10/10 round-trip tests pass (`tools/test_uart_roundtrip.py`)
- 88/88 Python unit & conformance tests pass
- Compiled firmware: 294 KB flash, 22.7 KB globals (Arduino-ESP32 core 3.3.8)
- The pure DCP layer is approximately 14 KB over a baseline empty
  sketch (measurement script in `docs/paper/figures/`)

See [docs/RATIONALE.md §7](docs/RATIONALE.md) for what the hardware
validation does and does not prove.

## Manifest

```yaml
dcp: 0.1
device:
  id:     lamp-kitchen-01
  model:  smart_lamp_v1
  vendor: example.dev

intents:
  - name: set_brightness
    params:
      level: { type: float, unit: percent, range: [0, 100] }
      fade:  { type: duration, unit: ms, default: 0 }
    capability: lamp.write
    idempotent: true
    dry_run: true

  - name: read_brightness
    returns: { type: float, unit: percent }
    capability: lamp.read

events:
  - name: motion_detected
    payload:
      confidence: { type: float, unit: ratio, range: [0, 1] }
    capability: lamp.read
```

`intent_id = crc16(name)` — manifests and firmware stay in sync without
coordination.

## Wire format

A single frame:

```
┌────────┬────────┬────────┬─────────────┬───────┐
│ ver:u8 │ kind:u8│ seq:u16│ intent_id:u16│ cbor  │
└────────┴────────┴────────┴─────────────┴───────┘
```

| field       | meaning                                                          |
|-------------|------------------------------------------------------------------|
| `ver`       | 1 for v0.1                                                       |
| `kind`      | 0x01 call · 0x02 reply · 0x03 event · 0x04 error · 0x81 dry-run |
| `seq`       | client-chosen, echoed in reply                                   |
| `intent_id` | CRC-16/CCITT of intent name                                      |
| `cbor`      | CBOR map: params / return / event payload / error                |

Reply status codes: `ok`, `denied`, `range`, `busy`, `unknown_intent`, `capability_required`.

## Adding a feature

See [docs/ADDING_FEATURES.md](docs/ADDING_FEATURES.md) for the full
5-step loop with a worked `blink(times, period)` example. The short
version: edit the manifest, add a C++ handler + binding, recompile,
flash, restart the MCP server — the LLM picks up the new tool
automatically. The Bridge needs no code change.

## Quickstart

```bash
pip install -e ".[mcp,serial,mqtt,ble,dev]"
python examples/lamp_demo.py              # in-process bridge ↔ fake lamp
pytest                                    # all tests
dcp inspect examples/lamp_manifest.yaml   # parsed manifest summary
dcp codegen examples/lamp_manifest.yaml -o /tmp/dcp_intents.h
```

### Run as an MCP server

The reference Bridge ships an MCP server that exposes each DCP intent as an
MCP tool. With ``--simulator`` it spins up an in-process fake device, so you
can demo with no hardware.

```bash
dcp serve examples/lamp_manifest.yaml --simulator               # no hardware
dcp serve examples/lamp_manifest.yaml --serial COM3             # real ESP32 over UART
dcp serve examples/lamp_manifest.yaml --mqtt broker.lan:1883 \  # MQTT
            --mqtt-prefix dcp/lamp-kitchen
dcp serve examples/lamp_manifest.yaml --ble AA:BB:CC:DD:EE:FF \ # BLE
            --ble-service 12345678-1234-5678-1234-567812345678
```

### Capability tokens (HMAC-SHA256)

For multi-tenant or scoped access, mint short-lived HMAC tokens and pass them
to the Bridge:

```bash
export DCP_SECRET=$(dcp token keygen)
dcp token mint --caps lamp.write,lamp.read --ttl 3600
# eyJjYXBzIjpb...sig
```

Tokens are verified by the Bridge on every call. The device sees only
already-authorized frames. Devices themselves do **not** verify signatures
in v0.2 — that requires on-device HMAC, which is on the roadmap.

To wire it into **Claude Desktop**, add this to your
``claude_desktop_config.json``:

```json
{
  "mcpServers": {
    "smart-lamp": {
      "command": "dcp",
      "args": [
        "serve",
        "C:/path/to/protocol/examples/lamp_manifest.yaml",
        "--simulator"
      ]
    }
  }
}
```

Then ask Claude *"set the lamp to 60% brightness"*. The call flow:

```
Claude ─MCP─▶ dcp serve ─Bridge─▶ Loopback ─DCP wire─▶ GenericSimulator
```

For production use, replace ``GenericSimulator`` with a real transport
(UART / MQTT / BLE — coming next).

## What's *not* in v0.1 (intentional)

- Multi-device transactions
- Firmware OTA
- Mesh routing
- LLM authentication (Bridge's problem)
- Capability token signing (stubbed — see `safety.py`)

## License

MIT.

## Roadmap

- [x] Wire format + manifest parser
- [x] Reference Python Bridge with loopback transport
- [x] Lamp example
- [x] MCP server wrapper + CLI (`dcp serve`)
- [x] Generic in-process device simulator
- [x] UART transport (COBS framing + CRC-16)
- [x] ESP32 reference firmware (Arduino-compatible C++)
- [x] Design rationale ([docs/RATIONALE.md](docs/RATIONALE.md))
- [x] CI (GitHub Actions, Linux + Windows, py 3.11–3.13)
- [x] MQTT transport
- [x] HMAC-SHA256 capability tokens (Bridge-side enforcement)
- [x] Manifest compiler: `dcp codegen` (YAML → C header)
- [x] Compile-time `DCP_ID(name)` macro in firmware
- [x] BLE GATT transport (bleak)
- [x] Release prep: CONTRIBUTING / CHANGELOG / CoC / SECURITY / issue templates
- [x] On-device HMAC verification (per-frame signatures, ESP32 firmware)
- [x] ESP32 BLE peripheral example (NimBLE-Arduino)
- [x] Conformance test suite (golden frames, language-neutral YAML)
- [x] Codegen `--stubs`: emits handler signatures + binding table
- [x] Quickstart video script ([docs/QUICKSTART_VIDEO.md](docs/QUICKSTART_VIDEO.md))
- [ ] Real-hardware UART validation (waiting on ESP32+CH340 board)
- [ ] Public launch under `device-context-protocol` GitHub org
