"""Regression coverage for the active web router's optional LEPRO registration."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

from hardware.lepro.config import LeproConfig
from hardware.lepro import integration
from tools.tool_router import ToolRouter
from ai.chat_engine import ChatEngine
import hardware.lepro as lepro_package
from types import ModuleType
import sys

bond_module = ModuleType("hardware.lepro.lib.lepro.bond")
bond_module.load_creds = lambda mac: None


class ActiveRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = LeproConfig(Path(self.tmp.name) / "selection.json")
        self.config.add_device("Bedroom", "AA:BB:CC:DD:EE:FF", model="ZB1")
        self.patch_config = patch.object(integration, "CONFIG", self.config)
        self.patch_config.start()
        self.addCleanup(self.patch_config.stop)

    def test_missing_credentials_omits_tool_and_preserves_router(self):
        router = ToolRouter()
        with patch.dict(
            sys.modules, {"hardware.lepro.lib.lepro.bond": bond_module}
        ), patch.object(bond_module, "load_creds", return_value=None):
            self.assertTrue(integration.register_selected(router))
        self.assertIn("lepro_list_devices", router.tools)
        self.assertNotIn("lepro_turn_on", router.tools)

    def test_registered_tool_is_visible_to_chat_engine_and_dispatches(self):
        router = ToolRouter()
        home = Path(self.tmp.name)
        credential = home / ".lepro" / "aa-bb-cc-dd-ee-ff.json"
        credential.parent.mkdir()
        credential.write_text("{}", encoding="utf-8")
        fake_controller = type("FakeController", (), {
            "turn_off": lambda self, device_id=None: {"success": True},
            "list_devices": lambda self: [],
        })()
        with patch("hardware.lepro.integration.Path.home", return_value=home), patch(
            "hardware.lepro.integration.LeproController", return_value=fake_controller
        ):
            self.assertTrue(integration.register_selected(router))
        engine = ChatEngine.__new__(ChatEngine)
        engine.tool_router = router
        import logging

        engine.logger = logging.getLogger("test.lepro")
        engine.prompt_builder = type("PromptBuilder", (), {"personality_arch": "v2"})()
        tools = engine._ollama_tools("turn off my lights")
        self.assertEqual([t["function"]["name"] for t in tools], ["lepro_turn_off"])
        all_off = engine._ollama_tools("turn everything off")
        self.assertEqual([t["function"]["name"] for t in all_off], ["lepro_turn_off_all"])
        result = engine.tool_router.call_tool("lepro_turn_off", {})
        self.assertTrue(result.success)

    def test_unconfigured_chat_does_not_expose_lepro(self):
        router = ToolRouter()
        engine = ChatEngine.__new__(ChatEngine)
        engine.tool_router = router
        import logging

        engine.logger = logging.getLogger("test.lepro")
        engine.prompt_builder = type("PromptBuilder", (), {"personality_arch": "v2"})()
        self.assertEqual(engine._ollama_tools("hello"), [])


if __name__ == "__main__":
    unittest.main()
