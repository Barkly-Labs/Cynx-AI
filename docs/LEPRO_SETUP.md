# CYN-X Lepro setup

## Verified hardware scope

The bundled `lepro-local` CLI identifies its control target as Lepro ZB1 RGB-IC string lights. The upstream setup guide marks the ZB1 string light with firmware `3_le_light_zb1_pid_55_v2.3.18` as verified and other Lepro products as unverified. CYN-X therefore enables control only after the operator confirms the model as ZB1. See the [upstream setup guide](https://github.com/lucavb/lepro-local/blob/main/docs/setup.md).

## Windows prerequisites

- Windows 10 or 11 with an enabled Bluetooth Low Energy adapter.
- Python 3.13 or 3.14. The script preserves existing Python installations.
- `uv` for an isolated virtual environment and dependencies.
- Git only if the bundled CLI source is missing and the operator chooses to clone the official repository.

Run from the CYN-X checkout:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_cynx_lepro.ps1
```

The script checks adapter presence, tries BLE discovery, accepts a manually entered MAC when discovery fails, and validates its format. It asks before cloning, confirms the ZB1 model before enabling control, reuses saved bonding credentials, and uses `lepro-bond` only for first-time pairing. It then runs the real status CLI and saves the device only after status succeeds. It does not change Bluetooth settings or issue an on/off test.

The Lepro CLI has no device-discovery command. Discovery comes from CYN-X's BLE service-UUID scanner; manual MAC entry is the fallback.

The CLI entry points verified from the bundled source are `lepro-ctl`, `lepro-status`, and `lepro-bond`. Control syntax is `lepro-ctl --mac <MAC> on`, `... off`, `... color --hue <0–359> --sat <0–1000> --val <0–1000> --brightness <0–1000>`, and `lepro-ctl mode list`. Status is `lepro-status --mac <MAC>`. First-time bonding is `lepro-bond --mac <MAC>`; the setup workflow skips this when saved credentials already exist.

## Packaging note

The vendored `hardware/lepro/pyproject.toml` references a README that is not present at that relative path, and its wheel package declaration does not match the vendored `lib/lepro` source layout. The setup script reports this. Its safe local path creates an isolated dependency environment and runs the source module, so it does not build the broken wheel or silently rewrite project metadata.

## Device configuration

CYN-X device selection is stored in `~/.cyn-x/lepro_devices.json`. Multiple named devices are retained. Lepro bonding credentials remain in the CLI's `~/.lepro/` directory. CYN-X stores the Python executable and CLI source root needed to invoke the CLI; it does not copy credential contents into its configuration.

## Troubleshooting

- **No adapter:** enable Bluetooth in Windows Settings or connect a BLE adapter, then rerun setup.
- **No discovery results:** keep the light powered, close the phone app if it is holding the BLE connection, then enter the MAC manually.
- **Bonding fails:** do not delete the saved credentials. Check that the light is in pairing range and rerun setup; an existing credentials file is reused.
- **Status fails:** verify the model is ZB1, the light is powered and in range, and the saved MAC matches the selected device.
- **CLI dependency error:** rerun setup to reuse and repair the isolated environment; no global Python packages are modified.
- **Other hardware:** remains unverified and is not exposed to the AI control tools.
