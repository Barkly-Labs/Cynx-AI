CYN-X Lepro Integration Patch

Apply this patch by extracting the archive into the CYN-X repository root and allowing the listed files to merge/overwrite. The ZIP preserves repository-relative paths.

The patch adds CLI-backed Lepro control, setup guidance, AI tool registration/routing, web integration, and related tests. It intentionally excludes local bonded-device data (hardware/lepro/devices.json).

After applying, run the project's test suite for the Lepro integration. Hardware control requires a bonded, supported Lepro ZB1 device and the CLI dependencies installed by setup_cynx_lepro.ps1.
