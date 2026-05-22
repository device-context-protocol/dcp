# Quickstart video — shot list & script

A 4-minute screencast that ends with Claude controlling a real ESP32 lamp.
The goal is "shows up in someone's Twitter feed and they immediately
understand what DCP is and want to try it."

## Frame at a glance

```
0:00–0:20  hook            screen: Claude controlling a desk lamp
0:20–0:55  the problem     screen: MCP works for SaaS, fails on MCUs
0:55–2:10  the solution    screen: manifest, Bridge, ESP32 sketch
2:10–3:30  live demo       screen: dcp serve, chat with Claude
3:30–4:00  call to action  screen: github.com/device-context-protocol
```

Total ≤ 4 minutes. Aim for 3:30.

## Hook (0:00 – 0:20)

**Cold open.** No logo, no title card. The lamp is on the desk. Voiceover
starts as the screen lights up.

> "Five minutes ago I asked Claude to set up a movie-night scene. This is
> what happened."

Cut to Claude Desktop. The chat shows:

```
You:  set up movie night

Claude calls tool: set_brightness({"level": 15, "fade": 2000})
Claude calls tool: set_color({"r": 255, "g": 150, "b": 0})
```

The desk lamp fades to warm orange. Pause one full second on the lamp.

## The problem (0:20 – 0:55)

Cut to a split screen.

**Left:** MCP architecture diagram — Claude → Server → SaaS APIs. Tools all
work. Caption: *MCP works great for SaaS tools.*

**Right:** Same diagram with the rightmost node replaced by an ESP32 photo.
A red ✗ overlays the connection. Caption: *MCP assumes JSON-RPC over
WebSocket. ESP32 has 320 KB of RAM. The math doesn't work.*

Voiceover:

> "MCP is brilliant for software tools — Slack, Jira, GitHub. But the protocol
> assumes JSON-RPC over WebSocket, and that's too heavy for the kind of
> hardware most physical devices ship on. Every 'Arduino MCP server' project
> on GitHub is either a $20 board acting as a $200 board, or a hand-rolled
> serial protocol with no schema."

## The solution (0:55 – 2:10)

Three-beat reveal. Hold each beat ~25 seconds.

### Beat 1: Manifest (0:55 – 1:20)

Open `examples/lamp_manifest.yaml` in an editor. Highlight one intent.

```yaml
- name: set_brightness
  params:
    level: { type: float, unit: percent, range: [0, 100] }
    fade:  { type: duration, unit: ms, default: 0 }
  capability: lamp.write
  idempotent: true
  dry_run: true
```

> "DCP starts with a manifest: a device-author-written list of *intents* —
> high-level actions, not register reads. Every parameter has a unit. Every
> intent declares whether it's safe to retry, and whether it supports a
> dry-run."

### Beat 2: Bridge (1:20 – 1:45)

Cut to `dcp serve` running in a terminal. Show the log lines as Claude calls
in. Caption: *The Bridge translates between MCP (the LLM's world) and DCP
(the device's world), and enforces every safety check before a byte hits
the wire.*

> "A small Python process — the Bridge — sits between Claude and the device.
> It speaks MCP to Claude, DCP to the device, and enforces every safety
> guarantee: ranges, capabilities, rate limits, dry-runs."

### Beat 3: Firmware (1:45 – 2:10)

Open `firmware/esp32/examples/lamp/lamp.ino`. Highlight one handler.

```cpp
dcp::Status handle_set_brightness(uint8_t kind, dcp::CborReader& p, ...) {
    double level = ...;
    ledcWrite(PWM_CHANNEL, (uint32_t)(level * 2.55f));
    return dcp::STATUS_OK;
}
```

> "And the device side is plain C++. CBOR map in, action out. The DCP
> layer is 27.6 KB of flash and under 1 KB of RAM on a $5 ESP32."

## Live demo (2:10 – 3:30)

**Don't cut anything here.** This is the trust-builder.

1. Show the lamp powered off. (2 sec)
2. In one terminal, run `dcp serve examples/lamp_manifest.yaml --serial COM3`. Show the "MCP ready" log line. (3 sec)
3. In Claude Desktop, open a new chat. (2 sec)
4. Type: *"Slowly fade the desk lamp from off to 80% over 3 seconds."*
5. Claude calls `set_brightness({"level": 80, "fade": 3000})`. The lamp obeys. **Hold for the full 3-second fade — do not cut.** (5 sec)
6. Type: *"Now make it warm white."*
7. Claude calls `set_color`. (3 sec)
8. Type: *"Read the current brightness."*
9. Claude calls `read_brightness`. Returns `{"value": 80.0}`. (3 sec)
10. Optionally: deliberately trigger a denied call. Type: *"Set the brightness to 5000."*. Claude calls `set_brightness({"level": 5000})`. Bridge rejects with `range`. Caption: *Safety is enforced even when the LLM hallucinates.* (8 sec)

## Call to action (3:30 – 4:00)

Title card. Three lines, large:

```
DCP — Device Context Protocol
github.com/device-context-protocol
MIT licensed · contributions welcome
```

Voiceover:

> "Open source, MIT, in the GitHub org link below. If you've got an ESP32
> in a drawer and a Claude subscription, you have everything you need to
> reproduce this in about ten minutes."

End on the lamp dimming gracefully to off.

## Production notes

- **Capture**: OBS at 1920×1080 / 60fps. Crop terminal to 110 cols × 30 rows.
- **Voice**: record after-the-fact in a quiet room, sync to gameplay. Don't
  improvise — use the script verbatim.
- **Music**: none for the demo segment (silence sells reality). A 5-second
  out-music sting under the CTA is fine.
- **Captions**: burn in for the diagrams. Don't caption the live demo — let
  the typing speak.
- **Length**: aim for 3:30. Anything over 4:00 stops getting watched.
- **First-frame**: must include the lamp. The thumbnail is the lamp.

## Edits we will not make

- No talking head.
- No "hi, I'm X." Start in medias res.
- No "let me explain the architecture". The diagram explains itself.
- No music under the live demo.
