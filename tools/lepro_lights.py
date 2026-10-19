"""CYN-X light control using the existing LeproDevice implementation."""
import asyncio
import json
from .base import BaseTool, ToolResult

class LeproLightsTool(BaseTool):
    name = "lepro_lights"
    description = "Control a selected bonded Lepro light. Use only for explicit light requests."

    def __init__(self, device_name, mac):
        from hardware.lepro.devices import LeproDevice
        self.device = LeproDevice(device_name, mac)

    def schema(self):
        return {"type":"function","function":{"name":self.name,"description":self.description,"parameters":{
            "type":"object","properties":{
                "action":{"type":"string","enum":["on","off","color"]},
                "brightness":{"type":"integer","minimum":10,"maximum":1000},
                **{c:{"type":"integer","minimum":0,"maximum":255} for c in ("red","green","blue")}
            },"required":["action"]}}}

    async def execute(self, arguments):
        try:
            if not isinstance(arguments, dict):
                raise ValueError("Arguments must be an object")
            action = arguments.get("action")
            if action not in ("on","off","color"):
                raise ValueError("Unsupported light action")
            brightness = arguments.get("brightness",1000)
            if type(brightness) is not int or not 10 <= brightness <= 1000:
                raise ValueError("Brightness must be an integer from 10 to 1000")
            rgb = {}
            if action == "color":
                for channel in ("red","green","blue"):
                    value = arguments.get(channel)
                    if type(value) is not int or not 0 <= value <= 255:
                        raise ValueError(f"{channel} must be an integer from 0 to 255")
                    rgb[channel] = value
            if action == "on":
                await self.device.turn_on(brightness=brightness)
            elif action == "off":
                await self.device.turn_off()
            else:
                await self.device.set_color_rgb(**rgb, brightness=brightness)
            data = {"action":action, **({"brightness":brightness} if action != "off" else {}), **rgb}
            return ToolResult(True, json.dumps(data), {"success":True,"output":data})
        except Exception as exc:
            return ToolResult(False, str(exc), {"success":False,"error":str(exc)})

    def call(self, args):
        # ChatEngine is synchronous, including its tool execution loop.
        # A dedicated event loop is used in this synchronous entry point.
        return asyncio.run(self.execute(args))
