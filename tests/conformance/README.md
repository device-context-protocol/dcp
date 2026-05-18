# DCP Conformance Suite

A language-neutral set of golden-frame tests. Any DCP implementation should
be able to load `golden_frames.yaml` and verify that:

1. **Encode**: building a frame with the given fields produces the listed
   `wire_hex`.
2. **Decode**: parsing the `wire_hex` reproduces the listed fields.
3. **Framing**: when `uart_wire_hex` is present, COBS+CRC encoding of the
   frame produces those bytes; decoding them recovers the frame.
4. **CRC**: `crc16` is the CRC-16/CCITT of the named bytes.

The Python reference test runner is in `test_conformance.py` and can serve
as a template for ports.

## File schema

```yaml
- name: "human-readable test name"
  kind: 0x01           # required: see Kind enum
  seq: 42              # required
  intent: "set_brightness"   # required: source string for the intent_id
  payload:             # required: CBOR map contents
    level: 50.0
  wire_hex: "01 01 ..."        # required: full DCP frame (header + cbor)
  uart_wire_hex: "0a 01 ..."   # optional: COBS-wrapped on-the-wire bytes (no trailing 0x00)
  crc16: 0x29b1                # optional: CRC-16 of wire_hex bytes
```

Whitespace in hex is allowed and ignored. Hex is lowercase.

## Adding a new test

1. Pick a single concrete frame shape (call, reply, event, dry-run, error).
2. Compute `wire_hex` from a known-good implementation.
3. Where the spec is silent, prefer the simplest possible CBOR encoding (no
   indefinite-length, no tags).

If your implementation disagrees with a golden frame, **the golden is the
specification**, not the other way around. Open an issue rather than
patching the YAML quietly.
