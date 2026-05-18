# Adding a new intent to your DCP device

The complete loop for "I want the LLM to be able to do X":

1. **Declare** the intent in the manifest
2. **Implement** the handler in firmware
3. **Test** with the round-trip script
4. **Re-flash**
5. **LLM picks it up automatically** — the Bridge re-reads the manifest

The Bridge and MCP server require no code change. The manifest is the
single source of truth: change it, regenerate optional artifacts, the LLM
sees the new tool. This document walks through a complete worked example
adding a `blink(times, period)` intent to the lamp.

---

## Step 1 — Manifest

Edit `examples/lamp_manifest.yaml`. Append to `intents:`:

```yaml
- name: blink
  params:
    times:  { type: int,      range: [1, 100],   default: 3 }
    period: { type: duration, unit: ms,
              range: [50, 5000], default: 200 }
  capability: lamp.write
  idempotent: false       # calling twice blinks twice
  dry_run:    true        # the LLM can ask "what would this do?"
```

What each field buys you, automatically:

- `range` → the Bridge rejects out-of-range calls before they reach the wire
- `default` → omitting the parameter in the LLM call uses the default
- `unit` → the LLM sees `unit: ms` in the tool schema and stops sending seconds
- `capability` → callers must hold `lamp.write` (token-gated)
- `dry_run: true` → the LLM gets a `__dry_run__` boolean parameter for free
- `idempotent: false` → the LLM is hinted that retries are unsafe

That's it for declaration. The Bridge will load this on next start and
expose a tool named `blink` to the LLM, with a full JSON Schema generated
from the param table.

---

## Step 2 — Firmware handler

Edit `firmware/esp32/examples/lamp/lamp.ino`. Add the handler:

```cpp
static dcp::Status handle_blink(uint8_t kind,
                                dcp::CborReader& params,
                                dcp::CborMap& reply,
                                void*) {
    int64_t times    = 3;       // defaults match the manifest
    double  period   = 200.0;

    // Parse CBOR params. Keys arrive in the order the caller sent them.
    while (params.remaining() > 0) {
        const char* key; size_t key_len;
        if (!params.next_key(&key, &key_len)) return dcp::STATUS_DENIED;
        if (key_len == 5 && memcmp(key, "times",  5) == 0) {
            if (!params.read_int(&times))    return dcp::STATUS_RANGE;
        } else if (key_len == 6 && memcmp(key, "period", 6) == 0) {
            if (!params.read_float(&period)) return dcp::STATUS_RANGE;
        } else {
            params.skip();          // forward-compat with new manifest fields
        }
    }

    // Belt-and-suspenders: re-check ranges. The Bridge already did this,
    // but defending here means a misbehaving Bridge can't drive the LED
    // outside the safe envelope.
    if (times < 1   || times  > 100)  return dcp::STATUS_RANGE;
    if (period < 50 || period > 5000) return dcp::STATUS_RANGE;

    // Dry-run: report what we would do, no side effects.
    if (kind == dcp::KIND_DRY_RUN) {
        reply.add_int("would_blink", times);
        reply.add_int("at_period_ms", (int64_t)period);
        return dcp::STATUS_OK;
    }

    // Actually blink. Restore the previous brightness when done.
    uint32_t saved = (uint32_t)(g_brightness * 2.55f);
    uint32_t half  = (uint32_t)(period / 2.0);
    for (int i = 0; i < times; ++i) {
        ledcWrite(LED_PIN, 255); delay(half);
        ledcWrite(LED_PIN, 0);   delay(half);
    }
    ledcWrite(LED_PIN, saved);

    return dcp::STATUS_OK;
}
```

Register it in the binding table — the array right above `setup()`:

```cpp
static dcp::IntentBinding bindings[] = {
    { DCP_ID("set_brightness"),  handle_set_brightness,  nullptr },
    { DCP_ID("set_color"),       handle_set_color,       nullptr },
    { DCP_ID("read_brightness"), handle_read_brightness, nullptr },
    { DCP_ID("blink"),           handle_blink,           nullptr },   // ← added
};
```

`DCP_ID("blink")` is a `constexpr` — the CRC-16 of the string is computed
at compile time and matched against the wire `intent_id`. Same string in
manifest and firmware means same id. No code generation step required.

---

## Step 3 — Test the new intent

Append a few cases to `tools/test_uart_roundtrip.py`'s `tests` list:

```python
("blink 3x default",       "blink", {"times": 3, "period": 200}, False, "ok"),
("blink dry-run 5x",       "blink", {"times": 5},                True,  "ok"),
("blink times out of range","blink",{"times": 9999},             False, "range"),
("blink with only defaults","blink", None,                       False, "ok"),
```

The third case verifies the **Bridge** rejects bad input before any byte
reaches the wire (status comes back as `range` from Python, not from the
firmware). The fourth case verifies defaults work end-to-end: the LLM
can just say `blink()` and get 3 blinks at 200ms.

---

## Step 4 — Compile & flash

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32 firmware\esp32\examples\lamp\lamp.ino
arduino-cli upload  --port COM5 --fqbn esp32:esp32:esp32 firmware\esp32\examples\lamp\lamp.ino
```

Then re-run the round-trip test — all rows should be `[OK]`. You should
see the LED actually blink during the "blink 3x default" row.

---

## Step 5 — The LLM gets it for free

Restart any LLM client that has the `dcp-lamp` MCP server connected
(Claude Code, Claude Desktop, etc). On the next conversation the new
tool is automatically listed:

```
blink(times: int = 3, period: number = 200, __dry_run__: bool = false)
   DCP intent: blink · capability: lamp.write
```

Ask the LLM *"flash the lamp 5 times quickly"* — it'll call
`blink({times: 5, period: 100})` and the LED will obey.

---

## Patterns by intent type

### Read intent (sensor)

```yaml
- name: read_temperature
  returns: { type: float, unit: celsius }
  capability: lamp.read
```

```cpp
static dcp::Status handle_read_temperature(uint8_t,
                                           dcp::CborReader&,
                                           dcp::CborMap& reply,
                                           void*) {
    double t_celsius = temperatureRead();  // ESP32 internal sensor
    reply.add_float("value", t_celsius);
    return dcp::STATUS_OK;
}
```

Single returned value, always shape `{"value": ...}`.

### Enum-style param

CBOR has no native enum; pass a string and validate. The manifest hints
with a description (DCP v0.1 doesn't yet have an `enum:` schema field —
roadmap):

```yaml
- name: set_mode
  params:
    mode: { type: string, default: "normal" }    # one of: normal, reading, sleep, movie
  capability: lamp.write
  idempotent: true
```

```cpp
const char* mode_str; size_t mode_len;
if (!params.read_string(&mode_str, &mode_len)) return dcp::STATUS_RANGE;
if (mode_len == 6 && memcmp(mode_str, "normal", 6) == 0)      { /* ... */ }
else if (mode_len == 7 && memcmp(mode_str, "reading", 7) == 0) { /* ... */ }
// etc.
else return dcp::STATUS_RANGE;
```

### Event (unsolicited push)

```yaml
events:
  - name: motion_detected
    payload:
      confidence: { type: float, unit: ratio, range: [0, 1] }
    capability: lamp.read
```

```cpp
// In loop(), when your sensor fires:
uint8_t buf[32];
dcp::CborMap m(buf, sizeof(buf));
m.begin();
m.add_float("confidence", 0.94);
dcp_instance->send_event("motion_detected", m);
```

The Bridge fans this out to any LLM session subscribed to `lamp.read`.

---

## Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `denied` with empty data from device | error reply buffer too small in firmware | bump the `uint8_t buf[N]` in your handler |
| `unknown_intent` for an intent you swore is in the manifest | spelling mismatch — `DCP_ID("foo")` vs manifest `name: Foo` | strings are byte-exact; rename one to match |
| LLM keeps sending out-of-range values | you forgot `range:` in the manifest | add it; the Bridge picks it up after restart |
| Long handler causes `busy` from the Bridge | `delay()` exceeded the Bridge timeout (default 2s) | shorten, or run async via FreeRTOS task and ack-then-event |
| `set_color` works but no light changes | you don't have an RGB LED wired up | that's by design — the example saves state and flashes the brightness LED to acknowledge |
| Capability check fails with `capability_required` | the LLM session's token doesn't include that capability | re-issue a token: `dcp token mint --caps lamp.write,lamp.read,...` |

---

## What the loop doesn't ask you to touch

The Python Bridge, the MCP server wrapper, the CLI, and the conformance
suite all work off the manifest. **You never edit Bridge code to add an
intent.** That's the protocol's load-bearing property: device authors
own the manifest + firmware; the Bridge is generic.

If you ever find yourself patching the Bridge for a specific device,
you've probably encoded device-specific knowledge in the wrong layer.
Move it to the manifest schema first, then the Bridge change.
