"""Register the optional Lepro CLI tools on a CYN-X tool router."""

import logging
from pathlib import Path

from hardware.lepro.config import LeproConfig
from hardware.lepro.controller import LeproController
from tools.lepro_tools import LeproLightsTool, lepro_tools

CONFIG = LeproConfig(Path.home() / ".cyn-x" / "lepro_devices.json")
LOG = logging.getLogger("cynx.lepro")


def register_selected(router):
    """Register tools only when at least one valid, bonded device is saved."""
    devices = CONFIG.list_devices()
    if not devices:
        LOG.info("Lepro tools unavailable: no configured devices")
        return False
    bonded = [device for device in devices if isinstance(device, dict) and device.get("enabled", True)
              and device.get("name") and device.get("mac")
              and str(device.get("model", "")).casefold() in {"zb1", "rgbic_light_zb1"}
              and (Path.home() / ".lepro" / (str(device["mac"]).replace(":", "-").lower() + ".json")).is_file()]
    controller = LeproController(CONFIG)
    available_tools = lepro_tools(controller)
    # Listing is read-only and remains available for configured but unbonded or
    # not-yet-verified devices. Physical control tools require a saved bond and
    # an explicitly confirmed supported model.
    router.register_tool(available_tools[0])
    if not bonded:
        LOG.info("Lepro list tool registered; no configured supported device has saved bond credentials")
        return True
    for tool in available_tools[1:]:
        router.register_tool(tool)
    router.register_tool(LeproLightsTool(controller))
    LOG.info("Lepro CLI tools registered for %d configured device(s)", len(bonded))
    return True


def select_device(router, mac, name, *, model=None):
    """Save a previously bonded device without replacing other configured lights."""
    credential = Path.home() / ".lepro" / (str(mac).replace(":", "-").lower() + ".json")
    if str(model or "").casefold() not in {"zb1", "rgbic_light_zb1"}:
        raise ValueError("This CLI is verified for Lepro ZB1 RGB-IC string lights only; confirm the model before enabling control.")
    if not credential.is_file():
        raise ValueError("Device is not bonded; complete one-time lepro-bond setup first.")
    device = CONFIG.add_device(name=name, mac=mac, discovered_name=name, model="ZB1")
    register_selected(router)
    LOG.info("Lepro device selection saved; device MAC redacted")
    return device
