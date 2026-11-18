"""Safe subprocess adapter for the bundled lepro-local CLI."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import colorsys
from pathlib import Path
from typing import Any

LOG = logging.getLogger("cynx.lepro")
MAC_PATTERN = re.compile(r"^[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}$")
SUPPORTED_EFFECTS = ("Steady", "Breathe", "Gradient", "Leftward", "Rightward", "Circle", "Flash", "CenterOut", "CenterIn")


class LeproCLIError(RuntimeError):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


class LeproCLIAdapter:
    """Builds fixed CLI argument vectors; model text is never a command."""

    TIMEOUT_SECONDS = 40

    def __init__(self, config=None, *, runner=subprocess.run, project_root=None):
        self.config = config
        self.runner = runner
        self.project_root = Path(project_root or Path(__file__).resolve().parents[1])

    def _python(self) -> str:
        configured = os.environ.get("CYNX_LEPRO_PYTHON")
        if not configured and self.config is not None:
            configured = self.config.load().get("cli_python")
        return str(configured or sys.executable)

    def _settings(self) -> dict[str, Any]:
        return self.config.load() if self.config is not None else {}

    def _command(self, command: str) -> tuple[list[str], dict[str, str]]:
        settings = self._settings()
        cli_root = Path(settings["cli_root"]) if settings.get("cli_root") else None
        if settings.get("cli_scripts_dir"):
            scripts = Path(settings["cli_scripts_dir"])
            suffix = ".exe" if os.name == "nt" else ""
            local_exe = scripts / (command + suffix)
            if local_exe.is_file():
                return [str(local_exe)], dict(os.environ)
        module_leaf = {"lepro-ctl": "ctl", "lepro-status": "status", "lepro-bond": "bond"}.get(command)
        prefix = settings.get("cli_module_prefix")
        if not prefix:
            exe = shutil.which(command)
            if exe:
                return [exe], dict(os.environ)
            prefix = "hardware.lepro.lib.lepro.cli"
        module = f"{prefix}.{module_leaf}" if module_leaf else None
        if module is None:
            raise LeproCLIError("cli_unavailable", "Unsupported Lepro CLI operation.")

        env = dict(os.environ)
        root = str(cli_root or self.project_root)
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = root + (os.pathsep + existing if existing else "")
        return [self._python(), "-m", module], env

    def _run(self, operation: str, args: list[str], *, timeout=None) -> dict[str, Any]:
        command, env = self._command(operation)
        settings = self._settings()
        cli_root = settings.get("cli_root")
        cwd = str(Path(cli_root)) if cli_root else str(self.project_root)
        started = time.monotonic()
        try:
            result = self.runner(
                command + args,
                cwd=cwd,
                env=env,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout or self.TIMEOUT_SECONDS,
                check=False,
            )
        except FileNotFoundError as exc:
            raise LeproCLIError("cli_unavailable", "Lepro CLI Python environment was not found.") from exc
        except subprocess.TimeoutExpired as exc:
            raise LeproCLIError("timeout", "Lepro CLI timed out while contacting the light.") from exc
        except OSError as exc:
            raise LeproCLIError("cli_execution_failed", f"Lepro CLI could not start: {exc}") from exc

        duration = round(time.monotonic() - started, 3)
        LOG.info("lepro_cli operation=%s exit_code=%s duration_seconds=%.3f", operation,
                 result.returncode, duration)
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if result.returncode != 0:
            message = stderr or stdout or f"Lepro CLI exited with code {result.returncode}."
            lowered = message.casefold()
            category = "cli_execution_failed"
            if "no credentials" in lowered or "not bonded" in lowered:
                category = "device_not_bonded"
            elif "light not found" in lowered or "device not found" in lowered:
                category = "device_disconnected"
            elif "bluetooth" in lowered and ("unavailable" in lowered or "adapter" in lowered):
                category = "bluetooth_unavailable"
            elif "no module named" in lowered or "modulenotfounderror" in lowered:
                category = "cli_unavailable"
                message = "Lepro CLI dependency is missing from its configured Python environment. Run the CYN-X Lepro setup script."
            raise LeproCLIError(category, message[:500])
        return {"stdout": stdout, "stderr": stderr, "duration_seconds": duration}

    @staticmethod
    def _validate_mac(mac: str) -> str:
        if not isinstance(mac, str) or not MAC_PATTERN.fullmatch(mac):
            raise LeproCLIError("invalid_device", "Configured device MAC address is invalid.")
        return mac.upper()

    def control(self, mac: str, action: str, *, hue=None, saturation=1000, value=1000,
                brightness=1000) -> dict[str, Any]:
        mac = self._validate_mac(mac)
        args = ["--mac", mac]
        if action in {"on", "off"}:
            args.append(action)
        elif action == "color":
            if type(hue) not in (int, float) or not 0 <= hue < 360:
                raise LeproCLIError("invalid_color", "Hue must be between 0 and 359.")
            for name, number in (("saturation", saturation), ("value", value), ("brightness", brightness)):
                if type(number) is not int or not 0 <= number <= 1000:
                    raise LeproCLIError("invalid_color", f"{name.title()} must be from 0 to 1000.")
            args += ["color", "--hue", str(hue), "--sat", str(saturation),
                     "--val", str(value), "--brightness", str(brightness)]
        else:
            raise LeproCLIError("unsupported_operation", "Unsupported Lepro CLI action.")
        result = self._run("lepro-ctl", args)
        return {"success": True, "action": action, "device_mac": mac,
                "cli_output": result["stdout"], "duration_seconds": result["duration_seconds"]}

    def status(self, mac: str) -> dict[str, Any]:
        mac = self._validate_mac(mac)
        result = self._run("lepro-status", ["--mac", mac])
        lines = [line.strip() for line in result["stdout"].splitlines() if line.strip()]
        if not lines:
            raise LeproCLIError("malformed_cli_output", "Lepro status CLI returned no status data.")
        try:
            payload = json.loads(lines[-1])
        except (ValueError, TypeError) as exc:
            raise LeproCLIError("malformed_cli_output", "Lepro status CLI returned unparseable status data.") from exc
        if not isinstance(payload, dict):
            raise LeproCLIError("malformed_cli_output", "Lepro status CLI returned an unexpected data shape.")
        return {"success": True, "device_mac": mac, "status": payload,
                "duration_seconds": result["duration_seconds"]}

    def effect(self, mac: str, effect: str, *, hue: int, saturation: int,
               value: int, brightness: int = 1000) -> dict[str, Any]:
        mac = self._validate_mac(mac)
        if effect not in SUPPORTED_EFFECTS:
            raise LeproCLIError("unsupported_effect", "Effect is not in the Lepro CLI allowlist.")
        for field, number in (("hue", hue), ("saturation", saturation),
                              ("value", value), ("brightness", brightness)):
            max_value = 359 if field == "hue" else 1000
            if type(number) is not int or not 0 <= number <= max_value:
                raise LeproCLIError("invalid_arguments", f"{field} must be from 0 to {max_value}.")
        red, green, blue = colorsys.hsv_to_rgb(hue / 360, saturation / 1000, value / 1000)
        color = "{:02X}{:02X}{:02X}".format(round(red * 255), round(green * 255), round(blue * 255))
        args = ["--mac", mac, "mode", "play", "diy", "--effect", effect,
                "--color", color, "--brightness", str(brightness)]
        result = self._run("lepro-ctl", args)
        return {"success": True, "action": "effect", "effect": effect,
                "device_mac": mac, "cli_output": result["stdout"],
                "duration_seconds": result["duration_seconds"]}

    def bond(self, mac: str) -> dict[str, Any]:
        mac = self._validate_mac(mac)
        return self._run("lepro-bond", ["--mac", mac])
