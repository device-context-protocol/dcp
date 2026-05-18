# Why DCP?

A short tour through the design space, the prior art we deliberately looked at,
and the choices DCP made. If you're going to disagree with us, please disagree
with the version below — not a strawman.

## The gap we are filling

The MCP ecosystem is exploding for SaaS tools: file systems, databases, ticket
trackers. **What it does not have, in any serious form, is a hardware story.**
Every "Arduino MCP server" or "ESP32 MCP server" project we surveyed in 2026
takes one of two shapes:

1. **MCU as MCP server**: JSON-RPC over WebSocket, running on a 240 MHz dual-core
   ESP32 with 320 KB of RAM. Works, but wastes 80% of the device on parsing
   `"jsonrpc":"2.0"`. Excludes every cheaper microcontroller.
2. **PC-side MCP server with serial passthrough**: an ad-hoc, project-specific
   text protocol over UART, with no schema, no safety model, no manifest. Each
   author reinvents framing.

DCP is the second shape, **standardized**: a compact wire format, a manifest,
and a safety boundary. We are not trying to replace MCP — we ship a Bridge
that translates DCP into MCP so any MCP host (Claude Desktop, IDEs) works
out of the box.

## Why not just use MCP on the device?

| Property | MCP | DCP |
|---|---|---|
| Encoding | JSON-RPC 2.0 (text) | CBOR over fixed-width header |
| Discovery | Runtime via `tools/list` | Static manifest, compile-time |
| Transport | WebSocket / stdio | Any byte stream (UART, MQTT, BLE, USB-CDC) |
| Smallest viable device | ~MB-class (Cortex-A or large Cortex-M) | ~kB-class (Cortex-M0+, AVR) |
| Safety model | Tool description, host-side enforcement | Capability tokens, Bridge-enforced |
| Trust boundary | Server | Bridge (separate from device) |

The decisive numbers are RAM and code size. A minimal MCP-over-WebSocket
implementation on ESP32 lands around 80–120 KB of code and tens of KB of
working RAM. DCP's reference firmware targets <16 KB of flash and <2 KB of
RAM. **That difference is the difference between every IoT device and only
the expensive ones.**

## Why not W3C Web of Things (WoT)?

WoT is the closest prior art and the one we studied hardest.

**What WoT gets right and we copied:**

- The Property / Action / Event triad. DCP's intents + events follow this
  shape almost exactly.
- The idea of a Thing Description (TD) as the source of truth.
- Affordances over registers — the same insight that drives our "intent, not
  register" rule.

**Why we did not adopt WoT directly:**

- **TDs are JSON-LD with optional SHACL validation.** That's the right call
  for browser-side semantic interop; it is the wrong call for an MCU.
- **No canonical wire format.** WoT operations bind to HTTP, CoAP, MQTT and
  others through Forms. Useful flexibility, but it pushes every implementer
  into protocol-design decisions DCP wants to remove.
- **No first-class safety model.** WoT has security schemes (basic, bearer,
  PSK) but no capability-scoping mechanism — and certainly not one designed
  for an LLM that might hallucinate a command.

A future version of DCP will likely add a WoT Thing Description importer.
Treating WoT as an interchange format and DCP as the runtime is consistent.

## Why not Matter?

Matter solves a different problem extremely well: **multi-vendor smart-home
device interop with end-to-end security**. We're not trying to be Matter.

What we deliberately did not take from Matter:

- **Cluster model with central data store.** Matter prescribes that, e.g., a
  light's brightness lives at attribute `0x06:0x0000:0x0000`. Beautiful for
  appliance categories that already exist; useless for custom hardware.
- **BDX, fabric onboarding, OTA transport.** Useful, but a 200-page spec
  worth of useful. DCP punts: use vendor tooling for OTA, use Thread/Zigbee
  underneath if you need a mesh.
- **TLV encoding.** Matter's TLV is comparable to CBOR in size but tightly
  coupled to Matter's type system. CBOR is more widely tooled.

The right way to think about it: Matter is a vertically integrated standard
for the smart-home category; DCP is an LLM-native interface for any device
whose authors didn't sign up to ship a Matter stack.

## Why not Sparkplug B (or MQTT-only)?

Sparkplug B is the closest thing the industrial IoT world has to a state
discipline. We took two ideas:

- **Birth / death messages** for online presence. We will add a `birth` and
  `death` event convention in v0.2.
- **Compact payloads.** Sparkplug B uses Protobuf; we use CBOR for tooling
  reasons but the spirit is the same.

What we deliberately rejected:

- **MQTT-required.** Sparkplug B is MQTT-only. DCP is transport-agnostic
  because a battery-powered sensor on BLE GATT or a CNC over RS-485 doesn't
  want an MQTT broker in the loop.
- **A schema fixed by Sparkplug.** Our manifest is open-ended; per-device
  intents are first class.

## Why not just OpenAPI + HTTP?

This is the most tempting "do nothing" alternative. For a Raspberry Pi-class
device with networking, OpenAPI works fine and we recommend it for that case.

DCP differs in three ways that matter for smaller devices and LLM safety:

1. **Wire size.** Even a small HTTP request burns hundreds of bytes on headers
   alone. DCP's call frame is typically 10–40 bytes total.
2. **Capability scoping.** OpenAPI has no native concept; you bolt OAuth on,
   and OAuth's session model wasn't designed for "this LLM session can
   dim lamps but not unlock doors."
3. **Dry-run as a first-class primitive.** OpenAPI can model it with a
   convention; DCP makes it a wire-format bit.

If you have a device that's already on the network and can run a small HTTP
server, **OpenAPI is fine**. DCP becomes worth it when the device is on a
serial bus, when you have many devices behind one Bridge, or when you want
the Bridge's safety guarantees regardless.

## Core design choices, justified

### 1. Intent, not register

`set_brightness(level: percent)`, not `write_pwm(pin=5, duty=128)`.

The LLM should not be inventing duty cycles. It should be choosing actions
in a space the device author has already declared safe. Register-level access
guarantees that an LLM with a confused world model will, sooner or later,
brick a device. Intent-level access guarantees only that the LLM might
*request* something silly — and the Bridge can reject it.

### 2. Units in the protocol

Every numeric parameter declares a unit (`percent`, `ms`, `celsius`, `lux`).
We have seen too many LLM-controlled-device demos where the model confidently
sent `set_temperature(72)` to a device expecting Celsius. We pay the manifest
verbosity cost on purpose.

### 3. Static intent table

Discovery at runtime is the natural choice for SaaS tools where the universe
of tools changes daily. For a device, the intent table is fixed at firmware
compile time. Making discovery static buys us:

- A 16-bit intent_id field on the wire (CRC-16 of the name)
- Zero RAM cost for a `tools/list` response
- Type-checked dispatch in the firmware

The cost is that adding an intent requires a firmware update *and* a new
manifest. We think that's correct: the intent table is part of the device's
contract with the world.

### 4. Safety lives in the Bridge

The device does range-check what it must. The Bridge does range-check what it
*should*, plus capability scoping, rate limiting, dry-run prediction, audit
logging, and rollback. **The MCU is not a security boundary; the Bridge is.**

This frees devices to be cheap and dumb, which is the only way DCP scales
down to the long tail of hardware.

### 5. CBOR over a fixed-width header

We did consider Protobuf (zero-copy on host, but generates a non-trivial
amount of MCU code), MessagePack (very close to CBOR, slightly less standard),
and plain bit-packed structs (smallest, but no flexibility for future fields).

CBOR is RFC 8949, widely tooled, has a 100-line MCU decoder, and was already
adopted by CoAP. It was the boring choice.

### 6. The Bridge is the only thing the LLM talks to

The LLM never sees a real device. It sees an MCP server backed by a Bridge.
This is the same architectural pattern that makes Claude Desktop tolerable to
operate: the host is a known quantity, the tools are signed off by the user,
and the LLM's reach is bounded by what the host exposes.

Pushing this same pattern down to hardware preserves the property that
**any LLM bug is, at worst, a Bridge bug**.

## Open questions

These are things we have not yet decided. Pull requests welcome.

- **Capability tokens.** Ed25519 with short TTL is the obvious choice, but it
  costs ~3 KB of code on MCUs without crypto acceleration. HMAC-SHA256 is the
  practical fallback. We will likely ship both.
- **Versioning policy.** Wire version is a byte; we have 255 unused values.
  But what about manifest schema evolution? Probably semver, but the
  compatibility rules need spelling out.
- **Mesh / multi-hop.** Out of scope for v0.1. The right answer is probably
  "use Thread or Zigbee underneath" — but we want to be sure DCP composes
  cleanly with those.
- **Subscriptions vs polling.** Events are unsolicited from device → Bridge.
  Should the Bridge offer LLM-side subscription filtering, or always fan out?

## What would change our minds

We will reconsider parts of this design if:

- The official MCP spec adds a binary transport binding with a small enough
  MCU footprint. (We don't expect this — MCP's design center is host-side
  tools, not embedded — but we'd happily fold in.)
- W3C WoT publishes a TD-to-CBOR canonicalization that fits in <8 KB of
  MCU code. At that point the gap between DCP and WoT closes.
- A Matter Working Group profile for "custom devices, no cluster required"
  ships and gets traction.

Otherwise: DCP is the bet that LLMs should be able to safely command physical
hardware that costs less than a smartphone — and that the protocol to do
that doesn't exist yet.
