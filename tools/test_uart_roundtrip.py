"""End-to-end UART round-trip test against real ESP32 hardware.

Usage:
    python tools/test_uart_roundtrip.py [COM_PORT]

Exercises every code path in the bridge x firmware boundary:
- valid call (set_brightness)
- read (read_brightness)
- dry-run (predicted, no side effect)
- out-of-range (Bridge-rejected)
- unknown intent (device-rejected with error frame)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Force stdout/stderr to UTF-8 so checkmarks render on Windows consoles.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent

from dcp.bridge import Bridge
from dcp.manifest import Manifest
from dcp.transports.uart import UartTransport


async def main(port: str) -> int:
    print(f"\n=== DCP UART round-trip test against {port} ===\n")

    manifest = Manifest.load(ROOT / "examples" / "lamp_manifest.yaml")
    print(f"loaded manifest: {manifest.device_id}  ({len(manifest.intents)} intents)")

    uart = UartTransport(port, baud=115200)
    await uart.open()
    print(f"opened UART {port} @ 115200")

    bridge = Bridge(
        manifest,
        uart,
        granted_capabilities={"lamp.write", "lamp.read"},
        timeout=3.0,
    )
    await bridge.start()
    print("Bridge started\n")

    tests = [
        ("set_brightness(50)",          "set_brightness", {"level": 50, "fade": 0},   False, "ok"),
        ("read_brightness",             "read_brightness", None,                       False, "ok"),
        ("set_brightness(0)  off",      "set_brightness", {"level": 0, "fade": 0},    False, "ok"),
        ("set_brightness(100) full",    "set_brightness", {"level": 100, "fade": 0},  False, "ok"),
        ("dry-run set_brightness(75)",  "set_brightness", {"level": 75},              True,  "ok"),
        ("set_brightness(5000) bad",    "set_brightness", {"level": 5000},            False, "range"),
        ("set_color orange",            "set_color",      {"r": 255, "g": 165, "b": 0}, False, "ok"),
        ("dry-run set_color cyan",      "set_color",      {"r": 0, "g": 255, "b": 255}, True,  "ok"),
        ("set_color out-of-range",      "set_color",      {"r": 999, "g": 0, "b": 0},   False, "range"),
        ("turn_into_pumpkin (unknown)", "turn_into_pumpkin", None,                    False, "unknown_intent"),
    ]

    passed = failed = 0
    for label, intent, params, dry, expected in tests:
        try:
            result = await bridge.call(intent, params, dry_run=dry)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗  {label:35s}  EXCEPTION: {e!r}")
            failed += 1
            continue

        ok = result.status == expected
        mark = "[OK]  " if ok else "[FAIL]"
        print(f"  {mark}  {label:35s}  status={result.status:20s} data={result.data}")
        if ok:
            passed += 1
        else:
            print(f"          expected status={expected}")
            failed += 1

    await bridge.stop()
    print(f"\n=== {passed} passed, {failed} failed ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "COM5"
    sys.exit(asyncio.run(main(port)))
