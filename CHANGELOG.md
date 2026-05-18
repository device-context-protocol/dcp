# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/) once
it reaches 1.0. Pre-1.0 releases may break compatibility.

## [Unreleased]

### Added

- **Wire-level HMAC-SHA256** (`Frame.encode(wire_secret=...)` / `decode(...)`):
  optional 16-byte truncated signature appended to every frame. Both Bridge
  and device must agree; no in-band downgrade marker by design.
- **Self-contained SHA-256 + HMAC-SHA256** in the ESP32 firmware
  (`DCPCrypto.h`/`.cpp`) — no mbedtls/ESP-IDF dependency, ~1 KB of code.
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
