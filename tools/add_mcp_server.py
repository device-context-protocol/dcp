"""Idempotently add a DCP MCP server entry to Claude Desktop's config.

Cross-platform. Auto-detects the config path:
  - Windows UWP (Microsoft Store install): %LOCALAPPDATA%\\Packages\\Claude_*\\LocalCache\\Roaming\\Claude\\
  - Windows installer:                     %APPDATA%\\Claude\\
  - macOS:                                 ~/Library/Application Support/Claude/
  - Linux:                                 ~/.config/Claude/

Usage:
  python add_mcp_server.py <manifest.yaml> --serial COM5
  python add_mcp_server.py /path/to/lamp.yaml --serial /dev/ttyUSB0 --name my-lamp
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from pathlib import Path


def find_config() -> Path:
    """Locate the Claude Desktop config file in a platform-agnostic way."""
    if platform.system() == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        uwp = list((local / "Packages").glob(
            "Claude_*/LocalCache/Roaming/Claude/claude_desktop_config.json"
        )) if local else []
        if uwp:
            return uwp[0]
        appdata = Path(os.environ.get("APPDATA", ""))
        if appdata:
            return appdata / "Claude" / "claude_desktop_config.json"
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def find_dcp_exe() -> str:
    """Resolve the dcp executable on PATH; fall back to bare 'dcp'."""
    exe = shutil.which("dcp")
    return exe or "dcp"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="Path to a DCP manifest YAML")
    parser.add_argument("--serial", required=True, help="Serial port (e.g. COM5 or /dev/ttyUSB0)")
    parser.add_argument("--name", default="dcp-device", help="MCP server entry name (default: dcp-device)")
    parser.add_argument("--config", type=Path, default=None, help="Override the config file location")
    args = parser.parse_args()

    cfg = args.config or find_config()
    if not cfg.exists():
        print(f"error: Claude config not found at {cfg}", file=sys.stderr)
        print("       launch Claude Desktop at least once, then re-run.", file=sys.stderr)
        return 1

    entry = {
        "command": find_dcp_exe(),
        "args": ["serve", str(Path(args.manifest).resolve()), "--serial", args.serial],
    }

    backup = cfg.with_suffix(".json.bak-dcp")
    if not backup.exists():
        shutil.copyfile(cfg, backup)
        print(f"backed up to {backup}")

    data = json.loads(cfg.read_text(encoding="utf-8"))
    data.setdefault("mcpServers", {})[args.name] = entry

    cfg.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"added/updated MCP server '{args.name}' in {cfg}")
    print(json.dumps(entry, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
