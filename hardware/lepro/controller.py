"""Configured-device selection and validated Lepro operations."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .cli_adapter import LeproCLIAdapter, LeproCLIError, MAC_PATTERN
from .colors import brightness_to_cli, resolve_color


def device_id(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", str(name).casefold()).strip("_")
    return value or "lepro_light"


class LeproController:
    def __init__(self, config, adapter=None):
        self.config = config
        self.adapter = adapter or LeproCLIAdapter(config)

    def list_devices(self):
        result = []
        for device in self.config.list_devices():
            if not isinstance(device, dict) or not device.get("name") or not device.get("mac"):
                continue
            mac = str(device["mac"])
            if not MAC_PATTERN.fullmatch(mac):
                continue
            credential = Path.home() / ".lepro" / (mac.replace(":", "-").lower() + ".json")
            zb1 = str(device.get("model", "")).casefold() in {"zb1", "rgbic_light_zb1"}
            enabled = device.get("enabled", True) is True
            result.append({
                "device_id": device.get("id") or device_id(device["name"]),
                "name": device["name"],
                "model": device.get("model"),
                "availability": "unknown",
                "bonded": credential.is_file(),
                "enabled": enabled,
                "capabilities": (["power", "brightness", "hsv_color", "status", "diy_effects"]
                                 if zb1 and enabled else []),
            })
        return result

    @staticmethod
    def _has_credentials(device):
        mac = str(device.get("mac", ""))
        return (Path.home() / ".lepro" / (mac.replace(":", "-").lower() + ".json")).is_file()

    def _select(self, requested=None):
        configured = [d for d in self.config.list_devices()
                      if isinstance(d, dict) and d.get("enabled", True) is True]
        devices = [d for d in configured
                   if str(d.get("model", "")).casefold() in {"zb1", "rgbic_light_zb1"}]
        if requested:
            key = str(requested).casefold()
            matches = [d for d in configured if key in {
                str(d.get("id", "")).casefold(), device_id(d.get("name", "")).casefold(),
                str(d.get("name", "")).casefold(),
            }]
            if len(matches) == 1:
                selected = matches[0]
                if str(selected.get("model", "")).casefold() not in {"zb1", "rgbic_light_zb1"}:
                    raise LeproCLIError("unsupported_device", "Only Lepro ZB1 RGB-IC string lights are verified by this CLI. Confirm the model with setup before enabling control.")
                if not self._has_credentials(selected):
                    raise LeproCLIError("device_not_bonded", "This light has no saved Lepro bonding credentials.")
                return selected
            raise LeproCLIError("device_not_found", f"Configured Lepro device '{requested}' was not found.")
        available = [device for device in devices if self._has_credentials(device)]
        if len(available) == 1:
            selected = available[0]
            return selected
        if not available:
            if devices:
                raise LeproCLIError("device_not_bonded", "No configured supported light has saved bonding credentials.")
            if configured:
                raise LeproCLIError("unsupported_device", "No configured device is confirmed as a supported Lepro ZB1 RGB-IC light.")
            raise LeproCLIError("device_not_found", "No Lepro lights are configured.")
        raise LeproCLIError("device_selection_required", "More than one bonded Lepro light is configured; specify device_id.")

    def get_status(self, requested=None):
        device = self._select(requested)
        status = self.adapter.status(device["mac"])
        status["device_id"] = device.get("id") or device_id(device["name"])
        status["device_name"] = device["name"]
        return status

    def turn_on(self, requested=None):
        device = self._select(requested)
        return self.adapter.control(device["mac"], "on")

    def turn_off(self, requested=None):
        device = self._select(requested)
        return self.adapter.control(device["mac"], "off")

    def turn_off_all(self):
        devices = [d for d in self.config.list_devices()
                   if isinstance(d, dict) and d.get("enabled", True) is True
                   and str(d.get("model", "")).casefold() in {"zb1", "rgbic_light_zb1"}
                   and self._has_credentials(d)]
        if not devices:
            raise LeproCLIError("device_not_found", "No enabled, bonded, supported Lepro lights are configured.")
        completed, failures = [], []
        for device in devices:
            try:
                self.adapter.control(device["mac"], "off")
                completed.append(device.get("id") or device_id(device["name"]))
            except LeproCLIError as exc:
                failures.append({"device_id": device.get("id") or device_id(device["name"]),
                                 "category": exc.category, "error": str(exc)})
        return {"success": not failures, "completed": completed, "failures": failures,
                "partial_success": bool(completed and failures)}

    def set_color(self, color, brightness=None, requested=None):
        device = self._select(requested)
        hsv = resolve_color(color)
        if brightness is not None:
            hsv["brightness"] = brightness_to_cli(brightness)
        else:
            hsv["brightness"] = 1000
        return self.adapter.control(device["mac"], "color", hue=hsv["hue"],
                                    saturation=hsv["saturation"], value=hsv["value"],
                                    brightness=hsv["brightness"])

    def set_brightness(self, brightness, requested=None):
        device = self._select(requested)
        percent = brightness_to_cli(brightness)
        current = self.adapter.status(device["mac"])["status"]
        raw_hsv = current.get("d5")
        if not isinstance(raw_hsv, str) or not re.fullmatch(r"[0-9A-Fa-f]{12}", raw_hsv):
            raise LeproCLIError("unsupported_operation", "The device did not report its current HSV color; brightness-only updates are unavailable.")
        hue = int(raw_hsv[0:4], 16)
        saturation = int(raw_hsv[4:8], 16)
        value = int(raw_hsv[8:12], 16)
        return self.adapter.control(device["mac"], "color", hue=hue,
                                    saturation=saturation, value=value,
                                    brightness=percent)

    def probe(self, requested=None):
        """One bounded status connection probe; the CLI does not keep sessions open."""
        return self.get_status(requested)

    def set_effect(self, effect, color="white", brightness=None, requested=None):
        from .cli_adapter import SUPPORTED_EFFECTS
        if effect not in SUPPORTED_EFFECTS:
            raise LeproCLIError("unsupported_effect", "Choose one of the effects exposed by lepro-ctl mode list.")
        device = self._select(requested)
        hsv = resolve_color(color)
        cli_brightness = 1000 if brightness is None else brightness_to_cli(brightness)
        return self.adapter.effect(device["mac"], effect, hue=hsv["hue"],
                                  saturation=hsv["saturation"], value=hsv["value"],
                                  brightness=cli_brightness)
