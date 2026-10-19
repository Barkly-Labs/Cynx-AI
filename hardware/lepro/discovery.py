"""BLE discovery with protocol-service identification and optional bonded credentials."""
GATT_SERVICE = "1e2aa501-7292-4263-a8f1-be907f039a1f"
from pathlib import Path
import json

def load_creds(mac):
    path = Path.home() / ".lepro" / (mac.replace(":", "-").lower() + ".json")
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None

async def discover(timeout=8):
    from bleak import BleakScanner
    results = []
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    for address, (device, adv) in devices.items():
        services = {s.lower() for s in (getattr(adv, "service_uuids", None) or [])}
        name = getattr(adv, "local_name", None) or getattr(device, "name", None) or "Unknown"
        # The protocol's advertised service is a stronger identifier than a generic name.
        if GATT_SERVICE.lower() not in services:
            continue
        mac = device.address
        results.append({"name": name, "mac": mac, "bonded": load_creds(mac) is not None})
    return results
