import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch
from tools.tool_router import ToolRouter
from tools.lepro_lights import LeproLightsTool
from hardware.lepro.config import LeproConfig

class LeproIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tool = LeproLightsTool.__new__(LeproLightsTool)
        self.tool.device = type('Fake', (), {})()
        self.tool.device.turn_on = AsyncMock()
        self.tool.device.turn_off = AsyncMock()
        self.tool.device.set_color_rgb = AsyncMock()

    def test_schema_and_dispatch(self):
        router = ToolRouter()
        router.register_tool(self.tool)
        schema = next(t for t in router.as_ollama_tools() if t['function']['name'] == 'lepro_lights')
        self.assertEqual(schema['function']['parameters']['properties']['brightness']['maximum'],1000)
        result = router.call_tool('lepro_lights', {'action':'on'})
        self.assertTrue(result.success)
        self.tool.device.turn_on.assert_awaited_once_with(brightness=1000)

    def test_off_and_color(self):
        self.assertTrue(self.tool.call({'action':'off'}).success)
        self.tool.device.turn_off.assert_awaited_once()
        self.assertTrue(self.tool.call({'action':'color','red':255,'green':0,'blue':20,'brightness':400}).success)
        self.tool.device.set_color_rgb.assert_awaited_once_with(red=255,green=0,blue=20,brightness=400)

    def test_validation(self):
        for args in ({'action':'bad'}, {'action':'on','brightness':1001}, {'action':'on','brightness':'200'}, {'action':'color','red':0,'green':1}, {'action':'color','red':256,'green':0,'blue':0}):
            self.assertFalse(self.tool.call(args).success)

    def test_failure_propagation(self):
        self.tool.device.turn_off.side_effect = RuntimeError('offline')
        result = self.tool.call({'action':'off'})
        self.assertFalse(result.success)
        self.assertIn('offline',result.output)

    def test_discovery_service(self):
        from hardware.lepro.discovery import discover
        GATT_SERVICE = "1e2aa501-7292-4263-a8f1-be907f039a1f"
        from types import SimpleNamespace
        from unittest.mock import patch
        fake = {'AA:BB:CC:DD:EE:FF':(SimpleNamespace(address='AA:BB:CC:DD:EE:FF',name='LP'),SimpleNamespace(service_uuids=[GATT_SERVICE],local_name='LP')),
                '11:22:33:44:55:66':(SimpleNamespace(address='11:22:33:44:55:66',name='other'),SimpleNamespace(service_uuids=[],local_name='other'))}
        with patch.dict('sys.modules', {'bleak':SimpleNamespace(BleakScanner=SimpleNamespace(discover=AsyncMock(return_value=fake)))}), patch('hardware.lepro.discovery.load_creds',return_value=None):
            found = asyncio.run(discover())
        self.assertEqual(len(found),1)
        self.assertFalse(found[0]['bonded'])

    def test_config_persistence(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            config = LeproConfig(Path(tmp)/'lights.json')
            config.add_device('Bedroom','AA:BB:CC:DD:EE:FF')
            self.assertEqual(LeproConfig(Path(tmp)/'lights.json').list_devices()[0]['name'],'Bedroom')

if __name__ == '__main__': unittest.main()
