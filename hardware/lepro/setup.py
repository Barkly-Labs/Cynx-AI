"""Interactive Lepro setup that uses the allowlisted upstream CLI."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .cli_adapter import LeproCLIAdapter, LeproCLIError
from .config import LeproConfig
from .discovery import discover


class LeproSetup:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = Path(base_dir or Path(__file__).resolve().parent)
        self.config = LeproConfig(Path.home() / ".cyn-x" / "lepro_devices.json")
        self.cli = LeproCLIAdapter(self.config)

    async def run(self) -> dict[str, Any]:
        print("\n=== CYN-X LEPRO SETUP ===\n")
        if not (self.base_dir / "lib" / "lepro" / "cli" / "ctl.py").is_file():
            return self.fail("cli", "The bundled lepro-local CLI source is missing.")
        try:
            devices = await discover()
        except Exception as exc:
            return self.fail("discovery", str(exc))
        if not devices:
            return self.fail("discovery", "No compatible Lepro BLE devices found; verify Bluetooth and try manual setup from PowerShell.")

        for index, device in enumerate(devices, start=1):
            print(f"[{index}] {device['name']} ({device['mac']}) bonded={device['bonded']}")
        try:
            selected = devices[int(input("Select a light: ").strip()) - 1]
        except (ValueError, IndexError):
            return self.fail("selection", "Please select one listed device.")
        name = input(f"Name this device [{selected['name']}]: ").strip() or selected["name"]
        if input("Confirm this is a Lepro ZB1 RGB-IC string light (y/N): ").strip().lower() not in {"y", "yes"}:
            return self.fail("model", "Only Lepro ZB1 RGB-IC string lights are verified by this CLI.")

        mac = selected["mac"]
        credential = Path.home() / ".lepro" / (mac.replace(":", "-").lower() + ".json")
        try:
            if credential.is_file():
                print("Existing bonding credentials found; reusing them.")
            else:
                print("Starting one-time Bluetooth bonding through lepro-bond.")
                self.cli.bond(mac)
                if not credential.is_file():
                    raise LeproCLIError("bond_failed", "The CLI did not create bonding credentials.")
            status = self.cli.status(mac)
            device = self.config.add_device(name, mac, discovered_name=selected["name"], model="ZB1")
        except Exception as exc:
            return self.fail(getattr(exc, "category", "setup"), str(exc))

        print(f"Setup complete: {name} ({mac}); status received from the device.")
        return {"success": True, "stage": "complete", "device": device,
                "status": status["status"]}

    @staticmethod
    def fail(stage: str, message: str) -> dict[str, Any]:
        print(f"Setup failed at {stage}: {message}")
        return {"success": False, "stage": stage, "message": message}


def main() -> None:
    result = asyncio.run(LeproSetup().run())
    raise SystemExit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
