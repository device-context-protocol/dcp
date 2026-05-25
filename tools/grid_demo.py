"""Grid Demo — LIVE LLM-driven version.

DeepSeek-V3 is exposed the move/grid_reset/narrate/set_status intents as
tools (via SiliconFlow). It receives natural-language prompts per scene
and PLANS its own moves. The host orchestrator only:
  - sets the scene tag + initial position
  - lets the LLM call move(...)
  - intercepts the call to draw the USER/LLM/DCP narration on screen
  - feeds results back so the LLM can self-correct on denials

Real LLM means: real planning, real reactions to denials. Each move
costs ~1-2s API latency, so the full demo runs ~60-90s.

Usage: python tools/grid_demo.py [COM_PORT]
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import urllib.request

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

GRANTED_CAPS = {"grid.write", "panel.write"}


def llm_call(messages: list[dict], tools: list[dict]) -> dict:
    body = json.dumps({
        "model": MODEL, "messages": messages, "tools": tools,
        "tool_choice": "auto", "temperature": 0.4,
    }).encode("utf-8")
    req = urllib.request.Request(
        SILICONFLOW_URL, data=body,
        headers={"Authorization": f"Bearer {SILICONFLOW_KEY}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def manifest_to_tools(manifest: Manifest) -> list[dict]:
    """Only expose the move intent to the LLM. Narration/status are
    orchestrator-owned so the visual stays consistent."""
    tools = []
    for intent in manifest.intents.values():
        if intent.name != "move":
            continue
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
        tools.append({
            "type": "function",
            "function": {
                "name": intent.name,
                "description": (
                    "Move the green square N cells in one direction "
                    "(up/down/left/right). Returns 'range' if it would "
                    "leave the 6x6 grid (cols 0-5, rows 0-5)."
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


SYSTEM_MSG = (
    "You are a tool-calling agent driving a green square on a 6x6 grid "
    "via the DCP protocol. Valid cells: columns 0-5, rows 0-5. Origin "
    "(0,0) is top-left. Tool: move(direction, steps). Direction is one "
    "of 'up','down','left','right'. After tool calls fulfil the user's "
    "request, give a brief one-line ack. If a call returns 'range', it "
    "means the move would leave the grid — accept it, do not retry the "
    "SAME args, but you may try smaller steps."
)


async def main(port: str) -> int:
    print(f"\n████ Grid Demo (LIVE LLM) → {port} ████")
    manifest = Manifest.load(ROOT / "examples" / "grid_demo_manifest.yaml")
    uart = UartTransport(port, baud=115200)
    await uart.open()
    bridge = Bridge(
        manifest, uart, granted_capabilities=GRANTED_CAPS, timeout=4.0,
    )
    await bridge.start()
    await asyncio.sleep(1.0)

    tools = manifest_to_tools(manifest)
    print(f"exposed 1 tool to LLM: move(direction, steps)")
    print(f"granted caps: {sorted(GRANTED_CAPS)}\n")

    # Helpers
    async def status(text):
        try: await bridge.call("set_status", {"text": text})
        except Exception: pass

    async def narrate(line, text, role="plain"):
        try: await bridge.call("narrate", {"line": line, "text": text[:38], "role": role})
        except Exception: pass

    async def clear():
        try: await bridge.call("clear_narration")
        except Exception: pass

    async def reset(x, y):
        try: await bridge.call("grid_reset", {"x": x, "y": y})
        except Exception: pass

    async def run_llm_scene(scene_tag, scene_prompt, max_steps=8,
                            user_short_text=None):
        """One scene: a user prompt to the LLM. The LLM plans moves.
        Narrate USER (line 0) at the top; LLM calls go to line 1; DCP
        results to line 2."""
        await status(scene_tag)
        await clear()
        if user_short_text:
            await narrate(0, f"USER: {user_short_text}", "user")
        await asyncio.sleep(1.5)

        messages = [
            {"role": "system", "content": SYSTEM_MSG},
            {"role": "user",   "content": scene_prompt},
        ]
        for step_i in range(max_steps):
            resp = llm_call(messages, tools)
            msg = resp["choices"][0]["message"]
            messages.append(msg)
            tcs = msg.get("tool_calls") or []
            if not tcs:
                content = (msg.get("content") or "").strip().replace("\n", " ")
                print(f"  LLM final: {content[:80]}")
                break

            for tc in tcs:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                call_str = f"LLM -> move({args.get('direction','?')}, {args.get('steps','?')})"
                await narrate(1, call_str, "llm")
                await narrate(2, "DCP ... validating", "dcp_req")
                await asyncio.sleep(0.7)

                try:
                    r = await bridge.call(name, args)
                    result = {"status": r.status, "data": r.data}
                except Exception as e:
                    result = {"status": "error", "data": {"message": str(e)}}

                if result["status"] == "ok":
                    await narrate(2, "DCP OK  in bounds, go", "dcp_ok")
                elif result["status"] == "range":
                    await narrate(2, "DCP NO  out of bounds", "dcp_err")
                else:
                    await narrate(2, f"DCP NO  {result['status']}", "dcp_err")

                print(f"  {call_str} -> {result}")
                messages.append({
                    "role": "tool", "tool_call_id": tc["id"],
                    "name": name, "content": json.dumps(result),
                })
                await asyncio.sleep(1.6)

    # ───── Scene 1: intro (orchestrator, no LLM) ─────
    print("\n[1/3] HOW THIS WORKS")
    await status("[1/3] HOW THIS WORKS")
    await reset(0, 0)
    await clear()
    await narrate(0, "USER: meet the grid + square", "user")
    await narrate(1, "LLM tool: move(dir, step)", "plain")
    await narrate(2, "DCP gates every move", "dcp_ok")
    await asyncio.sleep(5)

    # ───── Scene 2: live LLM walks a loop ─────
    print("\n[2/3] LLM MOVES THE SQUARE")
    await reset(0, 0)
    await run_llm_scene(
        scene_tag="[2/3] LLM MOVES THE SQUARE",
        user_short_text="walk a small loop",
        scene_prompt=(
            "The square is at (0,0). Move it in a small loop around the "
            "grid using 4 moves: right a few cells, down a few, left some, "
            "and up. End somewhere away from (0,0). Issue exactly 4 move "
            "tool calls, then say 'loop done'."
        ),
    )
    await asyncio.sleep(1.5)

    # ───── Scene 3: live LLM hits the boundary ─────
    print("\n[3/3] DCP STOPS A BAD MOVE")
    # Position square so an aggressive right move will overshoot.
    await reset(4, 2)
    await run_llm_scene(
        scene_tag="[3/3] DCP STOPS A BAD MOVE",
        user_short_text="push to the far right",
        scene_prompt=(
            "The square is at (4,2). Your task: reach column 5 in a single "
            "ambitious attempt — first try move(right, 5) to dramatically "
            "demonstrate the boundary. After you see what happens, use a "
            "smaller move to actually reach column 5. Issue at least 2 "
            "move calls (one ambitious, one correcting). Then say 'done'."
        ),
    )
    await asyncio.sleep(2.0)

    # Hold final state
    print("\n████ holding final state 20s ████")
    await asyncio.sleep(20)
    await bridge.stop()
    print("████ done ████")
    return 0


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "COM6"
    sys.exit(asyncio.run(main(port)))
