"""Latency benchmark for IoT-MCP's wire protocol — the apples-to-apples
counterpart to tools/bench_latency.py.

Same host, same UART, same baud (115200), same MCU (ESP32-S3), same
logical action (set_brightness=50). The only thing that changes is the
on-the-wire format: IoT-MCP uses newline-delimited JSON in both
directions (per servers/BUZZER/main.py and friends in their reference
repo); DCP uses CBOR + COBS + CRC inside a 6-byte header.

To run this, flash firmware/esp32/examples/iotmcp_echo to the device,
then::

    python tools/bench_latency_iotmcp.py --serial COM6 --count 1000

Writes one entry into docs/paper/figures/latency_data.json under the
key ``uart_s3_iotmcp``; the existing ``uart_s3`` (DCP) entry is
preserved, so the figure can plot the two side-by-side.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import serial_asyncio

ROOT = Path(__file__).resolve().parent.parent
JSON_OUT = ROOT / "docs" / "paper" / "figures" / "latency_data.json"


async def bench_async(port: str, baud: int, count: int, warmup: int) -> list[float]:
    """Use the same pyserial-asyncio pattern that the DCP UartTransport
    uses, so the host-side Python overhead is the same for both bench
    runs and the difference reflects pure protocol overhead."""
    reader, writer = await serial_asyncio.open_serial_connection(
        url=port, baudrate=baud)
    # Give the device firmware time to come up after the previous reset.
    await asyncio.sleep(2.0)
    # Drain any boot output.
    try:
        await asyncio.wait_for(reader.read(4096), timeout=0.2)
    except asyncio.TimeoutError:
        pass

    cmd = (json.dumps({"command": "set_brightness", "level": 50}) + "\n").encode()

    async def one_call() -> float:
        t0 = time.perf_counter()
        writer.write(cmd)
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=2.0)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        try:
            reply = json.loads(line.decode().rstrip())
        except json.JSONDecodeError as e:
            raise RuntimeError(f"malformed reply: {line!r} ({e})") from e
        if reply.get("result") != "ok":
            raise RuntimeError(f"bad reply: {reply}")
        return elapsed_ms

    print(f"  warmup x{warmup}...")
    for _ in range(warmup):
        await one_call()

    print(f"  timed x{count}...")
    samples = []
    for _ in range(count):
        samples.append(await one_call())
    writer.close()
    return samples


def bench(port: str, baud: int, count: int, warmup: int) -> list[float]:
    return asyncio.run(bench_async(port, baud, count, warmup))


def summarize(samples: list[float]) -> dict:
    q1, q3 = statistics.quantiles(samples, n=4)[0], statistics.quantiles(samples, n=4)[2]
    return {
        "n":      len(samples),
        "min":    round(min(samples), 4),
        "max":    round(max(samples), 4),
        "mean":   round(statistics.fmean(samples), 4),
        "median": round(statistics.median(samples), 4),
        "p50":    round(statistics.median(samples), 4),
        "p90":    round(statistics.quantiles(samples, n=10)[8], 4),
        "p99":    round(statistics.quantiles(samples, n=100)[98], 4),
        "stdev":  round(statistics.stdev(samples), 4),
        "q1":     round(q1, 4),
        "q3":     round(q3, 4),
        "iqr":    round(q3 - q1, 4),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--count", type=int, default=1000)
    ap.add_argument("--warmup", type=int, default=50)
    ap.add_argument("--label", default="IoT-MCP wire (ESP32-S3, native USB)")
    ap.add_argument("--key", default="uart_s3_iotmcp")
    args = ap.parse_args()

    print(f"Benchmark IoT-MCP wire on {args.serial} @ {args.baud}")
    samples = bench(args.serial, args.baud, args.count, args.warmup)
    summary = summarize(samples)
    summary["label"]        = args.label
    summary["intent"]       = "set_brightness"
    summary["measured_at"]  = time.strftime("%Y-%m-%d")
    summary["wire_protocol"] = "newline-delimited JSON"

    print(f"  median {summary['median']:.3f} ms,  p90 {summary['p90']:.3f},  p99 {summary['p99']:.3f}")

    if JSON_OUT.exists():
        data = json.loads(JSON_OUT.read_text(encoding="utf-8"))
    else:
        data = {}
    data[args.key] = summary
    JSON_OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"wrote key={args.key} into {JSON_OUT}")


if __name__ == "__main__":
    main()
