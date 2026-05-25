"""LLM drives DCP — feeds a natural-language prompt to DeepSeek-V3 (via
SiliconFlow), exposing the smart_panel's DCP intents as OpenAI-format
tools. The LLM picks tools, the bridge dispatches them to the device,
results flow back. The T-Panel screen updates live as the LLM works.

Usage:
    python tools/llm_drive_dcp.py "show 'hello world' on line 0 then make the swatch red"
    python tools/llm_drive_dcp.py "spell out DCP across 3 lines, end with a green swatch"

This is the headline paper demo: LLM speaks → hardware obeys, mediated by
DCP capability gating and dry-run prediction.
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


def manifest_to_tools(manifest: Manifest, granted: set[str]) -> list[dict]:
    """Translate DCP intents into OpenAI-format tool specs the LLM can call."""
    tools = []
    for intent in manifest.intents.values():
        if intent.capability and intent.capability not in granted:
            continue
        # Skip stubs the firmware always rejects
        if intent.name in ("move_motor", "read_motor_position"):
            continue
        props: dict[str, Any] = {}
        required: list[str] = []
        for p in intent.params.values():
            schema: dict[str, Any] = {"type": _json_type(p.type)}
            if p.range is not None:
                schema["minimum"], schema["maximum"] = p.range
            if p.default is None:
                required.append(p.name)
            schema["description"] = (
                f"{p.type}" + (f" {p.unit}" if p.unit else "")
                + (f", range {p.range}" if p.range else "")
            )
            props[p.name] = schema
        tools.append({
            "type": "function",
            "function": {
                "name": intent.name,
                "description": (
                    f"{intent.name} on device {manifest.device_id}. "
                    f"Capability: {intent.capability}. "
                    f"{'Idempotent.' if intent.idempotent else 'Has side effects.'}"
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
        "temperature": 0.3,
    }).encode("utf-8")
    req = urllib.request.Request(
        SILICONFLOW_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {SILICONFLOW_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"HTTP error: {e.code} {e.read().decode('utf-8', errors='replace')}\n")
        raise


async def main(user_prompt: str, port: str) -> int:
    print(f"\n=== LLM ({MODEL}) drives DCP on {port} ===")
    print(f"user prompt: {user_prompt}\n")

    manifest = Manifest.load(ROOT / "examples" / "smart_panel_manifest.yaml")
    uart = UartTransport(port, baud=115200)
    await uart.open()
    bridge = Bridge(
        manifest, uart,
        granted_capabilities={"panel.write", "panel.read", "can.write", "can.read"},
        timeout=3.0,
    )
    await bridge.start()
    await asyncio.sleep(1.0)   # let boot prints flush

    tools = manifest_to_tools(manifest, {"panel.write", "panel.read"})
    print(f"exposed {len(tools)} DCP intents as LLM tools: "
          f"{[t['function']['name'] for t in tools]}\n")

    system_msg = (
        "You control a small embedded panel via the DCP protocol. The panel "
        "has a 480x480 LCD with 4 text lines (line 0-3) and a color swatch. "
        "Available tools mirror DCP intents. Call tools to fulfil the user's "
        "request. Keep text under 20 characters per line. After all hardware "
        "actions complete, give the user a single short summary sentence."
    )
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user",   "content": user_prompt},
    ]

    for step in range(1, 10):
        print(f"--- LLM step {step} ---")
        resp = llm_call(messages, tools)
        msg = resp["choices"][0]["message"]
        messages.append(msg)

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            print(f"LLM final: {msg.get('content', '').strip()}")
            break

        for tc in tool_calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"] or "{}")
            print(f"  → tool_call: {name}({args})")
            try:
                r = await bridge.call(name, args)
                result = {"status": r.status, "data": r.data}
            except Exception as e:
                result = {"status": "error", "message": str(e)}
            print(f"    ← {result}")
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": name,
                "content": json.dumps(result),
            })
            await asyncio.sleep(0.3)   # let the screen update visibly

    await bridge.stop()
    print("\n=== done ===")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        prompt = ("Display 'Hello DCP' on line 0, 'driven by LLM' on line 1, "
                  "then set the swatch to a vibrant orange.")
    else:
        prompt = " ".join(args)
    port = "COM6"
    sys.exit(asyncio.run(main(prompt, port)))
