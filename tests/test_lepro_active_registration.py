"""Regression coverage for the active web router's optional LEPRO registration."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

from hardware.lepro.config import LeproConfig
from hardware.lepro import integration
from tools.tool_router import ToolRouter
from tools.lepro_lights import LeproLightsTool
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
        self.config = LeproConfig(Path(self.tmp.name) / 'selection.json')
        self.config.add_device('Bedroom', 'AA:BB:CC:DD:EE:FF')
        self.patch_config = patch.object(integration, 'CONFIG', self.config)
        self.patch_config.start()
        self.addCleanup(self.patch_config.stop)

    def test_missing_credentials_omits_tool_and_preserves_router(self):
        router = ToolRouter()
        with patch.dict(sys.modules, {'hardware.lepro.lib.lepro.bond': bond_module}), patch.object(bond_module, 'load_creds', return_value=None):
            self.assertFalse(integration.register_selected(router))
        self.assertNotIn('lepro_lights', router.tools)

    def test_registered_tool_is_visible_to_chat_engine_and_dispatches(self):
        router = ToolRouter()
        fake_device = type('FakeDevice', (), {})()
        fake_device.turn_off = AsyncMock()
        fake_devices = ModuleType('hardware.lepro.devices')
        fake_devices.LeproDevice = lambda name, mac: fake_device
        with patch.dict(sys.modules, {'hardware.lepro.lib.lepro.bond': bond_module}), \
             patch.object(bond_module, 'load_creds', return_value=object()), \
             patch.dict(sys.modules, {'hardware.lepro.devices': fake_devices}):
            self.assertTrue(integration.register_selected(router))
        engine = ChatEngine.__new__(ChatEngine)
        engine.tool_router = router
        import logging
        engine.logger = logging.getLogger('test.lepro')
        tools = engine._ollama_tools('turn off my lights')
        self.assertIn('lepro_lights', [t['function']['name'] for t in tools])
        self.assertEqual(tools[0]['function']['parameters']['properties']['brightness']['maximum'], 1000)
        result = engine.tool_router.call_tool('lepro_lights', {'action':'off'})
        self.assertTrue(result.success)
        fake_device.turn_off.assert_awaited_once()

    def test_unconfigured_chat_does_not_expose_lepro(self):
        router = ToolRouter()
        engine = ChatEngine.__new__(ChatEngine)
        engine.tool_router = router
        import logging
        engine.logger = logging.getLogger('test.lepro')
        self.assertEqual(engine._ollama_tools('hello'), [])


if __name__ == '__main__':
    unittest.main()
