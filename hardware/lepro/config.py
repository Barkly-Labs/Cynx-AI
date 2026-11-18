from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any


class LeproConfig:
    """Stores Lepro devices configured for CYN-X."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"devices": {}}

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"devices": {}}

        if not isinstance(data, dict):
            return {"devices": {}}

        data.setdefault("devices", {})
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, indent=2)
                handle.write("\n")
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def add_device(
        self,
        name: str,
        mac: str,
        device_type: str = "lepro",
        discovered_name: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Device name cannot be empty.")
        import re
        if not isinstance(mac, str) or not re.fullmatch(r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}", mac):
            raise ValueError("Device MAC address must use AA:BB:CC:DD:EE:FF format.")

        data = self.load()

        device_id = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_") or "lepro_light"

        device = {
            "id": device_id,
            "name": name,
            "mac": mac.upper(),
            "type": device_type,
            "configured": True,
            "enabled": True,
        }

        if discovered_name:
            device["discovered_name"] = discovered_name
        if model:
            device["model"] = model

        if not isinstance(data.get("devices"), dict):
            raise ValueError("Lepro configuration has an invalid devices section.")
        # Replace only a matching name or MAC. Keep every other configured light.
        for old_name, old_device in list(data["devices"].items()):
            if old_name.casefold() == name.casefold() or (
                isinstance(old_device, dict)
                and str(old_device.get("mac", "")).casefold() == mac.casefold()
            ):
                del data["devices"][old_name]
        data["devices"][name] = device

        self.save(data)

        return device

    def get_device(
        self,
        name: str,
    ) -> dict[str, Any] | None:

        return self.load()["devices"].get(name)

    def list_devices(self) -> list[dict[str, Any]]:
        devices = self.load().get("devices", {})
        return list(devices.values()) if isinstance(devices, dict) else []

    def set_cli_python(self, executable: str) -> None:
        data = self.load()
        data["cli_python"] = str(executable)
        self.save(data)
