import asyncio
import os
import unittest
import sys
import types
from unittest.mock import patch
from tools.tool_router import ToolRouter
_device_module = types.ModuleType("hardware.lepro.devices")
_device_module.LeproDevice = lambda **kwargs: FakeDevice() if "FakeDevice" in globals() else None
with patch.dict(sys.modules, {"hardware.lepro.devices": _device_module}):
    from tools.lepro_lights import LeproLightsTool

class FakeDevice:
    def __init__(self): self.calls=[]; self.fail=False
    async def turn_on(self, **kw): self.calls.append(('on',kw)); self._fail()
    async def turn_off(self): self.calls.append(('off',{})); self._fail()
    async def set_color_rgb(self, **kw): self.calls.append(('color',kw)); self._fail()
    def _fail(self):
        if self.fail: raise RuntimeError('Bluetooth unavailable')

class LeproTests(unittest.TestCase):
    def setUp(self):
        self.tool=LeproLightsTool.__new__(LeproLightsTool)
        self.tool.device=FakeDevice()
        self.router=ToolRouter()
        self.router.register_tool(self.tool)
    def test_schema(self):
        schema=self.router.as_ollama_tools()[0]['function']
        self.assertEqual(schema['parameters']['properties']['brightness']['maximum'],1000)
        self.assertEqual(schema['parameters']['properties']['red']['maximum'],255)
    def test_actions(self):
        for args in ({'action':'on'}, {'action':'off'}, {'action':'color','red':128,'green':0,'blue':255,'brightness':500}):
            self.assertTrue(self.router.call_tool('lepro_lights',args).success)
        self.assertEqual(len(self.tool.device.calls),3)
    def test_invalid(self):
        for args in ({'action':'invalid'}, {'action':'on','brightness':9}, {'action':'on','brightness':True}, {'action':'color','red':2,'green':3}, {'action':'color','red':256,'green':3,'blue':4}, {'action':'color','red':'x','green':3,'blue':4}):
            self.assertFalse(self.router.call_tool('lepro_lights',args).success)
        self.assertFalse(self.tool.device.calls)
    def test_failure(self):
        self.tool.device.fail=True
        result=self.router.call_tool('lepro_lights',{'action':'off'})
        self.assertFalse(result.success)
        self.assertIn('Bluetooth unavailable',result.output)
    def test_disabled(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertFalse(ToolRouter().register_configured_lepro())
    def test_bad_config(self):
        with patch.dict(os.environ,{'CYNX_LEPRO_NAME':'lamp','CYNX_LEPRO_MAC':'invalid'}):
            self.assertFalse(ToolRouter().register_configured_lepro())

if __name__=='__main__': unittest.main()
