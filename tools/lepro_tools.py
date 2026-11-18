"""CYN-X BaseTool wrappers for the validated Lepro controller."""

from __future__ import annotations

import json
import logging

from tools.base import BaseTool, ToolResult
from hardware.lepro.cli_adapter import LeproCLIError
from hardware.lepro.colors import UnsupportedColor

LOG = logging.getLogger("cynx.lepro")


class LeproActionTool(BaseTool):
    def __init__(self, controller, name, description, properties=None, required=None, action=None):
        self.controller = controller
        self.name = name
        self.description = description
        self.properties = properties or {}
        self.required = required or []
        self.action = action

    def schema(self):
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": {"type": "object", "properties": self.properties,
                           "required": self.required},
        }}

    def call(self, args):
        if not isinstance(args, dict):
            return ToolResult(False, "Lepro tool arguments must be an object.", {"category": "invalid_arguments"})
        try:
            if args.get("device_id") is not None and not isinstance(args.get("device_id"), str):
                raise ValueError("device_id must be a configured device name or ID.")
            if self.action == "brightness":
                value = args.get("brightness")
                if type(value) is not int or not 0 <= value <= 100:
                    raise ValueError("Brightness must be an integer from 0 to 100 percent.")
            if self.action == "color":
                if not isinstance(args.get("color"), str):
                    raise ValueError("color must be a supported color name.")
                value = args.get("brightness")
                if value is not None and (type(value) is not int or not 0 <= value <= 100):
                    raise ValueError("Brightness must be an integer from 0 to 100 percent.")
            if self.action == "list":
                result = {"devices": self.controller.list_devices()}
            else:
                device_id = args.get("device_id")
                if self.action == "status":
                    result = self.controller.get_status(device_id)
                elif self.action == "on":
                    result = self.controller.turn_on(device_id)
                elif self.action == "off":
                    result = self.controller.turn_off(device_id)
                elif self.action == "all_off":
                    result = self.controller.turn_off_all()
                elif self.action == "brightness":
                    brightness = args.get("brightness")
                    result = self.controller.set_brightness(brightness, device_id)
                elif self.action == "color":
                    result = self.controller.set_color(args.get("color"), args.get("brightness"), device_id)
                elif self.action == "effect":
                    result = self.controller.set_effect(args.get("effect"), args.get("color", "white"), args.get("brightness"), device_id)
                elif self.action == "reconnect":
                    result = self.controller.probe(device_id)
                    result["note"] = "One-shot BLE status probe succeeded; the CLI does not keep a connection open."
                else:
                    raise LeproCLIError("unsupported_operation", "Unsupported Lepro operation.")
            output = json.dumps(result, ensure_ascii=False)
            success = not isinstance(result, dict) or result.get("success") is not False
            LOG.info("lepro_tool name=%s success=%s", self.name, str(success).lower())
            return ToolResult(success, output, {"success": success, "result": result})
        except LeproCLIError as exc:
            LOG.warning("lepro_tool name=%s success=false category=%s", self.name, exc.category)
            payload = {"success": False, "category": exc.category, "error": str(exc)}
            return ToolResult(False, json.dumps(payload, ensure_ascii=False), payload)
        except UnsupportedColor as exc:
            payload = {"success": False, "category": "unsupported_color", "error": str(exc)}
            LOG.warning("lepro_tool name=%s success=false category=unsupported_color", self.name)
            return ToolResult(False, json.dumps(payload, ensure_ascii=False), payload)
        except (TypeError, ValueError) as exc:
            payload = {"success": False, "category": "invalid_arguments", "error": str(exc)}
            LOG.warning("lepro_tool name=%s success=false category=invalid_arguments", self.name)
            return ToolResult(False, json.dumps(payload, ensure_ascii=False), payload)
        except Exception as exc:
            payload = {"success": False, "category": "cli_execution_failed", "error": str(exc)[:500]}
            LOG.warning("lepro_tool name=%s success=false category=cli_execution_failed", self.name)
            return ToolResult(False, json.dumps(payload, ensure_ascii=False), payload)


def lepro_tools(controller):
    device_id = {"device_id": {"type": "string", "description": "Configured device name or ID; optional only when exactly one light is configured."}}
    return [
        LeproActionTool(controller, "lepro_list_devices", "List configured Lepro lights, saved bonding state, and verified control capabilities.", action="list"),
        LeproActionTool(controller, "lepro_get_status", "Query a Lepro light over BLE. Report only fields returned by the device.", device_id, action="status"),
        LeproActionTool(controller, "lepro_turn_on", "Turn on a configured Lepro light.", device_id, action="on"),
        LeproActionTool(controller, "lepro_turn_off", "Turn off a configured Lepro light.", device_id, action="off"),
        LeproActionTool(controller, "lepro_turn_off_all", "Turn off every enabled, bonded supported Lepro light. Use only when the user clearly asks to turn all lights or everything off.", action="all_off"),
        LeproActionTool(controller, "lepro_set_brightness", "Set Lepro light brightness from 0 to 100 percent. Reads current HSV first; returns an error if the CLI cannot preserve the current color.", {**device_id, "brightness": {"type": "integer", "minimum": 0, "maximum": 100}}, ["brightness"], "brightness"),
        LeproActionTool(controller, "lepro_set_color", "Set a supported named color. Supported names include red, orange, yellow, green, teal, cyan, blue, purple, lavender, pink, and white. Warm/cool color temperature is unsupported.", {**device_id, "color": {"type": "string"}, "brightness": {"type": "integer", "minimum": 0, "maximum": 100}}, ["color"], "color"),
        LeproActionTool(controller, "lepro_set_effect", "Apply a supported ZB1 DIY effect. Valid effects: Steady, Breathe, Gradient, Leftward, Rightward, Circle, Flash, CenterOut, CenterIn.", {**device_id, "effect": {"type": "string", "enum": ["Steady", "Breathe", "Gradient", "Leftward", "Rightward", "Circle", "Flash", "CenterOut", "CenterIn"]}, "color": {"type": "string"}, "brightness": {"type": "integer", "minimum": 0, "maximum": 100}}, ["effect"], "effect"),
        LeproActionTool(controller, "lepro_reconnect", "Run one bounded status probe to check whether a configured Lepro light can be reached over BLE; the CLI does not maintain a persistent connection.", device_id, action="reconnect"),
    ]


class LeproLightsTool(LeproActionTool):
    """Compatibility tool name retained for existing CYN-X prompts and callers."""
    def __init__(self, controller):
        super().__init__(controller, "lepro_lights", "Control a configured Lepro light using an allowlisted action.", {
            "action": {"type": "string", "enum": ["on", "off", "status", "color"]},
            "device_id": {"type": "string"}, "color": {"type": "string"},
            "brightness": {"type": "integer", "minimum": 0, "maximum": 100},
        }, ["action"])

    def call(self, args):
        if not isinstance(args, dict):
            return ToolResult(False, "Lepro tool arguments must be an object.")
        action = args.get("action")
        controller = self.controller
        try:
            if args.get("device_id") is not None and not isinstance(args.get("device_id"), str):
                raise ValueError("device_id must be a configured device name or ID.")
            if action == "on": result = controller.turn_on(args.get("device_id"))
            elif action == "off": result = controller.turn_off(args.get("device_id"))
            elif action == "all_off": result = controller.turn_off_all()
            elif action == "status": result = controller.get_status(args.get("device_id"))
            elif action == "color": result = controller.set_color(args.get("color"), args.get("brightness"), args.get("device_id"))
            elif action == "effect": result = controller.set_effect(args.get("effect"), args.get("color", "white"), args.get("brightness"), args.get("device_id"))
            else: raise LeproCLIError("unsupported_operation", "Unsupported Lepro action.")
            return ToolResult(True, json.dumps(result), {"success": True, "result": result})
        except UnsupportedColor as exc:
            payload = {"success": False, "category": "unsupported_color", "error": str(exc)}
            return ToolResult(False, json.dumps(payload), payload)
        except (LeproCLIError, TypeError, ValueError) as exc:
            category = getattr(exc, "category", "invalid_arguments")
            payload = {"success": False, "category": category, "error": str(exc)}
            return ToolResult(False, json.dumps(payload), payload)
        except Exception as exc:
            payload = {"success": False, "category": "cli_execution_failed", "error": str(exc)[:500]}
            return ToolResult(False, json.dumps(payload), payload)
