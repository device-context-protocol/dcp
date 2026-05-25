"""Storyboarded LLM-drives-DCP demo with on-screen narration.

The whole conversation flow is rendered on the T-Panel LCD itself:

    ┌────────────────────────────────────┐
    │ DCP smart-panel-01           [header from firmware]
    │ [SCENE 4/5] SAFETY GATE      ← line 0: scene tag
    │ USER: try motor 90°          ← line 1: user-intent summary
    │ LLM → move_motor(90)         ← line 2: LLM tool call
    │ DCP ✗ DENIED capability      ← line 3: protocol result
    │                              [color swatch]
    └────────────────────────────────────┘

The orchestrator writes lines 0-3 directly (it doesn't ask the LLM to
narrate); the LLM only picks tools. Each scene pauses 3-4 seconds per
step so the audience can read the flow before it advances.

Designed to be filmed in one take: aim a phone at the panel, run the
script, get a ~2-minute video that tells the full DCP story (intent
plan, tool exec, protocol-level capability gate, recovery).

Usage: python tools/llm_storyboard.py [COM_PORT]
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

GRANTED_CAPS = {"panel.write", "panel.read"}

# Pacing — generous so the screen is readable on video
SCENE_INTRO_HOLD = 3.0      # how long the scene-intro tableau is held
STEP_HOLD        = 2.5      # how long each user/LLM/DCP step is held
SCENE_END_HOLD   = 3.5      # pause between scenes
FINAL_HOLD       = 25.0     # closing card hold (closing UART resets the board)


SCENES = [
    {
        "tag":  "[1/5] INTRO",
        "user_short": "introduce yourself",
        "user_full":  "Introduce yourself to the audience. Write a 4-line "
                      "self-intro on display_text lines 4, 5, 6, 7 (each "
                      "≤32 chars). Tell them: who you are (LLM name), "
                      "what protocol you're using (DCP), what device "
                      "you're driving, and one fun fact about this setup.",
        "note":   "LLM plans 4 display_text calls",
    },
    {
        "tag":  "[2/5] DRY-RUN PREVIEW",
        "user_short": "preview a color before committing",
        "user_full":  "Demonstrate DCP's dry-run mechanism. The set_color "
                      "intent supports dry_run. First call set_color with "
                      "r=200 g=80 b=160 AND dry_run=true to see the "
                      "prediction (you'll get back would_r/would_g/would_b "
                      "without the device actuating). Then announce on "
                      "line 4 'dry-run ok, now committing', then call "
                      "set_color with the SAME r/g/b but dry_run=false to "
                      "actually commit. Finally on line 5 say 'commit ok'.",
        "note":   "predict-before-actuate (paper §3)",
    },
    {
        "tag":  "[3/5] CAPABILITY GATE",
        "user_short": "try to actuate the motor",
        "user_full":  "Test the capability gate. Call move_motor with "
                      "angle=90, speed=60. The DCP bridge will reject "
                      "this because you lack the motor.write capability "
                      "— observe the denial. Then try ONE more time with "
                      "different args (angle=45, speed=30) to confirm the "
                      "denial is unconditional, not a parameter issue. "
                      "On lines 4 and 5 narrate what happened. Do NOT "
                      "try the motor a third time.",
        "note":   "host-side capability denial (paper §5)",
    },
    {
        "tag":  "[4/5] RANGE GUARD",
        "user_short": "try invalid color value",
        "user_full":  "Demonstrate schema validation. Call set_color with "
                      "r=999 (out of range — valid is 0-255). The bridge "
                      "will reject it with status=range. After you see "
                      "the rejection, self-correct: call set_color again "
                      "with a valid value like r=200 g=140 b=20. On "
                      "line 4 narrate what you learned.",
        "note":   "manifest range enforcement (paper §3)",
    },
    {
        "tag":  "[5/5] CLOSING",
        "user_short": "wrap up the demo",
        "user_full":  "Wrap up. Write a 3-line closing on lines 4, 5, 6: "
                      "summarize the 3 DCP safety mechanisms you just "
                      "demonstrated (dry-run, capability gate, range "
                      "guard). On line 7 thank the audience. Set color "
                      "to a soft white-ish (r=230 g=230 b=240).",
        "note":   "summarize the 3 safety mechanisms",
    },
]


def manifest_to_tools(manifest: Manifest) -> list[dict]:
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
            schema["description"] = p.type + (f" {p.unit}" if p.unit else "")
            props[p.name] = schema
        # Surface dry_run as an explicit optional boolean param to the LLM
        # for intents that declare dry_run support. When the LLM passes
        # dry_run=true, the orchestrator routes it to bridge.call as a kwarg.
        if intent.dry_run:
            props["dry_run"] = {
                "type": "boolean",
                "description": "If true, predict the effect without actuating. "
                               "Returns would_* fields instead of executing.",
            }
        tools.append({
            "type": "function",
            "function": {
                "name": intent.name,
                "description": (
                    f"DCP intent on smart-panel-01. "
                    f"cap={intent.capability}. "
                    + ("Supports dry_run." if intent.dry_run else "")
                ),
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            },
        })
    return tools


def _json_type(dcp_type: str) -> str:
    return {"int":"integer","float":"number","string":"string",
            "bool":"boolean","duration":"integer"}.get(dcp_type, "string")


def llm_call(messages: list[dict], tools: list[dict]) -> dict:
    body = json.dumps({
        "model": MODEL, "messages": messages, "tools": tools,
        "tool_choice": "auto", "temperature": 0.4,
    }).encode("utf-8")
    req = urllib.request.Request(
        SILICONFLOW_URL, data=body,
        headers={"Authorization": f"Bearer {SILICONFLOW_KEY}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def _short_args(args: dict) -> str:
    """Squeeze tool-call args into a short on-screen representation."""
    if not args: return ""
    bits = []
    for k, v in list(args.items())[:3]:
        if isinstance(v, str):
            v = v[:14]
            bits.append(f"{k}={v!r}")
        else:
            bits.append(f"{k}={v}")
    return ",".join(bits)


def _short_status(status: str, data: dict) -> str:
    """Squeeze a DCP reply into a short on-screen representation."""
    if status == "ok":
        return "✓ ok"
    if status == "capability_required":
        return "✗ DENIED (cap)"
    if status in ("range", "denied"):
        return f"✗ {status}"
    return f"~ {status}"


async def screen_set(bridge: Bridge, *,
                     status=None,
                     l0=None, r0="plain",
                     l1=None, r1="plain",
                     l2=None, r2="plain",
                     l3=None, r3="plain",
                     swatch=None):
    """Push narration lines + status bar + swatch to the device.

    Each line takes (text, role); role drives text color on the device:
      user    = cyan
      llm     = amber
      dcp_ok  = green
      dcp_err = red
      dcp_req = gray
      plain   = black
    """
    if status is not None:
        try:    await bridge.call("set_status", {"text": status[:38]})
        except Exception: pass
    for line_no, (text, role) in enumerate([(l0, r0), (l1, r1), (l2, r2), (l3, r3)]):
        if text is None: continue
        try:
            await bridge.call("display_text",
                              {"line": line_no, "text": text[:38], "role": role})
        except Exception:
            pass
    if swatch is not None:
        r, g, b = swatch
        try:
            await bridge.call("set_color", {"r": r, "g": g, "b": b})
        except Exception:
            pass


async def run_scene(bridge: Bridge, tools: list[dict],
                    shared_messages: list[dict], scene: dict) -> None:
    tag, user_short, user_full = scene["tag"], scene["user_short"], scene["user_full"]

    print(f"\n┌─ {tag}  ({scene['note']})")

    # Scene intro tableau: status bar shows scene tag, line 0 shows user
    # request in cyan, narration body clear, LLM content (4-7) clear.
    try:
        await bridge.call("clear_screen")
    except Exception:
        pass
    await screen_set(bridge,
                     status=tag,
                     l0=f"USER: {user_short}",   r0="user",
                     l1="",                       r1="plain",
                     l2="",                       r2="plain",
                     l3="",                       r3="plain")
    print(f"│  USER → {user_short}")
    await asyncio.sleep(SCENE_INTRO_HOLD)

    # Hand off to LLM
    shared_messages.append({"role": "user", "content": user_full})
    for step in range(1, 8):
        resp = llm_call(shared_messages, tools)
        msg = resp["choices"][0]["message"]
        shared_messages.append(msg)
        tcs = msg.get("tool_calls") or []
        if not tcs:
            content = (msg.get("content") or "").strip().replace("\n", " ")
            print(f"│  LLM final: {content[:80]}")
            break

        for tc in tcs:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            short = _short_args(args)
            llm_line = f"LLM→ {name}({short[:22]})"
            print(f"│  {llm_line}")
            # Render the LLM intent on screen BEFORE we dispatch it.
            # The LLM is restricted to display_text line=3 (per system
            # prompt), so writes to lines 1+2 here won't be clobbered
            # by the LLM's own display calls.
            await screen_set(bridge,
                             l1=llm_line, r1="llm",
                             l2="DCP… waiting", r2="dcp_req")
            await asyncio.sleep(0.8)

            # Extract dry_run flag (LLM-facing) and route to bridge kwarg.
            dry = bool(args.pop("dry_run", False))
            try:
                r = await bridge.call(name, args, dry_run=dry)
                result = {"status": r.status, "data": r.data}
            except Exception as e:
                result = {"status": "error", "data": {"message": str(e)}}
            if dry:
                result["dry_run"] = True
            print(f"│      {result}")

            dcp_line = f"DCP {_short_status(result['status'], result['data'])}"
            role = "dcp_ok" if result["status"] == "ok" else "dcp_err"
            await screen_set(bridge, l2=dcp_line, r2=role)
            await asyncio.sleep(STEP_HOLD)

            shared_messages.append({
                "role": "tool", "tool_call_id": tc["id"],
                "name": name, "content": json.dumps(result),
            })

    # Scene end: leave the last LLM/DCP lines visible so audience absorbs.
    print(f"└─ scene end\n")
    await asyncio.sleep(SCENE_END_HOLD)


async def main(port: str) -> int:
    print(f"\n████ DCP STORYBOARD — {MODEL} → {port} ████")
    manifest = Manifest.load(ROOT / "examples" / "smart_panel_manifest.yaml")
    uart = UartTransport(port, baud=115200)
    await uart.open()
    bridge = Bridge(manifest, uart, granted_capabilities=GRANTED_CAPS, timeout=4.0)
    await bridge.start()
    await asyncio.sleep(1.0)

    tools = manifest_to_tools(manifest)
    print(f"manifest: {manifest.device_id}, {len(tools)} intents exposed")
    print(f"granted caps: {sorted(GRANTED_CAPS)} (motor.* intentionally OUT)\n")

    system_msg = (
        "You are a tool-calling agent driving a 480x480 LCD panel via "
        "the DCP protocol on a real LilyGo T-Panel S3.\n\n"
        "CRITICAL UI LAYOUT — your visible content area is display_text "
        "lines 4, 5, 6, 7 ONLY. Lines 0-3 are reserved for the demo "
        "runner's narration of the USER/LLM/DCP conversation flow and "
        "will be overwritten. Use line 4-7 for your content.\n\n"
        "Some intents support dry_run=true — pass that flag to preview "
        "the effect (you'll get would_* fields back) without actuating. "
        "Use it when you want to verify safety before commit.\n\n"
        "Keep each text line under 32 characters. After your tool calls "
        "fulfil the request, give a one-line final ack. If a tool "
        "returns 'capability_required' or 'range' or 'denied', accept "
        "it as informative — do not retry the SAME call, but you may "
        "self-correct with different arguments where the scene asks."
    )
    shared_messages = [{"role": "system", "content": system_msg}]

    # Opening title card before scene 1
    try: await bridge.call("clear_screen")
    except Exception: pass
    await screen_set(bridge,
                     status="DCP STORYBOARD — LLM × hardware",
                     l0="DeepSeek-V3 driving", r0="llm",
                     l1="DCP gating intents",  r1="dcp_ok",
                     l2="watch top→bottom",    r2="plain",
                     l3="5 scenes follow",     r3="plain")
    await asyncio.sleep(3.5)

    for scene in SCENES:
        await run_scene(bridge, tools, shared_messages, scene)

    print(f"\n████ holding final tableau for {FINAL_HOLD:.0f}s ████")
    await asyncio.sleep(FINAL_HOLD)
    await bridge.stop()
    print("████ storyboard done ████")
    return 0


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "COM6"
    sys.exit(asyncio.run(main(port)))
