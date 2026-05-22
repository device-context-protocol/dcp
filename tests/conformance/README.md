# DCP Conformance Suite

A language-neutral set of golden-frame tests. Any DCP implementation should
be able to load `golden_frames.yaml` and verify that:

1. **Encode**: building a frame with the given fields produces the listed
   header plus `cbor_hex`.
2. **Decode**: parsing the frame bytes derived from the header and `cbor_hex`
   reproduces the listed fields.
3. **Framing**: when `uart_wire_hex` is present, COBS+CRC encoding of the
   frame produces those bytes; decoding them recovers the frame.
4. **CRC**: when `crc16` is present, it is the CRC-16/CCITT of the frame
   bytes before UART wrapping.

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
  cbor_hex: "a1 65 ..."        # required: CBOR body bytes only
  uart_wire_hex: "0a 01 ..."   # optional: COBS-wrapped frame+CRC, no trailing 0x00
  crc16: 0x29b1                # optional: CRC-16 of full frame bytes
```

Whitespace in hex is allowed and ignored. Hex is lowercase.

## Adding a new test

1. Pick a single concrete frame shape (call, reply, event, dry-run, error).
2. Compute `cbor_hex` from a known-good implementation.
3. Include `uart_wire_hex` and `crc16` when you want to pin framing and CRC
   behavior for that case.
4. Where the spec is silent, prefer the simplest possible CBOR encoding (no
   indefinite-length, no tags).

If your implementation disagrees with a golden frame, **the golden is the
specification**, not the other way around. Open an issue rather than
patching the YAML quietly.
