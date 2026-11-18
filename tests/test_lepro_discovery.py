import asyncio
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from hardware.lepro.discovery import GATT_SERVICE, discover


class DiscoveryTests(unittest.TestCase):
    def test_filters_by_lepro_service_and_reports_saved_bond_state(self):
        devices = {
            "AA:BB:CC:DD:EE:01": (
                types.SimpleNamespace(address="AA:BB:CC:DD:EE:01", name="LP light"),
                types.SimpleNamespace(service_uuids=[GATT_SERVICE], local_name="Bedroom"),
            ),
            "AA:BB:CC:DD:EE:02": (
                types.SimpleNamespace(address="AA:BB:CC:DD:EE:02", name="Other"),
                types.SimpleNamespace(service_uuids=["00000000-0000-0000-0000-000000000000"], local_name="Other"),
            ),
        }
        bleak = types.ModuleType("bleak")
        bleak.BleakScanner = types.SimpleNamespace(discover=AsyncMock(return_value=devices))
        with patch.dict(sys.modules, {"bleak": bleak}), patch(
            "hardware.lepro.discovery.load_creds", return_value={"saved": True}
        ):
            found = asyncio.run(discover(timeout=1))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["name"], "Bedroom")
        self.assertTrue(found[0]["bonded"])

    def test_no_matching_devices_returns_empty_list(self):
        bleak = types.ModuleType("bleak")
        bleak.BleakScanner = types.SimpleNamespace(discover=AsyncMock(return_value={}))
        with patch.dict(sys.modules, {"bleak": bleak}):
            self.assertEqual(asyncio.run(discover(timeout=1)), [])


if __name__ == "__main__":
    unittest.main()
