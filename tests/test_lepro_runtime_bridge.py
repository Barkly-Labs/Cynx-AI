import asyncio
import unittest
from unittest.mock import AsyncMock
from tools.tool_router import ToolRouter
from tools.lepro_lights import LeproLightsTool

class LeproRuntimeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tool = LeproLightsTool.__new__(LeproLightsTool)
        self.tool.device = type('FakeDevice', (), {})()
        self.tool.device.turn_on = AsyncMock()
        self.tool.device.turn_off = AsyncMock()
        self.tool.device.set_color_rgb = AsyncMock()
        self.router = ToolRouter()
        self.router.register_tool(self.tool)

    def test_schema_and_dispatch(self):
        schema = next(s for s in self.router.as_ollama_tools() if s['function']['name']=='lepro_lights')
        self.assertEqual(schema['function']['parameters']['properties']['brightness']['maximum'], 1000)
        result = self.router.call_tool('lepro_lights', {'action':'color','red':255,'green':0,'blue':100})
        self.assertTrue(result.success)
        self.tool.device.set_color_rgb.assert_awaited_once_with(red=255,green=0,blue=100,brightness=1000)

    def test_dispatch_from_active_event_loop(self):
        async def invoke():
            return self.router.call_tool('lepro_lights', {'action':'on','brightness':400})
        result = asyncio.run(invoke())
        self.assertTrue(result.success)
        self.tool.device.turn_on.assert_awaited_once_with(brightness=400)

    def test_error_does_not_claim_success(self):
        self.tool.device.turn_off.side_effect = RuntimeError('Bluetooth disconnected')
        result = self.router.call_tool('lepro_lights', {'action':'off'})
        self.assertFalse(result.success)
        self.assertFalse(result.metadata['success'])

    def test_invalid_arguments_never_touch_device(self):
        result = self.router.call_tool('lepro_lights', {'action':'color','red':256,'green':0,'blue':0})
        self.assertFalse(result.success)
        self.tool.device.set_color_rgb.assert_not_awaited()

if __name__ == '__main__': unittest.main()
