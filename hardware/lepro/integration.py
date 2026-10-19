"""Optional LEPRO registration; no BLE operations during startup."""
import logging
from pathlib import Path

from hardware.lepro.config import LeproConfig

CONFIG = LeproConfig(Path.home() / '.cyn-x' / 'lepro_devices.json')
LOG = logging.getLogger('cynx.lepro')


def register_selected(router):
    """Register a previously selected, authenticated device on *this* router."""
    devices = CONFIG.list_devices()
    if not devices:
        LOG.info('LEPRO unavailable: no selected device; use web discovery and selection')
        return False
    if len(devices) != 1:
        LOG.warning('LEPRO unavailable: ambiguous saved selection (%d devices)', len(devices))
        return False
    device = devices[0]
    if not isinstance(device, dict) or not device.get('name') or not device.get('mac'):
        LOG.warning('LEPRO unavailable: incomplete saved device selection')
        return False
    try:
        from hardware.lepro.lib.lepro.bond import load_creds
        if load_creds(device['mac']) is None:
            LOG.warning('LEPRO unavailable: selected device lacks valid bonding credentials')
            return False
        from tools.lepro_lights import LeproLightsTool
        tool = LeproLightsTool(device['name'], device['mac'])
        router.register_tool(tool)
    except Exception as exc:
        LOG.warning('LEPRO unavailable: device registration failed (%s)', type(exc).__name__)
        return False
    LOG.info('LEPRO registered on active router (device identity redacted)')
    return True


def select_device(router, mac, name):
    """Persist only after a valid authenticated device and tool are ready."""
    from hardware.lepro.lib.lepro.bond import normalize_mac, load_creds
    from tools.lepro_lights import LeproLightsTool
    mac = normalize_mac(mac)
    if load_creds(mac) is None:
        raise ValueError('Device discovered but not bonded; complete one-time LEPRO bonding first')
    tool = LeproLightsTool(name, mac)
    # Avoid erasing the previous selection when initialization fails.
    old = CONFIG.load()
    try:
        CONFIG.save({'devices': {}})
        CONFIG.add_device(name=name, mac=mac, discovered_name=name)
    except Exception:
        CONFIG.save(old)
        raise
    router.register_tool(tool)
    LOG.info('LEPRO selection saved and tool registered on active router')
