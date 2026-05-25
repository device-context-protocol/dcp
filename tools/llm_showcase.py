"""DCP showcase — LLM-orchestrated multi-scene demo for the paper/README.

Runs a sequence of scenes. Each scene is a single LLM turn with a focused
brief; the LLM plans the tool calls; the bridge executes them on the
T-Panel; pixels (and the buzzer) react in real time. Between scenes, brief
pauses so a phone camera can catch the transition.

Scenes:
  1. Title card        — 4 lines of intro text + swatch sweep
  2. Colorscape        — three colors with matching mood labels
  3. Musical fanfare   — play 4-5 notes via play_tone, captioning each one
  4. Capability gate   — LLM tries move_motor; firmware rejects with denied
                          (shows DCP's safety gating, even against the LLM)
  5. Closing card      — clear, summary, final color

Usage:
    python tools/llm_showcase.py            # COM6 default
    python tools/llm_showcase.py COM5
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dcp.bridge import Bridge
from dcp.manifest import Manifest
from dcp.transports.uart import UartTransport

SILICONFLOW_KEY = "sk-ykonfzvoicczdkbinhggechwuterhefnxahszmmrzeikkszv"
SILICONFLOW_URL = "https://api.siliconflow.cn/v1/chat/completions"
MODEL           = "deepseek-ai/DeepSeek-V3"

# Which DCP capabilities the LLM is granted. Anything outside this set
# returns "denied" at the bridge or "denied" at the device — the LLM
# learns about that the hard way in scene 4.
GRANTED_CAPS = {"panel.write", "panel.read"}

# Scenes: (title, brief). The LLM gets the brief plus context that it
# is mid-demo (so it doesn't preface every turn).
SCENES: list[tuple[str, str]] = [
    ("Title card",
     "We are opening a live demo. Use display_text to put exactly these "
     "four lines on the panel: line 0 'Device Context', line 1 'Protocol "
     "(DCP)', line 2 'live demo on', line 3 'LilyGo T-Panel'. Then set "
     "the swatch to a calm deep blue (e.g. r=20 g=60 b=180). Don't add "
     "extra fluff text in your final reply — just confirm 'title shown'."),

    ("Colorscape",
     "Clear the screen. Then for three moods — energy, calm, growth — "
     "in sequence: display one short mood word on line 1, set the swatch "
     "to a color that matches that mood, and pause logically between "
     "moods (by issuing the next display_text and set_color). Use lines "
     "0 and 2 to show the mood index ('Mood 1 of 3', etc). End with the "
     "growth mood (green-ish) on screen. Final reply: 'colorscape done'."),

    ("Musical fanfare",
     "Clear the screen. Now perform a short 5-note ascending fanfare on "
     "the buzzer via play_tone. Suggested notes: C5(523), E5(659), G5(784), "
     "C6(1047), E6(1319), each with duration ~200ms. Before each tone, "
     "update line 1 to caption the note ('note 1 of 5: C5', etc) and "
     "change the swatch color to evoke that note. Final reply: 'fanfare "
     "complete'."),

    ("Capability gate",
     "Without clearing the screen, attempt to call move_motor with "
     "angle=90 to demonstrate hardware actuation. The device may or may "
     "not respond favorably. After you observe the result, update line 0 "
     "to 'capability check' and line 3 to summarize what happened in "
     "under 18 chars (e.g. 'motor: denied OK'). Set the swatch to a warm "
     "amber (r=220 g=140 b=20) to signal a non-fatal denial. Final reply: "
     "report what status the device returned for move_motor."),

    ("Closing card",
     "Clear the screen. Display: line 0 'DCP demo done', line 1 'thanks "
     "for watching', line 2 'paper: arXiv', line 3 'github.com/dcp'. Set "
     "the swatch to a soft purple (r=140 g=90 b=200). Final reply: "
     "'closing card up'."),
]


def manifest_to_tools(manifest: Manifest) -> list[dict]:
    """Expose ALL granted-capability intents AND the motor stub.

    The motor stub is intentionally in the tool list even though the LLM
    lacks motor.write — we want it to attempt the call so the demo shows
    the capability gate at work.
    """
    tools = []
    for intent in manifest.intents.values():
        props: dict[str, Any] = {}
        required: list[str] = []
        for p in intent.params.values():
            schema: dict[str, Any] = {"type": _json_type(p.type)}
            if p.range is not None:
                schema["minimum"], schema["maximum"] = p.range
            if p.default is None:
                required.append(p.name)
            desc = p.type + (f" {p.unit}" if p.unit else "")
            if p.range:
                desc += f", in [{p.range[0]}, {p.range[1]}]"
            schema["description"] = desc
            props[p.name] = schema
        tools.append({
            "type": "function",
            "function": {
                "name": intent.name,
                "description": f"DCP intent on smart-panel-01. cap={intent.capability}",
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            },
        })
    return tools


def _json_type(dcp_type: str) -> str:
    return {
        "int": "integer", "float": "number", "string": "string",
        "bool": "boolean", "duration": "integer",
    }.get(dcp_type, "string")


def llm_call(messages: list[dict], tools: list[dict]) -> dict:
    body = json.dumps({
        "model": MODEL,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.4,
    }).encode("utf-8")
    req = urllib.request.Request(
        SILICONFLOW_URL, data=body,
        headers={
            "Authorization": f"Bearer {SILICONFLOW_KEY}",
            "Content-Type": "application/json",
        })
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


async def run_scene(title: str, brief: str, bridge: Bridge,
                    tools: list[dict], shared_messages: list[dict]) -> None:
    print(f"\n┌─ Scene: {title}")
    print(f"│  brief: {brief[:80]}...")

    shared_messages.append({"role": "user", "content": brief})

    for step in range(1, 6):
        resp = llm_call(shared_messages, tools)
        msg = resp["choices"][0]["message"]
        shared_messages.append(msg)
        tcs = msg.get("tool_calls") or []
        if not tcs:
            content = (msg.get("content") or "").strip().replace("\n", " ")
            print(f"│  LLM done: {content[:120]}")
            break
        for tc in tcs:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            print(f"│  → {name}({json.dumps(args, ensure_ascii=False)})")
            try:
                r = await bridge.call(name, args)
                result = {"status": r.status, "data": r.data}
            except Exception as e:
                result = {"status": "error", "message": str(e)}
            shared_messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": name,
                "content": json.dumps(result),
            })
            tag = "✓" if result["status"] == "ok" else "✗"
            print(f"│    {tag} {result}")
            await asyncio.sleep(0.4)   # pacing for visible updates
    print("└─ scene end\n")


async def main(port: str) -> int:
    print(f"\n████ DCP showcase — {MODEL} → {port} ████")

    manifest = Manifest.load(ROOT / "examples" / "smart_panel_manifest.yaml")
    uart = UartTransport(port, baud=115200)
    await uart.open()
    bridge = Bridge(
        manifest, uart, granted_capabilities=GRANTED_CAPS, timeout=4.0,
    )
    await bridge.start()
    await asyncio.sleep(1.0)

    tools = manifest_to_tools(manifest)
    print(f"manifest: {manifest.device_id}, {len(tools)} tools exposed to LLM")
    print(f"granted caps: {sorted(GRANTED_CAPS)}\n")

    system_msg = (
        "You are presenting a live demo of the Device Context Protocol "
        "(DCP) running on a LilyGo T-Panel S3. The panel has a 480x480 "
        "LCD with a header, four text lines (0-3, each ≤18 chars), a "
        "color swatch, and a piezo buzzer. You issue tool calls; the "
        "panel reacts in physical reality. Style: minimal, intentional, "
        "no padding text. After all tool calls in a scene, give a brief "
        "final acknowledgement so the demo runner knows you're done. "
        "Some tools may return denied — that's expected and demonstrates "
        "DCP's safety gating; never argue with a denial, just report it."
    )
    shared_messages = [{"role": "system", "content": system_msg}]

    for title, brief in SCENES:
        await run_scene(title, brief, bridge, tools, shared_messages)
        await asyncio.sleep(2.0)   # camera-friendly pause between scenes

    # Hold the final card on screen for 20s — closing bridge/UART pulses
    # DTR/RTS and resets the ESP32, wiping the demo state.
    print("\n████ holding closing card for 20s — closing port now will reset the board ████")
    await asyncio.sleep(20)
    await bridge.stop()
    print("████ showcase done ████")
    return 0


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "COM6"
    sys.exit(asyncio.run(main(port)))
