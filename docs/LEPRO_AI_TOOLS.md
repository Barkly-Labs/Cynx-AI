# CYN-X Lepro AI tools

Lighting tools are exposed only for enabled, bonded devices confirmed as Lepro ZB1 RGB-IC string lights. In V2 personality architecture, CYN-X offers only lighting tools relevant to an explicit lighting request.

| Tool | Behavior |
| --- | --- |
| `lepro_list_devices` | Lists saved device IDs/names, model, saved-bond presence, and verified capability names. Reachability is `unknown` until a status request succeeds. |
| `lepro_get_status` | Runs the CLI status query and returns parsed device fields only. It does not guess power or color if the device omits them. |
| `lepro_turn_on` / `lepro_turn_off` | Runs the matching `lepro-ctl` power operation. |
| `lepro_turn_off_all` | Turns off all enabled, bonded ZB1 lights only when the user clearly asks for all lights or says “turn everything off.” Reports partial success per device. |
| `lepro_set_brightness` | Accepts an integer percentage from 0 to 100, reads the current HSV state, preserves hue/saturation/value, and converts percent to the CLI's 0–1000 brightness range. It errors when current HSV is unavailable. |
| `lepro_set_color` | Resolves a supported color name to fixed HSV values and uses the CLI's `color --hue --sat --val --brightness` arguments. Optional brightness is 0–100 percent. |
| `lepro_set_effect` | Uses the CLI `mode play diy` command with the allowlisted effect names below. |
| `lepro_reconnect` | Runs one bounded status probe. The CLI opens a temporary BLE session per command; it does not maintain a persistent connection. |

Supported named colors: red, orange, yellow, green, teal, cyan, blue, purple, lavender, pink, and white. `dark`, `light`, `soft`, `pale`, `saturated`, `less saturated`, and `muted` modifiers are applied deterministically. Warm/cool white temperature is unsupported because this CLI command set does not expose a validated CCT operation.

Effects are restricted to the CLI's `DIY_EFFECTS` choices: `Steady`, `Breathe`, `Gradient`, `Leftward`, `Rightward`, `Circle`, `Flash`, `CenterOut`, and `CenterIn`. The CLI's TB1 preset files are not offered because the vendored source says their LED topology must not be replayed on ZB1.

All device operations use subprocess argument arrays with `shell=False`. The model can select only predefined operations; it cannot supply shell text, executable paths, arbitrary flags, MAC addresses, or credential operations. Device IDs resolve only against saved CYN-X configuration. Bonding is a setup operation, never an AI tool.

## Error behavior

Errors are structured with categories such as `device_not_found`, `device_selection_required`, `unsupported_device`, `device_not_bonded`, `device_disconnected`, `bluetooth_unavailable`, `unsupported_color`, `unsupported_effect`, `unsupported_operation`, `timeout`, and `malformed_cli_output`. Tool output reports failure when the CLI exits unsuccessfully; it does not claim success based on a requested action alone.

## Example requests

- “Turn my bedroom lights on.”
- “Set the office light to dark red.”
- “Dim the bedroom lights to 20 percent.”
- “Are my lights connected?”
- “Make the bedroom light breathe in soft pink.”

If more than one light is configured, specify a device name or ID. A status tool call is needed to verify actual connectivity.
