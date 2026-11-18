import unittest

from tools.tool_router import ToolRouter
from tools.lepro_tools import lepro_tools


class FakeController:
    def __init__(self): self.calls = []
    def turn_on(self, device_id=None): self.calls.append(("on", device_id)); return {"success": True}
    def turn_off(self, device_id=None): self.calls.append(("off", device_id)); return {"success": True}
    def turn_off_all(self): self.calls.append(("all_off",)); return {"success": True}
    def get_status(self, device_id=None): self.calls.append(("status", device_id)); return {"success": True}
    def set_brightness(self, brightness, requested=None): self.calls.append(("brightness", brightness, requested)); return {"success": True}
    def set_color(self, color, brightness=None, requested=None): self.calls.append(("color", color, brightness, requested)); return {"success": True}
    def set_effect(self, effect, color="white", brightness=None, requested=None): self.calls.append(("effect", effect, color, brightness, requested)); return {"success": True}
    def probe(self, device_id=None): self.calls.append(("probe", device_id)); return {"success": True}
    def list_devices(self): return []


class LeproRuntimeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.controller = FakeController()
        self.router = ToolRouter()
        for tool in lepro_tools(self.controller): self.router.register_tool(tool)

    def test_separate_tool_names_and_schema(self):
        schemas = {item["function"]["name"]: item["function"]["parameters"] for item in self.router.as_ollama_tools()}
        self.assertIn("lepro_turn_on", schemas)
        self.assertEqual(schemas["lepro_set_brightness"]["properties"]["brightness"]["maximum"], 100)
        self.assertEqual(schemas["lepro_set_effect"]["properties"]["effect"]["enum"][-1], "CenterIn")

    def test_dispatch_and_unknown_actions(self):
        self.assertTrue(self.router.call_tool("lepro_turn_on", {}).success)
        self.assertTrue(self.router.call_tool("lepro_set_brightness", {"brightness": 20}).success)
        self.assertFalse(self.router.call_tool("lepro_set_brightness", {"brightness": 200}).success)
        self.assertEqual([call[0] for call in self.controller.calls], ["on", "brightness"])


if __name__ == "__main__":
    unittest.main()
