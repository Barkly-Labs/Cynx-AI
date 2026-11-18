import unittest

from tools.tool_router import ToolRouter
from tools.lepro_lights import LeproLightsTool


class FakeController:
    def __init__(self):
        self.calls = []
        self.error = None

    def _call(self, operation, *args):
        self.calls.append((operation, args))
        if self.error:
            raise self.error
        return {"success": True, "operation": operation}

    def turn_on(self, device_id=None): return self._call("on", device_id)
    def turn_off(self, device_id=None): return self._call("off", device_id)
    def get_status(self, device_id=None): return self._call("status", device_id)
    def set_color(self, color, brightness=None, device_id=None): return self._call("color", color, brightness, device_id)


class LeproTests(unittest.TestCase):
    def setUp(self):
        self.controller = FakeController()
        self.tool = LeproLightsTool(self.controller)
        self.router = ToolRouter()
        self.router.register_tool(self.tool)

    def test_schema_and_allowlisted_actions(self):
        schema = self.router.as_ollama_tools()[0]["function"]["parameters"]
        self.assertEqual(schema["properties"]["action"]["enum"], ["on", "off", "status", "color"])
        for args in ({"action": "on"}, {"action": "off"}, {"action": "color", "color": "pink", "brightness": 20}):
            self.assertTrue(self.router.call_tool("lepro_lights", args).success)
        self.assertEqual(len(self.controller.calls), 3)

    def test_invalid_action_is_rejected(self):
        result = self.tool.call({"action": "arbitrary shell command"})
        self.assertFalse(result.success)
        self.assertEqual(self.controller.calls, [])

    def test_errors_do_not_claim_success(self):
        self.controller.error = RuntimeError("CLI disconnected")
        result = self.tool.call({"action": "off"})
        self.assertFalse(result.success)
        self.assertIn("CLI disconnected", result.output)


if __name__ == "__main__":
    unittest.main()
