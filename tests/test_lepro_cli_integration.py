import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hardware.lepro.cli_adapter import LeproCLIAdapter, LeproCLIError
from hardware.lepro.colors import UnsupportedColor, brightness_to_cli, resolve_color
from hardware.lepro.config import LeproConfig
from hardware.lepro.controller import LeproController


class CliAdapterTests(unittest.TestCase):
    def test_allowlisted_cli_uses_argument_array_without_shell(self):
        calls = []

        def runner(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, "Done.\n", "")

        adapter = LeproCLIAdapter(runner=runner, project_root=Path.cwd())
        result = adapter.control("AA:BB:CC:DD:EE:FF", "off")
        self.assertTrue(result["success"])
        args, options = calls[0]
        self.assertIn("off", args)
        self.assertIs(options["shell"], False)
        self.assertEqual(options["capture_output"], True)
        with self.assertRaises(LeproCLIError):
            adapter.control("AA:BB:CC:DD:EE:FF", "off; del *")
        self.assertEqual(len(calls), 1)

    def test_status_requires_json_returned_by_cli(self):
        def runner(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, "Provisioning: ZB1\n{\"d1\":1,\"d5\":\"0000000003E8\"}\n", "")

        result = LeproCLIAdapter(runner=runner).status("aa:bb:cc:dd:ee:ff")
        self.assertEqual(result["status"]["d1"], 1)

        def malformed(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, "Raw response only\n", "")

        with self.assertRaises(LeproCLIError) as err:
            LeproCLIAdapter(runner=malformed).status("AA:BB:CC:DD:EE:FF")
        self.assertEqual(err.exception.category, "malformed_cli_output")

    def test_timeout_is_structured(self):
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

        with self.assertRaises(LeproCLIError) as err:
            LeproCLIAdapter(runner=timeout).control("AA:BB:CC:DD:EE:FF", "on")
        self.assertEqual(err.exception.category, "timeout")

    def test_effect_command_uses_only_cli_allowlist(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, "Done.\n", "")
        with patch("hardware.lepro.cli_adapter.shutil.which", return_value=None):
            adapter = LeproCLIAdapter(runner=runner, project_root=Path.cwd())
            adapter.effect("AA:BB:CC:DD:EE:FF", "Breathe", hue=330,
                           saturation=400, value=900, brightness=300)
            self.assertIn("Breathe", calls[0])
            self.assertIn("diy", calls[0])
            with self.assertRaises(LeproCLIError):
                adapter.effect("AA:BB:CC:DD:EE:FF", "arbitrary", hue=0,
                               saturation=0, value=1000)
        self.assertEqual(len(calls), 1)


class ColorTests(unittest.TestCase):
    def test_named_and_modified_colors(self):
        self.assertEqual(resolve_color("red")["hue"], 0)
        self.assertEqual(resolve_color("dark blue")["value"], 350)
        self.assertLess(resolve_color("soft pink")["saturation"], resolve_color("pink")["saturation"])
        self.assertEqual(resolve_color("hot pink")["saturation"], 1000)

    def test_unsupported_temperature_and_invalid_values(self):
        with self.assertRaises(UnsupportedColor):
            resolve_color("warm white")
        with self.assertRaises(UnsupportedColor):
            resolve_color("ultraviolet")
        with self.assertRaises(UnsupportedColor):
            resolve_color("deep red")
        self.assertEqual(brightness_to_cli(20), 200)
        for invalid in (-1, 101, True, "20"):
            with self.assertRaises(ValueError):
                brightness_to_cli(invalid)


class DeviceConfigurationTests(unittest.TestCase):
    def test_adding_lights_preserves_prior_devices(self):
        with TemporaryDirectory() as temp:
            config = LeproConfig(Path(temp) / "devices.json")
            config.add_device("Bedroom", "AA:BB:CC:DD:EE:01", model="ZB1")
            config.add_device("Office", "AA:BB:CC:DD:EE:02", model="ZB1")
            self.assertEqual({d["name"] for d in config.list_devices()}, {"Bedroom", "Office"})

    def test_brightness_preserves_reported_hsv_and_requires_verified_model(self):
        with TemporaryDirectory() as temp:
            config = LeproConfig(Path(temp) / "devices.json")
            config.add_device("Bedroom", "AA:BB:CC:DD:EE:01", model="ZB1")
            class Adapter:
                def status(self, mac):
                    return {"status": {"d5": "00F003E803E8"}}
                def control(self, mac, action, **kwargs):
                    return {"action": action, **kwargs}
            home = Path(temp)
            cred = home / ".lepro" / "aa-bb-cc-dd-ee-01.json"
            cred.parent.mkdir()
            cred.write_text("{}", encoding="utf-8")
            with patch("hardware.lepro.controller.Path.home", return_value=home):
                result = LeproController(config, Adapter()).set_brightness(20)
            self.assertEqual(result["hue"], 240)
            self.assertEqual(result["saturation"], 1000)
            self.assertEqual(result["value"], 1000)
            self.assertEqual(result["brightness"], 200)

            raw = config.load()
            raw["devices"]["Bedroom"]["model"] = "unknown"
            config.save(raw)
            with patch("hardware.lepro.controller.Path.home", return_value=home), self.assertRaises(LeproCLIError) as err:
                LeproController(config, Adapter()).turn_on()
            self.assertEqual(err.exception.category, "unsupported_device")

    def test_turn_off_all_reports_partial_success(self):
        with TemporaryDirectory() as temp:
            home = Path(temp)
            config = LeproConfig(home / "devices.json")
            config.add_device("Bedroom", "AA:BB:CC:DD:EE:01", model="ZB1")
            config.add_device("Office", "AA:BB:CC:DD:EE:02", model="ZB1")
            creds = home / ".lepro"
            creds.mkdir()
            for mac in ("aa-bb-cc-dd-ee-01", "aa-bb-cc-dd-ee-02"):
                (creds / f"{mac}.json").write_text("{}", encoding="utf-8")
            class Adapter:
                def control(self, mac, action, **kwargs):
                    if mac.endswith("02"):
                        raise LeproCLIError("device_disconnected", "offline")
                    return {"success": True}
            with patch("hardware.lepro.controller.Path.home", return_value=home):
                result = LeproController(config, Adapter()).turn_off_all()
            self.assertFalse(result["success"])
            self.assertTrue(result["partial_success"])
            self.assertEqual(len(result["completed"]), 1)
            self.assertEqual(len(result["failures"]), 1)


if __name__ == "__main__":
    unittest.main()
