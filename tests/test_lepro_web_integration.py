import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from tools.tool_router import ToolRouter
from tools.lepro_lights import LeproLightsTool
from hardware.lepro.config import LeproConfig


class LeproIntegrationTests(unittest.TestCase):
    def setUp(self):
        class Fake:
            def __init__(self): self.calls = []
            def turn_on(self, device_id=None): self.calls.append("on"); return {"success": True}
            def turn_off(self, device_id=None): self.calls.append("off"); return {"success": True}
            def get_status(self, device_id=None): self.calls.append("status"); return {"success": True}
            def set_color(self, color, brightness=None, device_id=None): self.calls.append("color"); return {"success": True}
        self.controller = Fake()
        self.tool = LeproLightsTool(self.controller)

    def test_schema_and_dispatch(self):
        router = ToolRouter()
        router.register_tool(self.tool)
        schema = next(
            t
            for t in router.as_ollama_tools()
            if t["function"]["name"] == "lepro_lights"
        )
        self.assertEqual(schema["function"]["parameters"]["properties"]["action"]["enum"], ["on", "off", "status", "color"])
        result = router.call_tool("lepro_lights", {"action": "on"})
        self.assertTrue(result.success)

    def test_off_and_color(self):
        self.assertTrue(self.tool.call({"action": "off"}).success)
        self.assertTrue(self.tool.call({"action": "color", "color": "pink", "brightness": 20}).success)
        self.assertEqual(len(self.controller.calls), 2)

    def test_validation(self):
        for args in (
            {"action": "bad"},
        ):
            self.assertFalse(self.tool.call(args).success)

    def test_failure_propagation(self):
        self.controller.turn_off = lambda self, device_id=None: (_ for _ in ()).throw(RuntimeError("offline"))
        router = ToolRouter()
        router.register_tool(self.tool)
        result = router.call_tool("lepro_lights", {"action": "off"})
        self.assertFalse(result.success)

    def test_discovery_service(self):
        from hardware.lepro.discovery import discover

        GATT_SERVICE = "1e2aa501-7292-4263-a8f1-be907f039a1f"
        from types import SimpleNamespace
        from unittest.mock import patch

        fake = {
            "AA:BB:CC:DD:EE:FF": (
                SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name="LP"),
                SimpleNamespace(service_uuids=[GATT_SERVICE], local_name="LP"),
            ),
            "11:22:33:44:55:66": (
                SimpleNamespace(address="11:22:33:44:55:66", name="other"),
                SimpleNamespace(service_uuids=[], local_name="other"),
            ),
        }
        with patch.dict(
            "sys.modules",
            {
                "bleak": SimpleNamespace(
                    BleakScanner=SimpleNamespace(discover=AsyncMock(return_value=fake))
                )
            },
        ), patch("hardware.lepro.discovery.load_creds", return_value=None):
            found = asyncio.run(discover())
        self.assertEqual(len(found), 1)
        self.assertFalse(found[0]["bonded"])

    def test_config_persistence(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            config = LeproConfig(Path(tmp) / "lights.json")
            config.add_device("Bedroom", "AA:BB:CC:DD:EE:FF")
            self.assertEqual(
                LeproConfig(Path(tmp) / "lights.json").list_devices()[0]["name"],
                "Bedroom",
            )


if __name__ == "__main__":
    unittest.main()
