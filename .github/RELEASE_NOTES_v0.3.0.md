# DCP v0.3.0 — hardware-validated draft

**The first release where every line of the protocol stack — Python Bridge,
ESP32 firmware, conformance suite — runs end-to-end on a real
$5 microcontroller, with an LLM at the other end of the wire.**

This is a *draft* release: the spec is stable for v0.x but unsigned, the
hardware matrix is still single-MCU, and the empirical safety study is
future work (see `docs/RATIONALE.md §7` and `docs/paper/main.tex §7`).

## Headline numbers

- **88 / 88** Python unit and conformance tests pass
- **10 / 10** round-trip tests pass against ESP32-WROOM-32 (CH340, 115 200 baud)
- **Frame size:** 19 bytes for a typical `set_brightness(50)` call;
  35 bytes with the optional HMAC tail
- **Firmware footprint:** the DCP layer measures 27.6 KB flash and
  0.6 KB RAM over an empty Arduino sketch (measured)
- **Five transports** ship: loopback, UART (COBS + CRC-16), MQTT,
  BLE GATT, in-process simulator. Plus the MCP server wrapper that
  surfaces every intent to any MCP host

## What's in this release

### Wire & protocol
- v0.3 spec at [SPEC.md](../../SPEC.md): 6-byte header + CBOR map +
  optional 16-byte HMAC-SHA256, with all five status codes and the
  manifest schema documented normatively.
- Language-neutral [conformance suite](../../tests/conformance/) (golden
  YAML + Python runner).

### Reference implementations
- **Python Bridge** (asyncio): manifest loader, range/type/capability
  enforcement, dry-run wire bit, HMAC-SHA256 capability tokens, wire-level
  HMAC.
- **MCP server wrapper**: every manifest intent → MCP tool, zero code
  per device.
- **ESP32 firmware** (Arduino-compatible C++): hand-rolled CBOR subset,
  self-contained SHA-256 (no mbedTLS dep), COBS framing, constexpr
  `DCP_ID(name)` macro for compile-time intent IDs. Also includes BLE
  GATT peripheral via NimBLE-Arduino.

### Developer experience
- [`dcp` CLI](../../README.md): `serve / inspect / codegen / token`.
- [`docs/ADDING_FEATURES.md`](../../docs/ADDING_FEATURES.md): the
  5-step loop to add a new intent (manifest → handler → test → flash →
  LLM picks it up).
- [`tools/test_uart_roundtrip.py`](../../tools/test_uart_roundtrip.py):
  hardware integration harness.

### Docs & design
- [`docs/RATIONALE.md`](../../docs/RATIONALE.md): why not MCP-on-MCU,
  why not WoT, why not Matter, why not Sparkplug B, why not OpenAPI.
- [`docs/paper/main.tex`](../../docs/paper/main.tex): position paper
  with figures, ready for arXiv submission.
- [`docs/site/`](../../docs/site/): Vue 3 + Vite 7 + Tailwind v4 landing.

### Release prep
- MIT, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, issue / PR templates,
  GitHub Actions CI (Linux + Windows × Python 3.11 / 3.12 / 3.13).

## Honest caveats

- Only one MCU validated so far (ESP32-WROOM-32). Cortex-M0+ port is
  v0.4's headline.
- No measured A/B against IoT-MCP — that's the follow-up paper.
- Spec is **draft**: a v1.0 freeze is gated on a second-implementer
  port (we're hoping for community C or Rust).
- Wire-level HMAC has no in-band marker — deliberate, but means
  configuration discipline matters. See `SPEC.md §7`.

## Try it in five minutes

```bash
pip install -e ".[mcp,serial,dev]"        # all extras: ,mqtt,ble for those
dcp inspect examples/lamp_manifest.yaml
dcp serve   examples/lamp_manifest.yaml --simulator
# in another shell, point any MCP host at the simulator
```

For real hardware, see [`firmware/esp32/README.md`](../../firmware/esp32/README.md).

## Thanks

To the IoT-MCP team (Yang et al., arXiv:2510.01260) for proving the
direction; to the W3C WoT working group for the description-layer
prior art; and to the MCP team at Anthropic for the upstream we extend.
