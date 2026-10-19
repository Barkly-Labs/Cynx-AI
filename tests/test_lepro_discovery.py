import asyncio
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
from hardware.lepro.discovery import LeproDiscovery

def fake_modules():
    bond=types.ModuleType("hardware.lepro.lib.lepro.bond")
    bond.load_creds=lambda mac: {"mock": True}
    device=types.ModuleType("hardware.lepro.devices")
    device.LeproDevice=lambda name,mac: types.SimpleNamespace(name=name,mac=mac)
    return {"hardware.lepro.lib.lepro.bond":bond,"hardware.lepro.devices":device}

class DiscoveryTests(unittest.TestCase):
    def test_no_devices(self):
        with tempfile.TemporaryDirectory() as tmp:
            scanner = types.SimpleNamespace(discover=lambda **kw: asyncio.sleep(0, result=[]))
            with patch.dict('sys.modules', {'bleak': types.SimpleNamespace(BleakScanner=scanner), **fake_modules()}):
                with self.assertRaisesRegex(RuntimeError, 'No bonded'):
                    asyncio.run(LeproDiscovery(Path(tmp)/'lights.json').resolve())
    def test_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            devices=[types.SimpleNamespace(name='LP',address=x) for x in ('AA:BB:CC:DD:EE:01','AA:BB:CC:DD:EE:02')]
            scanner=types.SimpleNamespace(discover=lambda **kw: asyncio.sleep(0,result=devices))
            with patch.dict('sys.modules', {'bleak':types.SimpleNamespace(BleakScanner=scanner), **fake_modules()}):
                with self.assertRaisesRegex(RuntimeError,'Multiple bonded'):
                    asyncio.run(LeproDiscovery(Path(tmp)/'lights.json').resolve())
    def test_no_scan_for_saved_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=LeproDiscovery(Path(tmp)/'lights.json')
            d.config.add_device('Desk','AA:BB:CC:DD:EE:01')
            with patch.dict(sys.modules, fake_modules()):
                result=asyncio.run(d.resolve())
                self.assertEqual(result.name,'Desk')
