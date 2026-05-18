"""dcp — command line entry point."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

SECRET_ENV = "DCP_SECRET"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dcp",
        description="Device Context Protocol — bridge LLM agents to physical devices",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser(
        "serve",
        help="Run an MCP server backed by a DCP device or simulator",
    )
    serve.add_argument("manifest", type=Path, help="Path to a DCP manifest YAML")
    backend = serve.add_mutually_exclusive_group(required=True)
    backend.add_argument(
        "--simulator",
        action="store_true",
        help="Spawn an in-process simulator instead of connecting to real hardware",
    )
    backend.add_argument(
        "--serial",
        metavar="PORT",
        help="Serial port for UART transport (e.g. COM3 or /dev/ttyUSB0)",
    )
    backend.add_argument(
        "--mqtt",
        metavar="HOST[:PORT]",
        help="MQTT broker for MQTT transport (default port 1883)",
    )
    backend.add_argument(
        "--ble",
        metavar="ADDRESS",
        help="BLE device address (host MAC or platform-specific id)",
    )
    serve.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="Baud rate for --serial (default: 115200)",
    )
    serve.add_argument(
        "--mqtt-prefix",
        default="dcp/default",
        help="MQTT topic prefix (default: dcp/default)",
    )
    serve.add_argument(
        "--ble-service",
        default=None,
        help="BLE service UUID for --ble (required when --ble is set)",
    )
    serve.add_argument(
        "--grant",
        default="",
        metavar="CAP[,CAP...]",
        help="Comma-separated capabilities to grant the LLM "
             "(default: all capabilities declared by the manifest)",
    )

    inspect = sub.add_parser("inspect", help="Print a parsed manifest summary")
    inspect.add_argument("manifest", type=Path)

    codegen = sub.add_parser(
        "codegen",
        help="Generate a C/C++ header with intent IDs from a manifest",
    )
    codegen.add_argument("manifest", type=Path)
    codegen.add_argument("-o", "--out", type=Path, required=True, help="Output header path")
    codegen.add_argument(
        "--guard",
        default=None,
        help="Override the include-guard macro name",
    )
    codegen.add_argument(
        "--stubs",
        action="store_true",
        help="Also emit handler signatures and a DCP_BINDINGS table",
    )

    token = sub.add_parser("token", help="Mint or verify HMAC capability tokens")
    token_sub = token.add_subparsers(dest="token_cmd", required=True)

    mint = token_sub.add_parser("mint", help="Mint a token")
    mint.add_argument(
        "--caps", required=True, metavar="CAP[,CAP...]",
        help="Comma-separated capabilities to encode",
    )
    mint.add_argument("--ttl", type=int, default=3600, help="Seconds until expiry (default 3600)")
    mint.add_argument("--sub", default=None, help="Optional subject/session id")
    mint.add_argument(
        "--secret-hex", default=None,
        help=f"HMAC secret as hex; defaults to ${SECRET_ENV}",
    )

    keygen = token_sub.add_parser("keygen", help="Print a fresh random secret (hex)")
    keygen.add_argument("--bytes", type=int, default=32)

    return parser


def _resolve_capabilities(manifest_path: Path, grant: str) -> set[str]:
    if grant:
        return {c.strip() for c in grant.split(",") if c.strip()}
    from dcp.manifest import Manifest

    m = Manifest.load(manifest_path)
    caps = {i.capability for i in m.intents.values() if i.capability}
    caps |= {e.capability for e in m.events.values() if e.capability}
    return caps


def _cmd_inspect(manifest_path: Path) -> int:
    from dcp.manifest import Manifest
    from dcp.wire import intent_id

    m = Manifest.load(manifest_path)
    print(f"device: {m.device_id}  ({m.vendor} / {m.model})")
    print(f"intents: {len(m.intents)}")
    for intent in m.intents.values():
        flags = []
        if intent.idempotent:
            flags.append("idempotent")
        if intent.dry_run:
            flags.append("dry-run")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        print(f"  - {intent.name}  id=0x{intent_id(intent.name):04x}{flag_str}")
        for pname, p in intent.params.items():
            extras = []
            if p.unit:
                extras.append(p.unit)
            if p.range:
                extras.append(f"[{p.range[0]}, {p.range[1]}]")
            extra_str = f"  {{{', '.join(extras)}}}" if extras else ""
            print(f"      · {pname}: {p.type}{extra_str}")
    print(f"events: {len(m.events)}")
    for event in m.events.values():
        print(f"  - {event.name}  id=0x{intent_id(event.name):04x}")
    return 0


def _cmd_serve(
    manifest_path: Path,
    *,
    simulator: bool,
    serial_port: str | None,
    baud: int,
    mqtt: str | None,
    mqtt_prefix: str,
    ble: str | None,
    ble_service: str | None,
    grant: str,
) -> int:
    from dcp.mcp_server import _configure_logging, run_mcp_server

    _configure_logging()
    capabilities = _resolve_capabilities(manifest_path, grant)
    mqtt_host: str | None = None
    mqtt_port = 1883
    if mqtt:
        if ":" in mqtt:
            host, port = mqtt.rsplit(":", 1)
            mqtt_host, mqtt_port = host, int(port)
        else:
            mqtt_host = mqtt
    if ble and not ble_service:
        print("error: --ble requires --ble-service <uuid>", file=sys.stderr)
        return 2
    asyncio.run(
        run_mcp_server(
            manifest_path,
            simulator=simulator,
            serial_port=serial_port,
            baud=baud,
            mqtt_host=mqtt_host,
            mqtt_port=mqtt_port,
            mqtt_prefix=mqtt_prefix,
            ble_address=ble,
            ble_service=ble_service,
            capabilities=capabilities,
        )
    )
    return 0


def _cmd_codegen(manifest_path: Path, out: Path, guard: str | None, stubs: bool) -> int:
    from dcp.codegen import write

    write(manifest_path, out, guard=guard, with_stubs=stubs)
    print(f"wrote {out}", file=sys.stderr)
    return 0


def _resolve_secret(arg_hex: str | None) -> bytes:
    raw = arg_hex or os.environ.get(SECRET_ENV)
    if not raw:
        print(
            f"error: pass --secret-hex or set ${SECRET_ENV}. "
            f"Generate one with `dcp token keygen`.",
            file=sys.stderr,
        )
        sys.exit(2)
    try:
        return bytes.fromhex(raw)
    except ValueError as e:
        print(f"error: secret must be valid hex: {e}", file=sys.stderr)
        sys.exit(2)


def _cmd_token_mint(caps: str, ttl: int, sub: str | None, secret_hex: str | None) -> int:
    from dcp.tokens import mint

    secret = _resolve_secret(secret_hex)
    cap_set = {c.strip() for c in caps.split(",") if c.strip()}
    if not cap_set:
        print("error: at least one capability required", file=sys.stderr)
        return 2
    print(mint(cap_set, secret=secret, ttl_seconds=ttl, subject=sub))
    return 0


def _cmd_token_keygen(n_bytes: int) -> int:
    import secrets as _secrets

    print(_secrets.token_hex(n_bytes))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "serve":
        return _cmd_serve(
            args.manifest,
            simulator=args.simulator,
            serial_port=args.serial,
            baud=args.baud,
            mqtt=args.mqtt,
            mqtt_prefix=args.mqtt_prefix,
            ble=args.ble,
            ble_service=args.ble_service,
            grant=args.grant,
        )
    if args.cmd == "inspect":
        return _cmd_inspect(args.manifest)
    if args.cmd == "codegen":
        return _cmd_codegen(args.manifest, args.out, args.guard, args.stubs)
    if args.cmd == "token":
        if args.token_cmd == "mint":
            return _cmd_token_mint(args.caps, args.ttl, args.sub, args.secret_hex)
        if args.token_cmd == "keygen":
            return _cmd_token_keygen(args.bytes)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
