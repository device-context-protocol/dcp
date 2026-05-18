"""MCP server wrapper — expose a DCP device as an MCP server.

Requires the ``mcp`` extra::

    pip install -e ".[mcp]"

Each DCP intent in the manifest becomes one MCP tool. The MCP server speaks
stdio, so it plugs into Claude Desktop / any MCP host out of the box.

For v0.1 only the in-process simulator backend is supported. Real transports
(UART, MQTT, BLE) come next on the roadmap.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from dcp.bridge import Bridge
from dcp.manifest import Intent, Manifest, Param
from dcp.simulator import GenericSimulator
from dcp.transports.loopback import LoopbackTransport

log = logging.getLogger("dcp.mcp")


def _param_schema(p: Param) -> dict:
    schema: dict = {}
    if p.type in ("float", "duration"):
        schema["type"] = "number"
    elif p.type == "int":
        schema["type"] = "integer"
    elif p.type == "bool":
        schema["type"] = "boolean"
    elif p.type == "string":
        schema["type"] = "string"
    else:
        schema["type"] = "string"

    if p.range is not None:
        schema["minimum"] = p.range[0]
        schema["maximum"] = p.range[1]

    desc_bits = []
    if p.unit:
        desc_bits.append(f"unit: {p.unit}")
    if p.default is not None:
        schema["default"] = p.default
        desc_bits.append(f"default: {p.default}")
    if desc_bits:
        schema["description"] = "; ".join(desc_bits)
    return schema


def _intent_input_schema(intent: Intent) -> dict:
    properties = {n: _param_schema(p) for n, p in intent.params.items()}
    properties["__dry_run__"] = {
        "type": "boolean",
        "description": "If true, ask the device to predict the result without applying side effects",
        "default": False,
    }
    required = [n for n, p in intent.params.items() if p.default is None]
    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _intent_description(intent: Intent) -> str:
    bits = [f"DCP intent: {intent.name}"]
    if intent.idempotent:
        bits.append("idempotent")
    if intent.dry_run:
        bits.append("dry-run supported")
    if intent.capability:
        bits.append(f"capability: {intent.capability}")
    return " · ".join(bits)


async def run_mcp_server(
    manifest_path: Path,
    *,
    simulator: bool = False,
    serial_port: str | None = None,
    baud: int = 115200,
    mqtt_host: str | None = None,
    mqtt_port: int = 1883,
    mqtt_prefix: str = "dcp/default",
    ble_address: str | None = None,
    ble_service: str | None = None,
    capabilities: set[str] | None = None,
) -> None:
    try:
        from mcp.server.lowlevel import NotificationOptions, Server
        from mcp.server.models import InitializationOptions
        from mcp.server.stdio import stdio_server
        import mcp.types as types
    except ImportError as e:
        raise SystemExit(
            "MCP SDK not installed. Run: pip install -e '.[mcp]'"
        ) from e

    manifest = Manifest.load(manifest_path)

    sim_task: asyncio.Task | None = None
    transport: object

    if simulator:
        host_tr, device_tr = LoopbackTransport.pair()
        sim = GenericSimulator(manifest, device_tr)
        sim_task = asyncio.create_task(sim.run(), name="dcp.simulator")
        transport = host_tr
    elif serial_port:
        from dcp.transports.uart import UartTransport

        uart = UartTransport(serial_port, baud=baud)
        await uart.open()
        transport = uart
    elif mqtt_host:
        from dcp.transports.mqtt import MqttTransport

        mqtt = MqttTransport(mqtt_host, port=mqtt_port, prefix=mqtt_prefix, host_side=True)
        await mqtt.open()
        transport = mqtt
    elif ble_address:
        if not ble_service:
            raise ValueError("ble_service UUID is required when using BLE backend")
        from dcp.transports.ble import BleTransport

        ble = BleTransport(ble_address, service_uuid=ble_service)
        await ble.open()
        transport = ble
    else:
        raise ValueError("one of simulator / serial_port / mqtt_host / ble_address must be provided")

    bridge = Bridge(
        manifest,
        transport,  # type: ignore[arg-type]
        granted_capabilities=capabilities or set(),
    )
    await bridge.start()

    server_name = f"dcp-{manifest.device_id}"
    server: Server = Server(server_name)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=intent.name,
                description=_intent_description(intent),
                inputSchema=_intent_input_schema(intent),
            )
            for intent in manifest.intents.values()
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
        args = dict(arguments or {})
        dry_run = bool(args.pop("__dry_run__", False))
        result = await bridge.call(name, args, dry_run=dry_run)
        body = json.dumps(
            {"status": result.status, "data": result.data},
            default=str,
            ensure_ascii=False,
        )
        return [types.TextContent(type="text", text=body)]

    log.info(
        "dcp-mcp ready · device=%s · intents=%d · capabilities=%s",
        manifest.device_id,
        len(manifest.intents),
        sorted(capabilities or []),
    )

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name=server_name,
                    server_version="0.1.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    finally:
        await bridge.stop()
        if sim_task is not None:
            sim_task.cancel()
            try:
                await sim_task
            except (asyncio.CancelledError, Exception):
                pass


def _configure_logging() -> None:
    # stdio is reserved for the MCP protocol — everything else goes to stderr.
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(name)s %(levelname)s | %(message)s",
    )
