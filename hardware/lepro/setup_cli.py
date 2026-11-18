"""Small setup helper used by setup_cynx_lepro.ps1."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

from hardware.lepro.cli_adapter import LeproCLIAdapter, LeproCLIError
from hardware.lepro.config import LeproConfig

CONFIG = LeproConfig(Path.home() / ".cyn-x" / "lepro_devices.json")


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    configure = sub.add_parser("configure")
    configure.add_argument("python")
    configure.add_argument("cli_root")
    configure.add_argument("module_prefix")
    sub.add_parser("discover")
    bond = sub.add_parser("bond")
    bond.add_argument("mac")
    status = sub.add_parser("status")
    status.add_argument("mac")
    add = sub.add_parser("add")
    add.add_argument("name")
    add.add_argument("mac")
    add.add_argument("model")
    args = parser.parse_args(argv)

    try:
        if args.action == "configure":
            data = CONFIG.load()
            data.update(cli_python=args.python, cli_root=args.cli_root,
                        cli_module_prefix=args.module_prefix, cli_scripts_dir=None)
            CONFIG.save(data)
            result = {"success": True, "configured": True}
        elif args.action == "discover":
            from hardware.lepro.discovery import discover
            result = {"success": True, "devices": asyncio.run(discover())}
        elif args.action == "bond":
            mac = LeproCLIAdapter._validate_mac(args.mac)
            credential = Path.home() / ".lepro" / (mac.replace(":", "-").lower() + ".json")
            if credential.is_file():
                result = {"success": True, "reused_existing_credentials": True}
            else:
                result = LeproCLIAdapter(CONFIG).bond(mac)
                if not credential.is_file():
                    raise LeproCLIError("bond_failed", "The CLI completed without creating bonding credentials.")
                result["credentials_created"] = True
        elif args.action == "status":
            result = LeproCLIAdapter(CONFIG).status(args.mac)
        else:
            if args.model.casefold() not in {"zb1", "rgbic_light_zb1"}:
                raise ValueError("Only Lepro ZB1 RGB-IC string lights are verified by this CLI.")
            result = CONFIG.add_device(args.name, args.mac, model="ZB1")
            result = {"success": True, "device": result}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        category = getattr(exc, "category", "setup_failed")
        print(json.dumps({"success": False, "category": category, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
