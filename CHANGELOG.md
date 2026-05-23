# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/) once
it reaches 1.0. Pre-1.0 releases may break compatibility.

## [Unreleased]

## [0.3.1] - 2026-05-24

### Added

- **String parameter constraints** in the manifest: `pattern` (regex,
  `re.fullmatch`) and `max_length` for `type: string` params. Both
  optional and backward-compatible — absent constraints mean any
  string passes. Enforced at the Bridge in `dcp.safety.check_call`;
  violations raise `SafetyError("range", ...)` and surface as a
  `range` reply status on the wire. Caught by an empirical study
  (`tools/gen_llm_corpus.py` + `tools/bench_hallucination_empirical.py`)
  where 295 real LLM-emitted tool calls across two models exposed a
  prompt-injection gap that pre-v0.3.1 DCP couldn't close.

### Tools

- `tools/gen_llm_corpus.py` — drive an LLM (DeepSeek V3, Qwen2.5-72B
  via SiliconFlow) with adversarial prompts, capture the tool calls
  it emits.
- `tools/bench_hallucination_empirical.py` — feed the captured corpus
  through every protocol's host-side validator (DCP, Raw MCP,
  IoT-MCP, OpenAPI) and produce
  `docs/paper/figures/hallucination_data.json`.
- `tools/bench_latency_iotmcp.py` + `firmware/esp32/examples/iotmcp_echo`
  — apples-to-apples DCP-vs-IoT-MCP latency benchmark on the same
  ESP32-S3 hardware over the same UART. Result: 15.60 ms vs 15.59 ms
  median round-trip, within 5 µs of each other; capability scoping
  and full schema validation add no measurable cost.

### Fixed

- `examples/smart_panel_manifest.yaml` declared `play_tone`'s
  `duration` as `type: duration`, which `safety._coerce` converts to
  a Python `float` and Bridge serializes as CBOR float64; the device
  firmware reads it with `CborReader::read_int()` and rejected every
  call. Now declared as `type: int` (the underlying unit, `ms`, is
  naturally integer). The four other example manifests still use
  `type: duration` and will need the same treatment if they exercise
  the path.
- LILYGO T-Panel S3 bring-up: `firmware/esp32/examples/smart_panel`
  now uses GPIO 38 for the buzzer instead of GPIO 19 (which is
  ESP32-S3 USB D-, and pin-moding it to OUTPUT killed the native
  USB-CDC after the first flash). Wire clock dropped from 800 kHz
  to 400 kHz to stay inside the XL9535 GPIO expander's I2C max.
  `TouchLib`'s CST3240 chip-model define added.

## [0.3.0] - 2026-05-18

### Added

- **Wire-level HMAC-SHA256** (`Frame.encode(wire_secret=...)` / `decode(...)`):
  optional 16-byte truncated signature appended to every frame. Both Bridge
  and device must agree; no in-band downgrade marker by design.
- **Self-contained SHA-256 + HMAC-SHA256** in the ESP32 firmware
  (`DCPCrypto.h`/`.cpp`) — no mbedtls/ESP-IDF dependency.
- **DCPBle**: ESP32 BLE peripheral via NimBLE-Arduino. Same intent table as
  `DCP`; one service, c2d/d2c characteristics derived from service UUID by
  convention (`0xC1` / `0xD1` last byte).
- **Conformance suite**: `tests/conformance/golden_frames.yaml` + Python
  runner. Language-neutral; ports can write equivalent runners.
- **Codegen `--stubs`**: emits handler-function signatures and a
  `DCP_BINDINGS[]` table so the firmware author only writes business logic.
- **Quickstart video script** at `docs/QUICKSTART_VIDEO.md`.

### Changed

- `Bridge` constructor takes `wire_secret=` for per-frame signing.

### Fixed

- **Footprint numbers corrected to measured values.** Earlier docs
  claimed the DCP layer was "~14 KB" of flash and cited a `<16 KB`
  design target. A reproducible measurement
  (`docs/paper/figures/measure_footprint.py`, differencing the lamp
  example against an empty Arduino sketch) shows the DCP layer is
  **27.6 KB of flash and 0.6 KB of RAM** on ESP32. The flash figure is
  above the original `<16 KB` target — the target predated the
  on-device HMAC-SHA256 path — and is now reported as measured across
  the README, paper, and firmware docs. The RAM figure (0.6 KB) came in
  well under target.
- **Latency figure is now measured**, not illustrative
  (`tools/bench_latency.py`, 1000 round-trips per transport).

## [0.2.0] - 2026-05-12

### Added

- **HMAC-SHA256 capability tokens** (`dcp.tokens`): mint, verify, expiry.
  Bridge accepts `token=` + `secret=` at construction and enforces capabilities
  from the token on every call.
- **MQTT transport** (`dcp.transports.mqtt`): `dcp/{prefix}/{c2d,d2c}` topic
  convention, QoS 1, paho-mqtt 2.x callback API.
- **BLE GATT transport** (`dcp.transports.ble`): one service, c2d/d2c
  characteristics derived from service UUID by convention.
- **YAML → C header codegen** (`dcp codegen`): generates intent IDs, event
  IDs, capability constants, and a manifest hash.
- **Compile-time `DCP_ID(name)` macro** in firmware (C++14 constexpr CRC-16),
  removing the runtime `intent_id()` call from `setup()`.
- **CLI subcommands**: `dcp codegen`, `dcp token mint`, `dcp token keygen`.
- **CLI flags on `dcp serve`**: `--mqtt HOST[:PORT]`, `--mqtt-prefix`,
  `--ble ADDRESS`, `--ble-service UUID`.
- Smarter `GenericSimulator`: read intents named `read_X` / `get_X` return
  the last value written by `set_X`.

### Changed

- `Bridge` constructor now optionally takes `token=` and `secret=`.
- README quickstart updated to install all extras by default.

## [0.1.0] - 2026-05-12

### Added

- Wire format: 6-byte header + CBOR payload, CRC-16/CCITT intent IDs.
- Manifest parser (YAML → dataclasses) with units, ranges, capability strings.
- Safety layer: range checks, type coercion, capability gating.
- Bridge orchestrator with async call/reply, event subscription, dry-run.
- Transports: `LoopbackTransport` (in-memory), `UartTransport` (COBS + CRC-16
  over pyserial-asyncio).
- `GenericSimulator` for hardware-free demos.
- MCP server wrapper (`dcp serve --simulator | --serial`) exposing each
  intent as an MCP tool.
- `dcp` CLI with `serve` and `inspect` subcommands.
- ESP32 reference firmware (Arduino-compatible C++): tiny CBOR subset, COBS
  framing, CRC-16, intent dispatch, dry-run support. Target <16 KB flash.
- Smart-lamp example: manifest, Python demo, ESP32 sketch.
- Design rationale doc (`docs/RATIONALE.md`) covering MCP / WoT / Matter /
  Sparkplug B / OpenAPI comparisons.
- GitHub Actions CI: Linux + Windows × Python 3.11–3.13, pytest + ruff.

[Unreleased]: https://github.com/device-context-protocol/dcp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/device-context-protocol/dcp/releases/tag/v0.2.0
[0.1.0]: https://github.com/device-context-protocol/dcp/releases/tag/v0.1.0
