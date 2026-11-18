"""Deterministic color names and modifiers for Lepro's HSV CLI."""

from __future__ import annotations

import re


_COLORS = {
    "red": (0, 1000, 1000),
    "orange": (30, 1000, 1000),
    "yellow": (60, 1000, 1000),
    "green": (120, 1000, 1000),
    "teal": (174, 1000, 700),
    "cyan": (180, 1000, 1000),
    "blue": (240, 1000, 1000),
    "purple": (275, 1000, 800),
    "lavender": (270, 450, 1000),
    "pink": (330, 650, 1000),
    "white": (0, 0, 1000),
}


class UnsupportedColor(ValueError):
    pass


def resolve_color(value: str) -> dict[str, int]:
    """Convert a supported color phrase to validated Lepro HSV values."""
    if not isinstance(value, str):
        raise UnsupportedColor("Color must be a supported color name.")

    phrase = re.sub(r"[^a-z ]", " ", value.casefold())
    phrase = " ".join(phrase.split())
    # Warm/cool white needs a dedicated color-temperature command, which this
    # CLI does not provide. Do not silently approximate it as RGB white.
    if phrase in {"warm white", "cool white", "warm", "cool"}:
        raise UnsupportedColor(
            "This Lepro CLI cannot set white color temperature; warm/cool white is unsupported."
        )

    words = phrase.split()
    base = next((word for word in reversed(words) if word in _COLORS), None)
    if base is None:
        raise UnsupportedColor(f"Unsupported color: {value.strip() or '(empty)'}")

    hue, saturation, val = _COLORS[base]
    modifiers = set(words[: words.index(base)])
    allowed_modifiers = {
        "dark", "darker", "light", "lighter", "soft", "softer", "pale",
        "saturated", "saturate", "less", "more", "muted", "hot", "bright", "brighter",
    }
    unknown = modifiers - allowed_modifiers
    if unknown:
        raise UnsupportedColor(f"Unsupported color modifier: {' '.join(sorted(unknown))}")
    if ("more" in modifiers or "less" in modifiers) and not ("saturated" in modifiers or "saturate" in modifiers):
        raise UnsupportedColor("Use 'more saturated' or 'less saturated' as the saturation modifier.")
    if "dark" in modifiers or "darker" in modifiers:
        val = 350
    if "light" in modifiers or "lighter" in modifiers:
        val = 1000
        saturation = min(saturation, 600)
    if "soft" in modifiers or "softer" in modifiers or "pale" in modifiers:
        saturation = min(saturation, 400)
        val = max(val, 850)
    if "hot" in modifiers:
        saturation = 1000
        val = 1000
    if "bright" in modifiers or "brighter" in modifiers:
        val = 1000
    if "less" in modifiers and "saturated" in modifiers:
        saturation = min(saturation, 350)
    elif "saturated" in modifiers or "saturate" in modifiers:
        saturation = 1000
    if "desaturated" in modifiers or "muted" in modifiers:
        saturation = min(saturation, 350)

    return {"hue": hue, "saturation": saturation, "value": val}


def brightness_to_cli(percent: int) -> int:
    if type(percent) is not int or not 0 <= percent <= 100:
        raise ValueError("Brightness must be an integer from 0 to 100 percent.")
    return percent * 10
