"""YAML manifest → C/C++ header generator.

Produces a header with intent/event IDs resolved at compile time (no runtime
``crc16`` calls), plus capability string constants for documentation.

Usage::

    dcp codegen examples/lamp_manifest.yaml -o firmware/esp32/examples/lamp/dcp_intents.h
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from textwrap import dedent

from dcp.manifest import Manifest
from dcp.wire import intent_id


def _identifier(name: str) -> str:
    """Convert ``set_brightness`` → ``SET_BRIGHTNESS``; strip anything weird."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", name).upper()
    if safe and safe[0].isdigit():
        safe = "_" + safe
    return safe


def _manifest_hash(manifest_text: str) -> str:
    return hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()[:16]


def render(
    manifest_path: Path,
    *,
    guard: str | None = None,
    with_stubs: bool = False,
) -> str:
    text = manifest_path.read_text(encoding="utf-8")
    manifest = Manifest.from_dict(__import__("yaml").safe_load(text))
    digest = _manifest_hash(text)
    guard = guard or f"DCP_INTENTS_{_identifier(manifest.device_id)}_H"

    lines: list[str] = [
        "// Auto-generated from a DCP manifest. Do not edit by hand.",
        f"// Source: {manifest_path.name}",
        f"// Device: {manifest.device_id}  ({manifest.vendor} / {manifest.model})",
        f"// Manifest SHA-256[:16]: {digest}",
        "",
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        "#include <stdint.h>",
        "",
        "// ---- Intents ----",
    ]
    for intent in manifest.intents.values():
        ident = _identifier(intent.name)
        bits = []
        if intent.idempotent:
            bits.append("idempotent")
        if intent.dry_run:
            bits.append("dry-run")
        if intent.capability:
            bits.append(f"cap={intent.capability}")
        comment = f"  // {' · '.join(bits)}" if bits else ""
        lines.append(
            f"static constexpr uint16_t DCP_INTENT_{ident} = 0x{intent_id(intent.name):04x};{comment}"
        )

    if manifest.events:
        lines += ["", "// ---- Events ----"]
        for event in manifest.events.values():
            ident = _identifier(event.name)
            lines.append(
                f"static constexpr uint16_t DCP_EVENT_{ident} = 0x{intent_id(event.name):04x};"
            )

    caps = sorted({i.capability for i in manifest.intents.values() if i.capability}
                  | {e.capability for e in manifest.events.values() if e.capability})
    if caps:
        lines += ["", "// ---- Capabilities (informational; enforced by the Bridge) ----"]
        for cap in caps:
            ident = _identifier(cap.replace(".", "_"))
            lines.append(f'#define DCP_CAP_{ident} "{cap}"')

    if with_stubs:
        lines += ["", "// ---- Handler signatures ----",
                  "// Implement these in your sketch. The generated binding table below",
                  "// references them by name; do not rename without regenerating this file.",
                  "",
                  "#ifdef __cplusplus",
                  "#include \"DCP.h\"",
                  ""]
        for intent in manifest.intents.values():
            lines.append(
                f"dcp::Status handle_{intent.name}(uint8_t kind, dcp::CborReader& params, "
                f"dcp::CborMap& reply, void* user);"
            )
        lines += ["",
                  "static dcp::IntentBinding DCP_BINDINGS[] = {"]
        for intent in manifest.intents.values():
            lines.append(
                f'    {{ DCP_ID("{intent.name}"), handle_{intent.name}, nullptr }},'
            )
        lines += ["};",
                  "static constexpr size_t DCP_BINDINGS_COUNT = "
                  "sizeof(DCP_BINDINGS) / sizeof(DCP_BINDINGS[0]);",
                  "",
                  "#endif // __cplusplus"]

    lines += ["", f"#endif // {guard}", ""]
    return "\n".join(lines)


def write(
    manifest_path: Path,
    out_path: Path,
    *,
    guard: str | None = None,
    with_stubs: bool = False,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        render(manifest_path, guard=guard, with_stubs=with_stubs),
        encoding="utf-8",
    )
