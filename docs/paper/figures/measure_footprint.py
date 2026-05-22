"""Measure the DCP firmware footprint.

Compiles a baseline empty Arduino sketch and the lamp example with the
same FQBN, and reports the delta — the flash and RAM cost that the DCP
layer (protocol + framing + CBOR + SHA-256 + the lamp handlers) adds on
top of the bare Arduino-ESP32 runtime.

This is the measurement behind the footprint figures cited in the paper
and README (27.6 KB flash / 0.6 KB RAM for the DCP layer on ESP32). Run
it to reproduce; results are written to footprint_data.json, which
fig_footprint() in make_figures.py reads.

Usage:
    python measure_footprint.py [--fqbn esp32:esp32:esp32]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]                       # docs/paper/figures -> repo root
LAMP = REPO / "firmware" / "esp32" / "examples" / "lamp"
DCP_LIB = REPO / "firmware" / "esp32"
JSON_OUT = HERE / "footprint_data.json"

_FLASH_RE = re.compile(r"Sketch uses (\d+) bytes")
_GLOB_RE = re.compile(r"Global variables use (\d+) bytes")


def compile_sketch(sketch_dir: Path, fqbn: str) -> tuple[int, int]:
    """Compile a sketch and return (flash_bytes, globals_bytes)."""
    proc = subprocess.run(
        ["arduino-cli", "compile", "--clean", "--fqbn", fqbn,
         "--library", str(DCP_LIB), str(sketch_dir)],
        capture_output=True, text=True)
    text = proc.stdout + proc.stderr
    flash = _FLASH_RE.search(text)
    glob = _GLOB_RE.search(text)
    if not flash or not glob:
        sys.stderr.write(text)
        sys.exit(f"compile failed / size lines not found for {sketch_dir.name}")
    return int(flash.group(1)), int(glob.group(1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fqbn", default="esp32:esp32:esp32",
                    help="board FQBN (default esp32:esp32:esp32 = WROOM-32)")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "baseline"
        base.mkdir()
        (base / "baseline.ino").write_text("void setup() {}\nvoid loop() {}\n")
        print(f"compiling empty baseline  ({args.fqbn}) ...")
        b_flash, b_glob = compile_sketch(base, args.fqbn)

    print(f"compiling lamp example    ({args.fqbn}) ...")
    l_flash, l_glob = compile_sketch(LAMP, args.fqbn)

    d_flash = l_flash - b_flash
    d_glob = l_glob - b_glob

    print()
    print(f"  baseline empty sketch : {b_flash:>8,} B flash   {b_glob:>7,} B globals")
    print(f"  lamp example (w/ DCP) : {l_flash:>8,} B flash   {l_glob:>7,} B globals")
    print(f"  DCP layer delta       : {d_flash:>8,} B flash   {d_glob:>7,} B globals")
    print(f"                        = {d_flash/1024:.1f} KB flash, {d_glob/1024:.1f} KB RAM")

    result = {
        "fqbn": args.fqbn,
        "baseline_flash": b_flash,
        "baseline_globals": b_glob,
        "lamp_flash": l_flash,
        "lamp_globals": l_glob,
        "dcp_layer_flash": d_flash,
        "dcp_layer_globals": d_glob,
        "dcp_layer_flash_kb": round(d_flash / 1024, 1),
        "dcp_layer_globals_kb": round(d_glob / 1024, 1),
    }
    JSON_OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"\n  -> {JSON_OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
