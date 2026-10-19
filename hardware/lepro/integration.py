"""Shared optional Lepro registration for supported CYN-X entry points."""
from pathlib import Path
from hardware.lepro.config import LeproConfig

CONFIG = LeproConfig(Path.home() / ".cyn-x" / "lepro_devices.json")

def register_selected(router):
    devices = CONFIG.list_devices()
    if not devices:
        return False
    device = devices[0]
    from tools.lepro_lights import LeproLightsTool
    from hardware.lepro.lib.lepro.bond import load_creds
    if load_creds(device["mac"]) is None:
        return False
    router.register_tool(LeproLightsTool(device["name"], device["mac"]))
    return True

def select_device(router, mac, name):
    from hardware.lepro.lib.lepro.bond import normalize_mac, load_creds
    from tools.lepro_lights import LeproLightsTool
    mac = normalize_mac(mac)
    if load_creds(mac) is None:
        raise ValueError("Device is discoverable but not bonded. Bond it once using the existing Lepro CLI.")
    CONFIG.save({"devices": {}})
    CONFIG.add_device(name=name, mac=mac, discovered_name=name)
    router.register_tool(LeproLightsTool(name, mac))
