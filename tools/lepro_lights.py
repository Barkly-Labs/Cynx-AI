
from __future__ import annotations

from typing import Any

from hardware.lepro.devices import LeproDevice

from .base import BaseTool, ToolResult


class LeproLightsTool(BaseTool):
    """CYN-X tool for controlling Lepro lights."""

    name = "lepro_lights"
    description = (
        "Control a bonded Lepro light device connected to CYN-X "
        "over Bluetooth."
    )

    def __init__(
        self,
        device_name: str,
        mac: str,
    ):
        self.device = LeproDevice(
            name=device_name,
            mac=mac,
        )

    def schema(self) -> dict[str, Any]:
        """Return the tool schema exposed to CYN."""

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "on",
                                "off",
                                "color",
                            ],
                            "description": (
                                "The light action to perform."
                            ),
                        },
                        "brightness": {
                            "type": "integer",
                            "minimum": 10,
                            "maximum": 1000,
                            "description": (
                                "Brightness from 10 to 1000."
                            ),
                        },
                        "red": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 255,
                            "description": "Red value from 0 to 255.",
                        },
                        "green": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 255,
                            "description": "Green value from 0 to 255.",
                        },
                        "blue": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 255,
                            "description": "Blue value from 0 to 255.",
                        },
                    },
                    "required": [
                        "action",
                    ],
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Validate model arguments before any Bluetooth operation."""
        if not isinstance(arguments, dict):
            return ToolResult(False, "LEPRO arguments must be an object")
        action = arguments.get("action")
        if action not in ("on", "off", "color"):
            return ToolResult(False, f"Unsupported LEPRO action: {action!r}")

        def integer(key: str, default: int | None, low: int, high: int) -> int:
            value = arguments.get(key, default)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{key} must be an integer from {low} to {high}")
            return value

        try:
            if action == "off":
                await self.device.turn_off()
                return ToolResult(True, "LEPRO lights turned off", {"action": "off"})
            brightness = integer("brightness", 1000, 10, 1000)
            if action == "on":
                await self.device.turn_on(brightness=brightness)
                return ToolResult(True, "LEPRO lights turned on", {"action": "on", "brightness": brightness})
            red = integer("red", None, 0, 255)
            green = integer("green", None, 0, 255)
            blue = integer("blue", None, 0, 255)
            await self.device.set_color_rgb(red=red, green=green, blue=blue, brightness=brightness)
            return ToolResult(True, "LEPRO color set", {"action": "color", "red": red, "green": green, "blue": blue, "brightness": brightness})
        except Exception as exc:
            return ToolResult(False, f"LEPRO operation failed: {exc}")
